import asyncio
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.config import settings
from app.engine.steps.approval import ApprovalRequiredException, run_approval_step
from app.engine.steps.condition import run_condition_step
from app.engine.steps.llm import run_llm_step
from app.engine.steps.tool import run_tool_step
from app.llm.provider_errors import ProviderExecutionError, normalize_provider_error
from app.models.run import Run
from app.models.step_execution import StepExecution
from app.models.step_result import StepResult
from app.models.workflow import Workflow
from app.tools.registry import ToolRegistry
from app.utils.preview import sanitize_preview_payload
from app.utils.template_renderer import render_template_object


logger = structlog.get_logger(__name__)


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
) -> StepExecution:
    now = datetime.now(timezone.utc)
    step_execution = await _get_existing_step_execution(db, run_id, step_id)
    if step_execution is None:
        step_execution = StepExecution(
            run_id=run_id,
            step_index=step_index,
            step_key=step_id,
            step_type=step_type,
            step_label=_step_label(step, step_id),
            status="running",
            attempt_number=1,
            max_attempts=_max_attempts_for_step(step, step_type),
            started_at=now,
            provider=step.get("provider"),
            model=step.get("model"),
            tool_name=step.get("tool") if step_type == "tool" else None,
            input_preview=input_preview,
        )
        db.add(step_execution)
    else:
        step_execution.step_index = step_index
        step_execution.step_type = step_type
        step_execution.step_label = _step_label(step, step_id)
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


def _error_details(error: Exception | str | None) -> dict[str, Any] | None:
    if error is None:
        return None
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
    if step_type == "tool" or ToolRegistry.get(step_type) is not None:
        return await run_tool_step(step, context, db)
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
                if step_type in {"tool", "llm"}:
                    output, attempt_number = await _execute_step_with_retry(step, context, run_id, db)
                else:
                    output = await _dispatch_step(step, context, run_id, db)
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


async def resume_run(run_id: str, step_id: str, db: AsyncSession) -> None:
    await _upsert_step(
        db,
        run_id,
        step_id,
        "approval",
        "completed",
        output={"approved": True},
    )
    step_execution = await _get_existing_step_execution(db, run_id, step_id)
    if step_execution is not None:
        await _finish_step_execution(
            db,
            step_execution,
            "completed",
            attempt_number=1,
            output_preview={"approved": True},
        )
    run = await db.get(Run, run_id)
    if run is not None:
        run.status = "pending"
    await db.commit()
    logger.info("run.retrying", run_id=run_id, step_id=step_id)
    await execute_run(run_id, db)
