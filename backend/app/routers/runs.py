import inspect
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.branch_execution import BranchExecution
from app.models.run import Run
from app.models.step_execution import StepExecution
from app.models.step_result import StepResult
from app.models.user import User
from app.schemas.run import RunDetail, RunRead, RunTimelineRead


router = APIRouter(tags=["runs"])


async def enqueue_workflow_run(run_id: str) -> None:
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job("execute_workflow", run_id)
    finally:
        close = getattr(pool, "close", None)
        if close is not None:
            result = close()
            if inspect.isawaitable(result):
                await result


@router.get("/", response_model=list[RunRead])
async def list_runs(
    workflow_id: str | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Run]:
    query = select(Run)
    if workflow_id is not None:
        query = query.where(Run.workflow_id == workflow_id)
    if status_filter is not None:
        query = query.where(Run.status == status_filter)

    result = await db.execute(query.order_by(Run.created_at.desc()).limit(limit))
    return list(result.scalars().all())


@router.get("/{id}", response_model=RunDetail)
async def get_run(
    id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    run = await db.get(Run, id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    result = await db.execute(
        select(StepResult).where(StepResult.run_id == id).order_by(StepResult.created_at.asc())
    )
    run_data = RunRead.model_validate(run).model_dump()
    run_data["step_results"] = list(result.scalars().all())
    return run_data


@router.get("/{run_id}/timeline", response_model=RunTimelineRead)
async def get_run_timeline(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    result = await db.execute(
        select(StepExecution)
        .where(StepExecution.run_id == run_id)
        .order_by(StepExecution.step_index.asc(), StepExecution.created_at.asc())
    )
    steps = list(result.scalars().all())
    branch_result = await db.execute(
        select(BranchExecution)
        .where(BranchExecution.run_id == run_id)
        .order_by(BranchExecution.created_at.asc())
    )
    failed_step = next((step for step in steps if step.status == "failed"), None)
    return {
        "run": run,
        "steps": steps,
        "branches": list(branch_result.scalars().all()),
        "failed_step_key": failed_step.step_key if failed_step else None,
    }


@router.post("/{id}/cancel", response_model=RunRead)
async def cancel_run(
    id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Run:
    run = await db.get(Run, id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.status in ("completed", "failed", "cancelled"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Run cannot be cancelled")

    run.status = "cancelled"
    await db.commit()
    await db.refresh(run)
    return run


@router.post("/{id}/retry", response_model=RunRead)
async def retry_run(
    id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Run:
    run = await db.get(Run, id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.status != "failed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Run cannot be retried")

    run.status = "pending"
    run.error = None
    await db.commit()
    await db.refresh(run)
    await enqueue_workflow_run(run.id)
    return run
