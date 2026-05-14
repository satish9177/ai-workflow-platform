"""add switch parent step tracking

Revision ID: a3c4d5e6f7a8
Revises: f2a9b7c6d5e4
Create Date: 2026-05-14 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "f2a9b7c6d5e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("step_executions", sa.Column("parent_step_id", sa.String(), nullable=True))
    op.create_index(
        "ix_step_executions_run_parent_step",
        "step_executions",
        ["run_id", "parent_step_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_step_executions_run_parent_step", table_name="step_executions")
    op.drop_column("step_executions", "parent_step_id")
