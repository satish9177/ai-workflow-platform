from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class StepResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    step_id: str
    step_type: str
    status: str
    input: dict[str, Any] | None
    output: dict[str, Any] | None
    error: str | None
    duration_ms: int | None
    created_at: datetime


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workflow_id: str
    status: str
    trigger_data: dict[str, Any] | None
    context: dict[str, Any] | None
    current_step: str | None
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class RunDetail(RunRead):
    step_results: list[StepResultRead]
