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
    current_branch_depth: int
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class RunDetail(RunRead):
    step_results: list[StepResultRead]


class StepExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    branch_execution_id: str | None
    step_index: int
    step_key: str
    step_type: str
    step_label: str | None
    foreach_index: int | None
    foreach_item: Any | None
    branch_key: str | None
    status: str
    attempt_number: int
    max_attempts: int
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    error_details: dict[str, Any] | None
    input_preview: dict[str, Any] | None
    output_preview: dict[str, Any] | None
    provider: str | None
    model: str | None
    tool_name: str | None
    created_at: datetime
    updated_at: datetime


class RunTimelineRead(BaseModel):
    run: RunRead
    steps: list[StepExecutionRead]
    failed_step_key: str | None = None
