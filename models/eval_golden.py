"""ORM model for the `eval_golden` table — added in Phase 4, when the eval harness
needs a ground-truth question set to score retrieval/faithfulness against.
"""

import uuid

from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Text

from models.base import Base


class EvalGolden(Base):
    """One hand-authored golden question, with its expected chunk(s) and answer.

    Purpose: ground truth for the eval harness (Phase 4) — Recall@k and MRR are
        computed against `expected_chunk_ids`; `expected_answer` is kept for human
        review of the harness's output, not compared programmatically (grading
        free-text answer similarity is out of scope — see
        docs/private/ARCHITECTURE_LEDGER.md).
    Inputs: n/a (ORM model).
    Outputs: n/a (ORM model).
    Complexity: n/a.
    Failure cases: none beyond standard NOT NULL constraints.
    """

    __tablename__ = "eval_golden"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False
    )
    expected_answer: Mapped[str] = mapped_column(Text, nullable=False)
