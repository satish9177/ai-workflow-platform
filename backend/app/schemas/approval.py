from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    step_id: str
    token: str
    status: str
    context: dict[str, Any] | None
    approver_email: str
    expires_at: datetime
    responded_at: datetime | None
    created_at: datetime


class ApprovalActionRequest(BaseModel):
    note: str | None = None
