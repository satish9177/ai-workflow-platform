import asyncio
import inspect
import json
import re
from datetime import datetime, timezone
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.config import settings
from app.engine.steps.approval import ApprovalRequiredException, run_approval_step
from app.engine.steps.condition import run_condition_step
from app.engine.steps.llm import run_llm_step
from app.engine.steps.tool import run_tool_step
from app.llm.provider_errors import ProviderExecutionError, normalize_provider_error
from app.models.branch_execution import BranchExecution
from app.models.run import Run
from app.models.step_execution import StepExecution
from app.models.step_result import StepResult
from app.models.workflow import Workflow
from app.tools.registry import ToolRegistry
from app.utils.preview import sanitize_preview_payload
from app.utils.template_renderer import render_template_object


logger = structlog.get_logger(__name__)
APPROVAL_AUTO_APPROVED_STATUS = "auto_approved"
APPROVAL_AUTO_REJECTED_STATUS = "auto_rejected"
COMPLETED_STEP_STATUSES = {"completed", APPROVAL_AUTO_APPROVED_STATUS}
FAILED_STEP_STATUSES = {"failed", APPROVAL_AUTO_REJECTED_STATUS}
TERMINAL_BRANCH_STATUSES = COMPLETED_STEP_STATUSES | FAILED_STEP_STATUSES | {"cancelled"}
ACTIVE_FOREACH_STATUSES = {"running"}
RECOVERABLE_FOREACH_STATUSES = {"queued"}
DEFAULT_FOREACH_CONCURRENCY_LIMIT = 10
APPROVAL_REJECTED_ERROR = "Rejected by approver"


async def _get_existing_step(db: AsyncSession, run_id: str, step_id: str) -> StepResult | None:
    result = await db.execute(
        select(StepResult).where(StepResult.run_id == run_id, StepResult.step_id == step_id)
    )
    return result.scalar_one_or_none()


async def _upsert_step(
    db: AsyncSession,
    run_id: str,
    step_id: str,
    step_type: str,
    status: str,
    input: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
    error: str | None = None,
    duration_ms: int | None = None,
) -> StepResult:
    step_result = await _get_existing_step(db, run_id, step_id)
    if step_result is None:
        step_result = StepResult(
            run_id=run_id,
            step_id=step_id,
            step_type=step_type,
            status=status,
            input=input,
            output=output,
            error=error,
            duration_ms=duration_ms,
        )
        db.add(step_result)
    else:
        step_result.status = status
        step_result.input = input
        step_result.output = output
        step_result.error = error
        step_result.duration_ms = duration_ms

    await db.flush()
    return step_result


async def _get_existing_step_execution(
    db: AsyncSession,
    run_id: str,
    step_key: str,
) -> StepExecution | None:
    result = await db.execute(
        select(StepExecution).where(
            StepExecution.run_id == run_id,
            StepExecution.step_key == step_key,
        )
    )
    return result.scalar_one_or_none()


async def _get_existing_foreach_step_execution(
    db: AsyncSession,
    run_id: str,
    step_key: str,
    foreach_index: int,
    branch_execution_id: str | None = None,
) -> StepExecution | None:
    statement = select(StepExecution).where(
        StepExecution.run_id == run_id,
        StepExecution.step_key == step_key,
        StepExecution.foreach_index == foreach_index,
    )
    if branch_execution_id is not None:
        statement = statement.where(StepExecution.branch_execution_id == branch_execution_id)
    result = await db.execute(statement.order_by(StepExecution.created_at.desc(), StepExecution.id.desc()).limit(1))
    return result.scalars().first()


async def _get_branch_execution(db: AsyncSession, run_id: str, step_key: str) -> BranchExecution | None:
    result = await db.execute(
        select(BranchExecution).where(
            BranchExecution.run_id == run_id,
            BranchExecution.step_key == step_key,
        )
    )
    return result.scalar_one_or_none()


def _step_label(step: dict[str, Any], step_id: str) -> str:
    return str(step.get("label") or step.get("name") or step_id)


def _duration_ms(started_at: datetime | None, completed_at: datetime) -> int | None:
    if started_at is None:
        return None
    return max(0, int((completed_at - started_at).total_seconds() * 1000))


def _max_attempts_for_step(step: dict[str, Any], step_type: str) -> int:
    if step_type not in {"tool", "llm"}:
        return 1
    max_attempts, _ = _get_retry_config(step)
    return max_attempts


async def _start_step_execution(
    db: AsyncSession,
    run_id: str,
    step_index: int,
    step: dict[str, Any],
    step_id: str,
    step_type: str,
    input_preview: dict[str, Any] | None = None,
    branch_execution_id: str | None = None,
    branch_key: str | None = None,
    foreach_index: int | None = None,
    foreach_item: Any | None = None,
) -> StepExecution:
    now = datetime.now(timezone.utc)
    if foreach_index is not None:
        step_execution = await _get_existing_foreach_step_execution(
            db,
            run_id,
            step_id,
            foreach_index,
            branch_execution_id=branch_execution_id,
        )
    else:
        step_execution = await _get_existing_step_execution(db, run_id, step_id)
    if step_execution is None:
        step_execution = StepExecution(
            run_id=run_id,
            step_index=step_index,
            step_key=step_id,
            step_type=step_type,
            step_label=_step_label(step, step_id),
            branch_execution_id=branch_execution_id,
            branch_key=branch_key,
            foreach_index=foreach_index,
            foreach_item=foreach_item,
            status="running",
            attempt_number=1,
            max_attempts=_max_attempts_for_step(step, step_type),
            started_at=now,
            provider=step.get("provider"),
            model=step.get("model"),
            tool_name=step.get("tool") if step_type == "tool" else None,
            input_preview=input_preview,
        )
        if foreach_index is not None:
            try:
                async with db.begin_nested():
                    db.add(step_execution)
                    await db.flush()
            except IntegrityError:
                existing = await _get_existing_foreach_step_execution(
                    db,
                    run_id,
                    step_id,
                    foreach_index,
                )
                if existing is None:
                    raise
                return existing
            return step_execution
        db.add(step_execution)
    else:
        step_execution.step_index = step_index
        step_execution.step_type = step_type
        step_execution.step_label = _step_label(step, step_id)
        step_execution.branch_execution_id = branch_execution_id
        step_execution.branch_key = branch_key
        step_execution.foreach_index = foreach_index
        step_execution.foreach_item = foreach_item
        step_execution.status = "running"
        step_execution.attempt_number = 1
        step_execution.max_attempts = _max_attempts_for_step(step, step_type)
        step_execution.started_at = step_execution.started_at or now
        step_execution.completed_at = None
        step_execution.duration_ms = None
        step_execution.error_details = None
        step_execution.provider = step.get("provider")
        step_execution.model = step.get("model")
        step_execution.tool_name = step.get("tool") if step_type == "tool" else None
        step_execution.input_preview = input_preview
        step_execution.output_preview = None

    await db.flush()
    return step_execution


async def _finish_step_execution(
    db: AsyncSession,
    step_execution: StepExecution,
    status: str,
    attempt_number: int = 1,
    error: Exception | str | None = None,
    output_preview: dict[str, Any] | None = None,
) -> StepExecution:
    completed_at = datetime.now(timezone.utc)
    step_execution.status = status
    step_execution.attempt_number = attempt_number
    step_execution.completed_at = completed_at
    step_execution.duration_ms = _duration_ms(step_execution.started_at, completed_at)
    step_execution.error_details = _error_details(error)
    if output_preview is not None:
        step_execution.output_preview = output_preview
    await db.flush()
    return step_execution


def _error_details(error: Exception | str | dict[str, Any] | None) -> dict[str, Any] | None:
    if error is None:
        return None
    if isinstance(error, dict):
        return error
    if isinstance(error, ProviderExecutionError):
        return error.to_error_details()
    return {"message": str(error)}


def _step_error_message(error: Exception) -> str:
    if isinstance(error, ProviderExecutionError):
        return error.message
    return str(error)


def _build_input_preview(step: dict[str, Any], context: dict[str, Any], step_type: str) -> dict[str, Any] | None:
    try:
        if step_type == "llm":
            system_template = step.get("system") or step.get("system_prompt") or ""
            preview = {
                "prompt": render_template_object(step.get("prompt", ""), context),
                "provider": step.get("provider") or settings.default_llm_provider,
                "model": step.get("model") or settings.default_llm_model,
            }
            if system_template:
                preview["system"] = render_template_object(system_template, context)
            return sanitize_preview_payload(preview)

        if step_type == "tool" or ToolRegistry.get(step_type) is not None:
            tool_name = step.get("tool_name") or step.get("tool") or step.get("type")
            raw_params = step.get("params") or step.get("config") or {}
            preview = {
                "tool": tool_name,
                "action": step.get("action", "execute"),
                "params": render_template_object(raw_params, context),
            }
            return sanitize_preview_payload(preview)

        if step_type == "approval":
            rendered_step = render_template_object(step, context)
            return sanitize_preview_payload(
                {
                    "message": rendered_step.get("message"),
                    "subject": rendered_step.get("subject"),
                    "body": rendered_step.get("body"),
                    "approver_email": rendered_step.get("approver_email")
                    or rendered_step.get("approver_email_template"),
                }
            )

        if step_type == "condition":
            return sanitize_preview_payload(render_template_object(step, context))
    except Exception as exc:
        return {"preview_error": str(exc)}

    return None


def _build_output_preview(step_type: str, output: dict[str, Any]) -> dict[str, Any]:
    if step_type == "llm":
        return sanitize_preview_payload(
            {
                "response": output.get("response"),
                "provider": output.get("provider"),
                "model": output.get("model"),
                "usage": output.get("usage"),
            }
        )
    if step_type == "tool":
        return sanitize_preview_payload({"response": output})
    if step_type == "condition":
        return sanitize_preview_payload(output)
    return sanitize_preview_payload(output)


def _build_parallel_group_output_preview(output: dict[str, Any]) -> dict[str, Any]:
    return sanitize_preview_payload(output)


def _step_type(step: dict[str, Any]) -> str:
    return step.get("type") or step.get("step_type") or ""


def _validate_step_for_execution(step: dict[str, Any]) -> tuple[str, str]:
    step_id = step.get("id")
    if not step_id:
        raise ValueError("Invalid workflow step: missing id")

    step_type = _step_type(step)
    if not step_type:
        raise ValueError("Invalid workflow step: missing type")

    return step_id, step_type


def _get_retry_config(step: dict[str, Any]) -> tuple[int, float]:
    retry = step.get("retry", {})
    if not isinstance(retry, dict):
        retry = {}

    try:
        max_attempts = int(retry.get("max_attempts", 1))
    except (TypeError, ValueError):
        max_attempts = 1
    if max_attempts < 1:
        max_attempts = 1

    try:
        backoff_seconds = float(retry.get("backoff_seconds", 0.0))
    except (TypeError, ValueError):
        backoff_seconds = 0.0
    if backoff_seconds < 0:
        backoff_seconds = 0.0

    return max_attempts, backoff_seconds


async def _dispatch_step(
    step: dict[str, Any],
    context: dict[str, Any],
    run_id: str,
    db: AsyncSession,
) -> Any:
    step_type = _step_type(step)
    if step_type == "condition":
        return await run_condition_step(step, context)
    if step_type == "llm":
        return await run_llm_step(step, context, run_id, db)
    if step_type == "approval":
        return await run_approval_step(step, context, run_id, db)
    if step_type == "parallel_group":
        raise ValueError("Nested parallel_group execution is not supported yet")
    if step_type == "foreach":
        raise ValueError("Nested foreach execution is not supported")
    if step_type == "tool" or ToolRegistry.get(step_type) is not None:
        return await run_tool_step(step, context, db, run_id=run_id)
    raise ValueError(f"Unsupported step type: {step_type}")


async def _execute_step_with_retry(
    step: dict[str, Any],
    context: dict[str, Any],
    run_id: str,
    db: AsyncSession,
) -> tuple[Any, int]:
    step_type = _step_type(step)
    if step_type not in {"tool", "llm"}:
        return await _dispatch_step(step, context, run_id, db), 1
    if "retry" not in step:
        return await _dispatch_step(step, context, run_id, db), 1

    max_attempts, backoff_seconds = _get_retry_config(step)
    for attempt in range(1, max_attempts + 1):
        try:
            return await _dispatch_step(step, context, run_id, db), attempt
        except Exception as exc:
            provider_error = (
                normalize_provider_error(
                    exc,
                    provider=step.get("provider") or "unknown",
                    model=step.get("model"),
                )
                if step_type == "llm"
                else None
            )
            if provider_error is not None and not provider_error.retryable:
                provider_error.attempt_number = attempt
                raise provider_error from exc
            if attempt >= max_attempts:
                if provider_error is not None:
                    provider_error.attempt_number = attempt
                    raise provider_error from exc
                raise Exception(
                    f"Failed after {attempt}/{max_attempts} attempts. Last error: {exc}"
                ) from exc
            await asyncio.sleep(backoff_seconds)

    raise RuntimeError("Retry execution ended unexpectedly")


async def _enqueue_parallel_branch(
    branch_execution_id: str,
    run_id: str,
    group_step_key: str,
    branch_index: int,
) -> None:
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job("execute_parallel_branch_job", branch_execution_id, run_id, group_step_key, branch_index)
    finally:
        close = getattr(pool, "close", None)
        if close is not None:
            result = close()
            if inspect.isawaitable(result):
                await result


async def _enqueue_foreach_iteration(
    branch_execution_id: str,
    run_id: str,
    foreach_step_key: str,
    item_index: int,
) -> None:
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job("execute_foreach_iteration_job", branch_execution_id, run_id, foreach_step_key, item_index)
    finally:
        close = getattr(pool, "close", None)
        if close is not None:
            result = close()
            if inspect.isawaitable(result):
                await result


class ParallelGroupPending(Exception):
    pass


class ParallelGroupExecutor:
    async def start(
        self,
        *,
        run: Run,
        workflow: Workflow,
        step: dict[str, Any],
        step_index: int,
        context: dict[str, Any],
        db: AsyncSession,
    ) -> BranchExecution:
        group_key = str(step["id"])
        existing = await _get_branch_execution(db, run.id, group_key)
        if existing is not None:
            logger.info(
                "parallel_group.already_started",
                run_id=run.id,
                workflow_id=workflow.id,
                step_key=group_key,
                branch_execution_id=existing.id,
                status=existing.status,
            )
            return existing

        child_steps = step.get("steps") or []
        branch_execution = BranchExecution(
            run_id=run.id,
            step_key=group_key,
            branch_type="parallel_group",
            status="running",
            total_branches=len(child_steps),
            completed_branches=0,
            failed_branches=0,
            cancelled_branches=0,
            merge_triggered=False,
            fail_fast=bool(step.get("fail_fast", False)),
            fail_fast_triggered=False,
            merged_context=None,
            started_at=datetime.now(timezone.utc),
        )
        db.add(branch_execution)
        run.context = context
        run.status = "running"
        run.current_step = group_key
        await db.commit()
        await db.refresh(branch_execution)

        logger.info(
            "parallel_group.started",
            run_id=run.id,
            workflow_id=workflow.id,
            step_key=group_key,
            branch_execution_id=branch_execution.id,
            total_branches=branch_execution.total_branches,
        )
        for branch_index, _child_step in enumerate(child_steps):
            await _enqueue_parallel_branch(branch_execution.id, run.id, group_key, branch_index)

        return branch_execution


def _lookup_context_path(context: dict[str, Any], path: str) -> Any:
    current: Any = context
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            return None
    return current


def _resolve_foreach_items_expression(items: Any, context: dict[str, Any]) -> list[Any]:
    if isinstance(items, list):
        rendered = render_template_object(items, context)
        if not isinstance(rendered, list):
            raise ValueError("foreach items must resolve to a list")
        return rendered

    if isinstance(items, str):
        expression = items.strip()
        exact_variable = re.fullmatch(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)\s*\}\}", expression)
        if exact_variable:
            resolved = _lookup_context_path(context, exact_variable.group(1))
            if not isinstance(resolved, list):
                raise ValueError("foreach items must resolve to a list")
            return resolved

        rendered = render_template_object(items, context)
        try:
            decoded = json.loads(rendered)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("foreach items must resolve to a list") from exc
        if not isinstance(decoded, list):
            raise ValueError("foreach items must resolve to a list")
        return decoded

    raise ValueError("foreach items must resolve to a list")


def _foreach_concurrency_limit(step: dict[str, Any], total_items: int) -> int:
    try:
        configured = int(step.get("concurrency_limit") or DEFAULT_FOREACH_CONCURRENCY_LIMIT)
    except (TypeError, ValueError):
        configured = DEFAULT_FOREACH_CONCURRENCY_LIMIT
    return max(1, min(configured, max(total_items, 1)))


async def _reserve_foreach_iteration(
    db: AsyncSession,
    *,
    run_id: str,
    branch_execution_id: str,
    foreach_step: dict[str, Any],
    foreach_step_index: int,
    item_index: int,
    item: Any,
) -> StepExecution:
    child_step = foreach_step.get("step") or {}
    branch_key, iteration_step = _foreach_iteration_step(str(foreach_step["id"]), child_step, item_index)
    iteration_step_key = str(iteration_step["id"])
    existing = await _get_existing_foreach_step_execution(
        db,
        run_id,
        iteration_step_key,
        item_index,
        branch_execution_id=branch_execution_id,
    )
    if existing is not None:
        if existing.status not in TERMINAL_BRANCH_STATUSES and existing.status not in ACTIVE_FOREACH_STATUSES:
            existing.status = "pending"
            existing.branch_execution_id = branch_execution_id
            existing.step_key = iteration_step_key
            existing.branch_key = branch_key
            existing.foreach_index = item_index
            existing.foreach_item = item
            existing.completed_at = None
            existing.duration_ms = None
            existing.error_details = None
        await db.flush()
        return existing

    step_execution = StepExecution(
        run_id=run_id,
        branch_execution_id=branch_execution_id,
        step_index=(foreach_step_index + 1) * 1000 + item_index,
        step_key=iteration_step_key,
        step_type=str(iteration_step.get("type") or ""),
        step_label=_step_label(iteration_step, str(iteration_step["id"])),
        status="pending",
        attempt_number=1,
        max_attempts=_max_attempts_for_step(iteration_step, str(iteration_step.get("type") or "")),
        branch_key=branch_key,
        foreach_index=item_index,
        foreach_item=item,
    )
    try:
        async with db.begin_nested():
            db.add(step_execution)
            await db.flush()
    except IntegrityError:
        existing = await _get_existing_foreach_step_execution(
            db,
            run_id,
            iteration_step_key,
            item_index,
        )
        if existing is None:
            raise
        return existing
    return step_execution


async def _queue_foreach_iteration(
    db: AsyncSession,
    *,
    run_id: str,
    branch_execution: BranchExecution,
    foreach_step: dict[str, Any],
    foreach_step_index: int,
    item_index: int,
    item: Any,
) -> bool:
    child_step = foreach_step.get("step") or {}
    _branch_key, iteration_step = _foreach_iteration_step(str(foreach_step["id"]), child_step, item_index)
    step_id, step_type = _validate_step_for_execution(iteration_step)
    step_execution = await _reserve_foreach_iteration(
        db,
        run_id=run_id,
        branch_execution_id=branch_execution.id,
        foreach_step=foreach_step,
        foreach_step_index=foreach_step_index,
        item_index=item_index,
        item=item,
    )
    if step_execution.status not in TERMINAL_BRANCH_STATUSES:
        step_execution.status = "queued"
        step_execution.completed_at = None
        step_execution.duration_ms = None
        step_execution.error_details = None
    await db.commit()

    try:
        await _enqueue_foreach_iteration(branch_execution.id, run_id, branch_execution.step_key, item_index)
    except Exception as exc:
        failed_execution = (
            await _get_existing_foreach_step_execution(
                db,
                run_id,
                step_id,
                item_index,
                branch_execution_id=branch_execution.id,
            )
            or step_execution
        )
        await _finish_step_execution(db, failed_execution, "failed", error=exc)
        await _upsert_step(
            db,
            run_id,
            step_id,
            step_type,
            "failed",
            input=iteration_step,
            error=f"Failed to enqueue foreach iteration: {exc}",
        )
        await _sync_foreach_branch_counters(db, branch_execution.id)
        await db.commit()
        logger.exception(
            "foreach.iteration_enqueue_failed",
            foreach_id=branch_execution.id,
            step_key=branch_execution.step_key,
            iteration_step_key=step_id,
            item_index=item_index,
            next_iteration_dispatched=False,
            error=str(exc),
        )
        return False
    return True


class ForeachExecutor:
    async def start(
        self,
        *,
        run: Run,
        workflow: Workflow,
        step: dict[str, Any],
        step_index: int,
        context: dict[str, Any],
        db: AsyncSession,
    ) -> BranchExecution:
        foreach_key = str(step["id"])
        existing = await _get_branch_execution(db, run.id, foreach_key)
        if existing is not None:
            logger.info(
                "foreach.already_started",
                run_id=run.id,
                workflow_id=workflow.id,
                step_key=foreach_key,
                branch_execution_id=existing.id,
                status=existing.status,
            )
            return existing

        items = _resolve_foreach_items_expression(step.get("items"), context)
        branch_execution = BranchExecution(
            run_id=run.id,
            step_key=foreach_key,
            branch_type="foreach",
            status="running",
            total_branches=len(items),
            completed_branches=0,
            failed_branches=0,
            cancelled_branches=0,
            merge_triggered=False,
            fail_fast=bool(step.get("fail_fast", False)),
            fail_fast_triggered=False,
            foreach_items=items,
            merged_context=None,
            started_at=datetime.now(timezone.utc),
        )
        db.add(branch_execution)
        run.context = context
        run.status = "running"
        run.current_step = foreach_key
        await db.commit()
        await db.refresh(branch_execution)

        if not items:
            await _merge_foreach_if_ready(db, branch_execution.id, run.id, foreach_key)
            return branch_execution

        limit = _foreach_concurrency_limit(step, len(items))
        logger.info(
            "foreach.started",
            run_id=run.id,
            workflow_id=workflow.id,
            step_key=foreach_key,
            branch_execution_id=branch_execution.id,
            total_items=len(items),
            concurrency_limit=limit,
        )
        dispatch_results = []
        for item_index in range(limit):
            dispatched = await _queue_foreach_iteration(
                db,
                run_id=run.id,
                branch_execution=branch_execution,
                foreach_step=step,
                foreach_step_index=step_index,
                item_index=item_index,
                item=items[item_index],
            )
            dispatch_results.append(dispatched)

        if not all(dispatch_results):
            await _merge_foreach_if_ready(db, branch_execution.id, run.id, foreach_key)

        return branch_execution


def _find_parallel_group(workflow: Workflow, group_step_key: str) -> tuple[int, dict[str, Any]]:
    for index, step in enumerate(workflow.steps):
        if step.get("id") == group_step_key and step.get("type") == "parallel_group":
            return index, step
    raise ValueError(f"Parallel group not found: {group_step_key}")


def _branch_step(group_step_key: str, step: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    child_id = step.get("id")
    if not child_id:
        raise ValueError("Invalid parallel branch step: missing id")
    branch_key = str(child_id)
    dotted_key = f"{group_step_key}.{branch_key}"
    return branch_key, {**step, "id": dotted_key}


async def _mark_branch_terminal(
    db: AsyncSession,
    branch_execution_id: str,
    status: str,
) -> BranchExecution | None:
    values: dict[str, Any] = {}
    if status == "completed":
        values["completed_branches"] = BranchExecution.completed_branches + 1
    elif status == "failed":
        values["failed_branches"] = BranchExecution.failed_branches + 1
    elif status == "cancelled":
        values["cancelled_branches"] = BranchExecution.cancelled_branches + 1
    else:
        raise ValueError(f"Unsupported branch terminal status: {status}")

    result = await db.execute(
        update(BranchExecution)
        .where(BranchExecution.id == branch_execution_id, BranchExecution.merge_triggered.is_(False))
        .values(**values)
        .returning(BranchExecution)
    )
    return result.scalar_one_or_none()


def _all_branches_terminal(branch_execution: BranchExecution) -> bool:
    terminal_count = (
        branch_execution.completed_branches
        + branch_execution.failed_branches
        + branch_execution.cancelled_branches
    )
    return terminal_count >= branch_execution.total_branches


async def _claim_merge(db: AsyncSession, branch_execution_id: str) -> BranchExecution | None:
    result = await db.execute(
        update(BranchExecution)
        .where(BranchExecution.id == branch_execution_id, BranchExecution.merge_triggered.is_(False))
        .values(merge_triggered=True)
        .returning(BranchExecution)
    )
    return result.scalar_one_or_none()


async def _synthesize_parallel_group_output(
    db: AsyncSession,
    run_id: str,
    group_step: dict[str, Any],
) -> dict[str, Any]:
    branches: dict[str, Any] = {}
    for child_step in group_step.get("steps") or []:
        branch_key = str(child_step["id"])
        dotted_key = f"{group_step['id']}.{branch_key}"
        step_result = await _get_existing_step(db, run_id, dotted_key)
        if step_result is None:
            branches[branch_key] = {"status": "missing"}
        elif step_result.status == "completed":
            branches[branch_key] = step_result.output
        else:
            branches[branch_key] = {"status": step_result.status, "error": step_result.error}
    return {"branches": branches}


async def _merge_parallel_group_if_ready(
    db: AsyncSession,
    branch_execution_id: str,
    run_id: str,
    group_step_key: str,
) -> None:
    branch_execution = await db.get(BranchExecution, branch_execution_id)
    if branch_execution is not None:
        await db.refresh(branch_execution)
    if branch_execution is None or not _all_branches_terminal(branch_execution):
        await db.commit()
        return

    claimed = await _claim_merge(db, branch_execution_id)
    if claimed is None:
        await db.commit()
        return

    run = await db.get(Run, run_id)
    if run is None:
        await db.commit()
        return
    workflow = await db.get(Workflow, run.workflow_id)
    if workflow is None:
        run.status = "failed"
        run.error = "Workflow not found"
        await db.commit()
        return

    group_step_index, group_step = _find_parallel_group(workflow, group_step_key)
    merged_output = await _synthesize_parallel_group_output(db, run_id, group_step)
    now = datetime.now(timezone.utc)
    branch_execution = await db.get(BranchExecution, branch_execution_id)
    if branch_execution is None:
        await db.commit()
        return
    branch_execution.completed_at = now
    branch_execution.merged_context = merged_output

    group_step_execution = await _get_existing_step_execution(db, run_id, group_step_key)
    if branch_execution.failed_branches or branch_execution.cancelled_branches:
        branch_execution.status = "failed"
        await _upsert_step(
            db,
            run_id,
            group_step_key,
            "parallel_group",
            "failed",
            input=group_step,
            output=merged_output,
            error="One or more parallel branches failed",
        )
        if group_step_execution is not None:
            await _finish_step_execution(
                db,
                group_step_execution,
                "failed",
                error="One or more parallel branches failed",
                output_preview=_build_parallel_group_output_preview(merged_output),
            )
        run.status = "failed"
        run.error = "One or more parallel branches failed"
        run.context = {**(run.context or {}), group_step_key: merged_output}
        await db.commit()
        logger.warning(
            "parallel_group.failed",
            run_id=run_id,
            workflow_id=workflow.id,
            step_key=group_step_key,
            branch_execution_id=branch_execution_id,
        )
        return

    branch_execution.status = "completed"
    context = dict(run.context or {})
    context[group_step_key] = merged_output
    if group_step.get("output_as"):
        context[str(group_step["output_as"])] = merged_output
    run.context = context
    await _upsert_step(
        db,
        run_id,
        group_step_key,
        "parallel_group",
        "completed",
        input=group_step,
        output=merged_output,
    )
    if group_step_execution is not None:
        await _finish_step_execution(
            db,
            group_step_execution,
            "completed",
            output_preview=_build_parallel_group_output_preview(merged_output),
        )
    await db.commit()
    logger.info(
        "parallel_group.completed",
        run_id=run_id,
        workflow_id=workflow.id,
        step_key=group_step_key,
        branch_execution_id=branch_execution_id,
    )
    await execute_run(run_id, db)


async def _pause_branch_approval(
    db: AsyncSession,
    *,
    run: Run,
    branch_execution: BranchExecution,
    step_execution: StepExecution,
    step_id: str,
    step_type: str,
    input_step: dict[str, Any],
) -> None:
    await _finish_step_execution(
        db,
        step_execution,
        "awaiting_approval",
        attempt_number=1,
        output_preview={"approval_required": True},
    )
    await _upsert_step(db, run.id, step_id, step_type, "paused", input=input_step)
    branch_execution.status = "partially_paused"
    run.status = "partially_paused"
    run.current_step = branch_execution.step_key
    await db.commit()


async def _finish_branch_approval(
    db: AsyncSession,
    *,
    run_id: str,
    step_id: str,
    approved: bool,
    timed_out: bool = False,
    timeout_action: str | None = None,
) -> tuple[StepExecution | None, BranchExecution | None]:
    step_execution = await _get_existing_step_execution(db, run_id, step_id)
    if step_execution is None or step_execution.branch_execution_id is None:
        return step_execution, None

    step_execution_status = (
        APPROVAL_AUTO_APPROVED_STATUS
        if timed_out and approved
        else APPROVAL_AUTO_REJECTED_STATUS
        if timed_out
        else "completed"
        if approved
        else "failed"
    )
    step_result_status = "completed" if approved else "failed"
    output = {"approved": approved}
    if timed_out:
        output.update(
            {
                "timed_out": True,
                "timeout_action": timeout_action or ("approve" if approved else "reject"),
            }
        )
    error_message = None if approved else ("Approval timed out" if timed_out else APPROVAL_REJECTED_ERROR)
    error_details = (
        {
            "type": "ApprovalTimedOut",
            "message": "Approval timed out",
            "timeout_action": timeout_action or "reject",
        }
        if timed_out and not approved
        else error_message
    )
    await _upsert_step(
        db,
        run_id,
        step_id,
        "approval",
        step_result_status,
        output=output if approved else None,
        error=error_message,
    )
    await _finish_step_execution(
        db,
        step_execution,
        step_execution_status,
        attempt_number=1,
        error=error_details,
        output_preview={
            **output,
            "status": (
                "auto_approved"
                if timed_out and approved
                else "auto_rejected"
                if timed_out
                else "approved"
                if approved
                else "rejected"
            ),
        },
    )
    branch_execution = await db.get(BranchExecution, step_execution.branch_execution_id)
    return step_execution, branch_execution


async def _resume_parallel_branch_approval(
    db: AsyncSession,
    *,
    run_id: str,
    step_id: str,
    approved: bool,
    timed_out: bool = False,
    timeout_action: str | None = None,
) -> bool:
    _step_execution, branch_execution = await _finish_branch_approval(
        db,
        run_id=run_id,
        step_id=step_id,
        approved=approved,
        timed_out=timed_out,
        timeout_action=timeout_action,
    )
    if branch_execution is None or branch_execution.branch_type != "parallel_group":
        return False

    branch_status = "completed" if approved else "failed"
    await _mark_branch_terminal(db, branch_execution.id, branch_status)
    run = await db.get(Run, run_id)
    if run is not None and approved:
        run.status = "running"
    await db.commit()
    await _merge_parallel_group_if_ready(db, branch_execution.id, run_id, branch_execution.step_key)
    return True


def _find_foreach_step(workflow: Workflow, foreach_step_key: str) -> tuple[int, dict[str, Any]]:
    for index, step in enumerate(workflow.steps):
        if step.get("id") == foreach_step_key and step.get("type") == "foreach":
            return index, step
    raise ValueError(f"Foreach step not found: {foreach_step_key}")


def _foreach_iteration_step(foreach_step_key: str, step: dict[str, Any], item_index: int) -> tuple[str, dict[str, Any]]:
    child_id = step.get("id")
    if not child_id:
        raise ValueError("Invalid foreach iteration step: missing id")
    branch_key = str(item_index)
    dotted_key = f"{foreach_step_key}.{item_index}.{child_id}"
    return branch_key, {**step, "id": dotted_key}


async def _foreach_started_indices(db: AsyncSession, branch_execution_id: str) -> set[int]:
    result = await db.execute(
        select(StepExecution.foreach_index).where(
            StepExecution.branch_execution_id == branch_execution_id,
            StepExecution.foreach_index.is_not(None),
            StepExecution.status.in_(
                TERMINAL_BRANCH_STATUSES
                | ACTIVE_FOREACH_STATUSES
                | RECOVERABLE_FOREACH_STATUSES
                | {"awaiting_approval"}
            ),
        )
    )
    return {int(index) for index in result.scalars().all() if index is not None}


async def _foreach_queued_indices(db: AsyncSession, branch_execution_id: str) -> list[int]:
    result = await db.execute(
        select(StepExecution.foreach_index)
        .where(
            StepExecution.branch_execution_id == branch_execution_id,
            StepExecution.foreach_index.is_not(None),
            StepExecution.status.in_(RECOVERABLE_FOREACH_STATUSES),
        )
        .order_by(StepExecution.foreach_index.asc())
    )
    return [int(index) for index in result.scalars().all() if index is not None]


async def _foreach_running_count(
    db: AsyncSession,
    branch_execution_id: str,
    include_recoverable: bool = False,
) -> int:
    active_statuses = set(ACTIVE_FOREACH_STATUSES)
    if include_recoverable:
        active_statuses |= RECOVERABLE_FOREACH_STATUSES
    result = await db.execute(
        select(StepExecution.status).where(
            StepExecution.branch_execution_id == branch_execution_id,
            StepExecution.foreach_index.is_not(None),
        )
    )
    return sum(1 for status in result.scalars().all() if status in active_statuses)


async def _foreach_awaiting_approval_count(db: AsyncSession, branch_execution_id: str) -> int:
    result = await db.execute(
        select(StepExecution.status).where(
            StepExecution.branch_execution_id == branch_execution_id,
            StepExecution.foreach_index.is_not(None),
            StepExecution.status == "awaiting_approval",
        )
    )
    return len(result.scalars().all())


async def _sync_foreach_branch_counters(db: AsyncSession, branch_execution_id: str) -> BranchExecution | None:
    """Rebuild foreach fan-in counters from persisted iteration state.

    Foreach iteration jobs are retried independently. If a worker completes the
    external side effect and persists StepResult but is retried before branch
    accounting runs, we need fan-in to be idempotent instead of increment-only.
    """
    await db.flush()
    branch_execution = await db.get(BranchExecution, branch_execution_id)
    if branch_execution is None or branch_execution.merge_triggered:
        return branch_execution

    result = await db.execute(
        select(StepExecution.foreach_index, StepExecution.status).where(
            StepExecution.branch_execution_id == branch_execution_id,
            StepExecution.foreach_index.is_not(None),
        )
    )
    rows = result.all()
    statuses = [status for _index, status in rows]
    branch_execution.completed_branches = sum(1 for status in statuses if status in COMPLETED_STEP_STATUSES)
    branch_execution.failed_branches = sum(1 for status in statuses if status in FAILED_STEP_STATUSES)
    branch_execution.cancelled_branches = max(
        branch_execution.cancelled_branches,
        sum(1 for status in statuses if status == "cancelled"),
    )
    await db.flush()
    currently_running_count = sum(1 for status in statuses if status in ACTIVE_FOREACH_STATUSES)
    merge_ready = _all_branches_terminal(branch_execution)
    logger.debug(
        "foreach.terminal_counters_synced",
        foreach_id=branch_execution.id,
        step_key=branch_execution.step_key,
        total_items=branch_execution.total_branches,
        completed_count=branch_execution.completed_branches,
        failed_count=branch_execution.failed_branches,
        cancelled_count=branch_execution.cancelled_branches,
        currently_running_count=currently_running_count,
        merge_condition_true=merge_ready,
    )
    return branch_execution


async def _reconcile_terminal_foreach_iteration(
    db: AsyncSession,
    *,
    run_id: str,
    branch_execution_id: str,
    child_step: dict[str, Any],
    step_id: str,
    step_type: str,
    step_index: int,
    branch_key: str,
    foreach_index: int,
    foreach_item: Any,
    input_preview: dict[str, Any] | None,
    step_result: StepResult,
) -> BranchExecution | None:
    status = step_result.status
    if status not in TERMINAL_BRANCH_STATUSES:
        return await _sync_foreach_branch_counters(db, branch_execution_id)

    step_execution = await _get_existing_foreach_step_execution(
        db,
        run_id,
        step_id,
        foreach_index,
        branch_execution_id=branch_execution_id,
    )
    if step_execution is None:
        step_execution = await _start_step_execution(
            db,
            run_id,
            step_index,
            child_step,
            step_id,
            step_type,
            input_preview=input_preview,
            branch_execution_id=branch_execution_id,
            branch_key=branch_key,
            foreach_index=foreach_index,
            foreach_item=foreach_item,
        )

    if step_execution.status not in TERMINAL_BRANCH_STATUSES:
        output_preview = None
        if status == "completed" and step_result.output is not None:
            output_preview = _build_output_preview(step_type, step_result.output)
        await _finish_step_execution(
            db,
            step_execution,
            status,
            error=step_result.error,
            output_preview=output_preview,
        )

    updated = await _sync_foreach_branch_counters(db, branch_execution_id)
    if updated is not None:
        currently_running_count = await _foreach_running_count(db, branch_execution_id)
        logger.debug(
            "foreach.iteration_terminal_reconciled",
            foreach_id=branch_execution_id,
            step_key=updated.step_key,
            iteration_step_key=step_id,
            foreach_index=foreach_index,
            terminal_status=status,
            total_items=updated.total_branches,
            completed_count=updated.completed_branches,
            failed_count=updated.failed_branches,
            cancelled_count=updated.cancelled_branches,
            currently_running_count=currently_running_count,
            merge_condition_true=_all_branches_terminal(updated),
        )
    return updated


async def _enqueue_next_foreach_iterations(
    db: AsyncSession,
    branch_execution: BranchExecution,
    run_id: str,
    foreach_step: dict[str, Any],
    foreach_step_index: int,
    redispatch_recoverable: bool = False,
) -> None:
    total_items = branch_execution.total_branches
    terminal_count = (
        branch_execution.completed_branches
        + branch_execution.failed_branches
        + branch_execution.cancelled_branches
    )
    started = await _foreach_started_indices(db, branch_execution.id)
    next_iteration_index = next((index for index in range(total_items) if index not in started), None)
    if branch_execution.fail_fast_triggered:
        logger.debug(
            "foreach.next_iteration_dispatch_skipped",
            foreach_id=branch_execution.id,
            step_key=branch_execution.step_key,
            total_items=total_items,
            completed_count=branch_execution.completed_branches,
            failed_count=branch_execution.failed_branches,
            cancelled_count=branch_execution.cancelled_branches,
            currently_running_count=max(0, len(started) - terminal_count),
            next_iteration_index=next_iteration_index,
            next_iteration_dispatched=False,
            reason="fail_fast_triggered",
        )
        await db.commit()
        return
    if total_items <= 0:
        logger.debug(
            "foreach.next_iteration_dispatch_skipped",
            foreach_id=branch_execution.id,
            step_key=branch_execution.step_key,
            total_items=total_items,
            completed_count=branch_execution.completed_branches,
            failed_count=branch_execution.failed_branches,
            cancelled_count=branch_execution.cancelled_branches,
            currently_running_count=0,
            next_iteration_index=None,
            next_iteration_dispatched=False,
            reason="empty_items",
        )
        await db.commit()
        return

    running_count = await _foreach_running_count(
        db,
        branch_execution.id,
        include_recoverable=not redispatch_recoverable,
    )
    limit = _foreach_concurrency_limit(foreach_step, total_items)
    available_slots = max(0, limit - running_count)
    if available_slots == 0:
        logger.debug(
            "foreach.next_iteration_dispatch_skipped",
            foreach_id=branch_execution.id,
            step_key=branch_execution.step_key,
            total_items=total_items,
            completed_count=branch_execution.completed_branches,
            failed_count=branch_execution.failed_branches,
            cancelled_count=branch_execution.cancelled_branches,
            currently_running_count=running_count,
            next_iteration_index=next_iteration_index,
            next_iteration_dispatched=False,
            concurrency_limit=limit,
            reason="concurrency_limit_reached",
        )
        await db.commit()
        return

    queued_indices = await _foreach_queued_indices(db, branch_execution.id) if redispatch_recoverable else []
    fresh_indices = [index for index in range(total_items) if index not in started]
    next_indices = (queued_indices + fresh_indices)[:available_slots]
    items = branch_execution.foreach_items or []
    dispatched_indices = []
    for item_index in next_indices:
        dispatched = await _queue_foreach_iteration(
            db,
            run_id=run_id,
            branch_execution=branch_execution,
            foreach_step=foreach_step,
            foreach_step_index=foreach_step_index,
            item_index=item_index,
            item=items[item_index],
        )
        if dispatched:
            dispatched_indices.append(item_index)
    updated_branch = await db.get(BranchExecution, branch_execution.id)
    if updated_branch is not None:
        branch_execution = updated_branch
    logger.debug(
        "foreach.next_iteration_dispatched",
        foreach_id=branch_execution.id,
        step_key=branch_execution.step_key,
        total_items=total_items,
        completed_count=branch_execution.completed_branches,
        failed_count=branch_execution.failed_branches,
        cancelled_count=branch_execution.cancelled_branches,
        currently_running_count=running_count,
        next_iteration_index=dispatched_indices[0] if dispatched_indices else next_iteration_index,
        dispatched_indices=dispatched_indices,
        next_iteration_dispatched=bool(dispatched_indices),
        concurrency_limit=limit,
    )
    if len(dispatched_indices) != len(next_indices):
        await _merge_foreach_if_ready(db, branch_execution.id, run_id, branch_execution.step_key)
        return
    await db.commit()


async def _cancel_remaining_foreach_iterations(db: AsyncSession, branch_execution_id: str) -> BranchExecution | None:
    result = await db.execute(
        update(BranchExecution)
        .where(BranchExecution.id == branch_execution_id, BranchExecution.merge_triggered.is_(False))
        .values(
            cancelled_branches=(
                BranchExecution.total_branches
                - BranchExecution.completed_branches
                - BranchExecution.failed_branches
            ),
            fail_fast_triggered=True,
        )
        .returning(BranchExecution)
    )
    return result.scalar_one_or_none()


async def _resume_foreach_iteration_approval(
    db: AsyncSession,
    *,
    run_id: str,
    step_id: str,
    approved: bool,
    timed_out: bool = False,
    timeout_action: str | None = None,
) -> bool:
    step_execution, branch_execution = await _finish_branch_approval(
        db,
        run_id=run_id,
        step_id=step_id,
        approved=approved,
        timed_out=timed_out,
        timeout_action=timeout_action,
    )
    if (
        step_execution is None
        or branch_execution is None
        or branch_execution.branch_type != "foreach"
        or step_execution.foreach_index is None
    ):
        return False

    updated = await _sync_foreach_branch_counters(db, branch_execution.id)
    if updated is None:
        await _merge_foreach_if_ready(db, branch_execution.id, run_id, branch_execution.step_key)
        return True

    run = await db.get(Run, run_id)
    workflow = await db.get(Workflow, run.workflow_id) if run is not None else None
    if run is not None and approved:
        run.status = "running"

    if not approved and updated.fail_fast:
        updated = await _cancel_remaining_foreach_iterations(db, branch_execution.id)
        if updated is not None:
            await _merge_foreach_if_ready(db, branch_execution.id, run_id, branch_execution.step_key)
        return True

    if _all_branches_terminal(updated):
        await _merge_foreach_if_ready(db, branch_execution.id, run_id, branch_execution.step_key)
        return True

    if workflow is not None:
        foreach_step_index, foreach_step = _find_foreach_step(workflow, branch_execution.step_key)
        awaiting_approval_count = await _foreach_awaiting_approval_count(db, branch_execution.id)
        await _enqueue_next_foreach_iterations(
            db,
            updated,
            run_id,
            foreach_step,
            foreach_step_index,
            redispatch_recoverable=awaiting_approval_count == 0,
        )
    else:
        await db.commit()
    return True


async def resume_branch_approval(
    run_id: str,
    step_id: str,
    approved: bool,
    db: AsyncSession,
    *,
    timed_out: bool = False,
    timeout_action: str | None = None,
) -> bool:
    if await _resume_parallel_branch_approval(
        db,
        run_id=run_id,
        step_id=step_id,
        approved=approved,
        timed_out=timed_out,
        timeout_action=timeout_action,
    ):
        return True
    if await _resume_foreach_iteration_approval(
        db,
        run_id=run_id,
        step_id=step_id,
        approved=approved,
        timed_out=timed_out,
        timeout_action=timeout_action,
    ):
        return True
    return False


async def reject_approval(
    run_id: str,
    step_id: str,
    db: AsyncSession,
    *,
    timed_out: bool = False,
    timeout_action: str | None = None,
) -> bool:
    if await resume_branch_approval(
        run_id,
        step_id,
        False,
        db,
        timed_out=timed_out,
        timeout_action=timeout_action,
    ):
        return True

    now = datetime.now(timezone.utc)
    run = await db.get(Run, run_id)
    if run is not None:
        run.status = "failed"
        run.error = "Approval timed out" if timed_out else APPROVAL_REJECTED_ERROR
        run.completed_at = now

    step_execution = await _get_existing_step_execution(db, run_id, step_id)
    if step_execution is None:
        result = await db.execute(
            select(StepExecution)
            .where(StepExecution.run_id == run_id, StepExecution.status == "awaiting_approval")
            .order_by(StepExecution.started_at.desc().nullslast(), StepExecution.created_at.desc())
        )
        step_execution = result.scalars().first()

    await _upsert_step(
        db,
        run_id,
        step_id,
        "approval",
        "failed",
        error="Approval timed out" if timed_out else APPROVAL_REJECTED_ERROR,
    )
    if step_execution is not None:
        error_details: dict[str, Any] | str = (
            {
                "type": "ApprovalTimedOut",
                "message": "Approval timed out",
                "timeout_action": timeout_action or "reject",
            }
            if timed_out
            else {
                "type": "ApprovalRejected",
                "message": APPROVAL_REJECTED_ERROR,
            }
        )
        await _finish_step_execution(
            db,
            step_execution,
            APPROVAL_AUTO_REJECTED_STATUS if timed_out else "failed",
            attempt_number=1,
            error=error_details,
            output_preview={
                "approved": False,
                "status": "auto_rejected" if timed_out else "rejected",
                **({"timed_out": True, "timeout_action": timeout_action or "reject"} if timed_out else {}),
            },
        )
    else:
        logger.warning(
            "approval.reject_step_execution_not_found",
            run_id=run_id,
            step_id=step_id,
            timed_out=timed_out,
        )
    await db.commit()
    return False


async def _synthesize_foreach_output(
    db: AsyncSession,
    run_id: str,
    foreach_step: dict[str, Any],
    branch_execution: BranchExecution,
) -> dict[str, Any]:
    results: list[Any] = []
    child_step = foreach_step.get("step") or {}
    child_id = str(child_step.get("id", "step"))
    for item_index in range(branch_execution.total_branches):
        dotted_key = f"{foreach_step['id']}.{item_index}.{child_id}"
        step_result = await _get_existing_step(db, run_id, dotted_key)
        if step_result is None:
            results.append({"status": "cancelled" if branch_execution.fail_fast_triggered else "missing"})
        elif step_result.status == "completed":
            results.append(step_result.output)
        else:
            results.append({"status": step_result.status, "error": step_result.error})
    return {
        "results": results,
        "completed_count": branch_execution.completed_branches,
        "failed_count": branch_execution.failed_branches,
    }


async def _merge_foreach_if_ready(
    db: AsyncSession,
    branch_execution_id: str,
    run_id: str,
    foreach_step_key: str,
) -> None:
    branch_execution = await db.get(BranchExecution, branch_execution_id)
    if branch_execution is None:
        logger.warning(
            "foreach.merge_evaluation_missing_branch",
            foreach_id=branch_execution_id,
            step_key=foreach_step_key,
            merge_condition_true=False,
            merge_job_dispatched=False,
        )
        await db.commit()
        return

    currently_running_count = await _foreach_running_count(db, branch_execution_id)
    merge_ready = _all_branches_terminal(branch_execution)
    logger.debug(
        "foreach.merge_evaluated",
        foreach_id=branch_execution.id,
        step_key=branch_execution.step_key,
        total_items=branch_execution.total_branches,
        completed_count=branch_execution.completed_branches,
        failed_count=branch_execution.failed_branches,
        cancelled_count=branch_execution.cancelled_branches,
        currently_running_count=currently_running_count,
        merge_condition_true=merge_ready,
        merge_job_dispatched=merge_ready,
    )
    if not merge_ready:
        await db.commit()
        return

    claimed = await _claim_merge(db, branch_execution_id)
    if claimed is None:
        logger.debug(
            "foreach.merge_claim_skipped",
            foreach_id=branch_execution.id,
            step_key=branch_execution.step_key,
            total_items=branch_execution.total_branches,
            completed_count=branch_execution.completed_branches,
            failed_count=branch_execution.failed_branches,
            cancelled_count=branch_execution.cancelled_branches,
            currently_running_count=currently_running_count,
            merge_condition_true=True,
            merge_job_dispatched=False,
            reason="already_claimed",
        )
        await db.commit()
        return

    run = await db.get(Run, run_id)
    if run is None:
        await db.commit()
        return
    workflow = await db.get(Workflow, run.workflow_id)
    if workflow is None:
        run.status = "failed"
        run.error = "Workflow not found"
        await db.commit()
        return

    _foreach_step_index, foreach_step = _find_foreach_step(workflow, foreach_step_key)
    branch_execution = await db.get(BranchExecution, branch_execution_id)
    if branch_execution is None:
        await db.commit()
        return
    merged_output = await _synthesize_foreach_output(db, run_id, foreach_step, branch_execution)
    now = datetime.now(timezone.utc)
    branch_execution.completed_at = now
    branch_execution.merged_context = merged_output

    foreach_step_execution = await _get_existing_step_execution(db, run_id, foreach_step_key)
    if branch_execution.failed_branches or branch_execution.cancelled_branches:
        branch_execution.status = "failed"
        await _upsert_step(
            db,
            run_id,
            foreach_step_key,
            "foreach",
            "failed",
            input=foreach_step,
            output=merged_output,
            error="One or more foreach iterations failed",
        )
        if foreach_step_execution is not None:
            await _finish_step_execution(
                db,
                foreach_step_execution,
                "failed",
                error="One or more foreach iterations failed",
                output_preview=sanitize_preview_payload(merged_output),
            )
        run.status = "failed"
        run.error = "One or more foreach iterations failed"
        run.context = {**(run.context or {}), foreach_step_key: merged_output}
        await db.commit()
        logger.warning(
            "foreach.failed",
            run_id=run_id,
            workflow_id=workflow.id,
            step_key=foreach_step_key,
            branch_execution_id=branch_execution_id,
        )
        return

    branch_execution.status = "completed"
    context = dict(run.context or {})
    context[foreach_step_key] = merged_output
    if foreach_step.get("output_as"):
        context[str(foreach_step["output_as"])] = merged_output
    run.context = context
    await _upsert_step(
        db,
        run_id,
        foreach_step_key,
        "foreach",
        "completed",
        input=foreach_step,
        output=merged_output,
    )
    if foreach_step_execution is not None:
        await _finish_step_execution(
            db,
            foreach_step_execution,
            "completed",
            output_preview=sanitize_preview_payload(merged_output),
        )
    await db.commit()
    logger.info(
        "foreach.completed",
        run_id=run_id,
        workflow_id=workflow.id,
        step_key=foreach_step_key,
        branch_execution_id=branch_execution_id,
    )
    await execute_run(run_id, db)


async def execute_foreach_iteration(
    branch_execution_id: str,
    run_id: str,
    foreach_step_key: str,
    item_index: int,
    db: AsyncSession,
) -> None:
    run = await db.get(Run, run_id)
    if run is None:
        logger.warning("foreach_iteration.run_not_found", run_id=run_id, branch_execution_id=branch_execution_id)
        return
    workflow = await db.get(Workflow, run.workflow_id)
    if workflow is None:
        logger.warning("foreach_iteration.workflow_not_found", run_id=run_id, workflow_id=run.workflow_id)
        return

    foreach_step_index, foreach_step = _find_foreach_step(workflow, foreach_step_key)
    branch_execution = await db.get(BranchExecution, branch_execution_id)
    if branch_execution is None:
        logger.warning("foreach_iteration.branch_execution_not_found", branch_execution_id=branch_execution_id)
        return
    if branch_execution.fail_fast_triggered:
        await _merge_foreach_if_ready(db, branch_execution_id, run_id, foreach_step_key)
        return
    items = branch_execution.foreach_items or []
    if item_index >= len(items):
        raise ValueError(f"Foreach item index out of range: {item_index}")

    branch_key, child_step = _foreach_iteration_step(foreach_step_key, foreach_step.get("step") or {}, item_index)
    step_id, step_type = _validate_step_for_execution(child_step)
    if step_type in {"parallel_group", "foreach"}:
        raise ValueError(f"Nested orchestration step is not supported in foreach: {step_type}")

    item = items[item_index]
    context: dict[str, Any] = dict(run.context or {})
    if run.trigger_data:
        context.setdefault("trigger_data", run.trigger_data)
    item_variable = str(foreach_step.get("item_variable") or "item")
    index_variable = str(foreach_step.get("index_variable") or "index")
    context[item_variable] = item
    context[index_variable] = item_index
    context["foreach"] = {"item": item, "index": item_index}

    step_index = (foreach_step_index + 1) * 1000 + item_index
    input_preview = _build_input_preview(child_step, context, step_type)
    existing = await _get_existing_step(db, run_id, step_id)
    if existing is not None and existing.status in TERMINAL_BRANCH_STATUSES:
        updated = await _reconcile_terminal_foreach_iteration(
            db,
            run_id=run_id,
            branch_execution_id=branch_execution_id,
            child_step=child_step,
            step_id=step_id,
            step_type=step_type,
            step_index=step_index,
            branch_key=branch_key,
            foreach_index=item_index,
            foreach_item=item,
            input_preview=input_preview,
            step_result=existing,
        )
        if updated is None:
            await _merge_foreach_if_ready(db, branch_execution_id, run_id, foreach_step_key)
            return
        if _all_branches_terminal(updated):
            await _merge_foreach_if_ready(db, branch_execution_id, run_id, foreach_step_key)
            return
        current_index, current_foreach_step = _find_foreach_step(workflow, foreach_step_key)
        await _enqueue_next_foreach_iterations(db, updated, run_id, current_foreach_step, current_index)
        return

    existing_step_execution = await _get_existing_foreach_step_execution(
        db,
        run_id,
        step_id,
        item_index,
        branch_execution_id=branch_execution_id,
    )
    if existing_step_execution is not None and existing_step_execution.status in (
        ACTIVE_FOREACH_STATUSES | {"awaiting_approval"}
    ):
        logger.info(
            "foreach_iteration.already_active",
            run_id=run_id,
            workflow_id=workflow.id,
            foreach_step_key=foreach_step_key,
            item_index=item_index,
            step_key=step_id,
            status=existing_step_execution.status,
        )
        await db.commit()
        return

    step_execution = await _start_step_execution(
        db,
        run_id,
        step_index,
        child_step,
        step_id,
        step_type,
        input_preview=input_preview,
        branch_execution_id=branch_execution_id,
        branch_key=branch_key,
        foreach_index=item_index,
        foreach_item=item,
    )
    await _upsert_step(db, run_id, step_id, step_type, "running", input=child_step)
    await db.commit()

    iteration_status = "completed"
    try:
        attempt_number = 1
        if step_type in {"tool", "llm"}:
            output, attempt_number = await _execute_step_with_retry(child_step, context, run_id, db)
        else:
            output = await _dispatch_step(child_step, context, run_id, db)

        normalized_output = output if isinstance(output, dict) else {"result": output}
        await _upsert_step(
            db,
            run_id,
            step_id,
            step_type,
            "completed",
            input=child_step,
            output=normalized_output,
        )
        await _finish_step_execution(
            db,
            step_execution,
            "completed",
            attempt_number=attempt_number,
            output_preview=_build_output_preview(step_type, normalized_output),
        )
        logger.info(
            "foreach_iteration.completed",
            run_id=run_id,
            workflow_id=workflow.id,
            foreach_step_key=foreach_step_key,
            item_index=item_index,
            step_key=step_id,
        )
    except ApprovalRequiredException:
        await _pause_branch_approval(
            db,
            run=run,
            branch_execution=branch_execution,
            step_execution=step_execution,
            step_id=step_id,
            step_type=step_type,
            input_step=child_step,
        )
        logger.info(
            "foreach_iteration.awaiting_approval",
            run_id=run_id,
            workflow_id=workflow.id,
            foreach_step_key=foreach_step_key,
            item_index=item_index,
            step_key=step_id,
        )
        current_index, current_foreach_step = _find_foreach_step(workflow, foreach_step_key)
        await _enqueue_next_foreach_iterations(db, branch_execution, run_id, current_foreach_step, current_index)
        return
    except Exception as exc:
        iteration_status = "failed"
        await _finish_step_execution(
            db,
            step_execution,
            "failed",
            attempt_number=getattr(exc, "attempt_number", _max_attempts_for_step(child_step, step_type)),
            error=exc,
        )
        await _upsert_step(
            db,
            run_id,
            step_id,
            step_type,
            "failed",
            input=child_step,
            error=_step_error_message(exc),
        )
        logger.exception(
            "foreach_iteration.failed",
            run_id=run_id,
            workflow_id=workflow.id,
            foreach_step_key=foreach_step_key,
            item_index=item_index,
            step_key=step_id,
            error=str(exc),
        )

    updated = await _sync_foreach_branch_counters(db, branch_execution_id)
    if updated is None:
        logger.debug(
            "foreach.iteration_terminal_accounting_missing_branch",
            foreach_id=branch_execution_id,
            foreach_step_key=foreach_step_key,
            item_index=item_index,
            terminal_status=iteration_status,
            merge_condition_true=False,
        )
        await _merge_foreach_if_ready(db, branch_execution_id, run_id, foreach_step_key)
        return

    currently_running_count = await _foreach_running_count(db, branch_execution_id)
    merge_ready = _all_branches_terminal(updated)
    logger.debug(
        "foreach.iteration_terminal_accounted",
        foreach_id=branch_execution_id,
        step_key=updated.step_key,
        iteration_step_key=step_id,
        item_index=item_index,
        terminal_status=iteration_status,
        total_items=updated.total_branches,
        completed_count=updated.completed_branches,
        failed_count=updated.failed_branches,
        cancelled_count=updated.cancelled_branches,
        currently_running_count=currently_running_count,
        merge_condition_true=merge_ready,
    )

    if iteration_status == "failed" and updated.fail_fast:
        updated = await _cancel_remaining_foreach_iterations(db, branch_execution_id)
        if updated is not None:
            currently_running_count = await _foreach_running_count(db, branch_execution_id)
            logger.debug(
                "foreach.fail_fast_triggered",
                foreach_id=branch_execution_id,
                step_key=updated.step_key,
                total_items=updated.total_branches,
                completed_count=updated.completed_branches,
                failed_count=updated.failed_branches,
                cancelled_count=updated.cancelled_branches,
                currently_running_count=currently_running_count,
                merge_condition_true=_all_branches_terminal(updated),
            )
            await _merge_foreach_if_ready(db, branch_execution_id, run_id, foreach_step_key)
        return

    if merge_ready:
        await _merge_foreach_if_ready(db, branch_execution_id, run_id, foreach_step_key)
        return

    current_index, current_foreach_step = _find_foreach_step(workflow, foreach_step_key)
    await _enqueue_next_foreach_iterations(db, updated, run_id, current_foreach_step, current_index)


async def execute_parallel_branch(
    branch_execution_id: str,
    run_id: str,
    group_step_key: str,
    branch_index: int,
    db: AsyncSession,
) -> None:
    run = await db.get(Run, run_id)
    if run is None:
        logger.warning("parallel_branch.run_not_found", run_id=run_id, branch_execution_id=branch_execution_id)
        return
    workflow = await db.get(Workflow, run.workflow_id)
    if workflow is None:
        logger.warning("parallel_branch.workflow_not_found", run_id=run_id, workflow_id=run.workflow_id)
        return
    branch_execution = await db.get(BranchExecution, branch_execution_id)
    if branch_execution is None:
        logger.warning("parallel_branch.branch_execution_not_found", run_id=run_id, branch_execution_id=branch_execution_id)
        return

    group_step_index, group_step = _find_parallel_group(workflow, group_step_key)
    child_steps = group_step.get("steps") or []
    if branch_index >= len(child_steps):
        raise ValueError(f"Parallel branch index out of range: {branch_index}")
    branch_key, child_step = _branch_step(group_step_key, child_steps[branch_index])
    step_id, step_type = _validate_step_for_execution(child_step)
    if step_type in {"parallel_group", "foreach"}:
        raise ValueError(f"Nested orchestration step is not supported in parallel_group: {step_type}")

    existing = await _get_existing_step(db, run_id, step_id)
    if existing is not None and existing.status in TERMINAL_BRANCH_STATUSES:
        await _merge_parallel_group_if_ready(db, branch_execution_id, run_id, group_step_key)
        return

    context: dict[str, Any] = dict(run.context or {})
    if run.trigger_data:
        context.setdefault("trigger_data", run.trigger_data)

    step_index = (group_step_index + 1) * 1000 + branch_index
    input_preview = _build_input_preview(child_step, context, step_type)
    step_execution = await _start_step_execution(
        db,
        run_id,
        step_index,
        child_step,
        step_id,
        step_type,
        input_preview=input_preview,
        branch_execution_id=branch_execution_id,
        branch_key=branch_key,
    )
    await _upsert_step(db, run_id, step_id, step_type, "running", input=child_step)
    await db.commit()

    branch_status = "completed"
    try:
        attempt_number = 1
        if step_type in {"tool", "llm"}:
            output, attempt_number = await _execute_step_with_retry(child_step, context, run_id, db)
        else:
            output = await _dispatch_step(child_step, context, run_id, db)

        normalized_output = output if isinstance(output, dict) else {"result": output}
        context[step_id] = normalized_output
        if child_step.get("output_as"):
            context[str(child_step["output_as"])] = normalized_output
        await _upsert_step(
            db,
            run_id,
            step_id,
            step_type,
            "completed",
            input=child_step,
            output=normalized_output,
        )
        await _finish_step_execution(
            db,
            step_execution,
            "completed",
            attempt_number=attempt_number,
            output_preview=_build_output_preview(step_type, normalized_output),
        )
        logger.info(
            "parallel_branch.completed",
            run_id=run_id,
            workflow_id=workflow.id,
            group_step_key=group_step_key,
            branch_key=branch_key,
            step_key=step_id,
        )
    except ApprovalRequiredException:
        await _pause_branch_approval(
            db,
            run=run,
            branch_execution=branch_execution,
            step_execution=step_execution,
            step_id=step_id,
            step_type=step_type,
            input_step=child_step,
        )
        logger.info(
            "parallel_branch.awaiting_approval",
            run_id=run_id,
            workflow_id=workflow.id,
            group_step_key=group_step_key,
            branch_key=branch_key,
            step_key=step_id,
        )
        return
    except Exception as exc:
        branch_status = "failed"
        await _finish_step_execution(
            db,
            step_execution,
            "failed",
            attempt_number=getattr(exc, "attempt_number", _max_attempts_for_step(child_step, step_type)),
            error=exc,
        )
        await _upsert_step(
            db,
            run_id,
            step_id,
            step_type,
            "failed",
            input=child_step,
            error=_step_error_message(exc),
        )
        logger.exception(
            "parallel_branch.failed",
            run_id=run_id,
            workflow_id=workflow.id,
            group_step_key=group_step_key,
            branch_key=branch_key,
            step_key=step_id,
            error=str(exc),
        )

    await _mark_branch_terminal(db, branch_execution_id, branch_status)
    await _merge_parallel_group_if_ready(db, branch_execution_id, run_id, group_step_key)


async def execute_run(run_id: str, db: AsyncSession) -> None:
    run = await db.get(Run, run_id)
    if run is None:
        logger.warning("run.not_found", run_id=run_id)
        return

    workflow = await db.get(Workflow, run.workflow_id)
    if workflow is None:
        run.status = "failed"
        run.error = "Workflow not found"
        await db.commit()
        logger.error("run.failed", run_id=run_id, workflow_id=run.workflow_id, error="Workflow not found")
        return

    logger.info("run.started", run_id=run.id, workflow_id=workflow.id)
    context: dict[str, Any] = dict(run.context or {})
    if run.trigger_data:
        context.setdefault("trigger_data", run.trigger_data)

    run.status = "running"
    run.started_at = run.started_at or datetime.now(timezone.utc)
    run.error = None
    await db.commit()

    try:
        for step_index, step in enumerate(workflow.steps):
            step_id, step_type = _validate_step_for_execution(step)
            existing = await _get_existing_step(db, run_id, step_id)
            if existing is not None and existing.status == "completed":
                if existing.output is not None:
                    context[step_id] = existing.output
                    if step.get("output_as"):
                        context[step["output_as"]] = existing.output
                continue

            logger.info(
                "step.started",
                run_id=run_id,
                workflow_id=workflow.id,
                step_id=step_id,
                step_type=step_type,
            )
            run.current_step = step_id
            await _upsert_step(db, run_id, step_id, step_type, "running", input=step)
            input_preview = _build_input_preview(step, context, step_type)
            step_execution = await _start_step_execution(
                db,
                run_id,
                step_index,
                step,
                step_id,
                step_type,
                input_preview=input_preview,
            )
            await db.commit()  

            try:
                attempt_number = 1
                if step_type == "parallel_group":
                    await ParallelGroupExecutor().start(
                        run=run,
                        workflow=workflow,
                        step=step,
                        step_index=step_index,
                        context=context,
                        db=db,
                    )
                    raise ParallelGroupPending()
                if step_type == "foreach":
                    await ForeachExecutor().start(
                        run=run,
                        workflow=workflow,
                        step=step,
                        step_index=step_index,
                        context=context,
                        db=db,
                    )
                    raise ParallelGroupPending()
                if step_type in {"tool", "llm"}:
                    output, attempt_number = await _execute_step_with_retry(step, context, run_id, db)
                else:
                    output = await _dispatch_step(step, context, run_id, db)
            except ParallelGroupPending:
                logger.info(
                    "run.waiting_for_orchestration_step",
                    run_id=run_id,
                    workflow_id=workflow.id,
                    step_id=step_id,
                    step_type=step_type,
                )
                return
            except ApprovalRequiredException:
                await _finish_step_execution(
                    db,
                    step_execution,
                    "awaiting_approval",
                    attempt_number=1,
                    output_preview={"approval_required": True},
                )
                await _upsert_step(db, run_id, step_id, step_type, "paused", input=step)
                run.status = "paused"
                run.context = context
                await db.commit()
                logger.info(
                    "run.paused",
                    run_id=run_id,
                    workflow_id=workflow.id,
                    step_id=step_id,
                    step_type=step_type,
                )
                return
            except Exception as exc:
                await _finish_step_execution(
                    db,
                    step_execution,
                    "failed",
                    attempt_number=getattr(exc, "attempt_number", _max_attempts_for_step(step, step_type)),
                    error=exc,
                )
                await _upsert_step(db, run_id, step_id, step_type, "failed", input=step, error=_step_error_message(exc))
                await db.commit()
                logger.exception(
                    "step.failed",
                    run_id=run_id,
                    workflow_id=workflow.id,
                    step_id=step_id,
                    step_type=step_type,
                    error=str(exc),
                )
                raise

            normalized_output = output if isinstance(output, dict) else {"result": output}
            context[step_id] = normalized_output
            if step.get("output_as"):
                context[step["output_as"]] = normalized_output
            await _upsert_step(
                db,
                run_id,
                step_id,
                step_type,
                "completed",
                input=step,
                output=normalized_output,
            )
            await _finish_step_execution(
                db,
                step_execution,
                "completed",
                attempt_number=attempt_number,
                output_preview=_build_output_preview(step_type, normalized_output),
            )
            await db.commit()
            logger.info(
                "step.completed",
                run_id=run_id,
                workflow_id=workflow.id,
                step_id=step_id,
                step_type=step_type,
            )

        run.status = "completed"
        run.context = context
        run.current_step = None
        run.completed_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info("run.completed", run_id=run_id, workflow_id=workflow.id)
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)
        run.context = context
        await db.commit()
        logger.exception("run.failed", run_id=run_id, workflow_id=workflow.id, error=str(exc))


async def resume_run(
    run_id: str,
    step_id: str,
    db: AsyncSession,
    *,
    timed_out: bool = False,
    timeout_action: str | None = None,
) -> None:
    approval_output = {"approved": True}
    if timed_out:
        approval_output.update(
            {
                "timed_out": True,
                "timeout_action": timeout_action or "approve",
            }
        )
    if await resume_branch_approval(
        run_id,
        step_id,
        True,
        db,
        timed_out=timed_out,
        timeout_action=timeout_action,
    ):
        logger.info("branch_approval.resumed", run_id=run_id, step_id=step_id)
        return

    await _upsert_step(
        db,
        run_id,
        step_id,
        "approval",
        "completed",
        output=approval_output,
    )
    step_execution = await _get_existing_step_execution(db, run_id, step_id)
    if step_execution is not None:
        await _finish_step_execution(
            db,
            step_execution,
            APPROVAL_AUTO_APPROVED_STATUS if timed_out else "completed",
            attempt_number=1,
            output_preview={
                **approval_output,
                "status": "auto_approved" if timed_out else "approved",
            },
        )
    run = await db.get(Run, run_id)
    if run is not None:
        run.status = "pending"
    await db.commit()
    logger.info("run.retrying", run_id=run_id, step_id=step_id)
    await execute_run(run_id, db)
