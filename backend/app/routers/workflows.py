import inspect
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.run import Run
from app.models.user import User
from app.models.workflow import Workflow
from app.schemas.workflow import WorkflowCreate, WorkflowRead, WorkflowUpdate


router = APIRouter(tags=["workflows"])


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


@router.get("/", response_model=list[WorkflowRead])
async def list_workflows(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Workflow]:
    result = await db.execute(select(Workflow).order_by(Workflow.created_at.desc()))
    return list(result.scalars().all())


@router.post("/", response_model=WorkflowRead, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    payload: WorkflowCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Workflow:
    workflow = Workflow(**payload.model_dump())
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)
    return workflow


@router.get("/{id}", response_model=WorkflowRead)
async def get_workflow(
    id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Workflow:
    workflow = await db.get(Workflow, id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return workflow


@router.put("/{id}", response_model=WorkflowRead)
async def update_workflow(
    id: str,
    payload: WorkflowUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Workflow:
    workflow = await db.get(Workflow, id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(workflow, field, value)

    await db.commit()
    await db.refresh(workflow)
    return workflow


@router.delete("/{id}")
async def delete_workflow(
    id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    result = await db.execute(delete(Workflow).where(Workflow.id == id))
    if result.rowcount == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    await db.commit()
    return {"deleted": True}


@router.post("/{id}/run", status_code=status.HTTP_202_ACCEPTED)
async def trigger_workflow_run(
    id: str,
    body: dict[str, Any] = Body(default_factory=dict),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    workflow = await db.get(Workflow, id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    run = Run(workflow_id=id, status="pending", trigger_data=body.get("trigger_data") or {})
    db.add(run)
    await db.commit()
    await db.refresh(run)
    await enqueue_workflow_run(run.id)
    return {"run_id": run.id, "status": "queued"}


@router.post("/{id}/toggle")
async def toggle_workflow(
    id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    workflow = await db.get(Workflow, id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    workflow.is_active = not workflow.is_active
    await db.commit()
    await db.refresh(workflow)
    return {"is_active": workflow.is_active}
