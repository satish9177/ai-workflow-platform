from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkflowCreate(BaseModel):
    name: str
    description: str | None = None
    steps: list[dict[str, Any]] = Field(min_length=1)
    trigger_type: Literal["manual", "cron", "webhook"]
    trigger_config: dict[str, Any] = {}


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[dict[str, Any]] | None = Field(default=None, min_length=1)
    trigger_type: Literal["manual", "cron", "webhook"] | None = None
    trigger_config: dict[str, Any] | None = None


class WorkflowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    steps: list[dict[str, Any]]
    trigger_type: str
    trigger_config: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime | None
