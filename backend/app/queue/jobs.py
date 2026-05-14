from app.database import AsyncSessionLocal
from app.engine.executor import execute_parallel_branch, execute_run, resume_run
import structlog


logger = structlog.get_logger(__name__)


async def execute_workflow(ctx, run_id: str) -> None:
    logger.info("arq.execute_workflow.started", run_id=run_id)
    try:
        async with AsyncSessionLocal() as db:
            await execute_run(run_id, db)
        logger.info("arq.execute_workflow.succeeded", run_id=run_id)
    except Exception:
        logger.exception("arq.execute_workflow.failed", run_id=run_id)
        raise


async def resume_workflow(ctx, run_id: str, step_id: str) -> None:
    logger.info("arq.resume_workflow.started", run_id=run_id, step_id=step_id)
    try:
        async with AsyncSessionLocal() as db:
            await resume_run(run_id, step_id, db)
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
        async with AsyncSessionLocal() as db:
            await execute_parallel_branch(branch_execution_id, run_id, group_step_key, branch_index, db)
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
