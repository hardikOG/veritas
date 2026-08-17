"""Seeds eval/fixtures/ into the database and populates eval_golden from GOLDEN_SET.

Run as a standalone script in the WORKER image/environment (`python -m eval.seed`),
never imported from the api process — it depends on ingestion.tasks, which imports
pypdf at module level (see ingestion/extract.py). The api image deliberately does
not carry pypdf (see docs/private/ARCHITECTURE_LEDGER.md, Phase 1/2 entries on the
api/worker dependency split); POST /eval/run (api-side, eval/runner.py) only reads
the eval_golden rows this script writes, it never ingests anything itself.

Idempotent: fixture ingestion reuses the same checksum-based dedup as POST
/documents (already-ingested fixtures are a no-op); eval_golden is fully replaced
each run, since GOLDEN_SET is the single source of truth for what should be in it.
"""

import hashlib
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

import ingestion.tasks
from core.config import get_settings
from core.constants import EXTENSION_TO_MIME
from db.session import make_engine, make_session_factory, session_scope
from eval.golden_set import GOLDEN_SET
from models import Chunk, Document, EvalGolden

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def seed_golden_set(session: Session) -> int:
    """Ingest eval/fixtures/ and replace eval_golden's contents from GOLDEN_SET.

    Purpose: builds the ground-truth data the eval harness scores against, from a
        small, human-authored, version-controlled corpus + question spec
        (eval/golden_set.py), so the eval harness's own database rows are
        reproducible from source rather than depending on whatever documents
        happen to already be in the database.
    Inputs: session — DB session (this process's, not ingestion.tasks's own —
        ingestion still writes through its own session_scope internally, same as
        every other caller of ingest_document).
    Outputs: the number of eval_golden rows written.
    Complexity: O(number of fixture documents + golden entries).
    Failure cases: raises ValueError if a fixture document ends up with zero chunks
        after ingestion (a golden question can't be scored against no chunks) —
        this should be unreachable for the checked-in fixtures, but would indicate
        a real ingestion problem, not something to silently skip.
    """
    document_by_fixture = {
        fixture_name: _ingest_fixture(session, fixture_name)
        for fixture_name in sorted({entry.source_fixture for entry in GOLDEN_SET})
    }

    session.execute(delete(EvalGolden))

    written = 0
    for entry in GOLDEN_SET:
        document = document_by_fixture[entry.source_fixture]
        chunk_ids = (
            session.execute(
                select(Chunk.id).where(Chunk.document_id == document.id).order_by(Chunk.chunk_index)
            )
            .scalars()
            .all()
        )
        if not chunk_ids:
            raise ValueError(f"fixture {entry.source_fixture!r} produced no chunks after ingestion")
        session.add(
            EvalGolden(
                question=entry.question,
                expected_chunk_ids=list(chunk_ids),
                expected_answer=entry.expected_answer,
            )
        )
        written += 1

    session.commit()
    return written


def _ingest_fixture(session: Session, fixture_name: str) -> Document:
    """Ingest one fixture file if not already ingested, returning its Document row."""
    path = FIXTURES_DIR / fixture_name
    content = path.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()

    document = session.execute(
        select(Document).where(Document.checksum == checksum)
    ).scalar_one_or_none()

    if document is None:
        document = Document(
            filename=fixture_name,
            mime=EXTENSION_TO_MIME[path.suffix.lower()],
            storage_path=str(path),
            status="queued",
            checksum=checksum,
        )
        session.add(document)
        session.commit()
        session.refresh(document)

    if document.status != "ready":
        ingestion.tasks.ingest_document(str(document.id))
        session.refresh(document)

    return document


if __name__ == "__main__":
    settings = get_settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    with session_scope(session_factory) as db_session:
        count = seed_golden_set(db_session)
    print(f"seeded {count} eval_golden rows")
