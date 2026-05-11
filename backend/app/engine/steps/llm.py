from typing import Any

from jinja2 import Template
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.memory import build_messages, save_turn


def render_template(template_str: str, context: dict[str, Any]) -> str:
    return Template(template_str).render(**context)


async def run_llm_step(
    step: dict[str, Any],
    context: dict[str, Any],
    run_id: str,
    db: AsyncSession,
) -> str:
    prompt = render_template(step.get("prompt", ""), context)
    session_id = step.get("session_id") or run_id
    system_prompt = render_template(step.get("system_prompt", ""), context)
    messages = await build_messages(db, session_id, prompt, system_prompt=system_prompt)

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=step.get("model", "gpt-4o-mini"),
        messages=messages,
    )
    reply = response.choices[0].message.content or ""

    await save_turn(db, session_id, "user", prompt, run_id=run_id)
    await save_turn(db, session_id, "assistant", reply, run_id=run_id)
    return reply
