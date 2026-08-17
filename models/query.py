"""ORM model for the `queries` table — added in Phase 3, when POST /ask needs it."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from models.base import Base


class Query(Base):
    """One POST /ask request's outcome — logged for observability and reused as
    the eval harness's raw material in Phase 4.

    Purpose: records what was asked, what (if anything) was answered, whether the
        cite-or-refuse gate refused it, and enough retrieval/verification detail
        (`retrieval_debug`) to debug or evaluate a specific answer after the fact.
    Inputs: n/a (ORM model).
    Outputs: n/a (ORM model).
    Complexity: n/a.
    Failure cases: none beyond standard NOT NULL constraints.
    """

    __tablename__ = "queries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    refused: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    retrieval_debug: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
