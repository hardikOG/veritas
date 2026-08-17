"""Unit tests for eval/metrics.py — pure functions, no DB dependency.

Cold-rebuild target (Phase 4): see docs/private/rebuild_targets.md.
"""

from eval.metrics import faithfulness_ratio, p95, recall_at_k, reciprocal_rank


def test_recall_at_k_full_hit_when_single_expected_chunk_is_in_top_k() -> None:
    retrieved = ["a", "b", "c", "d"]
    assert recall_at_k(retrieved, ["c"], k=3) == 1.0


def test_recall_at_k_miss_when_expected_chunk_is_outside_top_k() -> None:
    retrieved = ["a", "b", "c", "d"]
    assert recall_at_k(retrieved, ["d"], k=2) == 0.0


def test_recall_at_k_partial_hit_with_multiple_expected_chunks() -> None:
    retrieved = ["a", "b", "c", "d"]
    # only "a" of the two expected chunks is within top_k=2 -> 1/2
    assert recall_at_k(retrieved, ["a", "d"], k=2) == 0.5


def test_recall_at_k_empty_expected_is_a_miss_not_a_free_pass() -> None:
    assert recall_at_k(["a", "b"], [], k=5) == 0.0


def test_reciprocal_rank_first_position_is_one() -> None:
    assert reciprocal_rank(["a", "b", "c"], ["a"]) == 1.0


def test_reciprocal_rank_third_position_is_one_third() -> None:
    assert reciprocal_rank(["a", "b", "c"], ["c"]) == 1 / 3


def test_reciprocal_rank_zero_when_expected_chunk_never_appears() -> None:
    assert reciprocal_rank(["a", "b", "c"], ["z"]) == 0.0


def test_reciprocal_rank_uses_earliest_matching_rank_with_multiple_expected() -> None:
    # "b" (rank 2) should win over "c" (rank 3) since it appears first
    assert reciprocal_rank(["a", "b", "c"], ["c", "b"]) == 1 / 2


def test_faithfulness_ratio_is_the_mean_of_confidences() -> None:
    assert faithfulness_ratio([1.0, 0.5, 0.0]) == 0.5


def test_faithfulness_ratio_empty_list_is_zero_not_nan() -> None:
    assert faithfulness_ratio([]) == 0.0


def test_p95_of_hundred_values_is_the_95th_smallest() -> None:
    latencies = list(range(1, 101))  # 1..100
    assert p95(latencies) == 95.0


def test_p95_small_list_does_not_go_out_of_bounds() -> None:
    assert p95([10, 20, 30]) == 30.0


def test_p95_empty_list_is_zero() -> None:
    assert p95([]) == 0.0
