"""Integration tests for the Phase 1 pipeline: upload -> Celery task -> DB.

Requires a reachable Postgres/Redis (docker-compose or CI services) and downloads
the real embedding model on first run — no FakeEmbedder is used, matching the
project's approach for Phase 1 (only the LLM gets a Fake, per Phase 3).
"""

import io

from fastapi.testclient import TestClient
from sqlalchemy import select

import ingestion.tasks
from api.main import app
from core.config import get_settings
from db.session import make_engine, make_session_factory, session_scope
from models import Chunk, Document


def test_upload_ingests_and_reupload_is_idempotent() -> None:
    content = b"Veritas is a self-verifying RAG engine. " * 50
    with TestClient(app) as client:
        response = client.post(
            "/documents",
            files={"file": ("sample.txt", io.BytesIO(content), "text/plain")},
        )
        assert response.status_code == 202
        document_id = response.json()["id"]

        # POST /documents dispatches via celery_app.send_task() (by name, so the api
        # process never imports this task's heavy deps — see worker/celery_app.py),
        # which always publishes to the real broker regardless of any eager-mode
        # config, and no worker process is running in this test. Simulate the
        # worker's side by invoking the task body directly, same as the
        # crash-redelivery test below.
        ingestion.tasks.ingest_document(document_id)

        detail = client.get(f"/documents/{document_id}").json()
        assert detail["status"] == "ready"
        assert detail["chunk_count"] > 0

        # Byte-identical re-upload must be a no-op: same id, no re-ingestion.
        response2 = client.post(
            "/documents",
            files={"file": ("sample.txt", io.BytesIO(content), "text/plain")},
        )
        assert response2.status_code == 202
        assert response2.json()["id"] == document_id

        detail2 = client.get(f"/documents/{document_id}").json()
        assert detail2["chunk_count"] == detail["chunk_count"]


def test_ingest_document_is_safe_to_rerun_after_simulated_crash(tmp_path) -> None:
    """A worker that dies mid-task gets its task redelivered by Celery (acks_late).
    Simulates that redelivery by invoking the ingestion body twice for the same
    document — chunks must end up correct, not duplicated.
    """
    settings = get_settings()
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)

    sample_file = tmp_path / "crash-test.txt"
    sample_file.write_text("Alpha beta gamma delta epsilon. " * 30, encoding="utf-8")

    with session_scope(session_factory) as session:
        document = Document(
            filename="crash-test.txt",
            mime="text/plain",
            storage_path=str(sample_file),
            status="queued",
            checksum="crash-test-checksum-unique-0001",
        )
        session.add(document)
        session.flush()
        document_id = str(document.id)

    ingestion.tasks._run_ingestion(document_id)
    ingestion.tasks._run_ingestion(document_id)  # simulated redelivery after a crash

    with session_scope(session_factory) as session:
        chunks = (
            session.execute(select(Chunk).where(Chunk.document_id == document_id)).scalars().all()
        )
        indices = sorted(c.chunk_index for c in chunks)
        assert indices == list(range(len(indices)))  # no duplicates, no gaps

        document = session.get(Document, document_id)
        assert document is not None
        assert document.status == "ready"

        # cleanup so repeated test runs don't accumulate rows (chunks cascade)
        session.delete(document)
