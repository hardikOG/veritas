"""Unit tests for Reciprocal Rank Fusion — pure function, hand-built rankings."""

from retrieval.rrf import reciprocal_rank_fusion


def test_empty_rankings_yield_empty_result() -> None:
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []


def test_single_ranking_preserves_order() -> None:
    fused = reciprocal_rank_fusion([["a", "b", "c"]], k=60)
    assert [item_id for item_id, _ in fused] == ["a", "b", "c"]


def test_item_ranked_high_in_both_rankings_wins() -> None:
    bm25 = ["a", "b", "c"]
    dense = ["a", "c", "b"]
    fused = reciprocal_rank_fusion([bm25, dense], k=60)
    assert fused[0][0] == "a"


def test_fusion_is_not_just_one_signal_passed_through() -> None:
    """The two input rankings disagree enough that neither ranking's raw order is
    the fused order — proves genuine fusion, not one signal dominating.

    bm25 ranks: a=1, b=2, c=3. dense ranks: c=1, a=2, b=3.
    score(a) = 1/61 + 1/62 = 0.032522...  (bm25 rank 1, dense rank 2)
    score(b) = 1/62 + 1/63 = 0.032002...  (bm25 rank 2, dense rank 3)
    score(c) = 1/63 + 1/61 = 0.032266...  (bm25 rank 3, dense rank 1)
    -> fused order a, c, b: not bm25's order (a, b, c), not dense's order (c, a, b).
    """
    bm25 = ["a", "b", "c"]
    dense = ["c", "a", "b"]
    fused_order = [item_id for item_id, _ in reciprocal_rank_fusion([bm25, dense], k=60)]
    assert fused_order == ["a", "c", "b"]
    assert fused_order != bm25
    assert fused_order != dense


def test_one_empty_ranking_does_not_zero_out_the_result() -> None:
    """Skeptic check: if BM25 (or dense) returns nothing, fusion must still surface
    whatever the other ranking found — not silently drop everything."""
    bm25: list[str] = []
    dense = ["p", "q"]
    fused = reciprocal_rank_fusion([bm25, dense], k=60)
    assert [item_id for item_id, _ in fused] == ["p", "q"]


def test_item_present_in_only_one_ranking_is_still_included() -> None:
    bm25 = ["a", "b"]
    dense = ["b", "c"]
    fused_ids = {item_id for item_id, _ in reciprocal_rank_fusion([bm25, dense], k=60)}
    assert fused_ids == {"a", "b", "c"}


def test_item_in_both_rankings_scores_higher_than_item_in_only_one() -> None:
    bm25 = ["shared", "only_bm25"]
    dense = ["shared", "only_dense"]
    fused = dict(reciprocal_rank_fusion([bm25, dense], k=60))
    assert fused["shared"] > fused["only_bm25"]
    assert fused["shared"] > fused["only_dense"]


def test_larger_k_flattens_score_differences() -> None:
    ranking = ["a", "b"]
    fused_small_k = dict(reciprocal_rank_fusion([ranking], k=1))
    fused_large_k = dict(reciprocal_rank_fusion([ranking], k=1000))
    gap_small_k = fused_small_k["a"] - fused_small_k["b"]
    gap_large_k = fused_large_k["a"] - fused_large_k["b"]
    assert gap_small_k > gap_large_k
