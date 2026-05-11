from app.database import AsyncSessionLocal
from app.engine.executor import execute_run, resume_run


async def execute_workflow(ctx, run_id: str) -> None:
    async with AsyncSessionLocal() as db:
        await execute_run(run_id, db)


async def resume_workflow(ctx, run_id: str, step_id: str) -> None:
    async with AsyncSessionLocal() as db:
        await resume_run(run_id, step_id, db)
