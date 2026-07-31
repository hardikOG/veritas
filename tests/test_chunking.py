"""Unit tests for the pure sliding-window chunker — no DB, no embedder, no Celery."""

import pytest

from ingestion.chunk import chunk_text


class _WhitespaceTokenizer:
    """Fake tokenizer for testing chunk_text without loading a real model. Tokens
    are word indices into the most recently encoded text."""

    def __init__(self) -> None:
        self._words: list[str] = []

    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        self._words = text.split()
        return list(range(len(self._words)))

    def decode(self, token_ids: list[int]) -> str:
        return " ".join(self._words[i] for i in token_ids)


def test_chunk_text_empty_input_yields_no_chunks() -> None:
    assert chunk_text("", _WhitespaceTokenizer(), chunk_size=10, overlap=2) == []
    assert chunk_text("   ", _WhitespaceTokenizer(), chunk_size=10, overlap=2) == []


def test_chunk_text_shorter_than_one_window_yields_single_chunk() -> None:
    chunks = chunk_text("one two three", _WhitespaceTokenizer(), chunk_size=10, overlap=2)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].content == "one two three"
    assert chunks[0].token_count == 3


def test_chunk_text_produces_overlapping_windows() -> None:
    text = " ".join(f"w{i}" for i in range(10))
    chunks = chunk_text(text, _WhitespaceTokenizer(), chunk_size=4, overlap=1)
    assert [c.chunk_index for c in chunks] == [0, 1, 2, 3]
    assert chunks[0].content == "w0 w1 w2 w3"
    assert chunks[1].content == "w3 w4 w5 w6"
    assert chunks[2].content == "w6 w7 w8 w9"
    assert chunks[3].content == "w9"


def test_chunk_text_exact_multiple_of_chunk_size_no_overlap() -> None:
    text = " ".join(f"w{i}" for i in range(6))
    chunks = chunk_text(text, _WhitespaceTokenizer(), chunk_size=3, overlap=0)
    assert [c.content for c in chunks] == ["w0 w1 w2", "w3 w4 w5"]


def test_chunk_text_rejects_overlap_gte_chunk_size() -> None:
    with pytest.raises(ValueError):
        chunk_text("a b c", _WhitespaceTokenizer(), chunk_size=4, overlap=4)


def test_chunk_text_rejects_nonpositive_chunk_size() -> None:
    with pytest.raises(ValueError):
        chunk_text("a b c", _WhitespaceTokenizer(), chunk_size=0, overlap=0)
