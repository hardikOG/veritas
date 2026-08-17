"""Integration tests for POST /eval/run — FakeLLMClient (no network calls), real
retrieval/embedder/DB, per this project's testing rule that only the LLM gets a Fake.
"""

from fastapi.testclient import TestClient
from sqlalchemy import delete

from api.ask import get_llm_client_dependency
from api.main import app
from core.config import get_settings
from db.session import make_engine, make_session_factory, session_scope
from eval.golden_set import GOLDEN_SET
from eval.seed import seed_golden_set
from llm.fake import FakeLLMClient
from models import EvalGolden


def _session_factory():
    settings = get_settings()
    return make_session_factory(make_engine(settings))


def test_eval_run_returns_409_when_golden_set_is_empty() -> None:
    session_factory = _session_factory()
    with session_scope(session_factory) as session:
        session.execute(delete(EvalGolden))  # ensure genuinely empty for this test

    with TestClient(app) as client:
        response = client.post("/eval/run")

    assert response.status_code == 409


def test_eval_run_reports_metrics_over_the_seeded_golden_set() -> None:
    session_factory = _session_factory()
    with session_scope(session_factory) as session:
        seed_golden_set(session)

    with TestClient(app) as client:
        app.dependency_overrides[get_llm_client_dependency] = lambda: FakeLLMClient()
        try:
            response = client.post("/eval/run")
        finally:
            app.dependency_overrides.pop(get_llm_client_dependency, None)

    assert response.status_code == 200
    body = response.json()

    assert body["question_count"] == len(GOLDEN_SET)
    assert 0 <= body["refused_count"] <= body["question_count"]
    assert 0.0 <= body["mean_recall_at_k"] <= 1.0
    assert 0.0 <= body["mrr"] <= 1.0
    assert 0.0 <= body["mean_faithfulness"] <= 1.0
    assert body["p95_latency_ms"] >= 0.0

    # FakeLLMClient's default behavior cites the top-retrieved chunk verbatim, which
    # is always self-supporting (embedding the same text twice yields ~identical
    # vectors) -- this exercises the same real cite-or-refuse pipeline as POST /ask
    # (api.ask.answer_question), just proving none of these golden questions crash
    # or get refused for a trivially-supported answer.
    assert body["refused_count"] == 0
