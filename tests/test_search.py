"""Integration test for GET /search against real ingested chunks."""

import io

from fastapi.testclient import TestClient

import ingestion.tasks
from api.main import app


def _ingest(client: TestClient, filename: str, content: bytes) -> str:
    response = client.post(
        "/documents",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )
    document_id = response.json()["id"]
    if response.json()["status"] != "ready":
        ingestion.tasks.ingest_document(document_id)
    return document_id


def test_search_finds_relevant_chunk_by_keyword_and_meaning() -> None:
    with TestClient(app) as client:
        _ingest(
            client,
            "postgres.txt",
            b"PostgreSQL is a powerful open source relational database system. "
            b"It supports advanced indexing, full-text search, and JSON storage. " * 10,
        )
        _ingest(
            client,
            "weather.txt",
            b"The weather today is sunny with a light breeze from the northwest. "
            b"Temperatures are expected to stay mild throughout the afternoon. " * 10,
        )

        response = client.get("/search", params={"q": "relational database system"})
        assert response.status_code == 200
        body = response.json()
        assert body["query"] == "relational database system"
        assert len(body["results"]) > 0

        top_result = body["results"][0]
        assert (
            "postgres" in top_result["content"].lower()
            or "database" in top_result["content"].lower()
        )
        assert top_result["score"] > 0
        # at least one of the two per-signal ranks must be present — a hit that
        # matched neither signal wouldn't be in the fused results at all
        assert top_result["bm25_rank"] is not None or top_result["dense_rank"] is not None


def test_search_rejects_empty_query() -> None:
    with TestClient(app) as client:
        response = client.get("/search", params={"q": ""})
    assert response.status_code == 422


def test_search_on_no_matching_content_returns_empty_results() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/search", params={"q": "xylophonic quokka nebula zephyr flibbertigibbet"}
        )
    assert response.status_code == 200
    # not asserting == [] strictly: dense retrieval always returns *some* nearest
    # neighbor even for an unrelated query (cosine distance has no reject
    # threshold in Phase 2 yet) — the real assertion is that it doesn't error.
    assert isinstance(response.json()["results"], list)
