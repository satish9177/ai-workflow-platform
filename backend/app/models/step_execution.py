import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class StepExecution(Base):
    __tablename__ = "step_executions"
    __table_args__ = (
        Index(
            "uq_step_executions_foreach_iteration",
            "run_id",
            "step_key",
            "foreach_index",
            unique=True,
            postgresql_where=text("foreach_index IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    branch_execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("branch_executions.id", ondelete="SET NULL"),
        nullable=True,
    )
    parent_step_id: Mapped[str | None] = mapped_column(String, nullable=True)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    step_key: Mapped[str] = mapped_column(String, nullable=False)
    step_type: Mapped[str] = mapped_column(String, nullable=False)
    step_label: Mapped[str | None] = mapped_column(String, nullable=True)
    foreach_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    foreach_item: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    branch_key: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    input_preview: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    output_preview: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


Index("ix_step_executions_run_parent_step", StepExecution.run_id, StepExecution.parent_step_id)
