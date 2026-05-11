from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.steps.approval import ApprovalRequiredException, run_approval_step
from app.engine.steps.condition import run_condition_step
from app.engine.steps.llm import run_llm_step
from app.engine.steps.tool import run_tool_step
from app.models.run import Run
from app.models.step_result import StepResult
from app.models.workflow import Workflow
from app.tools.registry import ToolRegistry


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


def _step_type(step: dict[str, Any]) -> str:
    return step.get("type") or step.get("step_type") or ""


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


async def execute_run(run_id: str, db: AsyncSession) -> None:
    run = await db.get(Run, run_id)
    if run is None:
        return

    workflow = await db.get(Workflow, run.workflow_id)
    if workflow is None:
        run.status = "failed"
        run.error = "Workflow not found"
        await db.commit()
        return

    context: dict[str, Any] = dict(run.context or {})
    if run.trigger_data:
        context.setdefault("trigger_data", run.trigger_data)

    run.status = "running"
    run.started_at = run.started_at or datetime.now(timezone.utc)
    run.error = None
    await db.commit()

    try:
        for step in workflow.steps:
            step_id = step["id"]
            step_type = _step_type(step)
            existing = await _get_existing_step(db, run_id, step_id)
            if existing is not None and existing.status == "completed":
                if existing.output is not None:
                    context[step_id] = existing.output
                continue

            run.current_step = step_id
            await _upsert_step(db, run_id, step_id, step_type, "running", input=step)
            await db.commit()  

            try:
                output = await _dispatch_step(step, context, run_id, db)
            except ApprovalRequiredException:
                await _upsert_step(db, run_id, step_id, step_type, "paused", input=step)
                run.status = "paused"
                run.context = context
                await db.commit()
                return

            normalized_output = output if isinstance(output, dict) else {"result": output}
            context[step_id] = normalized_output
            await _upsert_step(
                db,
                run_id,
                step_id,
                step_type,
                "completed",
                input=step,
                output=normalized_output,
            )
            await db.commit()

        run.status = "completed"
        run.context = context
        run.current_step = None
        run.completed_at = datetime.now(timezone.utc)
        await db.commit()
    except Exception as exc:
        run.status = "failed"
        run.error = str(exc)
        run.context = context
        await db.commit()


async def resume_run(run_id: str, step_id: str, db: AsyncSession) -> None:
    await _upsert_step(
        db,
        run_id,
        step_id,
        "approval",
        "completed",
        output={"approved": True},
    )
    run = await db.get(Run, run_id)
    if run is not None:
        run.status = "pending"
    await db.commit()
    await execute_run(run_id, db)
