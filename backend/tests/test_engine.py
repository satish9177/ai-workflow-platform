import pytest

from app.engine.executor import execute_run
from app.engine.steps import approval as approval_step
from app.engine.steps.condition import evaluate_condition
from app.models.approval import Approval
from app.models.run import Run
from app.models.workflow import Workflow
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry
from conftest import TestingSessionLocal
from sqlalchemy import select


def test_evaluate_condition_true():
    assert evaluate_condition("count > 2", {"count": 3}) is True


def test_evaluate_condition_false():
    assert evaluate_condition("count > 2", {"count": 1}) is False


def test_evaluate_condition_length():
    assert evaluate_condition("items|length == 2", {"items": ["a", "b"]}) is True


def test_evaluate_condition_string_equality():
    assert evaluate_condition("status == 'ready'", {"status": "ready"}) is True


def test_evaluate_condition_injection_attempt_raises():
    with pytest.raises(ValueError):
        evaluate_condition("__import__('os').system('echo nope')", {})


@pytest.mark.asyncio
async def test_execute_run_completes(monkeypatch):
    async def fake_execute(tool_name, action, params, credentials):
        assert tool_name == "http_request"
        assert action == "execute"
        return ToolResult(success=True, data={"ok": True})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)

    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Tool workflow",
            steps=[
                {
                    "id": "fetch",
                    "type": "tool",
                    "tool_name": "http_request",
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

        await execute_run(run.id, db)
        await db.refresh(run)

        assert run.status == "completed"
        assert run.context["fetch"]["data"] == {"ok": True}


@pytest.mark.asyncio
async def test_execute_run_pauses_on_approval(monkeypatch):
    monkeypatch.setattr(approval_step, "_send_approval_email", lambda approval, step, context: None)

    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Approval workflow",
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

        await execute_run(run.id, db)
        await db.refresh(run)

        result = await db.execute(select(Approval).where(Approval.run_id == run.id))
        approval = result.scalar_one_or_none()
        assert approval is not None
        assert approval.step_id == "approve"
        assert run.status == "paused"
        assert run.current_step == "approve"
