"""ORM model for the `documents` table.

Schema is the Phase 0 starting point (`chunks`/`queries`/`eval_golden` follow once
their owning phase actually needs them — see docs/private/ARCHITECTURE_LEDGER.md for
why only `documents` and `chunks` are created in Phase 0).
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class Document(Base):
    """A single uploaded source document tracked through the ingestion pipeline.

    Purpose: represents one uploaded file from upload through ingestion completion
        (or failure). `checksum` is the idempotency key Phase 1's ingestion task uses
        to make re-ingesting the same file a no-op.
    Inputs: n/a (ORM model).
    Outputs: n/a (ORM model).
    Complexity: n/a.
    Failure cases: inserting a duplicate `checksum` violates the unique constraint —
        Phase 1's upload handler must check-then-reuse, not blindly insert.
    """

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status in ('queued','processing','ready','failed')",
            name="ck_documents_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    mime: Mapped[str] = mapped_column(String, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="queued")
    checksum: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
