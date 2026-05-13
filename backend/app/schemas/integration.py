from typing import Any
from datetime import datetime

from pydantic import BaseModel


class IntegrationRead(BaseModel):
    id: str | None = None
    name: str
    integration_type: str
    display_name: str
    is_enabled: bool
    status: str = "unknown"
    last_tested_at: datetime | None = None
    last_error: str | None = None
    credentials_set: bool
    has_credentials: bool


class IntegrationUpsert(BaseModel):
    credentials: dict[str, Any]
    config: dict[str, Any] = {}


class IntegrationCreate(BaseModel):
    integration_type: str
    display_name: str
    credentials: dict[str, Any] = {}
    config: dict[str, Any] = {}


class IntegrationUpdate(BaseModel):
    display_name: str | None = None
    credentials: dict[str, Any] | None = None
    config: dict[str, Any] | None = None


class IntegrationTestResponse(BaseModel):
    success: bool
    status: str
    message: str
