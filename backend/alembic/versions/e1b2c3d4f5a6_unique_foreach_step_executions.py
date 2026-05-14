"""unique foreach step executions

Revision ID: e1b2c3d4f5a6
Revises: d9a7c3e2f4b1
Create Date: 2026-05-14 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e1b2c3d4f5a6"
down_revision: Union[str, Sequence[str], None] = "d9a7c3e2f4b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Clean up any duplicate foreach rows from earlier retry races before enforcing
    # the identity invariant. Prefer the row with the most advanced lifecycle state.
    op.execute(
        """
        DELETE FROM step_executions se
        USING (
            SELECT id
            FROM (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY run_id, step_key, foreach_index
                        ORDER BY
                            CASE status
                                WHEN 'completed' THEN 6
                                WHEN 'failed' THEN 5
                                WHEN 'cancelled' THEN 4
                                WHEN 'awaiting_approval' THEN 3
                                WHEN 'running' THEN 2
                                WHEN 'queued' THEN 1
                                ELSE 0
                            END DESC,
                            updated_at DESC NULLS LAST,
                            created_at DESC NULLS LAST,
                            id DESC
                    ) AS row_number
                FROM step_executions
                WHERE foreach_index IS NOT NULL
            ) ranked
            WHERE ranked.row_number > 1
        ) duplicates
        WHERE se.id = duplicates.id
        """
    )
    op.create_index(
        "uq_step_executions_foreach_iteration",
        "step_executions",
        ["run_id", "step_key", "foreach_index"],
        unique=True,
        postgresql_where=sa.text("foreach_index IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_step_executions_foreach_iteration", table_name="step_executions")
