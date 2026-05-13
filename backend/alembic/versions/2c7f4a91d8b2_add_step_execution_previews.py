"""add_step_execution_previews

Revision ID: 2c7f4a91d8b2
Revises: 9f4d2c8b7a10
Create Date: 2026-05-13 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "2c7f4a91d8b2"
down_revision: Union[str, Sequence[str], None] = "9f4d2c8b7a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("step_executions", sa.Column("input_preview", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("step_executions", sa.Column("output_preview", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("step_executions", "output_preview")
    op.drop_column("step_executions", "input_preview")
