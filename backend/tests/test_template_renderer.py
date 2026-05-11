import pytest

from app.config import settings
from app.engine.executor import execute_run
from app.engine.steps.condition import run_condition_step
from app.engine.steps.tool import run_tool_step
from app.llm.registry import LLMRegistry
from app.llm.providers.mock import MockLLMProvider
from app.models.run import Run
from app.models.workflow import Workflow
from app.tools.base import ToolResult
from app.tools.registry import ToolRegistry
from app.utils.template_renderer import render_template_object
from conftest import TestingSessionLocal


def test_render_template_object_simple_string():
    result = render_template_object(
        {"message": "{{ trigger_data.message }}"},
        {"trigger_data": {"message": "hello"}},
    )

    assert result == {"message": "hello"}


def test_render_template_object_nested_dict_does_not_mutate_original():
    original = {"json": {"summary": "{{ summary_result.response }}"}}

    result = render_template_object(
        original,
        {"summary_result": {"response": "Engineering escalation is required."}},
    )

    assert result == {"json": {"summary": "Engineering escalation is required."}}
    assert original == {"json": {"summary": "{{ summary_result.response }}"}}


def test_render_template_object_nested_list():
    result = render_template_object(
        ["{{ a }}", {"x": "{{ b }}"}],
        {"a": "one", "b": "two"},
    )

    assert result == ["one", {"x": "two"}]


def test_render_template_object_missing_variable_is_empty_string():
    result = render_template_object(
        {"missing": "{{ missing.value }}"},
        {},
    )

    assert result == {"missing": ""}


@pytest.mark.asyncio
async def test_tool_params_render_nested_values(monkeypatch):
    captured: dict = {}

    async def fake_execute(tool_name, action, params, credentials):
        captured["params"] = params
        return ToolResult(success=True, data={"ok": True})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)

    async with TestingSessionLocal() as db:
        output = await run_tool_step(
            {
                "id": "send",
                "type": "tool",
                "tool": "http_request",
                "action": "execute",
                "params": {
                    "url": "https://example.test",
                    "json": {"summary": "{{ summary_result.response }}"},
                },
            },
            {"summary_result": {"response": "Rendered summary"}},
            db,
        )

    assert output["data"] == {"ok": True}
    assert captured["params"]["json"]["summary"] == "Rendered summary"


@pytest.mark.asyncio
async def test_http_request_receives_rendered_nested_json_body(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        is_success = True
        status_code = 200
        headers = {"content-type": "application/json"}
        text = '{"ok": true}'

        def json(self):
            return {"ok": True}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def request(self, *args, **kwargs):
            captured["json"] = kwargs.get("json")
            return FakeResponse()

    monkeypatch.setattr("app.tools.http_request.httpx.AsyncClient", FakeAsyncClient)

    async with TestingSessionLocal() as db:
        await run_tool_step(
            {
                "id": "notify",
                "type": "tool",
                "tool": "http_request",
                "action": "execute",
                "params": {
                    "url": "https://example.test/post",
                    "method": "POST",
                    "json": {
                        "summary": "{{ summary_result.response }}",
                    },
                },
            },
            {
                "summary_result": {
                    "response": "Customer payroll access issue requires engineering escalation.",
                },
            },
            db,
        )

    assert captured["json"] == {
        "summary": "Customer payroll access issue requires engineering escalation.",
    }


@pytest.mark.asyncio
async def test_condition_expression_can_be_rendered_from_context():
    result = await run_condition_step(
        {"id": "branch", "type": "condition", "condition": "{{ condition_expr }}"},
        {"condition_expr": "count > 1", "count": 2},
    )

    assert result["result"] is True


@pytest.mark.asyncio
async def test_workflow_end_to_end_recursive_tool_param_rendering(monkeypatch):
    mock_llm = MockLLMProvider()
    mock_llm.set_response("Engineering escalation is required.")
    LLMRegistry.clear()
    LLMRegistry.register(mock_llm)
    monkeypatch.setattr(settings, "default_llm_provider", "mock")
    monkeypatch.setattr(settings, "default_llm_model", "mock-model")
    captured: dict = {}

    async def fake_execute(tool_name, action, params, credentials):
        captured["params"] = params
        return ToolResult(success=True, data={"sent": True})

    monkeypatch.setattr(ToolRegistry, "execute", fake_execute)

    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Recursive rendering workflow",
            steps=[
                {
                    "id": "summarize",
                    "type": "llm",
                    "provider": "mock",
                    "prompt": "Summarize {{ trigger_data.message }}",
                    "output_as": "summary_result",
                },
                {
                    "id": "send",
                    "type": "tool",
                    "tool": "http_request",
                    "action": "execute",
                    "params": {
                        "url": "https://example.test",
                        "json": {
                            "summary": "{{ summary_result.response }}",
                        },
                    },
                },
            ],
            trigger_type="manual",
            trigger_config={},
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        run = Run(
            workflow_id=workflow.id,
            status="pending",
            trigger_data={"message": "an incident"},
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)

        await execute_run(run.id, db)
        await db.refresh(run)

    assert run.status == "completed"
    assert captured["params"]["json"]["summary"] == "Engineering escalation is required."
