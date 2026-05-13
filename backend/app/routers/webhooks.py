import inspect
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select
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


SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
    "x-auth-token",
    "x-access-token",
    "x-refresh-token",
    "x-webhook-secret",
}


def sanitize_webhook_headers(headers: dict[str, str] | Any) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in dict(headers).items():
        lowered = key.lower()
        if lowered in SENSITIVE_HEADER_NAMES or lowered.endswith("-token") or "secret" in lowered:
            sanitized_value = "[redacted]"
        else:
            sanitized_value = value
        sanitized[key] = sanitized_value
        normalized_key = lowered.replace("-", "_")
        if normalized_key != key:
            sanitized[normalized_key] = sanitized_value
    return sanitized


def _expected_webhook_secret(workflow: Workflow) -> str | None:
    trigger_config = workflow.trigger_config or {}
    trigger = trigger_config.get("trigger") if isinstance(trigger_config.get("trigger"), dict) else {}
    return trigger_config.get("secret") or trigger_config.get("webhook_secret") or trigger.get("secret")


async def _create_webhook_run(workflow: Workflow, trigger_data: dict[str, Any], db: AsyncSession) -> Run:
    run = Run(workflow_id=workflow.id, status="pending", trigger_data=trigger_data)
    db.add(run)
    await db.commit()
    await db.refresh(run)
    await enqueue_execute_workflow(run.id)
    return run


@router.post("/{webhook_id}", status_code=status.HTTP_202_ACCEPTED)
async def trigger_webhook(
    webhook_id: str,
    request: Request,
    token: str | None = Query(default=None),
    x_webhook_secret: str | None = Header(default=None, alias="X-Webhook-Secret"),
    body: dict[str, Any] = Body(default_factory=dict),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    result = await db.execute(select(Workflow).where(Workflow.webhook_id == webhook_id))
    workflow = result.scalar_one_or_none()

    if workflow is None and token is not None:
        workflow = await db.get(Workflow, webhook_id)
        if workflow is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
        if workflow.trigger_type != "webhook":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Workflow is not webhook-triggered")
        if (workflow.trigger_config or {}).get("webhook_token") != token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook token")
        run = await _create_webhook_run(workflow, body or {}, db)
        return {"run_id": run.id, "status": "queued"}

    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    if not workflow.is_active:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Workflow is inactive")
    if workflow.trigger_type != "webhook":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Workflow is not webhook-triggered")

    expected_secret = _expected_webhook_secret(workflow)
    if expected_secret and x_webhook_secret != expected_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret")

    trigger_data = {
        "body": body or {},
        "headers": sanitize_webhook_headers(dict(request.headers)),
        "query_params": dict(request.query_params),
    }
    run = await _create_webhook_run(workflow, trigger_data, db)
    return {"success": True, "run_id": run.id, "workflow_id": workflow.id}
