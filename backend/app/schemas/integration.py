from typing import Any

from pydantic import BaseModel


class IntegrationRead(BaseModel):
    name: str
    is_enabled: bool
    has_credentials: bool


class IntegrationUpsert(BaseModel):
    credentials: dict[str, Any]
    config: dict[str, Any] = {}
