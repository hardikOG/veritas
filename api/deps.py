"""FastAPI dependency-injection seams for DB/Redis, shared across routers."""

from collections.abc import Iterator

from fastapi import Request
from redis.asyncio import Redis
from sqlalchemy.orm import Session


def get_db(request: Request) -> Iterator[Session]:
    """FastAPI dependency yielding a Session for the duration of one request.

    Purpose: dependency-injection seam for Postgres access. Tests override this via
        `app.dependency_overrides` to simulate a failing database without needing a
        real outage.
    Inputs: request — used only to reach app.state.session_factory.
    Outputs: yields a Session; closes it once the route handler returns.
    Complexity: O(1) overhead beyond the wrapped queries.
    Failure cases: none raised here — query-level failures propagate to the route.
    """
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_redis(request: Request) -> Redis:
    """FastAPI dependency returning the process's shared Redis client.

    Purpose: dependency-injection seam for the Redis client, mirroring get_db. Tests
        override this via `app.dependency_overrides` to simulate a failing Redis.
    Inputs: request — the current Request (used only to reach app.state).
    Outputs: the Redis client constructed in the app's lifespan.
    Complexity: O(1).
    Failure cases: none — raises AttributeError only if called outside a running app
        (i.e. lifespan never ran), which cannot happen via normal request handling.
    """
    return request.app.state.redis
