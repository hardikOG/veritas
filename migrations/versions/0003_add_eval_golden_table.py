"""add eval_golden table

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-12

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "eval_golden",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("expected_chunk_ids", ARRAY(UUID(as_uuid=True)), nullable=False),
        sa.Column("expected_answer", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("eval_golden")
