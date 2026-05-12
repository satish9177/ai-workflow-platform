import pytest
from sqlalchemy import select

from app.engine import executor
from app.engine.steps import approval as approval_step
from app.models.approval import Approval
from app.models.run import Run
from app.models.step_result import StepResult
from app.models.workflow import Workflow
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry
from conftest import TestingSessionLocal


async def _create_and_execute_workflow(steps: list[dict]) -> tuple[Run, StepResult]:
    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Retry workflow",
            steps=steps,
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

        result = await db.execute(select(StepResult).where(StepResult.run_id == run.id))
        step_result = result.scalar_one()
        return run, step_result


@pytest.mark.asyncio
async def test_successful_step_no_retry_config(monkeypatch):
    async def fake_execute(tool_name, action, params, credentials):
        return ToolResult(success=True, data={"ok": True})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)

    run, step_result = await _create_and_execute_workflow(
        [
            {
                "id": "notify",
                "type": "tool",
                "tool": "http_request",
                "action": "execute",
                "params": {"url": "https://example.test"},
            }
        ]
    )

    assert run.status == "completed"
    assert step_result.status == "completed"


@pytest.mark.asyncio
async def test_tool_step_succeeds_after_retry(monkeypatch):
    calls = {"count": 0}

    async def fake_execute(tool_name, action, params, credentials):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary tool failure")
        return ToolResult(success=True, data={"ok": True})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)

    run, step_result = await _create_and_execute_workflow(
        [
            {
                "id": "notify",
                "type": "tool",
                "tool": "http_request",
                "action": "execute",
                "params": {"url": "https://example.test"},
                "retry": {"max_attempts": 3, "backoff_seconds": 0},
            }
        ]
    )

    assert run.status == "completed"
    assert step_result.status == "completed"
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_tool_step_fails_after_max_attempts(monkeypatch):
    calls = {"count": 0}

    async def fake_execute(tool_name, action, params, credentials):
        calls["count"] += 1
        raise RuntimeError("temporary tool failure")

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)

    run, step_result = await _create_and_execute_workflow(
        [
            {
                "id": "notify",
                "type": "tool",
                "tool": "http_request",
                "action": "execute",
                "params": {"url": "https://example.test"},
                "retry": {"max_attempts": 3, "backoff_seconds": 0},
            }
        ]
    )

    assert run.status == "failed"
    assert step_result.status == "failed"
    assert "3/3 attempts" in step_result.error
    assert calls["count"] == 3


@pytest.mark.asyncio
async def test_llm_step_succeeds_after_retry(monkeypatch):
    calls = {"count": 0}

    async def fake_run_llm_step(step, context, run_id, db):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary llm failure")
        return {"response": "ok", "provider": "mock", "model": "mock-model", "usage": {}}

    monkeypatch.setattr(executor, "run_llm_step", fake_run_llm_step)

    run, step_result = await _create_and_execute_workflow(
        [
            {
                "id": "summarize",
                "type": "llm",
                "prompt": "Summarize this",
                "retry": {"max_attempts": 3, "backoff_seconds": 0},
            }
        ]
    )

    assert run.status == "completed"
    assert step_result.status == "completed"
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_approval_step_not_retried(monkeypatch):
    monkeypatch.setattr(approval_step, "_send_approval_email", lambda approval, step, context: None)

    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Approval retry workflow",
            steps=[
                {
                    "id": "approve",
                    "type": "approval",
                    "approver_email": "approver@example.com",
                    "retry": {"max_attempts": 3, "backoff_seconds": 0},
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

        step_result = (
            await db.execute(select(StepResult).where(StepResult.run_id == run.id))
        ).scalar_one()
        approval = (
            await db.execute(select(Approval).where(Approval.run_id == run.id))
        ).scalar_one_or_none()

    assert run.status == "paused"
    assert step_result.status == "paused"
    assert approval is not None
