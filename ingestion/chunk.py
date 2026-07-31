"""Sliding-window chunker — pure function, unit-tested independently of Celery/DB."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    """One chunk's index and content, prior to embedding."""

    chunk_index: int
    content: str
    token_count: int


def chunk_text(
    text: str,
    tokenizer,
    chunk_size: int,
    overlap: int,
) -> list[TextChunk]:
    """Split text into overlapping, token-bounded windows.

    Purpose: Phase 1's chunker — sized in the embedder's own tokens (not characters
        or words), so a chunk is guaranteed to fit what the embedder will actually
        consume. Callers pass `min(constants.DEFAULT_CHUNK_SIZE, embedder.max_seq_length)`
        as chunk_size (see ingestion/tasks.py) so a chunk is never silently truncated
        by the model.
    Inputs: text — full document text; tokenizer — anything exposing `.encode(str) ->
        list[int]` and `.decode(list[int]) -> str` (the embedder's own HuggingFace
        tokenizer); chunk_size — max tokens per chunk; overlap — tokens repeated
        between consecutive chunks, must be < chunk_size.
    Outputs: ordered list of TextChunk, chunk_index starting at 0. Empty/whitespace-only
        text yields an empty list (nothing to embed, not an error).
    Complexity: O(n) in token count — one encode pass, one decode per chunk.
    Failure cases: raises ValueError if overlap >= chunk_size (would never advance,
        infinite loop) or chunk_size <= 0.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    if not text.strip():
        return []

    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if not token_ids:
        return []

    stride = chunk_size - overlap
    chunks: list[TextChunk] = []
    start = 0
    index = 0
    while start < len(token_ids):
        window = token_ids[start : start + chunk_size]
        chunks.append(
            TextChunk(
                chunk_index=index,
                content=tokenizer.decode(window),
                token_count=len(window),
            )
        )
        index += 1
        start += stride
    return chunks
