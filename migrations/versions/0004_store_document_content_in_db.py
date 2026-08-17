"""store document content in the database instead of a local filesystem path

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-12

Render (Phase 6) gives each service its own persistent disk -- a disk is never
shared between two services, so the local-path-on-shared-volume scheme that
works in docker-compose can't work once api and worker are separate Render
services. Storing the raw upload bytes in Postgres instead means both
processes reach it through the database connection they already share. See
docs/private/ARCHITECTURE_LEDGER.md's Phase 6 entry.
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("content", sa.LargeBinary(), nullable=True))
    op.drop_column("documents", "storage_path")


def downgrade() -> None:
    op.add_column(
        "documents", sa.Column("storage_path", sa.String(), nullable=False, server_default="")
    )
    op.drop_column("documents", "content")
