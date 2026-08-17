"""Veritas API entrypoint — FastAPI app assembly and process lifespan."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from api.ask import router as ask_router
from api.documents import router as documents_router
from api.health import router as health_router
from api.search import router as search_router
from core.config import get_settings
from core.logging import get_logger
from db.session import make_engine, make_session_factory

settings = get_settings()
logger = get_logger("veritas.api", settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Construct and tear down the Postgres and Redis clients alongside the app.

    Purpose: owns both clients' lifetimes so they are created once per process (not
        per-request), scoped to app.state rather than a module-level global.
    Inputs: app — the FastAPI application being started.
    Outputs: yields control while the app serves requests; no return value.
    Complexity: O(1).
    Failure cases: none — the engine and Redis client are both constructed lazily and
        do not connect eagerly, so a down dependency at boot does not prevent the API
        from starting (GET /health is what reports that, on a per-request basis).
    """
    app.state.engine = make_engine(settings)
    app.state.session_factory = make_session_factory(app.state.engine)
    app.state.redis = Redis.from_url(settings.redis_url)
    try:
        yield
    finally:
        await app.state.redis.aclose()
        app.state.engine.dispose()


app = FastAPI(title="Veritas API", version="0.1.0", lifespan=lifespan)
app.include_router(health_router)
app.include_router(documents_router)
app.include_router(search_router)
app.include_router(ask_router)
