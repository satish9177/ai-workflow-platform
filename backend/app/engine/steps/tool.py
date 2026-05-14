import base64
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.integration import Integration
from app.tools.registry import ToolRegistry
from app.utils.template_renderer import render_template_object


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
    return render_template_object(params, context)


def _prepare_tool_params(tool_name: str, params: Any) -> Any:
    if tool_name == "http_request" and isinstance(params, dict) and "json" in params and "body" not in params:
        return {**params, "body": params["json"]}
    return params


async def run_tool_step(step: dict[str, Any], context: dict[str, Any], db: AsyncSession) -> dict[str, Any]:
    tool_name = step.get("tool_name") or step.get("tool") or step.get("type")
    action = step.get("action", "execute")
    raw_params = step.get("params") or step.get("config") or {}
    rendered_params = render_params(raw_params, context)
    params = _prepare_tool_params(tool_name, rendered_params)
    credentials = await get_credentials(db, tool_name)

    result = await ToolRegistry.execute(tool_name, action, params, credentials)
    if not result.success:
        raise RuntimeError(result.error or f"Tool failed: {tool_name}")

    return {
        "data": result.data,
        "metadata": result.metadata,
    }
