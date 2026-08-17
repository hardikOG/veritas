"""Integration tests for POST /ask — real retrieval/embedder, FakeLLMClient (no
network calls, per this project's testing rule that only the LLM gets a Fake).
"""

import io

from fastapi.testclient import TestClient

import ingestion.tasks
from api.ask import get_llm_client_dependency
from api.main import app
from llm.fake import FakeLLMClient


def _ingest(client: TestClient, filename: str, content: bytes) -> str:
    response = client.post(
        "/documents",
        files={"file": (filename, io.BytesIO(content), "text/plain")},
    )
    document_id = response.json()["id"]
    if response.json()["status"] != "ready":
        ingestion.tasks.ingest_document(document_id)
    return document_id


def test_ask_answers_with_citations_for_a_well_supported_question() -> None:
    with TestClient(app) as client:
        _ingest(
            client,
            "veritas_facts.txt",
            b"Veritas verifies every claim in its answers against retrieved source "
            b"chunks before returning them to the caller. " * 5,
        )

        app.dependency_overrides[get_llm_client_dependency] = lambda: FakeLLMClient()
        try:
            response = client.post("/ask", json={"question": "How does Veritas verify answers?"})
        finally:
            app.dependency_overrides.pop(get_llm_client_dependency, None)

        assert response.status_code == 200
        body = response.json()
        assert body["refused"] is False
        assert body["answer"] is not None
        assert len(body["citations"]) > 0
        assert body["confidence"] == 1.0
        assert body["latency_ms"] >= 0


def test_ask_refuses_when_answer_is_not_well_supported_by_its_citation() -> None:
    with TestClient(app) as client:
        document_id = _ingest(
            client,
            "postgres_facts.txt",
            b"PostgreSQL is an open source relational database system. " * 5,
        )
        # Find a real chunk id to cite, so this exercises the similarity check
        # itself (not a "hallucinated citation" case, already covered in
        # tests/test_verify.py) -- an unrelated claim citing a REAL chunk.
        detail = client.get(f"/documents/{document_id}").json()
        assert detail["chunk_count"] > 0
        search_result = client.get("/search", params={"q": "PostgreSQL"}).json()
        real_chunk_id = search_result["results"][0]["chunk_id"]

        unsupported_answer = f"Bananas are a good source of potassium. [cite:{real_chunk_id}]"
        app.dependency_overrides[get_llm_client_dependency] = lambda: FakeLLMClient(
            canned_answer=unsupported_answer
        )
        try:
            response = client.post("/ask", json={"question": "What is PostgreSQL?"})
        finally:
            app.dependency_overrides.pop(get_llm_client_dependency, None)

        assert response.status_code == 200
        body = response.json()
        assert body["refused"] is True
        assert body["answer"] is None
        assert body["citations"] == []


def test_ask_refuses_immediately_when_nothing_is_retrieved_and_never_calls_the_llm(
    monkeypatch,
) -> None:
    monkeypatch.setattr("api.ask.hybrid_search", lambda *args, **kwargs: [])

    class _LLMThatMustNotBeCalled:
        def generate_cited_answer(self, question, context):
            raise AssertionError("LLM must not be called when retrieval finds nothing")

    with TestClient(app) as client:
        app.dependency_overrides[get_llm_client_dependency] = lambda: _LLMThatMustNotBeCalled()
        try:
            response = client.post(
                "/ask", json={"question": "anything, retrieval is mocked to find nothing"}
            )
        finally:
            app.dependency_overrides.pop(get_llm_client_dependency, None)

    assert response.status_code == 200
    body = response.json()
    assert body["refused"] is True
    assert body["answer"] is None
    assert body["confidence"] == 0.0


def test_ask_rejects_empty_question() -> None:
    with TestClient(app) as client:
        response = client.post("/ask", json={"question": ""})
    assert response.status_code == 422
