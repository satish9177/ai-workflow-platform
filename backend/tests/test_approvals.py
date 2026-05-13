from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.auth import create_approval_token
from app.engine import executor
from app.engine.steps import approval as approval_step
from app.models.approval import Approval
from app.models.run import Run
from app.models.step_execution import StepExecution
from app.models.workflow import Workflow
from app.routers import approvals as approvals_router
from app.routers import webhooks as webhooks_router
from conftest import TestingSessionLocal


pytestmark = pytest.mark.asyncio


async def create_run_with_approval(expires_at=None):
    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Approval workflow",
            steps=[{"id": "approve", "type": "approval", "approver_email": "approver@example.com"}],
            trigger_type="manual",
            trigger_config={},
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        run = Run(workflow_id=workflow.id, status="paused", trigger_data={}, current_step="approve")
        db.add(run)
        await db.commit()
        await db.refresh(run)

        step_execution = StepExecution(
            run_id=run.id,
            step_index=0,
            step_key="approve",
            step_type="approval",
            step_label="approve",
            status="awaiting_approval",
            attempt_number=1,
            max_attempts=1,
            started_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        db.add(step_execution)

        approval = Approval(
            run_id=run.id,
            step_id="approve",
            token="pending-token",
            status="pending",
            context={"amount": 100},
            approver_email="approver@example.com",
            expires_at=expires_at or datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add(approval)
        await db.flush()
        approval.token = create_approval_token(approval.id, approval.approver_email)
        await db.commit()
        await db.refresh(approval)

        return run.id, approval.id, approval.token


async def test_get_pending_approvals(client, auth_headers):
    run_id, approval_id, token = await create_run_with_approval()

    response = await client.get("/api/v1/approvals/pending", headers=auth_headers)

    assert response.status_code == 200
    approvals = response.json()
    assert len(approvals) == 1
    assert approvals[0]["id"] == approval_id
    assert approvals[0]["status"] == "pending"


async def test_approve_via_token(client, monkeypatch):
    enqueued = []

    async def fake_enqueue(run_id, step_id):
        enqueued.append((run_id, step_id))

    monkeypatch.setattr(approvals_router, "enqueue_resume_workflow", fake_enqueue)
    run_id, approval_id, token = await create_run_with_approval()

    response = await client.post(f"/api/v1/approvals/{token}/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert enqueued == [(run_id, "approve")]

    async with TestingSessionLocal() as db:
        approval = await db.get(Approval, approval_id)
        assert approval.status == "approved"


async def test_reject_via_token(client):
    run_id, approval_id, token = await create_run_with_approval()

    response = await client.post(f"/api/v1/approvals/{token}/reject")

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"

    async with TestingSessionLocal() as db:
        approval = await db.get(Approval, approval_id)
        run = await db.get(Run, run_id)
        step_execution = (
            await db.execute(select(StepExecution).where(StepExecution.run_id == run_id))
        ).scalar_one()
        assert approval.status == "rejected"
        assert run.status == "failed"
        assert run.error == "Rejected by approver"
        assert step_execution.status == "failed"
        assert step_execution.completed_at is not None
        assert step_execution.duration_ms is not None
        assert step_execution.error_details == {
            "type": "ApprovalRejected",
            "message": "Rejected by approver",
        }


async def test_reject_via_token_updates_executor_created_timeline(client, auth_headers, monkeypatch):
    monkeypatch.setattr(approval_step, "_send_approval_email", lambda approval, step, context: None)

    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Executor approval workflow",
            steps=[{"id": "approval_step", "type": "approval", "approver_email": "approver@example.com"}],
            trigger_type="manual",
            trigger_config={},
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        run = Run(workflow_id=workflow.id, status="pending", trigger_data={})
        db.add(run)
        await db.commit()
        await db.refresh(run)

        await executor.execute_run(run.id, db)
        await db.refresh(run)

        approval = (
            await db.execute(select(Approval).where(Approval.run_id == run.id))
        ).scalar_one()
        approval.step_id = "approve"
        await db.commit()
        run_id = run.id
        token = approval.token

    response = await client.post(f"/api/v1/approvals/{token}/reject")

    assert response.status_code == 200

    timeline = await client.get(f"/api/v1/runs/{run_id}/timeline", headers=auth_headers)

    assert timeline.status_code == 200
    data = timeline.json()
    assert data["run"]["status"] == "failed"
    assert data["failed_step_key"] == "approval_step"
    assert data["steps"][0]["status"] == "failed"
    assert data["steps"][0]["step_key"] == "approval_step"
    assert data["steps"][0]["completed_at"] is not None
    assert data["steps"][0]["duration_ms"] is not None
    assert data["steps"][0]["error_details"] == {
        "type": "ApprovalRejected",
        "message": "Rejected by approver",
    }


async def test_expired_token(client):
    expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    run_id, approval_id, token = await create_run_with_approval(expires_at=expires_at)

    response = await client.post(f"/api/v1/approvals/{token}/approve")

    assert response.status_code == 410
    assert response.json()["detail"] == "Approval expired"


async def test_invalid_token(client):
    response = await client.post("/api/v1/approvals/garbage-token/approve")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid approval token"


async def test_webhook_valid_token_creates_queued_run(client, monkeypatch):
    enqueued = []

    async def fake_enqueue(run_id):
        enqueued.append(run_id)

    monkeypatch.setattr(webhooks_router, "enqueue_execute_workflow", fake_enqueue)

    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Webhook workflow",
            steps=[{"id": "fetch", "type": "http_request", "config": {"url": "https://example.test"}}],
            trigger_type="webhook",
            trigger_config={"webhook_token": "secret"},
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)
        workflow_id = workflow.id

    response = await client.post(f"/webhooks/{workflow_id}?token=secret", json={"event": "created"})

    assert response.status_code == 202
    data = response.json()
    assert data["run_id"]
    assert data["status"] == "queued"
    assert enqueued == [data["run_id"]]

    async with TestingSessionLocal() as db:
        run = await db.get(Run, data["run_id"])
        assert run.status == "pending"
        assert run.trigger_data == {"event": "created"}


async def test_webhook_invalid_token_returns_401(client):
    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Webhook workflow",
            steps=[{"id": "fetch", "type": "http_request", "config": {"url": "https://example.test"}}],
            trigger_type="webhook",
            trigger_config={"webhook_token": "secret"},
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)
        workflow_id = workflow.id

    response = await client.post(f"/webhooks/{workflow_id}?token=wrong", json={"event": "created"})

    assert response.status_code == 401


async def test_integrations_list_returns_registered_tools(client, auth_headers):
    response = await client.get("/api/v1/integrations/", headers=auth_headers)

    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert {"http_request", "smtp_email", "whatsapp"}.issubset(names)
