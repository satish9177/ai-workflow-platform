import pytest
from sqlalchemy import select

from app.engine import executor
from app.models.run import Run
from app.models.step_execution import StepExecution
from app.models.workflow import Workflow
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry
from app.utils.preview import sanitize_preview_payload
from conftest import TestingSessionLocal


def test_sanitize_preview_payload_truncates_strings():
    value = sanitize_preview_payload({"text": "a" * 2100})

    assert value["text"].endswith("...[truncated]")
    assert len(value["text"]) < 2050


def test_sanitize_preview_payload_redacts_secrets():
    value = sanitize_preview_payload(
        {
            "authorization": "Bearer secret",
            "webhook_url": "https://hooks.slack.com/services/T000/B000/secret",
            "nested": {"api_key": "secret-key"},
        }
    )

    assert value["authorization"] == "[redacted]"
    assert value["webhook_url"] == "[redacted]"
    assert value["nested"]["api_key"] == "[redacted]"


def test_sanitize_preview_payload_keeps_usage_token_metrics():
    value = sanitize_preview_payload(
        {
            "usage": {
                "total_tokens": 100,
                "prompt_tokens": 40,
                "completion_tokens": 60,
                "max_tokens": 1000,
                "token_count": 100,
            }
        }
    )

    assert value["usage"]["total_tokens"] == 100
    assert value["usage"]["prompt_tokens"] == 40
    assert value["usage"]["completion_tokens"] == 60
    assert value["usage"]["max_tokens"] == 1000
    assert value["usage"]["token_count"] == 100


def test_sanitize_preview_payload_still_redacts_auth_tokens_and_webhook_urls():
    value = sanitize_preview_payload(
        {
            "token": "secret-token",
            "access_token": "secret-access-token",
            "refresh_token": "secret-refresh-token",
            "bearer_token": "secret-bearer-token",
            "callback": "https://discord.com/api/webhooks/123/secret",
        }
    )

    assert value["token"] == "[redacted]"
    assert value["access_token"] == "[redacted]"
    assert value["refresh_token"] == "[redacted]"
    assert value["bearer_token"] == "[redacted]"
    assert value["callback"] == "[redacted-url]"


@pytest.mark.asyncio
async def test_tool_step_preview_persistence_and_timeline_response(client, auth_headers, monkeypatch):
    async def fake_execute(tool_name, action, params, credentials):
        return ToolResult(success=True, data={"ok": True, "echo": params})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)

    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Preview workflow",
            steps=[
                {
                    "id": "notify",
                    "type": "tool",
                    "tool": "http_request",
                    "action": "execute",
                    "params": {
                        "url": "https://example.test",
                        "headers": {"Authorization": "Bearer secret"},
                        "json": {"message": "{{ trigger_data.message }}"},
                    },
                }
            ],
            trigger_type="manual",
            trigger_config={},
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        run = Run(workflow_id=workflow.id, status="pending", trigger_data={"message": "hello"})
        db.add(run)
        await db.commit()
        await db.refresh(run)

        await executor.execute_run(run.id, db)
        await db.refresh(run)
        run_id = run.id

        step_execution = (
            await db.execute(select(StepExecution).where(StepExecution.run_id == run_id))
        ).scalar_one()

    assert step_execution.input_preview["params"]["json"]["message"] == "hello"
    assert step_execution.input_preview["params"]["headers"]["Authorization"] == "[redacted]"
    assert step_execution.output_preview["response"]["data"]["ok"] is True

    response = await client.get(f"/api/v1/runs/{run_id}/timeline", headers=auth_headers)

    assert response.status_code == 200
    step = response.json()["steps"][0]
    assert step["input_preview"]["params"]["json"]["message"] == "hello"
    assert step["output_preview"]["response"]["data"]["ok"] is True


@pytest.mark.asyncio
async def test_llm_step_previews_prompt_and_response(monkeypatch):
    async def fake_run_llm_step(step, context, run_id, db):
        return {"response": f"Summary: {context['trigger_data']['message']}", "provider": "mock", "model": "mock-model", "usage": {}}

    monkeypatch.setattr(executor, "run_llm_step", fake_run_llm_step)

    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="LLM preview workflow",
            steps=[
                {
                    "id": "summarize",
                    "type": "llm",
                    "provider": "mock",
                    "model": "mock-model",
                    "prompt": "Summarize {{ trigger_data.message }}",
                }
            ],
            trigger_type="manual",
            trigger_config={},
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        run = Run(workflow_id=workflow.id, status="pending", trigger_data={"message": "payroll issue"})
        db.add(run)
        await db.commit()
        await db.refresh(run)

        await executor.execute_run(run.id, db)

        step_execution = (
            await db.execute(select(StepExecution).where(StepExecution.run_id == run.id))
        ).scalar_one()

    assert step_execution.input_preview["prompt"] == "Summarize payroll issue"
    assert step_execution.input_preview["provider"] == "mock"
    assert step_execution.output_preview["response"] == "Summary: payroll issue"
