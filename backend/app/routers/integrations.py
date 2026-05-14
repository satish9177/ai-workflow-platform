import base64
import os
from datetime import datetime, timezone
from typing import Any

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.engine import make_url
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.integration import Integration
from app.models.user import User
from app.models.workflow import Workflow
from app.schemas.integration import (
    IntegrationCreate,
    IntegrationRead,
    IntegrationTestResponse,
    IntegrationUpdate,
    IntegrationUpsert,
)
from app.tools.registry import ToolRegistry
from app.tools.integrations.email.smtp import SmtpEmailProvider


router = APIRouter(tags=["integrations"])
logger = structlog.get_logger(__name__)
EXTRA_INTEGRATION_TYPES = {"smtp"}
TOOL_ABSTRACTION_TYPES = {"email"}


def _available_integration_types() -> set[str]:
    return (set(ToolRegistry.all_names()) - TOOL_ABSTRACTION_TYPES) | EXTRA_INTEGRATION_TYPES


def _safe_database_name() -> str:
    try:
        return make_url(settings.database_url).database or ""
    except Exception:
        return "unknown"


def _fernet() -> Fernet:
    if not settings.encryption_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Encryption key is not configured",
        )
    try:
        key = base64.urlsafe_b64encode(bytes.fromhex(settings.encryption_key))
        return Fernet(key)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Encryption key is not configured",
        ) from exc


def _encrypt_credentials(credentials: dict[str, Any]) -> dict[str, Any]:
    fernet = _fernet()
    encrypted: dict[str, Any] = {}
    for key, value in credentials.items():
        encrypted[key] = fernet.encrypt(str(value).encode()).decode()
    return encrypted


def _decrypt_credentials(credentials: dict[str, Any]) -> dict[str, Any]:
    fernet = _fernet()
    decrypted: dict[str, Any] = {}
    for key, value in credentials.items():
        decrypted[key] = fernet.decrypt(value.encode()).decode() if isinstance(value, str) else value
    return decrypted


def _validate_tool(name: str) -> None:
    if name not in _available_integration_types():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")


def _read(integration: Integration | None, integration_type: str | None = None) -> IntegrationRead:
    if integration is None:
        tool_name = integration_type or ""
        return IntegrationRead(
            id=None,
            name=tool_name,
            integration_type=tool_name,
            display_name=tool_name,
            is_enabled=False,
            status="unknown",
            credentials_set=False,
            has_credentials=False,
        )

    credentials_set = bool(integration.credentials)
    return IntegrationRead(
        id=integration.id,
        name=integration.name,
        integration_type=integration.integration_type,
        display_name=integration.display_name,
        is_enabled=integration.is_enabled,
        status=integration.status,
        last_tested_at=integration.last_tested_at,
        last_error=integration.last_error,
        credentials_set=credentials_set,
        has_credentials=credentials_set,
    )


def _step_references_integration(step: Any, integration_id: str) -> bool:
    if isinstance(step, dict):
        if step.get("integration_id") == integration_id:
            return True
        return any(_step_references_integration(value, integration_id) for value in step.values())
    if isinstance(step, list):
        return any(_step_references_integration(value, integration_id) for value in step)
    return False


async def _is_referenced(db: AsyncSession, integration_id: str) -> bool:
    result = await db.execute(select(Workflow.steps))
    return any(_step_references_integration(steps, integration_id) for steps in result.scalars().all())


@router.get("", response_model=list[IntegrationRead])
@router.get("/", response_model=list[IntegrationRead])
async def list_integrations(
    integration_type: str | None = Query(default=None, alias="type"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[IntegrationRead]:
    if integration_type is not None:
        _validate_tool(integration_type)
        result = await db.execute(
            select(Integration)
            .where(Integration.integration_type == integration_type, Integration.is_enabled.is_(True))
            .order_by(Integration.created_at.asc())
        )
        return [_read(integration) for integration in result.scalars().all()]

    result = await db.execute(select(Integration).where(Integration.is_enabled.is_(True)).order_by(Integration.created_at.asc()))
    integrations = result.scalars().all()
    configured_types = {integration.integration_type for integration in integrations}
    available_types = sorted(_available_integration_types())
    placeholders = [
        _read(None, name)
        for name in available_types
        if name not in configured_types
    ]
    return [_read(integration) for integration in integrations] + placeholders


@router.post("", response_model=IntegrationRead, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=IntegrationRead, status_code=status.HTTP_201_CREATED)
async def create_integration(
    payload: IntegrationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IntegrationRead:
    _validate_tool(payload.integration_type)
    integration = Integration(
        name=payload.integration_type,
        integration_type=payload.integration_type,
        display_name=payload.display_name.strip() or payload.integration_type,
        credentials=_encrypt_credentials(payload.credentials) if payload.credentials else {},
        config=payload.config,
        is_enabled=True,
        status="unknown",
    )
    db.add(integration)
    await db.commit()
    await db.refresh(integration)
    return _read(integration)


@router.get("/{integration_id}", response_model=IntegrationRead)
async def get_integration(
    integration_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IntegrationRead:
    integration = await db.get(Integration, integration_id)
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    return _read(integration)


@router.patch("/{integration_id}", response_model=IntegrationRead)
async def update_integration(
    integration_id: str,
    payload: IntegrationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IntegrationRead:
    integration = await db.get(Integration, integration_id)
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")

    if payload.display_name is not None:
        integration.display_name = payload.display_name.strip() or integration.integration_type
    if payload.credentials is not None:
        integration.credentials = _encrypt_credentials(payload.credentials) if payload.credentials else {}
    if payload.config is not None:
        integration.config = payload.config

    await db.commit()
    await db.refresh(integration)
    return _read(integration)


@router.put("/{name}", response_model=IntegrationRead)
async def upsert_integration(
    name: str,
    payload: IntegrationUpsert,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IntegrationRead:
    _validate_tool(name)
    encrypted_credentials = _encrypt_credentials(payload.credentials)

    result = await db.execute(
        select(Integration)
        .where(Integration.integration_type == name, Integration.is_enabled.is_(True))
        .order_by(Integration.created_at.asc())
    )
    integration = result.scalars().first()
    if integration is None:
        integration = Integration(
            name=name,
            integration_type=name,
            display_name=f"{name} (Default)",
            credentials=encrypted_credentials,
            config=payload.config,
            is_enabled=True,
            status="unknown",
        )
        db.add(integration)
    else:
        integration.name = name
        integration.integration_type = name
        integration.credentials = encrypted_credentials
        integration.config = payload.config
        integration.is_enabled = True

    await db.commit()
    await db.refresh(integration)
    return _read(integration)


@router.delete("/{integration_id}")
async def delete_integration(
    integration_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    integration = await db.get(Integration, integration_id)
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    if await _is_referenced(db, integration_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Integration is used by a workflow")

    await db.execute(delete(Integration).where(Integration.id == integration_id))
    await db.commit()
    return {"deleted": True}


@router.post("/{name}/test")
async def test_integration(
    name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IntegrationTestResponse:
    logger.info(
        "integration.test.resolve.started",
        integration_id_or_type=name,
        database=_safe_database_name(),
        worker_pid=os.getpid(),
    )
    integration = await db.get(Integration, name)
    if integration is None:
        if ToolRegistry.get(name) is None and name not in EXTRA_INTEGRATION_TYPES:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
        result = await db.execute(
            select(Integration)
            .where(Integration.integration_type == name, Integration.is_enabled.is_(True))
            .order_by(Integration.created_at.asc())
        )
        integration = result.scalars().first()
        if integration is None:
            logger.warning(
                "integration.test.resolve.not_found",
                integration_id_or_type=name,
                database=_safe_database_name(),
                worker_pid=os.getpid(),
            )
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")

    logger.info(
        "integration.test.resolve.row_loaded",
        integration_id=integration.id,
        integration_type=integration.integration_type,
        status=integration.status,
        is_enabled=integration.is_enabled,
        database=_safe_database_name(),
        worker_pid=os.getpid(),
    )

    if integration.integration_type == "smtp":
        tool = None
    else:
        tool = ToolRegistry.get(integration.integration_type)
    if tool is None:
        if integration.integration_type != "smtp":
            integration.status = "failed"
            integration.last_tested_at = datetime.now(timezone.utc)
            integration.last_error = "Tool not found"
            await db.commit()
            return IntegrationTestResponse(success=False, status="failed", message="Tool not found")

    if not integration.credentials:
        integration.status = "failed"
        integration.last_tested_at = datetime.now(timezone.utc)
        integration.last_error = "Missing credentials"
        await db.commit()
        return IntegrationTestResponse(success=False, status="failed", message="Missing credentials")

    credentials = _decrypt_credentials(integration.credentials or {})
    if integration.integration_type == "smtp":
        smtp_result = await SmtpEmailProvider(credentials).test_connection()
        success = bool(smtp_result.get("success"))
        message = str(smtp_result.get("message") or "Connection successful")
    else:
        try:
            tool_result = await tool.test_connection(credentials)
        except Exception as exc:
            tool_result = None
            message = str(exc) or "Connection test failed"
        else:
            message = tool_result.error or "Connection successful"
        success = tool_result is not None and tool_result.success

    integration.status = "connected" if success else "failed"
    integration.last_tested_at = datetime.now(timezone.utc)
    integration.last_error = None if integration.status == "connected" else message
    await db.commit()

    return IntegrationTestResponse(
        success=integration.status == "connected",
        status=integration.status,
        message=message,
    )
