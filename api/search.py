"""GET /search — hybrid retrieval, returning fused top-k results with provenance."""

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import get_db
from core.config import get_settings
from core.constants import MAX_QUERY_LENGTH
from embedding.sentence_transformer import get_embedder
from retrieval.hybrid import hybrid_search

router = APIRouter()
settings = get_settings()


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1, max_length=MAX_QUERY_LENGTH),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Hybrid (BM25 + dense) search over ingested chunks, fused with RRF.

    Purpose: the Phase 2 read path — embeds the query, runs BM25 and dense
        retrieval independently, and returns the RRF-fused top-k with per-signal
        rank provenance so a caller can see why a result ranked where it did.
    Inputs: q — the query string (1..MAX_QUERY_LENGTH chars, enforced by FastAPI's
        Query validation before this function runs); db — injected session.
    Outputs: {"query", "results": [{"chunk_id", "document_id", "content", "score",
        "bm25_rank", "dense_rank"}, ...]}, best result first. An empty list is a
        valid (not error) response for a query matching nothing.
    Complexity: one embedding call plus two index-assisted Postgres queries,
        O(top_k log top_k) each.
    Failure cases: FastAPI returns 422 automatically if q is empty or too long,
        before this function runs.
    """
    embedder = get_embedder(settings)
    results = hybrid_search(db, embedder, q, top_k=settings.rerank_top_k, rrf_k=settings.rrf_k)
    return {
        "query": q,
        "results": [
            {
                "chunk_id": r.chunk_id,
                "document_id": r.document_id,
                "content": r.content,
                "score": r.score,
                "bm25_rank": r.bm25_rank,
                "dense_rank": r.dense_rank,
            }
            for r in results
        ],
    }
