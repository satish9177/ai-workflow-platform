import pytest
from sqlalchemy import select

from app.engine import executor
from app.engine.steps import approval as approval_step
from app.models.approval import Approval
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


async def _create_run(steps: list[dict], trigger_data: dict | None = None) -> str:
    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Switch workflow",
            trigger_type="manual",
            trigger_config={},
            steps=steps,
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        run = Run(workflow_id=workflow.id, status="pending", trigger_data=trigger_data or {})
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run.id


async def _run(run_id: str) -> Run:
    async with TestingSessionLocal() as db:
        await executor.execute_run(run_id, db)
        run = await db.get(Run, run_id)
        assert run is not None
        return run


async def _fake_tool(tool_name, action, params, credentials):
    return ToolResult(success=True, data={"tool": tool_name, "action": action, "params": params})


def _switch_step(on: str = "urgent", on_no_match: str = "skip") -> dict:
    return {
        "id": "route_by_priority",
        "type": "switch",
        "on": on,
        "on_no_match": on_no_match,
        "branches": {
            "urgent": [
                {
                    "id": "send_alert",
                    "type": "tool",
                    "tool": "http_request",
                    "action": "execute",
                    "params": {"url": "https://example.test/urgent"},
                    "output_as": "alert_result",
                }
            ],
            "normal": [
                {
                    "id": "send_email",
                    "type": "tool",
                    "tool": "http_request",
                    "action": "execute",
                    "params": {"url": "https://example.test/normal"},
                }
            ],
        },
        "default": [
            {
                "id": "fallback_notify",
                "type": "tool",
                "tool": "http_request",
                "action": "execute",
                "params": {"url": "https://example.test/default"},
            }
        ],
    }


async def test_switch_selected_branch_executes_and_skips_others(monkeypatch):
    monkeypatch.setattr(ToolRegistry, "execute", _fake_tool)
    run_id = await _create_run([_switch_step()])

    run = await _run(run_id)

    async with TestingSessionLocal() as db:
        steps = (
            await db.execute(
                select(StepExecution).where(StepExecution.run_id == run_id).order_by(StepExecution.step_key)
            )
        ).scalars().all()

    assert run.status == "completed"
    assert run.context["route_by_priority.__branch__"] == "urgent"
    assert run.context["route_by_priority.__evaluated__"] == "urgent"
    assert run.context["alert_result"]["data"]["params"]["url"] == "https://example.test/urgent"
    statuses = {step.step_key: step.status for step in steps}
    assert statuses["route_by_priority"] == "completed"
    assert statuses["route_by_priority.urgent"] == "completed"
    assert statuses["route_by_priority.normal"] == "skipped"
    assert statuses["route_by_priority.default"] == "skipped"
    assert statuses["route_by_priority.urgent.send_alert"] == "completed"
    assert "route_by_priority.normal.send_email" not in statuses


async def test_switch_default_branch_executes_when_no_match(monkeypatch):
    monkeypatch.setattr(ToolRegistry, "execute", _fake_tool)
    run_id = await _create_run([_switch_step(on="unknown")])

    run = await _run(run_id)

    async with TestingSessionLocal() as db:
        fallback = (
            await db.execute(
                select(StepExecution).where(StepExecution.step_key == "route_by_priority.default.fallback_notify")
            )
        ).scalar_one()

    assert run.status == "completed"
    assert run.context["route_by_priority.__branch__"] == "default"
    assert fallback.status == "completed"


async def test_switch_no_match_skip_completes_without_child_execution(monkeypatch):
    monkeypatch.setattr(ToolRegistry, "execute", _fake_tool)
    step = _switch_step(on="unknown")
    step.pop("default")
    run_id = await _create_run([step])

    run = await _run(run_id)

    async with TestingSessionLocal() as db:
        steps = (
            await db.execute(
                select(StepExecution).where(StepExecution.run_id == run_id).order_by(StepExecution.step_key)
            )
        ).scalars().all()

    statuses = {step.step_key: step.status for step in steps}
    assert run.status == "completed"
    assert run.context["route_by_priority"]["selected_branch"] is None
    assert statuses["route_by_priority.urgent"] == "skipped"
    assert statuses["route_by_priority.normal"] == "skipped"
    assert "route_by_priority.urgent.send_alert" not in statuses


async def test_switch_no_match_fail_fails_run(monkeypatch):
    monkeypatch.setattr(ToolRegistry, "execute", _fake_tool)
    step = _switch_step(on="unknown", on_no_match="fail")
    step.pop("default")
    run_id = await _create_run([step])

    run = await _run(run_id)

    assert run.status == "failed"
    assert "did not match branch" in (run.error or "")


async def test_switch_reexecution_reuses_persisted_branch_selection(monkeypatch):
    monkeypatch.setattr(ToolRegistry, "execute", _fake_tool)
    run_id = await _create_run([_switch_step(on="{{ trigger_data.route }}")], trigger_data={"route": "urgent"})
    await _run(run_id)

    async with TestingSessionLocal() as db:
        run = await db.get(Run, run_id)
        assert run is not None
        run.trigger_data = {"route": "normal"}
        run.status = "pending"
        step_result = (
            await db.execute(select(StepResult).where(StepResult.run_id == run_id, StepResult.step_id == "route_by_priority"))
        ).scalar_one()
        step_result.status = "running"
        step_result.output = step_result.output
        child_result = (
            await db.execute(
                select(StepResult).where(StepResult.run_id == run_id, StepResult.step_id == "route_by_priority.urgent.send_alert")
            )
        ).scalar_one()
        await db.delete(child_result)
        await db.commit()

    rerun = await _run(run_id)

    assert rerun.status == "completed"
    assert rerun.context["route_by_priority.__branch__"] == "urgent"


async def test_switch_inside_foreach(fake_queue, monkeypatch):
    monkeypatch.setattr(ToolRegistry, "execute", _fake_tool)
    run_id = await _create_run(
        [
            {
                "id": "route_each",
                "type": "foreach",
                "items": ["urgent", "normal"],
                "item_variable": "item",
                "concurrency_limit": 2,
                "step": _switch_step(on="{{ foreach.item }}"),
            }
        ]
    )
    await _run(run_id)
    for job in list(fake_queue.jobs):
        _name, args = job
        async with TestingSessionLocal() as db:
            await executor.execute_foreach_iteration(*args, db)

    async with TestingSessionLocal() as db:
        run = await db.get(Run, run_id)
        urgent_child = (
            await db.execute(select(StepExecution).where(StepExecution.step_key == "route_each.0.route_by_priority.urgent.send_alert"))
        ).scalar_one()
        normal_child = (
            await db.execute(select(StepExecution).where(StepExecution.step_key == "route_each.1.route_by_priority.normal.send_email"))
        ).scalar_one()

    assert run is not None
    assert run.status == "completed"
    assert urgent_child.status == "completed"
    assert normal_child.status == "completed"


async def test_switch_inside_parallel_group(fake_queue, monkeypatch):
    monkeypatch.setattr(ToolRegistry, "execute", _fake_tool)
    run_id = await _create_run(
        [
            {
                "id": "parallel_routes",
                "type": "parallel_group",
                "steps": [
                    _switch_step(on="urgent"),
                    {
                        "id": "notify",
                        "type": "tool",
                        "tool": "http_request",
                        "action": "execute",
                        "params": {"url": "https://example.test/notify"},
                    },
                ],
            }
        ]
    )
    await _run(run_id)
    for job in list(fake_queue.jobs):
        _name, args = job
        async with TestingSessionLocal() as db:
            await executor.execute_parallel_branch(*args, db)

    async with TestingSessionLocal() as db:
        run = await db.get(Run, run_id)
        switch_child = (
            await db.execute(select(StepExecution).where(StepExecution.step_key == "parallel_routes.route_by_priority.urgent.send_alert"))
        ).scalar_one()

    assert run is not None
    assert run.status == "completed"
    assert switch_child.status == "completed"


async def test_approval_inside_selected_switch_branch_pauses_and_resumes(monkeypatch):
    monkeypatch.setattr(ToolRegistry, "execute", _fake_tool)
    step = {
        "id": "approval_route",
        "type": "switch",
        "on": "urgent",
        "branches": {
            "urgent": [
                {
                    "id": "approve",
                    "type": "approval",
                    "approver_email": "approver@example.com",
                },
                {
                    "id": "after_approval",
                    "type": "tool",
                    "tool": "http_request",
                    "action": "execute",
                    "params": {"url": "https://example.test/after"},
                },
            ]
        },
    }
    run_id = await _create_run([step])

    run = await _run(run_id)
    assert run.status == "paused"

    async with TestingSessionLocal() as db:
        approval = (await db.execute(select(Approval).where(Approval.run_id == run_id))).scalar_one()
        await executor.resume_run(run_id, approval.step_id, db)

    async with TestingSessionLocal() as db:
        run = await db.get(Run, run_id)
        approval_step_execution = (
            await db.execute(select(StepExecution).where(StepExecution.step_key == "approval_route.urgent.approve"))
        ).scalar_one()
        after_step_execution = (
            await db.execute(select(StepExecution).where(StepExecution.step_key == "approval_route.urgent.after_approval"))
        ).scalar_one()

    assert run is not None
    assert run.status == "completed"
    assert approval_step_execution.status == "completed"
    assert after_step_execution.status == "completed"


async def test_switch_validation_requires_on(client, auth_headers):
    response = await client.post(
        "/api/v1/workflows/",
        headers=auth_headers,
        json={
            "name": "Invalid switch",
            "trigger_type": "manual",
            "steps": [
                {
                    "id": "route",
                    "type": "switch",
                    "branches": {"urgent": [{"id": "notify", "type": "condition", "condition": "true"}]},
                }
            ],
        },
    )

    assert response.status_code == 422
    assert "on is required" in str(response.json())


async def test_switch_validation_rejects_empty_branch(client, auth_headers):
    response = await client.post(
        "/api/v1/workflows/",
        headers=auth_headers,
        json={
            "name": "Invalid switch branch",
            "trigger_type": "manual",
            "steps": [
                {
                    "id": "route",
                    "type": "switch",
                    "on": "urgent",
                    "branches": {"urgent": []},
                }
            ],
        },
    )

    assert response.status_code == 422
    assert "branch steps must be a non-empty list" in str(response.json())


async def test_switch_validation_rejects_duplicate_ids_within_branch(client, auth_headers):
    response = await client.post(
        "/api/v1/workflows/",
        headers=auth_headers,
        json={
            "name": "Duplicate switch branch ids",
            "trigger_type": "manual",
            "steps": [
                {
                    "id": "route",
                    "type": "switch",
                    "on": "urgent",
                    "branches": {
                        "urgent": [
                            {"id": "notify", "type": "condition", "condition": "true"},
                            {"id": "notify", "type": "condition", "condition": "true"},
                        ]
                    },
                }
            ],
        },
    )

    assert response.status_code == 422
    assert "step ids must be unique within a branch" in str(response.json())
