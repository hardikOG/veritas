"""Unit tests for the cite-or-refuse verifier — pure function, hand-crafted vectors.

Cold-rebuild target (Phase 3): see docs/private/rebuild_targets.md.
"""

import math

from verifier.parse import CitedSentence
from verifier.verify import cosine_similarity, verify_claims

THRESHOLD = 0.5
MAX_FAILED_RATIO = 0.4


def test_cosine_similarity_identical_vectors_is_one() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_similarity_orthogonal_vectors_is_zero() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_opposite_vectors_is_negative_one() -> None:
    assert cosine_similarity([1.0, 0.0], [-1.0, 0.0]) == -1.0


def test_cosine_similarity_zero_vector_does_not_divide_by_zero() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_verify_claims_empty_input_is_an_immediate_refuse() -> None:
    result = verify_claims([], [], {}, threshold=THRESHOLD, max_failed_ratio=MAX_FAILED_RATIO)
    assert result.refused is True
    assert result.confidence == 0.0
    assert result.claims == []


def test_verify_claims_all_supported_is_not_refused() -> None:
    sentences = [CitedSentence(text="claim one", chunk_id="a")]
    claim_embeddings = [[1.0, 0.0]]
    chunk_embeddings = {"a": [1.0, 0.0]}  # identical -> similarity 1.0
    result = verify_claims(
        sentences, claim_embeddings, chunk_embeddings, THRESHOLD, MAX_FAILED_RATIO
    )
    assert result.refused is False
    assert result.confidence == 1.0
    assert result.claims[0].supported is True


def test_verify_claims_refuses_when_too_many_claims_fail() -> None:
    sentences = [
        CitedSentence(text="claim one", chunk_id="a"),
        CitedSentence(text="claim two", chunk_id="b"),
        CitedSentence(text="claim three", chunk_id="c"),
    ]
    claim_embeddings = [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]]
    chunk_embeddings = {
        "a": [0.0, 1.0],  # orthogonal -> similarity 0.0, unsupported
        "b": [0.0, 1.0],  # orthogonal -> unsupported
        "c": [1.0, 0.0],  # identical -> supported
    }
    # 2/3 fail = 0.667 failed ratio > 0.4 max_failed_ratio -> refused
    result = verify_claims(
        sentences, claim_embeddings, chunk_embeddings, THRESHOLD, MAX_FAILED_RATIO
    )
    assert result.refused is True
    assert math.isclose(result.confidence, 1 / 3)


def test_verify_claims_strips_individual_failing_claims_without_refusing() -> None:
    sentences = [
        CitedSentence(text="supported claim", chunk_id="a"),
        CitedSentence(text="supported claim two", chunk_id="b"),
        CitedSentence(text="unsupported claim", chunk_id="c"),
    ]
    claim_embeddings = [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]]
    chunk_embeddings = {
        "a": [1.0, 0.0],
        "b": [1.0, 0.0],
        "c": [0.0, 1.0],  # orthogonal -> unsupported
    }
    # 1/3 fail = 0.333 <= 0.4 max_failed_ratio -> not refused overall
    result = verify_claims(
        sentences, claim_embeddings, chunk_embeddings, THRESHOLD, MAX_FAILED_RATIO
    )
    assert result.refused is False
    supported_flags = [c.supported for c in result.claims]
    assert supported_flags == [True, True, False]


def test_verify_claims_treats_hallucinated_citation_as_unsupported_not_an_error() -> None:
    """A chunk_id the LLM cited that was never shown to it (or a typo'd id) must be
    treated exactly like a real-but-wrong citation: unsupported, not a crash."""
    sentences = [CitedSentence(text="claim citing a fake chunk", chunk_id="does-not-exist")]
    claim_embeddings = [[1.0, 0.0]]
    chunk_embeddings = {"a": [1.0, 0.0]}  # "does-not-exist" is absent
    result = verify_claims(
        sentences, claim_embeddings, chunk_embeddings, THRESHOLD, MAX_FAILED_RATIO
    )
    assert result.refused is True  # the only claim failed -> 100% failed ratio
    assert result.claims[0].supported is False
    assert result.claims[0].similarity == 0.0
