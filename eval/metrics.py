"""Pure eval metric functions — retrieval quality, faithfulness, latency.

Cold-rebuild target (Phase 4) — see docs/private/rebuild_targets.md. Kept free of
any DB/network dependency so every metric can be unit-tested with hand-built lists,
independent of eval/runner.py (which supplies the real retrieved/expected ids from
a live golden-set run).
"""

import math
from dataclasses import dataclass


def recall_at_k(retrieved_chunk_ids: list[str], expected_chunk_ids: list[str], k: int) -> float:
    """Fraction of a question's expected chunks that appear in the top-k retrieved.

    Purpose: the standard proportional Recall@k — reduces to a binary hit/miss when
        a question has exactly one expected chunk (the common golden-set case), but
        generalizes correctly to multi-relevant questions.
    Inputs: retrieved_chunk_ids — full ranked retrieval result, best first;
        expected_chunk_ids — the golden set's ground-truth relevant chunk ids for
        this question; k — how many of the top retrieved results count.
    Outputs: a float in [0, 1]. 0.0 (not undefined/NaN) when expected_chunk_ids is
        empty — a question with no recorded ground truth counts as a miss, not a
        free pass, so a badly-seeded golden entry can't inflate the average.
    Complexity: O(k) (top_k membership check is O(1) amortized via a set).
    Failure cases: none.
    """
    if not expected_chunk_ids:
        return 0.0
    top_k = set(retrieved_chunk_ids[:k])
    hits = sum(1 for chunk_id in expected_chunk_ids if chunk_id in top_k)
    return hits / len(expected_chunk_ids)


def reciprocal_rank(retrieved_chunk_ids: list[str], expected_chunk_ids: list[str]) -> float:
    """1 / rank of the first expected chunk found anywhere in the retrieved ranking.

    Purpose: the per-question term averaged into MRR (Mean Reciprocal Rank) across
        the golden set — rewards ranking a relevant chunk near the top, not merely
        including it somewhere in a long list (unlike recall_at_k, this is not
        capped to the top-k; it searches the full retrieved ranking).
    Inputs: retrieved_chunk_ids — full ranked retrieval result, best first (rank 1
        = index 0); expected_chunk_ids — ground-truth relevant chunk ids.
    Outputs: a float in [0, 1]. 0.0 if no expected chunk appears anywhere in
        retrieved_chunk_ids (or expected_chunk_ids is empty).
    Complexity: O(n), n = len(retrieved_chunk_ids), short-circuits on first hit.
    Failure cases: none.
    """
    expected = set(expected_chunk_ids)
    for rank, chunk_id in enumerate(retrieved_chunk_ids, start=1):
        if chunk_id in expected:
            return 1.0 / rank
    return 0.0


def faithfulness_ratio(confidences: list[float]) -> float:
    """Mean per-question faithfulness (verifier confidence) across the golden set.

    Purpose: aggregates verifier/verify.py's per-answer `confidence` (the fraction
        of claims that passed cite-or-refuse verification) into one number for the
        eval report.
    Inputs: confidences — one VerificationResult.confidence per golden question
        (0.0 for a question that was refused before any claim could be checked, per
        verifier/verify.py's own contract).
    Outputs: mean confidence, in [0, 1]. 0.0 for an empty list rather than NaN.
    Complexity: O(n).
    Failure cases: none.
    """
    if not confidences:
        return 0.0
    return sum(confidences) / len(confidences)


def p95(latencies_ms: list[int]) -> float:
    """95th-percentile latency, nearest-rank method.

    Purpose: the eval report's p95 latency figure — deliberately the same
        nearest-rank method a load-test/benchmark report would use, so numbers are
        comparable across this project's docs.
    Inputs: latencies_ms — one latency per golden question, milliseconds.
    Outputs: the 95th-percentile value from latencies_ms (an actual observed value,
        not interpolated). 0.0 for an empty list.
    Complexity: O(n log n) (sorting).
    Failure cases: none.
    """
    if not latencies_ms:
        return 0.0
    ordered = sorted(latencies_ms)
    index = max(0, min(math.ceil(0.95 * len(ordered)) - 1, len(ordered) - 1))
    return float(ordered[index])


@dataclass(frozen=True)
class EvalReport:
    """Aggregate result of running the golden set through the eval harness."""

    question_count: int
    refused_count: int
    mean_recall_at_k: float
    mrr: float
    mean_faithfulness: float
    p95_latency_ms: float
