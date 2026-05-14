import pytest

from app.engine.executor import execute_run
from app.engine.steps import approval as approval_step
from app.llm.registry import LLMRegistry
from app.llm.providers.mock import MockLLMProvider
from app.models.run import Run
from app.models.step_execution import StepExecution
from app.models.workflow import Workflow
from app.routers import webhooks as webhooks_router
from conftest import TestingSessionLocal


pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def mock_webhook_enqueue(monkeypatch):
    enqueued = []

    async def fake_enqueue(run_id):
        enqueued.append(run_id)

    monkeypatch.setattr(webhooks_router, "enqueue_execute_workflow", fake_enqueue)
    return enqueued


async def create_webhook_workflow(secret: str | None = None, is_active: bool = True) -> Workflow:
    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="V2 webhook workflow",
            steps=[
                {
                    "id": "notify",
                    "type": "tool",
                    "tool": "http_request",
                    "action": "execute",
                    "params": {"url": "https://example.test"},
                }
            ],
            trigger_type="webhook",
            trigger_config={"secret": secret} if secret else {},
            is_active=is_active,
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)
        return workflow


async def test_v2_webhook_trigger_creates_run_and_propagates_payload(client, mock_webhook_enqueue):
    workflow = await create_webhook_workflow()

    response = await client.post(
        f"/api/v1/webhooks/{workflow.webhook_id}?source=test",
        json={"event": "created"},
        headers={"X-Custom": "value"},
    )

    assert response.status_code == 202
    data = response.json()
    assert data["success"] is True
    assert data["workflow_id"] == workflow.id
    assert data["run_id"]
    assert mock_webhook_enqueue == [data["run_id"]]

    async with TestingSessionLocal() as db:
        run = await db.get(Run, data["run_id"])

    assert run.workflow_id == workflow.id
    assert run.status == "pending"
    assert run.trigger_data["body"] == {"event": "created"}
    assert run.trigger_data["query_params"] == {"source": "test"}
    assert run.trigger_data["headers"]["x-custom"] == "value"
    assert run.trigger_data["headers"]["x_custom"] == "value"


async def test_v2_webhook_secret_validation_success(client):
    workflow = await create_webhook_workflow(secret="abc123")

    response = await client.post(
        f"/api/v1/webhooks/{workflow.webhook_id}",
        json={"ok": True},
        headers={"X-Webhook-Secret": "abc123"},
    )

    assert response.status_code == 202
    assert response.json()["success"] is True


async def test_v2_webhook_secret_validation_failure(client):
    workflow = await create_webhook_workflow(secret="abc123")

    response = await client.post(
        f"/api/v1/webhooks/{workflow.webhook_id}",
        json={"ok": True},
        headers={"X-Webhook-Secret": "wrong"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid webhook secret"


async def test_v2_webhook_sanitizes_sensitive_headers(client):
    workflow = await create_webhook_workflow()

    response = await client.post(
        f"/api/v1/webhooks/{workflow.webhook_id}",
        json={"event": "created"},
        headers={
            "Authorization": "Bearer secret",
            "Cookie": "session=secret",
            "X-Api-Key": "secret-key",
            "X-Custom": "safe",
        },
    )

    assert response.status_code == 202
    run_id = response.json()["run_id"]

    async with TestingSessionLocal() as db:
        run = await db.get(Run, run_id)

    assert run.trigger_data["headers"]["authorization"] == "[redacted]"
    assert run.trigger_data["headers"]["cookie"] == "[redacted]"
    assert run.trigger_data["headers"]["x-api-key"] == "[redacted]"
    assert run.trigger_data["headers"]["x_api_key"] == "[redacted]"
    assert run.trigger_data["headers"]["x-custom"] == "safe"
    assert run.trigger_data["headers"]["x_custom"] == "safe"


async def test_v2_webhook_invalid_id_returns_404(client):
    response = await client.post("/api/v1/webhooks/missing", json={"ok": True})

    assert response.status_code == 404


async def test_v2_webhook_inactive_workflow_returns_409(client):
    workflow = await create_webhook_workflow(is_active=False)

    response = await client.post(f"/api/v1/webhooks/{workflow.webhook_id}", json={"ok": True})

    assert response.status_code == 409
    assert response.json()["detail"] == "Workflow is inactive"


async def test_v2_webhook_trigger_data_visible_in_timeline(client, auth_headers):
    workflow = await create_webhook_workflow()

    response = await client.post(
        f"/api/v1/webhooks/{workflow.webhook_id}",
        json={"event": "created"},
    )
    run_id = response.json()["run_id"]

    timeline = await client.get(f"/api/v1/runs/{run_id}/timeline", headers=auth_headers)

    assert timeline.status_code == 200
    assert timeline.json()["run"]["trigger_data"]["body"] == {"event": "created"}


async def test_v2_webhook_payload_renders_in_llm_prompt(client, monkeypatch):
    mock_llm = MockLLMProvider()
    mock_llm.set_response("ok")
    LLMRegistry.clear()
    LLMRegistry.register(mock_llm)

    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Webhook LLM workflow",
            steps=[
                {
                    "id": "summarize",
                    "type": "llm",
                    "provider": "mock",
                    "model": "mock-model",
                    "prompt": "{{ trigger_data.body.message }}",
                }
            ],
            trigger_type="webhook",
            trigger_config={},
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)
        webhook_id = workflow.webhook_id

    response = await client.post(
        f"/api/v1/webhooks/{webhook_id}",
        json={"message": "hello from webhook"},
    )
    assert response.status_code == 202
    run_id = response.json()["run_id"]

    async with TestingSessionLocal() as db:
        await execute_run(run_id, db)
        step_execution = (
            await db.execute(
                StepExecution.__table__.select().where(StepExecution.run_id == run_id)
            )
        ).mappings().one()

    assert mock_llm.last_request is not None
    assert mock_llm.last_request.messages[-1].content == "hello from webhook"
    assert step_execution["input_preview"]["prompt"] == "hello from webhook"


async def test_v2_webhook_trigger_data_renders_in_tool_params(client, monkeypatch):
    captured = {}

    async def fake_execute(tool_name, action, params, credentials):
        captured["params"] = params
        from app.tools.base import ToolResult

        return ToolResult(success=True, data={"ok": True})

    monkeypatch.setattr("app.tools.registry.ToolRegistry.execute", fake_execute)

    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Webhook tool workflow",
            steps=[
                {
                    "id": "notify",
                    "type": "tool",
                    "tool": "http_request",
                    "action": "execute",
                    "params": {
                        "url": "https://example.test",
                        "json": {
                            "message": "{{ trigger_data.body.message }}",
                            "event": "{{ trigger_data.headers.x_github_event }}",
                            "customer": "{{ trigger_data.query_params.customer_id }}",
                        },
                    },
                }
            ],
            trigger_type="webhook",
            trigger_config={},
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)
        webhook_id = workflow.webhook_id

    response = await client.post(
        f"/api/v1/webhooks/{webhook_id}?customer_id=cus_123",
        json={"message": "hello from webhook"},
        headers={"X-GitHub-Event": "issues"},
    )
    run_id = response.json()["run_id"]

    async with TestingSessionLocal() as db:
        await execute_run(run_id, db)

    assert captured["params"]["json"] == {
        "message": "hello from webhook",
        "event": "issues",
        "customer": "cus_123",
    }


async def test_v2_webhook_trigger_data_renders_in_approval_message(client, monkeypatch):
    monkeypatch.setattr(approval_step, "_send_approval_email", lambda approval, step, context: None)

    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Webhook approval workflow",
            steps=[
                {
                    "id": "approval_step",
                    "type": "approval",
                    "approver_email": "approver@example.com",
                    "message": "Approve {{ trigger_data.body.message }}",
                    "subject": "Customer {{ trigger_data.query_params.customer_id }}",
                }
            ],
            trigger_type="webhook",
            trigger_config={},
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)
        webhook_id = workflow.webhook_id

    response = await client.post(
        f"/api/v1/webhooks/{webhook_id}?customer_id=cus_123",
        json={"message": "hello from webhook"},
    )
    run_id = response.json()["run_id"]

    async with TestingSessionLocal() as db:
        await execute_run(run_id, db)
        step_execution = (
            await db.execute(
                StepExecution.__table__.select().where(StepExecution.run_id == run_id)
            )
        ).mappings().one()

    assert step_execution["input_preview"]["message"] == "Approve hello from webhook"
    assert step_execution["input_preview"]["subject"] == "Customer cus_123"


async def test_workflow_create_accepts_trigger_alias(client, auth_headers, sample_workflow):
    payload = {
        **sample_workflow,
        "trigger": {"type": "webhook", "secret": "abc123"},
    }
    payload.pop("trigger_type")

    response = await client.post("/api/v1/workflows/", json=payload, headers=auth_headers)

    assert response.status_code == 201
    data = response.json()
    assert data["trigger_type"] == "webhook"
    assert data["trigger_config"]["secret"] == "abc123"
    assert data["webhook_id"]
