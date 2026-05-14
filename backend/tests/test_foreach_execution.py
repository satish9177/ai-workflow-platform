import pytest
from sqlalchemy import select

from app.engine import executor
from app.models.branch_execution import BranchExecution
from app.models.run import Run
from app.models.step_execution import StepExecution
from app.models.step_result import StepResult
from app.models.workflow import Workflow
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry
from conftest import TestingSessionLocal


pytestmark = pytest.mark.asyncio


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple]] = []
        self.fail_on_enqueue_index: int | None = None

    async def enqueue_job(self, name, *args):
        if self.fail_on_enqueue_index is not None and args[-1] == self.fail_on_enqueue_index:
            raise RuntimeError("redis enqueue failed")
        self.jobs.append((name, args))
        return {"name": name, "args": args}

    async def close(self):
        return None


@pytest.fixture
def fake_foreach_queue(monkeypatch):
    queue = FakeQueue()

    async def fake_create_pool(*args, **kwargs):
        return queue

    monkeypatch.setattr(executor, "create_pool", fake_create_pool)
    return queue


async def _create_foreach_run(
    *,
    items,
    concurrency_limit: int = 2,
    fail_fast: bool = False,
    after_step: bool = True,
) -> str:
    steps = [
        {
            "id": "notify_each",
            "type": "foreach",
            "items": items,
            "item_variable": "item",
            "index_variable": "index",
            "concurrency_limit": concurrency_limit,
            "fail_fast": fail_fast,
            "step": {
                "id": "notify",
                "type": "tool",
                "tool": "http_request",
                "action": "execute",
                "params": {
                    "url": "https://example.test/{{ foreach.item }}",
                    "item": "{{ foreach.item }}",
                    "index": "{{ foreach.index }}",
                },
            },
        }
    ]
    if after_step:
        steps.append(
            {
                "id": "after_foreach",
                "type": "tool",
                "tool": "http_request",
                "action": "execute",
                "params": {"url": "https://example.test/after"},
            }
        )

    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Foreach workflow",
            trigger_type="manual",
            trigger_config={},
            steps=steps,
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        run = Run(
            workflow_id=workflow.id,
            status="pending",
            trigger_data={"items": ["alpha", "beta", "gamma"]},
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run.id


async def _start_run(run_id: str) -> None:
    async with TestingSessionLocal() as db:
        await executor.execute_run(run_id, db)


async def _run_iteration(job: tuple[str, tuple]) -> None:
    _name, args = job
    async with TestingSessionLocal() as db:
        await executor.execute_foreach_iteration(*args, db)


async def _drain_queue(queue: FakeQueue) -> None:
    processed = 0
    while processed < len(queue.jobs):
        job = queue.jobs[processed]
        processed += 1
        await _run_iteration(job)


async def _get_run(run_id: str) -> Run:
    async with TestingSessionLocal() as db:
        run = await db.get(Run, run_id)
        assert run is not None
        return run


async def test_foreach_successful_execution(fake_foreach_queue, monkeypatch):
    async def fake_execute(tool_name, action, params, credentials):
        if params["url"] == "https://example.test/after":
            return ToolResult(success=True, data={"after": True})
        return ToolResult(success=True, data={"item": params["item"], "index": params["index"]})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)
    run_id = await _create_foreach_run(items=["alpha", "beta", "gamma"], concurrency_limit=2)

    await _start_run(run_id)

    assert [job[0] for job in fake_foreach_queue.jobs] == [
        "execute_foreach_iteration_job",
        "execute_foreach_iteration_job",
    ]

    await _drain_queue(fake_foreach_queue)
    run = await _get_run(run_id)

    assert run.status == "completed"
    assert run.context["notify_each"]["completed_count"] == 3
    assert run.context["notify_each"]["failed_count"] == 0
    assert [result["data"]["item"] for result in run.context["notify_each"]["results"]] == ["alpha", "beta", "gamma"]
    assert run.context["after_foreach"]["data"] == {"after": True}


async def test_foreach_persists_resolved_items_from_trigger_data(fake_foreach_queue, monkeypatch):
    async def fake_execute(tool_name, action, params, credentials):
        return ToolResult(success=True, data={"item": params["item"]})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)
    run_id = await _create_foreach_run(items="{{ trigger_data.items }}", concurrency_limit=2, after_step=False)

    await _start_run(run_id)

    async with TestingSessionLocal() as db:
        branch = (await db.execute(select(BranchExecution).where(BranchExecution.run_id == run_id))).scalar_one()

    assert branch.foreach_items == ["alpha", "beta", "gamma"]


async def test_foreach_partial_failure_aggregates_results(fake_foreach_queue, monkeypatch):
    async def fake_execute(tool_name, action, params, credentials):
        if params["item"] == "beta":
            return ToolResult(success=False, error="beta failed")
        return ToolResult(success=True, data={"item": params["item"]})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)
    run_id = await _create_foreach_run(items=["alpha", "beta", "gamma"], concurrency_limit=2, after_step=False)

    await _start_run(run_id)
    await _drain_queue(fake_foreach_queue)
    run = await _get_run(run_id)

    assert run.status == "failed"
    assert run.context["notify_each"]["completed_count"] == 2
    assert run.context["notify_each"]["failed_count"] == 1
    assert run.context["notify_each"]["results"][1]["status"] == "failed"


async def test_foreach_fail_fast_cancels_remaining_iterations(fake_foreach_queue, monkeypatch):
    async def fake_execute(tool_name, action, params, credentials):
        return ToolResult(success=False, error="first failed")

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)
    run_id = await _create_foreach_run(
        items=["alpha", "beta", "gamma"],
        concurrency_limit=1,
        fail_fast=True,
        after_step=False,
    )

    await _start_run(run_id)
    await _run_iteration(fake_foreach_queue.jobs[0])
    run = await _get_run(run_id)

    async with TestingSessionLocal() as db:
        branch = (await db.execute(select(BranchExecution).where(BranchExecution.run_id == run_id))).scalar_one()

    assert run.status == "failed"
    assert branch.fail_fast_triggered is True
    assert branch.failed_branches == 1
    assert branch.cancelled_branches == 2
    assert len(fake_foreach_queue.jobs) == 1


async def test_foreach_empty_list_completes_immediately(fake_foreach_queue, monkeypatch):
    async def fake_execute(tool_name, action, params, credentials):
        return ToolResult(success=True, data={"after": True})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)
    run_id = await _create_foreach_run(items=[], concurrency_limit=2)

    await _start_run(run_id)
    run = await _get_run(run_id)

    assert fake_foreach_queue.jobs == []
    assert run.status == "completed"
    assert run.context["notify_each"] == {"results": [], "completed_count": 0, "failed_count": 0}


async def test_foreach_invalid_items_expression_fails_clearly(fake_foreach_queue):
    run_id = await _create_foreach_run(items="{{ trigger_data.source }}", concurrency_limit=2, after_step=False)

    await _start_run(run_id)
    run = await _get_run(run_id)

    assert run.status == "failed"
    assert "foreach items must resolve to a list" in run.error
    assert fake_foreach_queue.jobs == []


async def test_foreach_concurrency_limit_enforced(fake_foreach_queue, monkeypatch):
    async def fake_execute(tool_name, action, params, credentials):
        return ToolResult(success=True, data={"item": params["item"]})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)
    run_id = await _create_foreach_run(items=["alpha", "beta", "gamma", "delta"], concurrency_limit=2, after_step=False)

    await _start_run(run_id)

    assert len(fake_foreach_queue.jobs) == 2
    await _run_iteration(fake_foreach_queue.jobs[0])
    assert len(fake_foreach_queue.jobs) == 3
    await _run_iteration(fake_foreach_queue.jobs[1])
    assert len(fake_foreach_queue.jobs) == 4
    await _run_iteration(fake_foreach_queue.jobs[2])
    await _run_iteration(fake_foreach_queue.jobs[3])

    run = await _get_run(run_id)
    assert run.status == "completed"


async def test_foreach_iteration_timeline_visibility(fake_foreach_queue, monkeypatch, client, auth_headers):
    async def fake_execute(tool_name, action, params, credentials):
        return ToolResult(success=True, data={"item": params["item"]})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)
    run_id = await _create_foreach_run(items=["alpha", "beta"], concurrency_limit=2, after_step=False)

    await _start_run(run_id)
    await _drain_queue(fake_foreach_queue)

    response = await client.get(f"/api/v1/runs/{run_id}/timeline", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["branches"][0]["branch_type"] == "foreach"
    assert data["branches"][0]["foreach_items"] == ["alpha", "beta"]
    iteration_steps = [step for step in data["steps"] if step["step_key"].startswith("notify_each.")]
    assert {step["foreach_index"] for step in iteration_steps} == {0, 1}
    assert {step["foreach_item"] for step in iteration_steps} == {"alpha", "beta"}


async def test_foreach_reconciles_terminal_step_result_with_running_timeline_row(fake_foreach_queue, monkeypatch):
    async def fake_execute(tool_name, action, params, credentials):
        raise AssertionError("terminal StepResult should prevent re-executing the tool")

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)
    run_id = await _create_foreach_run(items=["alpha"], concurrency_limit=1, after_step=False)

    await _start_run(run_id)

    async with TestingSessionLocal() as db:
        step_execution = (
            await db.execute(
                select(StepExecution).where(
                    StepExecution.run_id == run_id,
                    StepExecution.step_key == "notify_each.0.notify",
                )
            )
        ).scalar_one()
        step_execution.status = "running"
        db.add(
            StepResult(
                run_id=run_id,
                step_id="notify_each.0.notify",
                step_type="tool",
                status="completed",
                input={"id": "notify"},
                output={"data": {"item": "alpha"}},
            )
        )
        await db.commit()

    await _run_iteration(fake_foreach_queue.jobs[0])

    async with TestingSessionLocal() as db:
        run = await db.get(Run, run_id)
        branch = (await db.execute(select(BranchExecution).where(BranchExecution.run_id == run_id))).scalar_one()
        step_execution = (
            await db.execute(
                select(StepExecution).where(
                    StepExecution.run_id == run_id,
                    StepExecution.step_key == "notify_each.0.notify",
                )
            )
        ).scalar_one()

    assert run is not None
    assert run.status == "completed"
    assert branch.status == "completed"
    assert branch.completed_branches == 1
    assert step_execution.status == "completed"
    assert step_execution.completed_at is not None


async def test_foreach_enqueue_failure_does_not_leave_phantom_running_iteration(fake_foreach_queue, monkeypatch):
    async def fake_execute(tool_name, action, params, credentials):
        return ToolResult(success=True, data={"item": params["item"]})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)
    fake_foreach_queue.fail_on_enqueue_index = 1
    run_id = await _create_foreach_run(items=["alpha", "beta"], concurrency_limit=2, after_step=False)

    await _start_run(run_id)
    await _drain_queue(fake_foreach_queue)

    async with TestingSessionLocal() as db:
        run = await db.get(Run, run_id)
        branch = (await db.execute(select(BranchExecution).where(BranchExecution.run_id == run_id))).scalar_one()
        beta_step = (
            await db.execute(
                select(StepExecution).where(
                    StepExecution.run_id == run_id,
                    StepExecution.step_key == "notify_each.1.notify",
                )
            )
        ).scalar_one()

    assert run is not None
    assert run.status == "failed"
    assert branch.failed_branches == 1
    assert branch.completed_branches == 1
    assert beta_step.status == "failed"
    assert beta_step.completed_at is not None
