from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.engine import executor
from app.engine.steps import approval as approval_step
from app.models.run import Run
from app.models.step_execution import StepExecution
from app.models.workflow import Workflow
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry
from conftest import TestingSessionLocal


pytestmark = pytest.mark.asyncio


async def test_run_timeline_endpoint_returns_run_and_ordered_steps(client, auth_headers):
    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Timeline workflow",
            steps=[],
            trigger_type="manual",
            trigger_config={},
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        run = Run(workflow_id=workflow.id, status="running", trigger_data={})
        db.add(run)
        await db.commit()
        await db.refresh(run)

        db.add_all(
            [
                StepExecution(
                    run_id=run.id,
                    step_index=1,
                    step_key="second",
                    step_type="tool",
                    step_label="second",
                    status="failed",
                    attempt_number=1,
                    max_attempts=1,
                    error_details={"message": "boom"},
                ),
                StepExecution(
                    run_id=run.id,
                    step_index=0,
                    step_key="first",
                    step_type="llm",
                    step_label="first",
                    status="completed",
                    attempt_number=1,
                    max_attempts=1,
                    started_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                    duration_ms=10,
                ),
            ]
        )
        await db.commit()
        run_id = run.id

    response = await client.get(f"/api/v1/runs/{run_id}/timeline", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["run"]["id"] == run_id
    assert [step["step_key"] for step in data["steps"]] == ["first", "second"]
    assert data["failed_step_key"] == "second"
    assert data["steps"][1]["error_details"] == {"message": "boom"}


async def test_execute_run_creates_completed_step_execution(monkeypatch):
    async def fake_execute(tool_name, action, params, credentials):
        return ToolResult(success=True, data={"ok": True})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)

    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Timeline execution workflow",
            steps=[
                {
                    "id": "notify",
                    "type": "tool",
                    "tool": "http_request",
                    "action": "execute",
                    "params": {"url": "https://example.test"},
                }
            ],
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

        step_execution = (
            await db.execute(select(StepExecution).where(StepExecution.run_id == run.id))
        ).scalar_one()

    assert run.status == "completed"
    assert step_execution.step_index == 0
    assert step_execution.step_key == "notify"
    assert step_execution.step_type == "tool"
    assert step_execution.status == "completed"
    assert step_execution.tool_name == "http_request"
    assert step_execution.started_at is not None
    assert step_execution.completed_at is not None
    assert step_execution.duration_ms is not None


async def test_approval_step_execution_awaits_approval(monkeypatch):
    monkeypatch.setattr(approval_step, "_send_approval_email", lambda approval, step, context: None)

    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Approval timeline workflow",
            steps=[
                {
                    "id": "approve",
                    "type": "approval",
                    "approver_email": "approver@example.com",
                }
            ],
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

        step_execution = (
            await db.execute(select(StepExecution).where(StepExecution.run_id == run.id))
        ).scalar_one()

    assert run.status == "paused"
    assert step_execution.status == "awaiting_approval"
    assert step_execution.step_key == "approve"
    assert step_execution.completed_at is not None
