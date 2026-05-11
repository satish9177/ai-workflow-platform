import pytest
from sqlalchemy import select

from app.config import settings
from app.engine.executor import execute_run
from app.llm.registry import LLMRegistry
from app.llm.providers.mock import MockLLMProvider
from app.models.memory import ConversationTurn
from app.models.run import Run
from app.models.workflow import Workflow
from conftest import TestingSessionLocal


@pytest.fixture
def mock_llm(monkeypatch):
    provider = MockLLMProvider()
    LLMRegistry.clear()
    LLMRegistry.register(provider)
    monkeypatch.setattr(settings, "default_llm_provider", "mock")
    monkeypatch.setattr(settings, "default_llm_model", "mock-model")
    yield provider
    LLMRegistry.clear()


async def _execute_llm_workflow(
    step: dict,
    mock_llm: MockLLMProvider,
    trigger_data: dict | None = None,
) -> Run:
    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="LLM workflow",
            steps=[step],
            trigger_type="manual",
            trigger_config={},
        )
        db.add(workflow)
        await db.commit()
        await db.refresh(workflow)

        run = Run(workflow_id=workflow.id, status="pending", trigger_data=trigger_data or {})
        db.add(run)
        await db.commit()
        await db.refresh(run)

        await execute_run(run.id, db)
        await db.refresh(run)
        return run


@pytest.mark.asyncio
async def test_llm_step_with_mock_provider_completes(mock_llm):
    mock_llm.set_response("Hello from mock")

    run = await _execute_llm_workflow(
        {"id": "draft", "type": "llm", "provider": "mock", "model": "mock-model", "prompt": "Say hi"},
        mock_llm,
    )

    assert run.status == "completed"
    assert run.context["draft"]["response"] == "Hello from mock"
    assert run.context["draft"]["provider"] == "mock"


@pytest.mark.asyncio
async def test_llm_step_defaults_provider_and_model(mock_llm):
    await _execute_llm_workflow(
        {"id": "default_llm", "type": "llm", "prompt": "Use defaults"},
        mock_llm,
    )

    assert mock_llm.last_request is not None
    assert mock_llm.last_request.model == "mock-model"


@pytest.mark.asyncio
async def test_llm_step_stores_output_by_step_id(mock_llm):
    mock_llm.set_response("Stored response")

    run = await _execute_llm_workflow(
        {"id": "summarize", "type": "llm", "provider": "mock", "prompt": "Summarize"},
        mock_llm,
    )

    assert run.context["summarize"]["response"] == "Stored response"


@pytest.mark.asyncio
async def test_llm_step_stores_output_as_alias(mock_llm):
    mock_llm.set_response("Alias response")

    run = await _execute_llm_workflow(
        {
            "id": "summarize",
            "type": "llm",
            "provider": "mock",
            "prompt": "Summarize",
            "output_as": "summary",
        },
        mock_llm,
    )

    assert run.context["summary"] == run.context["summarize"]


@pytest.mark.asyncio
async def test_llm_step_renders_jinja_context(mock_llm):
    await _execute_llm_workflow(
        {
            "id": "personalize",
            "type": "llm",
            "provider": "mock",
            "prompt": "Hello {{ trigger_data.name }}",
            "system": "Be concise for {{ trigger_data.name }}",
        },
        mock_llm,
        trigger_data={"name": "Ada"},
    )

    assert mock_llm.last_request is not None
    assert mock_llm.last_request.messages[0].content == "Be concise for Ada"
    assert mock_llm.last_request.messages[-1].content == "Hello Ada"


@pytest.mark.asyncio
async def test_invalid_temperature_validation_fails(client, auth_headers):
    response = await client.post(
        "/api/v1/workflows/",
        headers=auth_headers,
        json={
            "name": "Invalid temperature",
            "steps": [{"id": "ask", "type": "llm", "prompt": "Hi", "temperature": 3}],
            "trigger_type": "manual",
        },
    )

    assert response.status_code == 422
    assert "temperature must be between 0 and 2" in response.text


@pytest.mark.asyncio
async def test_invalid_provider_validation_fails(client, auth_headers):
    response = await client.post(
        "/api/v1/workflows/",
        headers=auth_headers,
        json={
            "name": "Invalid provider",
            "steps": [{"id": "ask", "type": "llm", "prompt": "Hi", "provider": "nope"}],
            "trigger_type": "manual",
        },
    )

    assert response.status_code == 422
    assert "provider must be one of" in response.text


@pytest.mark.asyncio
async def test_template_rendering_failure_fails_clearly(mock_llm):
    run = await _execute_llm_workflow(
        {"id": "broken", "type": "llm", "provider": "mock", "prompt": "Hello {{ name"},
        mock_llm,
    )

    assert run.status == "failed"
    assert run.error == "Failed to render LLM template"


@pytest.mark.asyncio
async def test_llm_step_saves_conversation_memory(mock_llm):
    mock_llm.set_response("Remembered")

    run = await _execute_llm_workflow(
        {"id": "remember", "type": "llm", "provider": "mock", "prompt": "Remember this"},
        mock_llm,
    )

    async with TestingSessionLocal() as db:
        result = await db.execute(
            select(ConversationTurn)
            .where(ConversationTurn.run_id == run.id)
            .order_by(ConversationTurn.created_at.asc())
        )
        turns = result.scalars().all()

    assert [(turn.role, turn.content) for turn in turns] == [
        ("user", "Remember this"),
        ("assistant", "Remembered"),
    ]
