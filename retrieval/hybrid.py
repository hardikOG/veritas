"""Hybrid retrieval: BM25 (Postgres tsvector/ts_rank) + dense (pgvector), fused with RRF."""

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from embedding.base import Embedder
from models import Chunk
from retrieval.rrf import reciprocal_rank_fusion


@dataclass(frozen=True)
class SearchResult:
    """One fused search hit, with enough provenance to see how it was ranked."""

    chunk_id: str
    document_id: str
    content: str
    score: float
    bm25_rank: int | None
    dense_rank: int | None
    # The chunk's own stored embedding — already fetched internally to build this
    # result, exposed here so Phase 3's verifier can reuse it (compare a claim's
    # embedding against its cited chunk) without a second DB round-trip. Not
    # included in GET /search's JSON response (api/search.py omits it) — a raw
    # embedding vector is not useful in a REST response for humans/grep.
    embedding: list[float] | None


def hybrid_search(
    session: Session,
    embedder: Embedder,
    query: str,
    top_k: int,
    rrf_k: int,
) -> list[SearchResult]:
    """Run BM25 and dense retrieval independently, then fuse with RRF.

    Purpose: the Phase 2 read path backing GET /search (and, in Phase 3, the
        retrieval step of POST /ask). Runs two independent rankings over the same
        candidate pool size, then combines them via reciprocal_rank_fusion so
        neither signal dominates just because its raw scores happen to have a wider
        numeric range.
    Inputs: session — DB session; embedder — anything satisfying the Embedder
        protocol, used only to embed the query text; query — the search string
        (already length-validated by the caller); top_k — how many candidates each
        of BM25/dense contributes, and how many fused results are returned; rrf_k —
        the RRF constant (see retrieval/rrf.py).
    Outputs: fused results, best first, each carrying its own bm25_rank/dense_rank
        (None if it didn't appear in that ranking) for provenance/debugging.
    Complexity: O(top_k log top_k) for each Postgres query (index-assisted), plus
        O(n log n) for the fusion itself, n = 2*top_k at most.
    Failure cases: none raised here — a query matching nothing in either ranking
        yields an empty list, not an error.
    """
    bm25_ids = _bm25_candidate_ids(session, query, top_k)
    dense_ids = _dense_candidate_ids(session, embedder, query, top_k)
    fused = reciprocal_rank_fusion([bm25_ids, dense_ids], k=rrf_k)[:top_k]
    if not fused:
        return []

    bm25_rank_by_id = {chunk_id: rank for rank, chunk_id in enumerate(bm25_ids, start=1)}
    dense_rank_by_id = {chunk_id: rank for rank, chunk_id in enumerate(dense_ids, start=1)}
    chunks_by_id = _fetch_chunks(session, [chunk_id for chunk_id, _ in fused])

    results = []
    for chunk_id, score in fused:
        chunk = chunks_by_id.get(chunk_id)
        if chunk is None:
            continue  # defensive: a chunk deleted between fusion and fetch
        results.append(
            SearchResult(
                chunk_id=chunk_id,
                document_id=str(chunk.document_id),
                content=chunk.content,
                score=score,
                bm25_rank=bm25_rank_by_id.get(chunk_id),
                dense_rank=dense_rank_by_id.get(chunk_id),
                embedding=_to_float_list(chunk.embedding),
            )
        )
    return results


def _bm25_candidate_ids(session: Session, query: str, limit: int) -> list[str]:
    """Sparse (full-text) candidate ids, best ts_rank first."""
    tsquery = func.plainto_tsquery("english", query)
    rows = (
        session.execute(
            select(Chunk.id)
            .where(Chunk.tsv.op("@@")(tsquery))
            .order_by(func.ts_rank(Chunk.tsv, tsquery).desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [str(row) for row in rows]


def _dense_candidate_ids(session: Session, embedder: Embedder, query: str, limit: int) -> list[str]:
    """Dense (embedding cosine-distance) candidate ids, closest first."""
    query_vector = embedder.embed([query])[0]
    rows = (
        session.execute(
            select(Chunk.id)
            .where(Chunk.embedding.is_not(None))
            .order_by(Chunk.embedding.cosine_distance(query_vector))
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [str(row) for row in rows]


def _to_float_list(embedding: Iterable[float] | None) -> list[float] | None:
    """Convert a pgvector-returned embedding to a list of native Python floats.

    Purpose: pgvector.sqlalchemy returns embeddings as a numpy array; plain
        `list(array)` yields `numpy.float32` scalars, not native floats, which
        silently breaks JSON serialization (e.g. writing retrieval_debug to the
        queries table's JSONB column) even though it looks like a normal list at a
        glance. `.tolist()` converts recursively to native types; this falls back
        to a plain `list()` if the value isn't a numpy array (e.g. already a plain
        list, from a different pgvector/driver version).
    Inputs: embedding — whatever Chunk.embedding deserializes to, or None.
    Outputs: a list[float] of native Python floats, or None.
    Complexity: O(n), n = embedding dimension.
    Failure cases: none.
    """
    if embedding is None:
        return None
    tolist = getattr(embedding, "tolist", None)
    return tolist() if callable(tolist) else list(embedding)


def _fetch_chunks(session: Session, chunk_ids: list[str]) -> dict[str, Chunk]:
    """Fetch full Chunk rows for a set of ids, keyed by string id."""
    if not chunk_ids:
        return {}
    rows = session.execute(select(Chunk).where(Chunk.id.in_(chunk_ids))).scalars().all()
    return {str(row.id): row for row in rows}
