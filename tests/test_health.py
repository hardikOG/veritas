"""Tests for GET /health — asserts it performs live checks, not a static 200.

The positive case exercises the real DB/Redis clients (requires docker-compose or CI
services to be up). The negative cases use app.dependency_overrides to simulate a
failing dependency deterministically, since actually killing a container mid-test
isn't practical in CI.
"""

from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from api.deps import get_db, get_redis
from api.main import app


def test_health_returns_200_when_dependencies_are_up() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["database"] == "ok"
    assert body["redis"] == "ok"
    assert "version" in body


class _BrokenSession:
    def execute(self, *args: object, **kwargs: object) -> None:
        raise SQLAlchemyError("connection refused")


def _broken_db() -> object:
    return _BrokenSession()


def test_health_returns_503_when_database_is_down() -> None:
    app.dependency_overrides[get_db] = _broken_db
    try:
        with TestClient(app) as client:
            response = client.get("/health")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["database"] == "failed"


class _BrokenRedis:
    async def ping(self) -> None:
        raise RedisError("connection refused")


def _broken_redis() -> object:
    return _BrokenRedis()


def test_health_returns_503_when_redis_is_down() -> None:
    app.dependency_overrides[get_redis] = _broken_redis
    try:
        with TestClient(app) as client:
            response = client.get("/health")
    finally:
        app.dependency_overrides.pop(get_redis, None)

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["redis"] == "failed"
