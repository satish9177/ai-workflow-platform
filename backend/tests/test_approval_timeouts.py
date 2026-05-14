from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.engine import approval_timeouts, executor
from app.engine.steps import approval as approval_step
from app.models.approval import Approval
from app.models.branch_execution import BranchExecution
from app.models.run import Run
from app.models.step_execution import StepExecution
from app.models.workflow import Workflow
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry
from conftest import TestingSessionLocal


pytestmark = pytest.mark.asyncio


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple]] = []

    async def enqueue_job(self, name, *args):
        self.jobs.append((name, args))
        return {"name": name, "args": args}

    async def close(self):
        return None


@pytest.fixture
def fake_queue(monkeypatch):
    queue = FakeQueue()

    async def fake_create_pool(*args, **kwargs):
        return queue

    monkeypatch.setattr(executor, "create_pool", fake_create_pool)
    return queue


@pytest.fixture(autouse=True)
def no_approval_email(monkeypatch):
    monkeypatch.setattr(approval_step, "_send_approval_email", lambda approval, step, context: None)


async def _fake_tool_success(tool_name, action, params, credentials):
    return ToolResult(success=True, data={"ok": True, "params": params})


async def _create_run(steps: list[dict]) -> str:
    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Approval timeout workflow",
            trigger_type="manual",
            trigger_config={},
            steps=steps,
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        run = Run(workflow_id=workflow.id, status="pending", trigger_data={})
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run.id


async def _approval_for_run(run_id: str) -> Approval:
    async with TestingSessionLocal() as db:
        approval = (
            await db.execute(select(Approval).where(Approval.run_id == run_id).order_by(Approval.step_id.asc()))
        ).scalars().first()
        assert approval is not None
        return approval


async def _force_due(approval_id: str) -> None:
    async with TestingSessionLocal() as db:
        approval = await db.get(Approval, approval_id)
        assert approval is not None
        approval.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()


async def _handle_timeout(approval_id: str) -> bool:
    async with TestingSessionLocal() as db:
        return await approval_timeouts.handle_approval_timeout(approval_id, db)


async def _run_foreach_job(job: tuple[str, tuple]) -> None:
    _name, args = job
    async with TestingSessionLocal() as db:
        await executor.execute_foreach_iteration(*args, db)


async def _run_parallel_job(job: tuple[str, tuple]) -> None:
    _name, args = job
    async with TestingSessionLocal() as db:
        await executor.execute_parallel_branch(*args, db)


async def test_linear_approval_timeout_reject_fails_workflow():
    run_id = await _create_run(
        [
            {
                "id": "approve",
                "type": "approval",
                "approver_email": "approver@example.com",
                "timeout_seconds": 5,
                "timeout_action": "reject",
            }
        ]
    )
    async with TestingSessionLocal() as db:
        await executor.execute_run(run_id, db)

    approval = await _approval_for_run(run_id)
    await _force_due(approval.id)

    assert await _handle_timeout(approval.id) is True

    async with TestingSessionLocal() as db:
        run = await db.get(Run, run_id)
        approval = await db.get(Approval, approval.id)
        step_execution = (
            await db.execute(select(StepExecution).where(StepExecution.run_id == run_id))
        ).scalar_one()

    assert run is not None
    assert run.status == "failed"
    assert run.error == "Approval timed out"
    assert approval is not None
    assert approval.status == "rejected"
    assert approval.timed_out_at is not None
    assert step_execution.status == "auto_rejected"
    assert step_execution.error_details == {
        "type": "ApprovalTimedOut",
        "message": "Approval timed out",
        "timeout_action": "reject",
    }
    assert step_execution.output_preview["status"] == "auto_rejected"


async def test_linear_approval_timeout_approve_resumes_workflow(monkeypatch):
    monkeypatch.setattr(ToolRegistry, "execute", _fake_tool_success)
    run_id = await _create_run(
        [
            {
                "id": "approve",
                "type": "approval",
                "approver_email": "approver@example.com",
                "timeout_seconds": 5,
                "timeout_action": "approve",
            },
            {
                "id": "notify",
                "type": "tool",
                "tool": "http_request",
                "action": "execute",
                "params": {"url": "https://example.test"},
            },
        ]
    )
    async with TestingSessionLocal() as db:
        await executor.execute_run(run_id, db)

    approval = await _approval_for_run(run_id)
    await _force_due(approval.id)

    assert await _handle_timeout(approval.id) is True

    async with TestingSessionLocal() as db:
        run = await db.get(Run, run_id)
        approval = await db.get(Approval, approval.id)
        step_executions = (
            await db.execute(select(StepExecution).where(StepExecution.run_id == run_id).order_by(StepExecution.step_index))
        ).scalars().all()

    assert run is not None
    assert run.status == "completed"
    assert approval is not None
    assert approval.status == "approved"
    assert step_executions[0].status == "auto_approved"
    assert step_executions[0].output_preview["status"] == "auto_approved"
    assert step_executions[1].status == "completed"


async def test_parallel_approval_timeout_reject_fails_only_branch_and_sibling_continues(fake_queue, monkeypatch):
    monkeypatch.setattr(ToolRegistry, "execute", _fake_tool_success)
    run_id = await _create_run(
        [
            {
                "id": "approval_group",
                "type": "parallel_group",
                "steps": [
                    {
                        "id": "approve",
                        "type": "approval",
                        "approver_email": "approver@example.com",
                        "timeout_seconds": 5,
                        "timeout_action": "reject",
                    },
                    {
                        "id": "notify",
                        "type": "tool",
                        "tool": "http_request",
                        "action": "execute",
                        "params": {"url": "https://example.test"},
                    },
                ],
            }
        ]
    )
    async with TestingSessionLocal() as db:
        await executor.execute_run(run_id, db)
    for job in list(fake_queue.jobs):
        await _run_parallel_job(job)

    approval = await _approval_for_run(run_id)
    await _force_due(approval.id)
    assert await _handle_timeout(approval.id) is True

    async with TestingSessionLocal() as db:
        run = await db.get(Run, run_id)
        branch = (await db.execute(select(BranchExecution).where(BranchExecution.run_id == run_id))).scalar_one()
        steps = (
            await db.execute(select(StepExecution).where(StepExecution.run_id == run_id).order_by(StepExecution.step_key))
        ).scalars().all()

    assert run is not None
    assert run.status == "failed"
    assert branch.failed_branches == 1
    assert branch.completed_branches == 1
    statuses = {step.step_key: step.status for step in steps}
    assert statuses["approval_group.approve"] == "auto_rejected"
    assert statuses["approval_group.notify"] == "completed"


async def test_foreach_approval_timeout_approve_resumes_iteration_and_aggregation(fake_queue):
    run_id = await _create_run(
        [
            {
                "id": "approve_each",
                "type": "foreach",
                "items": ["alpha"],
                "item_variable": "item",
                "concurrency_limit": 1,
                "step": {
                    "id": "approve",
                    "type": "approval",
                    "approver_email": "approver@example.com",
                    "message": "Approve {{ foreach.item }}",
                    "timeout_seconds": 5,
                    "timeout_action": "approve",
                },
            }
        ]
    )
    async with TestingSessionLocal() as db:
        await executor.execute_run(run_id, db)
    await _run_foreach_job(fake_queue.jobs[0])

    approval = await _approval_for_run(run_id)
    await _force_due(approval.id)
    assert await _handle_timeout(approval.id) is True

    async with TestingSessionLocal() as db:
        run = await db.get(Run, run_id)
        branch = (await db.execute(select(BranchExecution).where(BranchExecution.run_id == run_id))).scalar_one()
        step_execution = (
            await db.execute(select(StepExecution).where(StepExecution.step_key == "approve_each.0.approve"))
        ).scalar_one()

    assert run is not None
    assert run.status == "completed"
    assert branch.status == "completed"
    assert branch.completed_branches == 1
    assert step_execution.status == "auto_approved"


async def test_foreach_approval_timeout_reject_fails_only_iteration(fake_queue):
    run_id = await _create_run(
        [
            {
                "id": "approve_each",
                "type": "foreach",
                "items": ["alpha"],
                "item_variable": "item",
                "concurrency_limit": 1,
                "step": {
                    "id": "approve",
                    "type": "approval",
                    "approver_email": "approver@example.com",
                    "message": "Approve {{ foreach.item }}",
                    "timeout_seconds": 5,
                    "timeout_action": "reject",
                },
            }
        ]
    )
    async with TestingSessionLocal() as db:
        await executor.execute_run(run_id, db)
    await _run_foreach_job(fake_queue.jobs[0])

    approval = await _approval_for_run(run_id)
    await _force_due(approval.id)
    assert await _handle_timeout(approval.id) is True

    async with TestingSessionLocal() as db:
        run = await db.get(Run, run_id)
        branch = (await db.execute(select(BranchExecution).where(BranchExecution.run_id == run_id))).scalar_one()
        step_execution = (
            await db.execute(select(StepExecution).where(StepExecution.step_key == "approve_each.0.approve"))
        ).scalar_one()

    assert run is not None
    assert run.status == "failed"
    assert branch.status == "failed"
    assert branch.failed_branches == 1
    assert step_execution.status == "auto_rejected"


async def test_duplicate_timeout_job_is_idempotent():
    run_id = await _create_run(
        [
            {
                "id": "approve",
                "type": "approval",
                "approver_email": "approver@example.com",
                "timeout_seconds": 5,
                "timeout_action": "reject",
            }
        ]
    )
    async with TestingSessionLocal() as db:
        await executor.execute_run(run_id, db)

    approval = await _approval_for_run(run_id)
    await _force_due(approval.id)

    assert await _handle_timeout(approval.id) is True
    assert await _handle_timeout(approval.id) is False

    async with TestingSessionLocal() as db:
        approvals = (await db.execute(select(Approval).where(Approval.run_id == run_id))).scalars().all()
        step_executions = (await db.execute(select(StepExecution).where(StepExecution.run_id == run_id))).scalars().all()

    assert len(approvals) == 1
    assert len(step_executions) == 1


async def test_already_resolved_approval_timeout_noops():
    run_id = await _create_run(
        [
            {
                "id": "approve",
                "type": "approval",
                "approver_email": "approver@example.com",
                "timeout_seconds": 5,
                "timeout_action": "reject",
            }
        ]
    )
    async with TestingSessionLocal() as db:
        await executor.execute_run(run_id, db)

    approval = await _approval_for_run(run_id)
    await _force_due(approval.id)
    async with TestingSessionLocal() as db:
        approval_row = await db.get(Approval, approval.id)
        assert approval_row is not None
        approval_row.status = "approved"
        await db.commit()

    assert await _handle_timeout(approval.id) is False


async def test_timeout_poll_survives_scheduler_restart(monkeypatch):
    run_id = await _create_run(
        [
            {
                "id": "approve",
                "type": "approval",
                "approver_email": "approver@example.com",
                "timeout_seconds": 5,
                "timeout_action": "reject",
            }
        ]
    )
    async with TestingSessionLocal() as db:
        await executor.execute_run(run_id, db)
    approval = await _approval_for_run(run_id)
    await _force_due(approval.id)
    monkeypatch.setattr(approval_timeouts, "AsyncSessionLocal", TestingSessionLocal)

    await approval_timeouts.poll_approval_timeouts()

    async with TestingSessionLocal() as db:
        approval = await db.get(Approval, approval.id)
        run = await db.get(Run, run_id)

    assert approval is not None
    assert approval.status == "rejected"
    assert run is not None
    assert run.status == "failed"


async def test_approval_timeout_action_validation(client, auth_headers):
    response = await client.post(
        "/api/v1/workflows/",
        headers=auth_headers,
        json={
            "name": "Invalid timeout action",
            "trigger_type": "manual",
            "steps": [
                {
                    "id": "approve",
                    "type": "approval",
                    "approver_email": "approver@example.com",
                    "timeout_seconds": 30,
                    "timeout_action": "escalate",
                }
            ],
        },
    )

    assert response.status_code == 422
    assert "timeout_action must be approve or reject" in str(response.json())


async def test_approval_timeout_seconds_validation(client, auth_headers):
    response = await client.post(
        "/api/v1/workflows/",
        headers=auth_headers,
        json={
            "name": "Invalid timeout seconds",
            "trigger_type": "manual",
            "steps": [
                {
                    "id": "approve",
                    "type": "approval",
                    "approver_email": "approver@example.com",
                    "timeout_seconds": 0,
                    "timeout_action": "reject",
                }
            ],
        },
    )

    assert response.status_code == 422
    assert "timeout_seconds must be greater than 0" in str(response.json())
