"""add approval timeout metadata

Revision ID: f2a9b7c6d5e4
Revises: e1b2c3d4f5a6
Create Date: 2026-05-14 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f2a9b7c6d5e4"
down_revision: Union[str, Sequence[str], None] = "e1b2c3d4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("approvals", sa.Column("timeout_action", sa.String(), nullable=True))
    op.add_column("approvals", sa.Column("timed_out_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_approvals_pending_timeout_due",
        "approvals",
        ["expires_at"],
        unique=False,
        postgresql_where=sa.text("status = 'pending' AND timeout_action IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_approvals_pending_timeout_due", table_name="approvals")
    op.drop_column("approvals", "timed_out_at")
    op.drop_column("approvals", "timeout_action")
