import inspect
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.run import Run
from app.models.workflow import Workflow


router = APIRouter(tags=["webhooks"])


async def enqueue_execute_workflow(run_id: str) -> None:
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    try:
        await pool.enqueue_job("execute_workflow", run_id)
    finally:
        close = getattr(pool, "close", None)
        if close is not None:
            result = close()
            if inspect.isawaitable(result):
                await result


@router.post("/{workflow_id}", status_code=status.HTTP_202_ACCEPTED)
async def trigger_webhook(
    workflow_id: str,
    token: str = Query(...),
    body: dict[str, Any] = Body(default_factory=dict),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    workflow = await db.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    if workflow.trigger_type != "webhook":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Workflow is not webhook-triggered")
    if (workflow.trigger_config or {}).get("webhook_token") != token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook token")

    run = Run(workflow_id=workflow_id, status="pending", trigger_data=body or {})
    db.add(run)
    await db.commit()
    await db.refresh(run)
    await enqueue_execute_workflow(run.id)
    return {"run_id": run.id, "status": "queued"}
