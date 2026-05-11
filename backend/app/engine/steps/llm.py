from typing import Any
from dataclasses import asdict

from jinja2 import Template, TemplateError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.llm.registry import LLMRegistry
from app.llm.types import LLMMessage, LLMRequest
from app.memory import get_history, save_turn


def render_template(template_str: str, context: dict[str, Any]) -> str:
    try:
        return Template(template_str).render(**context)
    except TemplateError as exc:
        raise ValueError("Failed to render LLM template") from exc


async def run_llm_step(
    step: dict[str, Any],
    context: dict[str, Any],
    run_id: str,
    db: AsyncSession,
) -> dict[str, Any]:
    prompt = render_template(step.get("prompt", ""), context)
    session_id = step.get("session_id") or run_id
    system_template = step.get("system") or step.get("system_prompt") or ""
    system_prompt = render_template(system_template, context) if system_template else ""

    messages: list[LLMMessage] = []
    if system_prompt:
        messages.append(LLMMessage(role="system", content=system_prompt))
    for turn in await get_history(db, session_id):
        role = turn.get("role")
        if role in {"system", "user", "assistant"}:
            messages.append(LLMMessage(role=role, content=turn.get("content", "")))
    messages.append(LLMMessage(role="user", content=prompt))

    provider = step.get("provider") or settings.default_llm_provider
    model = step.get("model") or settings.default_llm_model
    request = LLMRequest(
        messages=messages,
        model=model,
        max_tokens=step.get("max_tokens", 1000),
        temperature=step.get("temperature", 0.3),
    )
    response = await LLMRegistry.complete(provider, request)

    await save_turn(db, session_id, "user", prompt, run_id=run_id)
    await save_turn(db, session_id, "assistant", response.content, run_id=run_id)
    return {
        "response": response.content,
        "provider": response.provider,
        "model": response.model,
        "usage": asdict(response.usage),
    }
