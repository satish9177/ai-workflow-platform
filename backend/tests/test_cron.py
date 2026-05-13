from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import main
from app.models.run import Run
from app.models.workflow import Workflow
from conftest import TestingSessionLocal


pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def use_test_sessionmaker(monkeypatch):
    monkeypatch.setattr(main, "AsyncSessionLocal", TestingSessionLocal)


async def test_cron_poll_creates_run_when_due(monkeypatch):
    enqueued = []

    async def fake_enqueue(run_id):
        enqueued.append(run_id)

    monkeypatch.setattr(main, "enqueue_execute_workflow", fake_enqueue)
    last_run = datetime.now(timezone.utc) - timedelta(minutes=2)

    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Cron workflow",
            steps=[{"id": "fetch", "type": "tool", "tool": "http_request", "action": "execute", "params": {"url": "https://example.test"}}],
            trigger_type="cron",
            trigger_config={"cron": "* * * * *", "last_run": last_run.isoformat()},
            is_active=True,
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)
        workflow_id = workflow.id

    await main._poll_cron_triggers()

    async with TestingSessionLocal() as db:
        runs = (
            await db.execute(select(Run).where(Run.workflow_id == workflow_id))
        ).scalars().all()
        workflow = await db.get(Workflow, workflow_id)

    assert len(runs) == 1
    assert runs[0].status == "pending"
    assert runs[0].trigger_data == {"source": "cron"}
    assert enqueued == [runs[0].id]
    assert workflow.trigger_config["last_run"]


async def test_cron_poll_creates_run_with_cron_expression_key(monkeypatch):
    enqueued = []

    async def fake_enqueue(run_id):
        enqueued.append(run_id)

    monkeypatch.setattr(main, "enqueue_execute_workflow", fake_enqueue)
    last_run = datetime.now(timezone.utc) - timedelta(minutes=2)

    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Cron expression workflow",
            steps=[{"id": "fetch", "type": "tool", "tool": "http_request", "action": "execute", "params": {"url": "https://example.test"}}],
            trigger_type="cron",
            trigger_config={"cron_expression": "* * * * *", "last_run": last_run.isoformat()},
            is_active=True,
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)
        workflow_id = workflow.id

    await main._poll_cron_triggers()

    async with TestingSessionLocal() as db:
        runs = (
            await db.execute(select(Run).where(Run.workflow_id == workflow_id))
        ).scalars().all()

    assert len(runs) == 1
    assert runs[0].trigger_data == {"source": "cron"}
    assert enqueued == [runs[0].id]


async def test_cron_poll_still_supports_legacy_cron_key(monkeypatch):
    enqueued = []

    async def fake_enqueue(run_id):
        enqueued.append(run_id)

    monkeypatch.setattr(main, "enqueue_execute_workflow", fake_enqueue)
    last_run = datetime.now(timezone.utc) - timedelta(minutes=2)

    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Legacy cron workflow",
            steps=[{"id": "fetch", "type": "tool", "tool": "http_request", "action": "execute", "params": {"url": "https://example.test"}}],
            trigger_type="cron",
            trigger_config={"cron": "* * * * *", "last_run": last_run.isoformat()},
            is_active=True,
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)
        workflow_id = workflow.id

    await main._poll_cron_triggers()

    async with TestingSessionLocal() as db:
        runs = (
            await db.execute(select(Run).where(Run.workflow_id == workflow_id))
        ).scalars().all()

    assert len(runs) == 1
    assert runs[0].trigger_data == {"source": "cron"}
    assert enqueued == [runs[0].id]


async def test_invalid_cron_does_not_crash_poller(monkeypatch):
    async def fake_enqueue(run_id):
        raise AssertionError("invalid cron should not enqueue")

    monkeypatch.setattr(main, "enqueue_execute_workflow", fake_enqueue)

    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Invalid cron workflow",
            steps=[{"id": "fetch", "type": "tool", "tool": "http_request", "action": "execute", "params": {"url": "https://example.test"}}],
            trigger_type="cron",
            trigger_config={"cron": "not a cron"},
            is_active=True,
        )
        db.add(workflow)
        await db.commit()

    await main._poll_cron_triggers()

    async with TestingSessionLocal() as db:
        runs = (await db.execute(select(Run))).scalars().all()

    assert runs == []
