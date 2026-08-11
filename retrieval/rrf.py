"""Reciprocal Rank Fusion — pure function, independent of BM25/dense specifics.

Cold-rebuild target (Phase 2) — see docs/private/rebuild_targets.md.
"""

from collections.abc import Sequence


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]],
    k: int = 60,
) -> list[tuple[str, float]]:
    """Fuse multiple rankings of the same item ids into one score-sorted ranking.

    Purpose: combines independent rankings (e.g. BM25 full-text rank and dense
        cosine-similarity rank) into a single fused order, without needing the two
        signals to share a comparable scale — RRF only uses each item's *position*
        in each ranking, never the raw scores.
    Inputs: rankings — a sequence of rankings, each an ordered sequence of item ids
        (best match first); an item missing from a given ranking simply contributes
        nothing from that ranking, rather than being penalized with a worst-case
        rank. k — the RRF constant (default 60, the standard value from the original
        RRF paper); higher k flattens the influence of rank differences.
    Outputs: a list of (item_id, fused_score) pairs, sorted by fused_score
        descending. An item's fused_score is `sum(1 / (k + rank))` over every
        ranking it appears in, rank being 1-indexed.
    Complexity: O(n log n), n = total (ranking, item) pairs across all rankings.
    Failure cases: none — an empty `rankings` (or all-empty individual rankings)
        yields an empty result, not an error.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item_id in enumerate(ranking, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
