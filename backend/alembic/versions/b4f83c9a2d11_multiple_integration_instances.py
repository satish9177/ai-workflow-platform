"""multiple_integration_instances

Revision ID: b4f83c9a2d11
Revises: 7b8f0d4c3a21
Create Date: 2026-05-13 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4f83c9a2d11"
down_revision: Union[str, Sequence[str], None] = "7b8f0d4c3a21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_integrations_name", "integrations", type_="unique")
    op.add_column("integrations", sa.Column("integration_type", sa.String(), nullable=True))
    op.add_column("integrations", sa.Column("display_name", sa.String(), nullable=True))
    op.add_column("integrations", sa.Column("status", sa.String(), server_default="unknown", nullable=False))
    op.add_column("integrations", sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("integrations", sa.Column("last_error", sa.Text(), nullable=True))

    op.execute("UPDATE integrations SET integration_type = name WHERE integration_type IS NULL")
    op.execute("UPDATE integrations SET display_name = name || ' (Default)' WHERE display_name IS NULL")

    op.alter_column("integrations", "integration_type", nullable=False)
    op.alter_column("integrations", "display_name", nullable=False)


def downgrade() -> None:
    op.drop_column("integrations", "last_error")
    op.drop_column("integrations", "last_tested_at")
    op.drop_column("integrations", "status")
    op.drop_column("integrations", "display_name")
    op.drop_column("integrations", "integration_type")
    op.create_unique_constraint("uq_integrations_name", "integrations", ["name"])
