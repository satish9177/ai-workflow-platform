"""parallel_foreach_foundation

Revision ID: c6e8a41f0b23
Revises: b4f83c9a2d11
Create Date: 2026-05-14 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c6e8a41f0b23"
down_revision: Union[str, Sequence[str], None] = "b4f83c9a2d11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "branch_executions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("step_key", sa.String(), nullable=False),
        sa.Column("branch_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column("total_branches", sa.Integer(), server_default="0", nullable=False),
        sa.Column("completed_branches", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_branches", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cancelled_branches", sa.Integer(), server_default="0", nullable=False),
        sa.Column("merge_triggered", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("fail_fast", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("fail_fast_triggered", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("foreach_items", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("merged_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_branch_executions_run_id", "branch_executions", ["run_id"])
    op.create_index("ix_branch_executions_run_id_step_key", "branch_executions", ["run_id", "step_key"])
    op.create_index("ix_branch_executions_status", "branch_executions", ["status"])

    op.add_column(
        "runs",
        sa.Column("current_branch_depth", sa.Integer(), server_default="0", nullable=False),
    )

    op.add_column("step_executions", sa.Column("branch_execution_id", sa.String(), nullable=True))
    op.add_column("step_executions", sa.Column("foreach_index", sa.Integer(), nullable=True))
    op.add_column(
        "step_executions",
        sa.Column("foreach_item", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("step_executions", sa.Column("branch_key", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_step_executions_branch_execution_id_branch_executions",
        "step_executions",
        "branch_executions",
        ["branch_execution_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_step_executions_branch_execution_id",
        "step_executions",
        ["branch_execution_id"],
    )
    op.create_index(
        "ix_step_executions_run_id_step_key_foreach_index",
        "step_executions",
        ["run_id", "step_key", "foreach_index"],
    )
    op.create_index("ix_step_executions_branch_key", "step_executions", ["branch_key"])


def downgrade() -> None:
    op.drop_index("ix_step_executions_branch_key", table_name="step_executions")
    op.drop_index("ix_step_executions_run_id_step_key_foreach_index", table_name="step_executions")
    op.drop_index("ix_step_executions_branch_execution_id", table_name="step_executions")
    op.drop_constraint(
        "fk_step_executions_branch_execution_id_branch_executions",
        "step_executions",
        type_="foreignkey",
    )
    op.drop_column("step_executions", "branch_key")
    op.drop_column("step_executions", "foreach_item")
    op.drop_column("step_executions", "foreach_index")
    op.drop_column("step_executions", "branch_execution_id")

    op.drop_column("runs", "current_branch_depth")

    op.drop_index("ix_branch_executions_status", table_name="branch_executions")
    op.drop_index("ix_branch_executions_run_id_step_key", table_name="branch_executions")
    op.drop_index("ix_branch_executions_run_id", table_name="branch_executions")
    op.drop_table("branch_executions")
