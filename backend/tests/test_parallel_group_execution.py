import asyncio

import pytest
from sqlalchemy import select

from app.engine import executor
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
def fake_parallel_queue(monkeypatch):
    queue = FakeQueue()

    async def fake_create_pool(*args, **kwargs):
        return queue

    monkeypatch.setattr(executor, "create_pool", fake_create_pool)
    return queue


async def _create_parallel_run() -> str:
    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Parallel workflow",
            trigger_type="manual",
            trigger_config={},
            steps=[
                {
                    "id": "notify_group",
                    "type": "parallel_group",
                    "concurrency_limit": 2,
                    "steps": [
                        {
                            "id": "email",
                            "type": "tool",
                            "tool": "http_request",
                            "action": "execute",
                            "params": {"url": "https://example.test/email"},
                        },
                        {
                            "id": "slack",
                            "type": "tool",
                            "tool": "http_request",
                            "action": "execute",
                            "params": {"url": "https://example.test/slack"},
                        },
                    ],
                },
                {
                    "id": "after_group",
                    "type": "tool",
                    "tool": "http_request",
                    "action": "execute",
                    "params": {"url": "https://example.test/after"},
                },
            ],
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        run = Run(workflow_id=workflow.id, status="pending", trigger_data={"source": "test"})
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run.id


async def _start_parallel_run(run_id: str) -> None:
    async with TestingSessionLocal() as db:
        await executor.execute_run(run_id, db)


async def _run_branch(job: tuple[str, tuple]) -> None:
    _name, args = job
    async with TestingSessionLocal() as db:
        await executor.execute_parallel_branch(*args, db)


async def _get_run(run_id: str) -> Run:
    async with TestingSessionLocal() as db:
        run = await db.get(Run, run_id)
        assert run is not None
        return run


async def test_parallel_group_all_branches_succeed_and_resume(fake_parallel_queue, monkeypatch):
    async def fake_execute(tool_name, action, params, credentials):
        return ToolResult(success=True, data={"url": params["url"]})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)
    run_id = await _create_parallel_run()

    await _start_parallel_run(run_id)

    assert [job[0] for job in fake_parallel_queue.jobs] == [
        "execute_parallel_branch_job",
        "execute_parallel_branch_job",
    ]
    run = await _get_run(run_id)
    assert run.status == "running"
    assert run.current_step == "notify_group"

    for job in list(fake_parallel_queue.jobs):
        await _run_branch(job)

    run = await _get_run(run_id)
    assert run.status == "completed"
    assert run.context["notify_group"]["branches"]["email"]["data"]["url"] == "https://example.test/email"
    assert run.context["notify_group"]["branches"]["slack"]["data"]["url"] == "https://example.test/slack"
    assert run.context["after_group"]["data"]["url"] == "https://example.test/after"


async def test_parallel_group_tracks_branch_execution_and_dotted_steps(fake_parallel_queue, monkeypatch):
    async def fake_execute(tool_name, action, params, credentials):
        return ToolResult(success=True, data={"ok": params["url"]})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)
    run_id = await _create_parallel_run()
    await _start_parallel_run(run_id)

    for job in list(fake_parallel_queue.jobs):
        await _run_branch(job)

    async with TestingSessionLocal() as db:
        branch = (await db.execute(select(BranchExecution).where(BranchExecution.run_id == run_id))).scalar_one()
        steps = (
            await db.execute(
                select(StepExecution)
                .where(StepExecution.run_id == run_id)
                .order_by(StepExecution.step_key.asc())
            )
        ).scalars().all()

    assert branch.status == "completed"
    assert branch.total_branches == 2
    assert branch.completed_branches == 2
    assert branch.failed_branches == 0
    assert branch.merge_triggered is True
    assert {step.step_key for step in steps} >= {
        "notify_group",
        "notify_group.email",
        "notify_group.slack",
        "after_group",
    }
    child_steps = [step for step in steps if step.step_key.startswith("notify_group.")]
    assert all(step.branch_execution_id == branch.id for step in child_steps)
    assert {step.branch_key for step in child_steps} == {"email", "slack"}


async def test_parallel_group_merge_is_idempotent(fake_parallel_queue, monkeypatch):
    async def fake_execute(tool_name, action, params, credentials):
        return ToolResult(success=True, data={"ok": True})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)
    run_id = await _create_parallel_run()
    await _start_parallel_run(run_id)

    jobs = list(fake_parallel_queue.jobs)
    for job in jobs:
        await _run_branch(job)
    await _run_branch(jobs[0])

    async with TestingSessionLocal() as db:
        branch = (await db.execute(select(BranchExecution).where(BranchExecution.run_id == run_id))).scalar_one()

    assert branch.completed_branches == 2
    assert branch.merge_triggered is True


async def test_parallel_group_concurrent_branch_completion(fake_parallel_queue, monkeypatch):
    async def fake_execute(tool_name, action, params, credentials):
        await asyncio.sleep(0)
        return ToolResult(success=True, data={"url": params["url"]})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)
    run_id = await _create_parallel_run()
    await _start_parallel_run(run_id)

    await asyncio.gather(*(_run_branch(job) for job in list(fake_parallel_queue.jobs)))

    run = await _get_run(run_id)
    async with TestingSessionLocal() as db:
        branch = (await db.execute(select(BranchExecution).where(BranchExecution.run_id == run_id))).scalar_one()

    assert run.status == "completed"
    assert branch.completed_branches == 2
    assert branch.status == "completed"


async def test_parallel_group_failed_branch_fails_parent_run(fake_parallel_queue, monkeypatch):
    async def fake_execute(tool_name, action, params, credentials):
        if params["url"].endswith("/slack"):
            return ToolResult(success=False, error="slack failed")
        return ToolResult(success=True, data={"url": params["url"]})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)
    run_id = await _create_parallel_run()
    await _start_parallel_run(run_id)

    for job in list(fake_parallel_queue.jobs):
        await _run_branch(job)

    run = await _get_run(run_id)
    async with TestingSessionLocal() as db:
        branch = (await db.execute(select(BranchExecution).where(BranchExecution.run_id == run_id))).scalar_one()
        failed_step = (
            await db.execute(
                select(StepExecution).where(
                    StepExecution.run_id == run_id,
                    StepExecution.step_key == "notify_group.slack",
                )
            )
        ).scalar_one()

    assert run.status == "failed"
    assert branch.status == "failed"
    assert branch.failed_branches == 1
    assert failed_step.status == "failed"
    assert run.context["notify_group"]["branches"]["slack"]["status"] == "failed"


async def test_parallel_group_timeline_includes_branch_metadata(fake_parallel_queue, monkeypatch, client, auth_headers):
    async def fake_execute(tool_name, action, params, credentials):
        return ToolResult(success=True, data={"ok": True})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)
    run_id = await _create_parallel_run()
    await _start_parallel_run(run_id)
    for job in list(fake_parallel_queue.jobs):
        await _run_branch(job)

    response = await client.get(f"/api/v1/runs/{run_id}/timeline", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["branches"][0]["step_key"] == "notify_group"
    assert data["branches"][0]["status"] == "completed"
    assert data["branches"][0]["merged_context"]["branches"]["email"]["data"]["ok"] is True
    assert {step["step_key"] for step in data["steps"]} >= {"notify_group.email", "notify_group.slack"}


async def test_linear_workflow_backward_compatibility(monkeypatch):
    async def fake_execute(tool_name, action, params, credentials):
        return ToolResult(success=True, data={"ok": True})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)
    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Linear workflow",
            steps=[
                {
                    "id": "fetch",
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

    assert run.status == "completed"
    assert run.context["fetch"]["data"] == {"ok": True}
