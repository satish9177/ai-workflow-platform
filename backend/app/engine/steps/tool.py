import base64
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.integration import Integration
from app.tools.registry import ToolRegistry
from app.utils.template_renderer import render_template_object


TOOL_INTEGRATION_TYPES = {
    "email": {"smtp"},
}


def _integration_matches_tool(tool_name: str, integration_type: str) -> bool:
    provider_types = TOOL_INTEGRATION_TYPES.get(tool_name)
    if provider_types is not None:
        return integration_type in provider_types
    return integration_type == tool_name


async def get_credentials(db: AsyncSession, tool_name: str, integration_id: str | None = None) -> dict[str, Any]:
    if integration_id:
        integration = await db.get(Integration, integration_id)
        if integration is None or not integration.is_enabled:
            raise RuntimeError(f"Integration not found: {integration_id}")
        if not _integration_matches_tool(tool_name, integration.integration_type):
            raise RuntimeError(f"Integration not found: {integration_id}")
    else:
        integration = None
        provider_types = TOOL_INTEGRATION_TYPES.get(tool_name)
        if provider_types is not None:
            result = await db.execute(
                select(Integration)
                .where(Integration.integration_type.in_(provider_types), Integration.is_enabled.is_(True))
                .order_by(Integration.created_at.asc())
            )
            integration = result.scalars().first()
            if integration is None:
                raise RuntimeError(f"No integration configured for tool: {tool_name}")
        else:
            result = await db.execute(
                select(Integration)
                .where(Integration.integration_type == tool_name, Integration.is_enabled.is_(True))
                .order_by(Integration.created_at.asc())
            )
            integration = result.scalars().first()
            if integration is None:
                result = await db.execute(
                    select(Integration)
                    .where(Integration.name == tool_name, Integration.is_enabled.is_(True))
                    .order_by(Integration.created_at.asc())
                )
                integration = result.scalars().first()
        if integration is None:
            if tool_name == "http_request":
                return {}
            raise RuntimeError(f"No integration configured for tool: {tool_name}")

    if not integration.credentials:
        if tool_name in TOOL_INTEGRATION_TYPES:
            return {"_integration_type": integration.integration_type}
        return {}

    key = base64.urlsafe_b64encode(bytes.fromhex(settings.encryption_key))
    fernet = Fernet(key)
    decrypted: dict[str, Any] = {}
    for name, value in integration.credentials.items():
        if isinstance(value, str):
            decrypted[name] = fernet.decrypt(value.encode()).decode()
        else:
            decrypted[name] = value
    if tool_name in TOOL_INTEGRATION_TYPES:
        decrypted["_integration_type"] = integration.integration_type
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
    credentials = await get_credentials(db, tool_name, step.get("integration_id"))

    result = await ToolRegistry.execute(tool_name, action, params, credentials)
    if not result.success:
        raise RuntimeError(result.error or f"Tool failed: {tool_name}")

    return {
        "data": result.data,
        "metadata": result.metadata,
    }
