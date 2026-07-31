"""ORM model for the `chunks` table."""

import uuid
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.config import get_settings
from models.base import Base

_settings = get_settings()


class Chunk(Base):
    """One sliding-window chunk of a document, with its dense embedding and tsvector.

    Purpose: the unit of retrieval — hybrid search (Phase 2) matches against
        `embedding` (dense, pgvector `<=>`) and `tsv` (sparse, `ts_rank`) independently
        before RRF-fusing the two rankings. `embedding`/`tsv` are nullable because
        Phase 0 only creates the table shape; Phase 1's ingestion task is what
        populates them.
    Inputs: n/a (ORM model).
    Outputs: n/a (ORM model).
    Complexity: n/a.
    Failure cases: a duplicate (document_id, chunk_index) violates the unique
        constraint — the chunker must not re-emit an existing index for the same
        document.
    """

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Any] = mapped_column(Vector(_settings.vector_dim), nullable=True)
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', content)", persisted=True), nullable=True
    )
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
