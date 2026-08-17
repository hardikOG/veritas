"""POST /ask — retrieve, generate a per-sentence-cited answer, verify, cite-or-refuse."""

import time
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.deps import get_db
from core.config import Settings, get_settings
from core.constants import MAX_QUERY_LENGTH
from embedding.base import Embedder
from embedding.sentence_transformer import get_embedder
from llm.anthropic_client import get_llm_client
from llm.base import ContextChunk, LLMClient
from models import Query as QueryLog
from retrieval.hybrid import hybrid_search
from verifier.parse import parse_cited_sentences
from verifier.verify import verify_claims

router = APIRouter()
settings = get_settings()


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=MAX_QUERY_LENGTH)


def get_llm_client_dependency() -> LLMClient:
    """FastAPI dependency wrapping get_llm_client(), so tests can override it with
    a FakeLLMClient via app.dependency_overrides — the real Anthropic client makes
    a network call, which per this project's testing rule tests must never do.
    Shared by POST /ask and POST /eval/run (api/eval.py imports this directly) so
    both routes use the same override target and the same cached client instance.
    """
    return get_llm_client(settings)


@router.post("/ask")
async def ask(
    request: AskRequest,
    db: Session = Depends(get_db),
    llm_client: LLMClient = Depends(get_llm_client_dependency),
) -> dict[str, Any]:
    """Answer a question, citing every claim, refusing if too many claims fail.

    Purpose: the HTTP surface over answer_question() — see that function for the
        actual cite-or-refuse pipeline.
    Inputs: request — {"question": str}; db, llm_client — injected.
    Outputs: {"answer", "citations", "confidence", "refused", "latency_ms"}.
    Complexity: see answer_question().
    Failure cases: FastAPI returns 422 for an empty/oversized question before this
        runs; see answer_question() for the rest.
    """
    embedder = get_embedder(settings)
    return answer_question(db, embedder, llm_client, settings, request.question)


def answer_question(
    db: Session,
    embedder: Embedder,
    llm_client: LLMClient,
    settings: Settings,
    question: str,
) -> dict[str, Any]:
    """The full cite-or-refuse pipeline: retrieve, generate, verify, log.

    Purpose: the cite-or-refuse guarantee end to end — retrieve context, ask the
        LLM for a per-sentence-cited answer, verify each claim against its cited
        chunk's embedding, strip unsupported claims, and refuse the whole answer if
        more than `verifier_max_failed_ratio` of claims fail. Refuses immediately
        (no LLM call) if retrieval finds nothing at all. Shared verbatim by POST
        /ask (api/ask.py's `ask` route) and the eval harness (eval/runner.py) — the
        harness must score this exact pipeline, not a second implementation of it
        that could silently drift out of sync with what POST /ask actually does.
    Inputs: db — DB session; embedder, llm_client — the retrieval/generation
        backends; settings — for top_k/rrf_k/verifier thresholds; question — the
        question text (already length-validated by the caller, if it's an HTTP
        request — eval/runner.py's golden questions are trusted, pre-authored text).
    Outputs: {"answer", "citations", "confidence", "refused", "latency_ms"}.
        `answer` is None when refused. `citations` lists only the claims that
        survived verification. Every call is logged to the `queries` table
        regardless of outcome.
    Complexity: one embedding call for retrieval, one LLM call, one embedding call
        for the claims (batched), O(top_k) DB work.
    Failure cases: LLM failures (network, auth) propagate to the caller — not a
        "refuse", since refuse means the LLM answered but wasn't well-supported.
    """
    start = time.perf_counter()

    results = hybrid_search(
        db, embedder, question, top_k=settings.rerank_top_k, rrf_k=settings.rrf_k
    )

    if not results:
        return _refuse(db, question, start, {"retrieved_chunks": 0})

    context = [ContextChunk(chunk_id=r.chunk_id, content=r.content) for r in results]
    raw_answer = llm_client.generate_cited_answer(question, context)

    cited_sentences = parse_cited_sentences(raw_answer)
    if not cited_sentences:
        return _refuse(
            db, question, start, {"retrieved_chunks": len(results), "raw_answer": raw_answer}
        )

    claim_embeddings = embedder.embed([s.text for s in cited_sentences])
    chunk_embeddings = {r.chunk_id: r.embedding for r in results if r.embedding is not None}

    verification = verify_claims(
        cited_sentences,
        claim_embeddings,
        chunk_embeddings,
        threshold=settings.verifier_threshold,
        max_failed_ratio=settings.verifier_max_failed_ratio,
    )

    debug = {
        "retrieved_chunks": len(results),
        "claims": [
            {"chunk_id": c.chunk_id, "similarity": c.similarity, "supported": c.supported}
            for c in verification.claims
        ],
    }

    if verification.refused:
        return _refuse(db, question, start, debug, confidence=verification.confidence)

    surviving = [c for c in verification.claims if c.supported]
    answer_text = " ".join(c.text for c in surviving)
    citations = [{"chunk_id": c.chunk_id, "similarity": c.similarity} for c in surviving]

    latency_ms = _elapsed_ms(start)
    _log_query(db, question, answer_text, False, verification.confidence, latency_ms, debug)

    return {
        "answer": answer_text,
        "citations": citations,
        "confidence": verification.confidence,
        "refused": False,
        "latency_ms": latency_ms,
    }


def _refuse(
    db: Session,
    question: str,
    start: float,
    debug: dict[str, Any],
    confidence: float = 0.0,
) -> dict[str, Any]:
    """Build and log a refused response — the one path every refuse case shares."""
    latency_ms = _elapsed_ms(start)
    _log_query(db, question, None, True, confidence, latency_ms, debug)
    return {
        "answer": None,
        "citations": [],
        "confidence": confidence,
        "refused": True,
        "latency_ms": latency_ms,
    }


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _log_query(
    db: Session,
    query_text: str,
    answer: str | None,
    refused: bool,
    confidence: float,
    latency_ms: int,
    retrieval_debug: dict[str, Any],
) -> None:
    """Persist one /ask call's outcome to the queries table."""
    db.add(
        QueryLog(
            query_text=query_text,
            answer=answer,
            refused=refused,
            confidence=confidence,
            latency_ms=latency_ms,
            retrieval_debug=retrieval_debug,
        )
    )
    db.commit()
