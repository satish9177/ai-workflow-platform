from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ALLOWED_STEP_TYPES = {"llm", "tool", "approval", "condition"}


def validate_workflow_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for index, step in enumerate(steps):
        step_label = f"Step {index + 1}"
        step_id = step.get("id")
        if not isinstance(step_id, str) or not step_id.strip():
            raise ValueError(f"{step_label}: id is required")

        step_type = step.get("type")
        if not isinstance(step_type, str) or not step_type.strip():
            raise ValueError(f"{step_label}: type is required")
        if step_type not in ALLOWED_STEP_TYPES:
            allowed = ", ".join(sorted(ALLOWED_STEP_TYPES))
            raise ValueError(f"{step_label}: type must be one of: {allowed}")

        if step_type == "tool":
            if not step.get("tool"):
                raise ValueError(f"{step_label}: tool is required for tool steps")
            if not step.get("action"):
                raise ValueError(f"{step_label}: action is required for tool steps")
        elif step_type == "approval":
            if not (step.get("approver_email") or step.get("approver_email_template")):
                raise ValueError(f"{step_label}: approver_email or approver_email_template is required for approval steps")
        elif step_type == "condition":
            if not step.get("condition"):
                raise ValueError(f"{step_label}: condition is required for condition steps")

    return steps


class WorkflowCreate(BaseModel):
    name: str
    description: str | None = None
    steps: list[dict[str, Any]] = Field(min_length=1)
    trigger_type: Literal["manual", "cron", "webhook"]
    trigger_config: dict[str, Any] = {}

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return validate_workflow_steps(steps)


class WorkflowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[dict[str, Any]] | None = Field(default=None, min_length=1)
    trigger_type: Literal["manual", "cron", "webhook"] | None = None
    trigger_config: dict[str, Any] | None = None

    @field_validator("steps")
    @classmethod
    def validate_steps(cls, steps: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        if steps is None:
            return None
        return validate_workflow_steps(steps)


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
