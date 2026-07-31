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
)
