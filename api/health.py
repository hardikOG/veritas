"""GET /health — readiness probe used by docker-compose, CI, and Render's health check."""

from typing import Any

from fastapi import APIRouter, Depends, Response, status
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from api.deps import get_db, get_redis
from core.logging import get_logger

logger = get_logger("veritas.api")
router = APIRouter()

APP_VERSION = "0.1.0"


@router.get("/health")
async def health(
    response: Response,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
) -> dict[str, Any]:
    """Report whether the API can actually reach Postgres and Redis right now.

    Purpose: a real readiness check, not a static 200 — issues one `SELECT 1` and one
        `PING` per call so a dependency outage is reflected immediately, not masked by
        a cached "ok". Doubles as Render's health check target in Phase 6.
    Inputs: db, redis_client — injected per-request dependencies (overridable in tests
        via app.dependency_overrides to simulate a failing dependency).
    Outputs: {"status", "database", "redis", "version"}. HTTP 200 if both dependencies
        are reachable, HTTP 503 if either is not.
    Complexity: O(1) — one trivial query, one PING.
    Failure cases: never raises — SQLAlchemyError and RedisError are each caught
        independently so one dependency's failure doesn't prevent reporting the
        other's real status.
    """
    db_ok = True
    redis_ok = True

    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        db_ok = False
        logger.error(
            "health check: database unreachable", extra={"extra_fields": {"error": str(exc)}}
        )

    try:
        await redis_client.ping()
    except RedisError as exc:
        redis_ok = False
        logger.error("health check: redis unreachable", extra={"extra_fields": {"error": str(exc)}})

    healthy = db_ok and redis_ok
    response.status_code = status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "healthy" if healthy else "unhealthy",
        "database": "ok" if db_ok else "failed",
        "redis": "ok" if redis_ok else "failed",
        "version": APP_VERSION,
    }
