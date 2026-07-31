"""Embedder interface — lets the dense-vector model be swapped without touching callers."""

from typing import Protocol


class Embedder(Protocol):
    """Anything that turns text into fixed-length dense vectors.

    Purpose: decouples ingestion/retrieval/verification from the specific embedding
        model in use, so `sentence-transformers` can later be swapped for an API-based
        model without changing any caller.
    """

    @property
    def dimension(self) -> int:
        """The fixed length of every vector this embedder produces."""
        ...

    @property
    def max_seq_length(self) -> int:
        """The model's maximum input length in tokens — text beyond this is truncated
        silently by the underlying model, so callers (the chunker in particular) must
        size windows to this, not to an arbitrary constant.
        """
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts.

        Purpose: the one operation every embedder must support.
        Inputs: texts — non-empty strings; behavior on empty strings is
            implementation-defined (sentence-transformers embeds them as a zero-ish
            vector rather than raising).
        Outputs: one vector per input text, each of length `dimension`, same order as
            input.
        Complexity: implementation-defined; the sentence-transformers implementation
            batches internally.
        Failure cases: implementation-defined.
        """
        ...
