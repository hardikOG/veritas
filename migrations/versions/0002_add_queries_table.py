"""add queries table

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-11

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "queries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("refused", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Numeric(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("retrieval_debug", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("queries")
