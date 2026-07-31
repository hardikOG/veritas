"""Celery application — the async ingestion worker (tasks land in Phase 1)."""

from celery import Celery

from core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "veritas",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    worker_concurrency=settings.celery_concurrency,
    # Crash-safety for Phase 1 ingestion: a worker that dies mid-task never acked it,
    # so the broker redelivers it to another worker instead of silently losing the
    # work. Tasks that rely on this (ingestion.tasks.ingest_document) are written to
    # be safely re-run from scratch. See docs/private/ARCHITECTURE_LEDGER.md.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

# Deliberately does NOT `import ingestion.tasks` here. The api container imports
# this module too (to enqueue tasks by name via celery_app.send_task(), without
# needing the task function itself importable) but does not have ingestion/embedding
# or their heavy ML dependencies (sentence-transformers, torch) installed — only the
# worker image does (see docker/Dockerfile.worker). Task registration instead happens
# via `celery --include=ingestion.tasks` on the worker's own start command, so only
# the actual worker process ever imports that module.
