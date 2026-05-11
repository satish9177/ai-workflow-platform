import base64
from typing import Any

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.integration import Integration
from app.models.user import User
from app.schemas.integration import IntegrationRead, IntegrationUpsert
from app.tools.registry import ToolRegistry


router = APIRouter(tags=["integrations"])


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
    if ToolRegistry.get(name) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool not found")


@router.get("/", response_model=list[IntegrationRead])
async def list_integrations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[IntegrationRead]:
    rows = await db.execute(select(Integration).where(Integration.is_enabled.is_(True)))
    integrations = {integration.name: integration for integration in rows.scalars().all()}
    return [
        IntegrationRead(
            name=name,
            is_enabled=integrations.get(name).is_enabled if name in integrations else False,
            has_credentials=bool(integrations.get(name) and integrations[name].credentials),
        )
        for name in ToolRegistry.all_names()
    ]


@router.put("/{name}", response_model=IntegrationRead)
async def upsert_integration(
    name: str,
    payload: IntegrationUpsert,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IntegrationRead:
    _validate_tool(name)
    encrypted_credentials = _encrypt_credentials(payload.credentials)

    result = await db.execute(select(Integration).where(Integration.name == name))
    integration = result.scalar_one_or_none()
    if integration is None:
        integration = Integration(
            name=name,
            credentials=encrypted_credentials,
            config=payload.config,
            is_enabled=True,
        )
        db.add(integration)
    else:
        integration.credentials = encrypted_credentials
        integration.config = payload.config
        integration.is_enabled = True

    await db.commit()
    await db.refresh(integration)
    return IntegrationRead(name=integration.name, is_enabled=integration.is_enabled, has_credentials=bool(integration.credentials))


@router.delete("/{name}")
async def delete_integration(
    name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    await db.execute(delete(Integration).where(Integration.name == name))
    await db.commit()
    return {"deleted": True}


@router.post("/{name}/test")
async def test_integration(
    name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool | str]:
    _validate_tool(name)
    result = await db.execute(select(Integration).where(Integration.name == name, Integration.is_enabled.is_(True)))
    integration = result.scalar_one_or_none()
    if integration is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")

    credentials = _decrypt_credentials(integration.credentials or {})
    tool = ToolRegistry.get(name)
    tool_result = await tool.test_connection(credentials)
    return {"success": tool_result.success, "message": tool_result.error or "Connection successful"}
