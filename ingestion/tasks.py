"""Celery task: extract -> chunk -> embed -> write, for one document.

Registered on the worker process only, via `--include=ingestion.tasks` on the
worker's start command (see docker/Dockerfile.worker) — not imported by
worker/celery_app.py directly, since the api process imports that module too and
must not pull in this module's heavy ML dependencies.
"""

from celery.exceptions import MaxRetriesExceededError
from redis.exceptions import RedisError
from sqlalchemy import delete, select
from sqlalchemy.exc import OperationalError

from core.config import get_settings
from core.constants import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, TASK_INGEST_DOCUMENT
from core.logging import get_logger
from db.session import make_engine, make_session_factory, session_scope
from embedding.sentence_transformer import get_embedder
from ingestion.chunk import chunk_text
from ingestion.extract import extract_text
from models import Chunk, Document
from worker.celery_app import celery_app

logger = get_logger("veritas.worker")
settings = get_settings()
_engine = make_engine(settings)
_session_factory = make_session_factory(_engine)

_TRANSIENT_EXCEPTIONS = (OperationalError, RedisError, ConnectionError)


@celery_app.task(bind=True, name=TASK_INGEST_DOCUMENT, max_retries=settings.ingest_max_retries)
def ingest_document(self, document_id: str) -> None:
    """Extract, chunk, embed, and persist one document's chunks.

    Purpose: the entire Phase 1 async pipeline. Idempotent and crash-safe by design:
        `task_acks_late`/`task_reject_on_worker_lost` (see worker/celery_app.py) mean
        Celery redelivers this task to another worker if the process dies mid-run
        without acking, and every write here deletes-then-rewrites this document's
        chunks in one transaction — so a redelivered task that partially ran before
        crashing safely redoes the work rather than duplicating or corrupting rows.
        Status only reaches 'ready' after every chunk commits; a mid-run crash leaves
        it at 'processing' until redelivery retries it.
    Inputs: document_id — a Document.id (str form of a UUID) already inserted with
        status='queued' by POST /documents.
    Outputs: None. On success, the document's chunks are (re)written and its status
        becomes 'ready'. On exhausted retries, status becomes 'failed' and the error
        is logged with the retry count — the "dead letter": Celery itself has no DLQ
        concept, so this status + log line is the queryable terminal-failure record.
    Complexity: O(text length) for chunking, O(chunk count) for embedding + writes.
    Failure cases: transient errors (DB/Redis unreachable) are retried with
        exponential backoff up to ingest_max_retries; anything else (corrupt file,
        unsupported mime) is not retried — it cannot succeed on retry — and fails the
        document immediately.
    """
    with session_scope(_session_factory) as session:
        document = session.get(Document, document_id)
        if document is None:
            logger.error(
                "ingest task: document not found",
                extra={"extra_fields": {"document_id": document_id}},
            )
            return
        document.status = "processing"

    try:
        _run_ingestion(document_id)
    except _TRANSIENT_EXCEPTIONS as exc:
        logger.error(
            "ingest task: transient failure, retrying",
            extra={
                "extra_fields": {
                    "document_id": document_id,
                    "retry": self.request.retries,
                    "error": str(exc),
                }
            },
        )
        try:
            raise self.retry(exc=exc, countdown=min(2**self.request.retries, 60))
        except MaxRetriesExceededError:
            _mark_failed(document_id, str(exc))
    except Exception as exc:  # noqa: BLE001 - deterministic failure, not retryable
        logger.error(
            "ingest task: non-retryable failure",
            extra={"extra_fields": {"document_id": document_id, "error": str(exc)}},
        )
        _mark_failed(document_id, str(exc))


def _run_ingestion(document_id: str) -> None:
    """Do the actual extract/chunk/embed/write work inside one transaction.

    Takes a row-level lock (`SELECT ... FOR UPDATE`) on the document for the
    duration of this transaction, not just `session.get()` — Celery's
    `task_acks_late`/`task_reject_on_worker_lost` (see worker/celery_app.py)
    means a redelivered task can genuinely run concurrently with the original
    attempt (not just sequentially after it), and the delete-then-insert chunk
    write below is only safe against *sequential* re-runs on its own; without
    the lock, two truly concurrent executions can each delete the other's
    freshly-inserted chunks out from under it and collide on
    `uq_chunks_document_index`. The lock makes a second concurrent call wait
    for the first to commit, then safely redo the (idempotent) work, instead
    of racing it.
    """
    with session_scope(_session_factory) as session:
        document = session.execute(
            select(Document).where(Document.id == document_id).with_for_update()
        ).scalar_one_or_none()
        if document is None:
            return  # deleted between the status update above and now; nothing to do

        text = extract_text(document.content or b"", document.mime)
        embedder = get_embedder(settings)
        # Bounded by the embedder's real max_seq_length, not just the constant, so a
        # chunk is never silently truncated by the model — see
        # docs/private/ARCHITECTURE_LEDGER.md.
        effective_chunk_size = min(DEFAULT_CHUNK_SIZE, embedder.max_seq_length)
        chunks = chunk_text(
            text,
            tokenizer=embedder.tokenizer,
            chunk_size=effective_chunk_size,
            overlap=min(DEFAULT_CHUNK_OVERLAP, effective_chunk_size - 1),
        )

        # Idempotent re-run safety: a redelivered task (or a resubmitted file with
        # different content but the same document row somehow) must not leave stale
        # chunks from a previous attempt lying around alongside fresh ones.
        session.execute(delete(Chunk).where(Chunk.document_id == document.id))

        if chunks:
            embeddings = embedder.embed([c.content for c in chunks])
            session.add_all(
                Chunk(
                    document_id=document.id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    embedding=embedding,
                    token_count=chunk.token_count,
                )
                for chunk, embedding in zip(chunks, embeddings, strict=True)
            )

        document.status = "ready"


def _mark_failed(document_id: str, reason: str) -> None:
    """Set a document's status to 'failed' and log the terminal reason."""
    with session_scope(_session_factory) as session:
        document = session.get(Document, document_id)
        if document is not None:
            document.status = "failed"
    logger.error(
        "ingest task: document marked failed",
        extra={"extra_fields": {"document_id": document_id, "reason": reason}},
    )
