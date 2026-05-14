"""unique pending approvals per run step

Revision ID: d9a7c3e2f4b1
Revises: c6e8a41f0b23
Create Date: 2026-05-14 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d9a7c3e2f4b1"
down_revision: Union[str, Sequence[str], None] = "c6e8a41f0b23"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_approvals_unique_pending_run_step",
        "approvals",
        ["run_id", "step_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_approvals_unique_pending_run_step", table_name="approvals")
