import pytest
from sqlalchemy import select

from app.engine import executor
from app.llm.errors import AuthenticationError, RateLimitError
from app.llm.provider_errors import is_retryable_provider_error, normalize_provider_error
from app.llm.providers.gemini import _map_gemini_error
from app.models.run import Run
from app.models.step_execution import StepExecution
from app.models.workflow import Workflow
from conftest import TestingSessionLocal


class GeminiRateLimitException(Exception):
    def code(self):
        return 429


async def _execute_llm_workflow(monkeypatch, fake_run_llm_step):
    monkeypatch.setattr(executor, "run_llm_step", fake_run_llm_step)

    async with TestingSessionLocal() as db:
        workflow = Workflow(
            name="Provider error workflow",
            steps=[
                {
                    "id": "generate",
                    "type": "llm",
                    "provider": "gemini",
                    "model": "gemini-2.5-flash",
                    "prompt": "Generate",
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

        step_execution = (
            await db.execute(select(StepExecution).where(StepExecution.run_id == run.id))
        ).scalar_one()
        return run, step_execution


def test_gemini_rate_limit_style_error_is_retryable():
    mapped = _map_gemini_error(GeminiRateLimitException("quota exceeded"))
    normalized = normalize_provider_error(mapped, provider="gemini", model="gemini-2.5-flash")

    assert normalized is not None
    assert normalized.error_type == "ProviderRateLimitError"
    assert normalized.provider == "gemini"
    assert normalized.model == "gemini-2.5-flash"
    assert normalized.retryable is True
    assert normalized.status_code == 429
    assert is_retryable_provider_error(normalized) is True


def test_invalid_api_key_error_is_non_retryable():
    normalized = normalize_provider_error(
        AuthenticationError("Invalid API key", provider="gemini", status_code=401),
        provider="gemini",
        model="gemini-2.5-flash",
    )

    assert normalized is not None
    assert normalized.error_type == "ProviderAuthenticationError"
    assert normalized.retryable is False
    assert normalized.status_code == 401
    assert is_retryable_provider_error(normalized) is False


@pytest.mark.asyncio
async def test_retry_wrapper_retries_retryable_provider_errors(monkeypatch):
    calls = {"count": 0}

    async def fake_run_llm_step(step, context, run_id, db):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RateLimitError("Rate limit exceeded", provider="gemini", retryable=True, status_code=429)
        return {"response": "ok", "provider": "gemini", "model": "gemini-2.5-flash", "usage": {}}

    run, step_execution = await _execute_llm_workflow(monkeypatch, fake_run_llm_step)

    assert run.status == "completed"
    assert step_execution.status == "completed"
    assert step_execution.attempt_number == 2
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_retry_wrapper_does_not_retry_non_retryable_provider_errors(monkeypatch):
    calls = {"count": 0}

    async def fake_run_llm_step(step, context, run_id, db):
        calls["count"] += 1
        raise AuthenticationError("Invalid API key", provider="gemini", status_code=401)

    run, step_execution = await _execute_llm_workflow(monkeypatch, fake_run_llm_step)

    assert run.status == "failed"
    assert step_execution.status == "failed"
    assert step_execution.attempt_number == 1
    assert step_execution.error_details["type"] == "ProviderAuthenticationError"
    assert step_execution.error_details["retryable"] is False
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_timeline_error_details_include_structured_provider_error(monkeypatch):
    calls = {"count": 0}

    async def fake_run_llm_step(step, context, run_id, db):
        calls["count"] += 1
        raise RateLimitError("Rate limit exceeded", provider="gemini", retryable=True, status_code=429)

    run, step_execution = await _execute_llm_workflow(monkeypatch, fake_run_llm_step)

    assert run.status == "failed"
    assert calls["count"] == 3
    assert step_execution.status == "failed"
    assert step_execution.attempt_number == 3
    assert step_execution.error_details == {
        "type": "ProviderRateLimitError",
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "message": "Rate limit exceeded",
        "retryable": True,
        "status_code": 429,
    }
