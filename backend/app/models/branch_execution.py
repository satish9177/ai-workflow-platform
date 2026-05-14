import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BranchExecution(Base):
    __tablename__ = "branch_executions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    step_key: Mapped[str] = mapped_column(String, nullable=False)
    branch_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    total_branches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_branches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_branches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cancelled_branches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    merge_triggered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fail_fast: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fail_fast_triggered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    foreach_items: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    merged_context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
