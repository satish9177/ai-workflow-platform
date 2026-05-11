import base64
from typing import Any

from cryptography.fernet import Fernet
from jinja2 import Template
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.integration import Integration
from app.tools.registry import ToolRegistry


async def get_credentials(db: AsyncSession, tool_name: str) -> dict[str, Any]:
    result = await db.execute(
        select(Integration).where(Integration.name == tool_name, Integration.is_enabled.is_(True))
    )
    integration = result.scalar_one_or_none()
    if integration is None or not integration.credentials:
        return {}

    key = base64.urlsafe_b64encode(bytes.fromhex(settings.encryption_key))
    fernet = Fernet(key)
    decrypted: dict[str, Any] = {}
    for name, value in integration.credentials.items():
        if isinstance(value, str):
            decrypted[name] = fernet.decrypt(value.encode()).decode()
        else:
            decrypted[name] = value
    return decrypted


def render_params(params: Any, context: dict[str, Any]) -> Any:
    if isinstance(params, str):
        return Template(params).render(**context)
    if isinstance(params, dict):
        return {key: render_params(value, context) for key, value in params.items()}
    if isinstance(params, list):
        return [render_params(item, context) for item in params]
    return params


async def run_tool_step(step: dict[str, Any], context: dict[str, Any], db: AsyncSession) -> dict[str, Any]:
    tool_name = step.get("tool_name") or step.get("tool") or step.get("type")
    action = step.get("action", "execute")
    raw_params = step.get("params") or step.get("config") or {}
    params = render_params(raw_params, context)
    credentials = await get_credentials(db, tool_name)

    result = await ToolRegistry.execute(tool_name, action, params, credentials)
    if not result.success:
        raise RuntimeError(result.error or f"Tool failed: {tool_name}")

    return {
        "data": result.data,
        "metadata": result.metadata,
    }
