"""Cite-or-refuse verification: strip unsupported claims, refuse if too many fail.

Cold-rebuild target (Phase 3) — see docs/private/rebuild_targets.md.
"""

import math
from dataclasses import dataclass

from verifier.parse import CitedSentence


@dataclass(frozen=True)
class VerifiedClaim:
    """One claim (sentence + cited chunk) after similarity checking."""

    text: str
    chunk_id: str
    similarity: float
    supported: bool


@dataclass(frozen=True)
class VerificationResult:
    """The outcome of verifying a full answer's claims."""

    claims: list[VerifiedClaim]
    refused: bool
    confidence: float


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors.

    Purpose: the core similarity metric between a claim's embedding and its cited
        chunk's stored embedding.
    Inputs: a, b — vectors of the same length (embedding dimension).
    Outputs: a float in [-1, 1] (in practice ~[0, 1] for sentence embeddings of
        related text). Returns 0.0 for a zero vector rather than dividing by zero.
    Complexity: O(n), n = vector length.
    Failure cases: none — a mismatched length raises naturally from the zip below
        rather than silently truncating.
    """
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def verify_claims(
    cited_sentences: list[CitedSentence],
    claim_embeddings: list[list[float]],
    chunk_embeddings: dict[str, list[float]],
    threshold: float,
    max_failed_ratio: float,
) -> VerificationResult:
    """Check each claim against its cited chunk; refuse the whole answer if too
    many claims fail.

    Purpose: the cite-or-refuse guarantee itself. Each claim is checked
        independently (sentence-level granularity — see
        docs/private/ARCHITECTURE_LEDGER.md for why this is the atomic unit, not
        sub-sentence clauses) against the specific chunk it cited, not against the
        retrieved context as a whole — a claim citing a real but wrong chunk fails
        exactly as a claim citing a fabricated chunk_id does (chunk_embeddings.get()
        returns None for either, treated identically as unsupported).
    Inputs: cited_sentences — parsed claims; claim_embeddings — one embedding per
        cited_sentences entry, same order (the caller embeds the claim text);
        chunk_embeddings — chunk_id -> stored embedding, for every chunk that was
        actually shown to the LLM; threshold — minimum cosine similarity for a
        claim to count as supported; max_failed_ratio — refuse if more than this
        fraction of claims fail.
    Outputs: VerificationResult. `claims` always contains every input claim
        (including unsupported ones, each flagged) so a caller can inspect exactly
        what was stripped. `refused=True` means the answer as a whole must not be
        shown to the user, regardless of which individual claims passed.
        `confidence` is the supported fraction, in [0, 1] — 0.0 when there are no
        claims at all (an immediate refuse, not a division by zero).
    Complexity: O(n * d), n = claim count, d = embedding dimension.
    Failure cases: none raised — a chunk_id with no matching entry in
        chunk_embeddings (hallucinated or mismatched citation) is treated as
        similarity 0.0 / unsupported, not an error.
    """
    claims = []
    for sentence, embedding in zip(cited_sentences, claim_embeddings, strict=True):
        chunk_embedding = chunk_embeddings.get(sentence.chunk_id)
        similarity = (
            0.0 if chunk_embedding is None else cosine_similarity(embedding, chunk_embedding)
        )
        claims.append(
            VerifiedClaim(
                text=sentence.text,
                chunk_id=sentence.chunk_id,
                similarity=similarity,
                supported=similarity >= threshold,
            )
        )

    if not claims:
        return VerificationResult(claims=[], refused=True, confidence=0.0)

    supported_count = sum(1 for c in claims if c.supported)
    failed_ratio = 1 - (supported_count / len(claims))

    return VerificationResult(
        claims=claims,
        refused=failed_ratio > max_failed_ratio,
        confidence=supported_count / len(claims),
    )
