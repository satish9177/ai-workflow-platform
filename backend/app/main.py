from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import inspect
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from croniter import croniter
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.run import Run
from app.models.workflow import Workflow
from app.routers.approvals import router as approvals_router
from app.routers.auth import router as auth_router
from app.routers.integrations import router as integrations_router
from app.routers.runs import router as runs_router
from app.routers.webhooks import router as webhooks_router
from app.routers.workflows import router as workflows_router


logger = logging.getLogger(__name__)


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


def _parse_last_run(value: str | None, fallback: datetime) -> datetime:
    if not value:
        return fallback

    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


async def _poll_cron_triggers() -> None:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Workflow).where(Workflow.is_active.is_(True), Workflow.trigger_type == "cron")
        )
        workflows = result.scalars().all()

        for workflow in workflows:
            trigger_config = dict(workflow.trigger_config or {})
            cron_expression = trigger_config.get("cron")
            if not cron_expression:
                continue

            try:
                fallback = workflow.created_at or now
                if fallback.tzinfo is None:
                    fallback = fallback.replace(tzinfo=timezone.utc)
                last_run = _parse_last_run(trigger_config.get("last_run"), fallback)
                next_fire = croniter(cron_expression, last_run).get_next(datetime)
                if next_fire.tzinfo is None:
                    next_fire = next_fire.replace(tzinfo=timezone.utc)

                if next_fire <= now:
                    run = Run(
                        workflow_id=workflow.id,
                        status="pending",
                        trigger_data={"source": "cron"},
                    )
                    db.add(run)
                    await db.commit()
                    await db.refresh(run)

                    await enqueue_execute_workflow(run.id)

                    trigger_config["last_run"] = now.isoformat()
                    workflow.trigger_config = trigger_config
                    await db.commit()
            except Exception:
                logger.exception("Failed polling cron workflow %s", workflow.id)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(_poll_cron_triggers, "interval", minutes=1)
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Workflow Platform", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1/auth")
app.include_router(workflows_router, prefix="/api/v1/workflows")
app.include_router(runs_router, prefix="/api/v1/runs")
app.include_router(approvals_router, prefix="/api/v1/approvals")
app.include_router(integrations_router, prefix="/api/v1/integrations")
app.include_router(webhooks_router, prefix="/webhooks")


@app.get("/health")
async def health():
    return {"status": "ok"}
