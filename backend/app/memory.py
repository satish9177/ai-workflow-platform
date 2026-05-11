from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import ConversationTurn


async def save_turn(
    db: AsyncSession,
    session_id: str,
    role: str,
    content: str,
    run_id: str | None = None,
) -> ConversationTurn:
    turn = ConversationTurn(
        session_id=session_id,
        run_id=run_id,
        role=role,
        content=content,
    )
    db.add(turn)
    await db.commit()
    await db.refresh(turn)
    return turn


async def get_history(db: AsyncSession, session_id: str, limit: int = 20) -> list[dict[str, str]]:
    result = await db.execute(
        select(ConversationTurn)
        .where(ConversationTurn.session_id == session_id)
        .order_by(ConversationTurn.created_at.desc())
        .limit(limit)
    )
    turns = reversed(result.scalars().all())
    return [{"role": turn.role, "content": turn.content} for turn in turns]


async def build_messages(
    db: AsyncSession,
    session_id: str,
    new_content: str,
    system_prompt: str = "",
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    messages.extend(await get_history(db, session_id))
    messages.append({"role": "user", "content": new_content})
    return messages
