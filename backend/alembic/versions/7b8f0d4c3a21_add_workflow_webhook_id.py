"""add_workflow_webhook_id

Revision ID: 7b8f0d4c3a21
Revises: 2c7f4a91d8b2
Create Date: 2026-05-13 00:00:00.000000
"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = "7b8f0d4c3a21"
down_revision: Union[str, Sequence[str], None] = "2c7f4a91d8b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workflows", sa.Column("webhook_id", sa.String(), nullable=True))
    bind = op.get_bind()
    workflow_ids = bind.execute(sa.text("SELECT id FROM workflows WHERE webhook_id IS NULL")).scalars().all()
    for workflow_id in workflow_ids:
        bind.execute(
            sa.text("UPDATE workflows SET webhook_id = :webhook_id WHERE id = :id"),
            {"webhook_id": str(uuid.uuid4()), "id": workflow_id},
        )
    op.alter_column("workflows", "webhook_id", nullable=False)
    op.create_unique_constraint(op.f("uq_workflows_webhook_id"), "workflows", ["webhook_id"])


def downgrade() -> None:
    op.drop_constraint(op.f("uq_workflows_webhook_id"), "workflows", type_="unique")
    op.drop_column("workflows", "webhook_id")
