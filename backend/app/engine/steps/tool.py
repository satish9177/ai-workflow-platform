import base64
import os
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.config import settings
from app.models.integration import Integration
from app.tools.registry import ToolRegistry
from app.utils.template_renderer import render_template_object


logger = structlog.get_logger(__name__)

TOOL_INTEGRATION_TYPES = {
    "email": {"smtp"},
}


def expected_integration_types(tool_name: str) -> set[str]:
    return TOOL_INTEGRATION_TYPES.get(tool_name) or {tool_name}


def _integration_matches_tool(tool_name: str, integration_type: str) -> bool:
    return integration_type in expected_integration_types(tool_name)


def _safe_database_name() -> str:
    try:
        return make_url(settings.database_url).database or ""
    except Exception:
        return "unknown"


def _resolution_context(
    *,
    run_id: str | None,
    step_key: str | None,
    tool_name: str,
    action: str | None,
    integration_id: str | None,
    filters: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "step_key": step_key,
        "tool": tool_name,
        "action": action,
        "integration_id": integration_id,
        "expected_integration_types": sorted(expected_integration_types(tool_name)),
        "db_query_filters": filters,
        "database": _safe_database_name(),
        "worker_pid": os.getpid(),
    }


def _integration_log_fields(integration: Integration | None) -> dict[str, Any]:
    return {
        "db_row_found": integration is not None,
        "found_integration_type": integration.integration_type if integration is not None else None,
        "found_status": integration.status if integration is not None else None,
        "found_is_enabled": integration.is_enabled if integration is not None else None,
    }


async def get_credentials(
    db: AsyncSession,
    tool_name: str,
    integration_id: str | None = None,
    *,
    run_id: str | None = None,
    step_key: str | None = None,
    action: str | None = None,
) -> dict[str, Any]:
    integration_id = integration_id.strip() if isinstance(integration_id, str) else integration_id
    if integration_id:
        filters = {"id": integration_id}
        logger.info(
            "integration.resolve.started",
            **_resolution_context(
                run_id=run_id,
                step_key=step_key,
                tool_name=tool_name,
                action=action,
                integration_id=integration_id,
                filters=filters,
            ),
        )
        result = await db.execute(select(Integration).where(Integration.id == integration_id))
        integration = result.scalar_one_or_none()
        logger.info(
            "integration.resolve.row_loaded",
            **_resolution_context(
                run_id=run_id,
                step_key=step_key,
                tool_name=tool_name,
                action=action,
                integration_id=integration_id,
                filters=filters,
            ),
            **_integration_log_fields(integration),
        )
        if integration is None or not integration.is_enabled:
            logger.warning(
                "integration.resolve.not_found_or_disabled",
                **_resolution_context(
                    run_id=run_id,
                    step_key=step_key,
                    tool_name=tool_name,
                    action=action,
                    integration_id=integration_id,
                    filters=filters,
                ),
                **_integration_log_fields(integration),
            )
            raise RuntimeError(f"Integration not found: {integration_id}")
        if not _integration_matches_tool(tool_name, integration.integration_type):
            expected = ", ".join(sorted(expected_integration_types(tool_name)))
            logger.warning(
                "integration.resolve.type_mismatch",
                **_resolution_context(
                    run_id=run_id,
                    step_key=step_key,
                    tool_name=tool_name,
                    action=action,
                    integration_id=integration_id,
                    filters=filters,
                ),
                **_integration_log_fields(integration),
            )
            raise RuntimeError(
                f"Integration {integration_id} has integration_type '{integration.integration_type}', "
                f"expected one of: {expected}"
            )
    else:
        integration = None
        provider_types = TOOL_INTEGRATION_TYPES.get(tool_name)
        if provider_types is not None:
            filters = {"integration_type": sorted(provider_types), "is_enabled": True}
            logger.info(
                "integration.resolve.started",
                **_resolution_context(
                    run_id=run_id,
                    step_key=step_key,
                    tool_name=tool_name,
                    action=action,
                    integration_id=None,
                    filters=filters,
                ),
            )
            result = await db.execute(
                select(Integration)
                .where(Integration.integration_type.in_(provider_types), Integration.is_enabled.is_(True))
                .order_by(Integration.created_at.asc())
            )
            integration = result.scalars().first()
            logger.info(
                "integration.resolve.row_loaded",
                **_resolution_context(
                    run_id=run_id,
                    step_key=step_key,
                    tool_name=tool_name,
                    action=action,
                    integration_id=None,
                    filters=filters,
                ),
                **_integration_log_fields(integration),
            )
            if integration is None:
                logger.warning(
                    "integration.resolve.no_fallback",
                    **_resolution_context(
                        run_id=run_id,
                        step_key=step_key,
                        tool_name=tool_name,
                        action=action,
                        integration_id=None,
                        filters=filters,
                    ),
                )
                raise RuntimeError(f"No integration configured for tool: {tool_name}")
        else:
            filters = {"integration_type": tool_name, "is_enabled": True}
            logger.info(
                "integration.resolve.started",
                **_resolution_context(
                    run_id=run_id,
                    step_key=step_key,
                    tool_name=tool_name,
                    action=action,
                    integration_id=None,
                    filters=filters,
                ),
            )
            result = await db.execute(
                select(Integration)
                .where(Integration.integration_type == tool_name, Integration.is_enabled.is_(True))
                .order_by(Integration.created_at.asc())
            )
            integration = result.scalars().first()
            if integration is None:
                filters = {"name": tool_name, "is_enabled": True}
                result = await db.execute(
                    select(Integration)
                    .where(Integration.name == tool_name, Integration.is_enabled.is_(True))
                    .order_by(Integration.created_at.asc())
                )
                integration = result.scalars().first()
            logger.info(
                "integration.resolve.row_loaded",
                **_resolution_context(
                    run_id=run_id,
                    step_key=step_key,
                    tool_name=tool_name,
                    action=action,
                    integration_id=None,
                    filters=filters,
                ),
                **_integration_log_fields(integration),
            )
        if integration is None:
            if tool_name == "http_request":
                return {}
            logger.warning(
                "integration.resolve.no_fallback",
                **_resolution_context(
                    run_id=run_id,
                    step_key=step_key,
                    tool_name=tool_name,
                    action=action,
                    integration_id=None,
                    filters=filters,
                ),
            )
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
    logger.info(
        "integration.resolve.completed",
        **_resolution_context(
            run_id=run_id,
            step_key=step_key,
            tool_name=tool_name,
            action=action,
            integration_id=integration_id,
            filters={"id": integration.id},
        ),
        **_integration_log_fields(integration),
    )
    return decrypted


def render_params(params: Any, context: dict[str, Any]) -> Any:
    return render_template_object(params, context)


def _prepare_tool_params(tool_name: str, params: Any) -> Any:
    if tool_name == "http_request" and isinstance(params, dict) and "json" in params and "body" not in params:
        return {**params, "body": params["json"]}
    return params


async def run_tool_step(
    step: dict[str, Any],
    context: dict[str, Any],
    db: AsyncSession,
    run_id: str | None = None,
) -> dict[str, Any]:
    tool_name = step.get("tool_name") or step.get("tool") or step.get("type")
    action = step.get("action", "execute")
    step_key = step.get("id") or step.get("step_key")
    raw_params = step.get("params") or step.get("config") or {}
    rendered_params = render_params(raw_params, context)
    params = _prepare_tool_params(tool_name, rendered_params)
    credentials = await get_credentials(
        db,
        tool_name,
        step.get("integration_id"),
        run_id=run_id,
        step_key=str(step_key) if step_key is not None else None,
        action=str(action),
    )

    result = await ToolRegistry.execute(tool_name, action, params, credentials)
    if not result.success:
        raise RuntimeError(result.error or f"Tool failed: {tool_name}")

    return {
        "data": result.data,
        "metadata": result.metadata,
    }
