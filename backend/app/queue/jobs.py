from app.database import AsyncSessionLocal
from app.engine.executor import execute_run, resume_run
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
