from app.database import AsyncSessionLocal
from app.engine.executor import execute_foreach_iteration, execute_parallel_branch, execute_run, resume_run
import structlog
from collections.abc import Awaitable, Callable
from typing import TypeVar
from sqlalchemy.ext.asyncio import AsyncSession


logger = structlog.get_logger(__name__)
T = TypeVar("T")


async def _run_with_session(job_name: str, work: Callable[[AsyncSession], Awaitable[T]], **log_context) -> T:
    db = AsyncSessionLocal()
    work_error: Exception | None = None
    try:
        return await work(db)
    except Exception as exc:
        work_error = exc
        try:
            await db.rollback()
        except Exception as rollback_error:
            logger.warning(
                "arq.db_session_rollback_failed",
                job_name=job_name,
                error=str(rollback_error),
                **log_context,
            )
        raise
    finally:
        try:
            await db.close()
        except Exception as close_error:
            logger.warning(
                "arq.db_session_close_failed",
                job_name=job_name,
                error=str(close_error),
                business_error=work_error is not None,
                **log_context,
            )
            if work_error is not None:
                # Preserve the original business failure instead of masking it
                # with a connection cleanup issue.
                pass


async def execute_workflow(ctx, run_id: str) -> None:
    logger.info("arq.execute_workflow.started", run_id=run_id)
    try:
        await _run_with_session("execute_workflow", lambda db: execute_run(run_id, db), run_id=run_id)
        logger.info("arq.execute_workflow.succeeded", run_id=run_id)
    except Exception:
        logger.exception("arq.execute_workflow.failed", run_id=run_id)
        raise


async def resume_workflow(ctx, run_id: str, step_id: str) -> None:
    logger.info("arq.resume_workflow.started", run_id=run_id, step_id=step_id)
    try:
        await _run_with_session("resume_workflow", lambda db: resume_run(run_id, step_id, db), run_id=run_id, step_id=step_id)
        logger.info("arq.resume_workflow.succeeded", run_id=run_id, step_id=step_id)
    except Exception:
        logger.exception("arq.resume_workflow.failed", run_id=run_id, step_id=step_id)
        raise


async def execute_parallel_branch_job(
    ctx,
    branch_execution_id: str,
    run_id: str,
    group_step_key: str,
    branch_index: int,
) -> None:
    logger.info(
        "arq.execute_parallel_branch.started",
        branch_execution_id=branch_execution_id,
        run_id=run_id,
        group_step_key=group_step_key,
        branch_index=branch_index,
    )
    try:
        await _run_with_session(
            "execute_parallel_branch",
            lambda db: execute_parallel_branch(branch_execution_id, run_id, group_step_key, branch_index, db),
            branch_execution_id=branch_execution_id,
            run_id=run_id,
            group_step_key=group_step_key,
            branch_index=branch_index,
        )
        logger.info(
            "arq.execute_parallel_branch.succeeded",
            branch_execution_id=branch_execution_id,
            run_id=run_id,
            group_step_key=group_step_key,
            branch_index=branch_index,
        )
    except Exception:
        logger.exception(
            "arq.execute_parallel_branch.failed",
            branch_execution_id=branch_execution_id,
            run_id=run_id,
            group_step_key=group_step_key,
            branch_index=branch_index,
        )
        raise


async def execute_foreach_iteration_job(
    ctx,
    branch_execution_id: str,
    run_id: str,
    foreach_step_key: str,
    item_index: int,
) -> None:
    logger.info(
        "arq.execute_foreach_iteration.started",
        branch_execution_id=branch_execution_id,
        run_id=run_id,
        foreach_step_key=foreach_step_key,
        item_index=item_index,
    )
    try:
        await _run_with_session(
            "execute_foreach_iteration",
            lambda db: execute_foreach_iteration(branch_execution_id, run_id, foreach_step_key, item_index, db),
            branch_execution_id=branch_execution_id,
            run_id=run_id,
            foreach_step_key=foreach_step_key,
            item_index=item_index,
        )
        logger.info(
            "arq.execute_foreach_iteration.succeeded",
            branch_execution_id=branch_execution_id,
            run_id=run_id,
            foreach_step_key=foreach_step_key,
            item_index=item_index,
        )
    except Exception:
        logger.exception(
            "arq.execute_foreach_iteration.failed",
            branch_execution_id=branch_execution_id,
            run_id=run_id,
            foreach_step_key=foreach_step_key,
            item_index=item_index,
        )
        raise
