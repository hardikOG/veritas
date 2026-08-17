"""Unit tests for parsing the LLM's [cite:CHUNK_ID]-marked answer format."""

from verifier.parse import parse_cited_sentences


def test_empty_answer_yields_no_sentences() -> None:
    assert parse_cited_sentences("") == []


def test_single_sentence_with_citation() -> None:
    result = parse_cited_sentences("PostgreSQL supports full-text search. [cite:abc123]")
    assert len(result) == 1
    assert result[0].text == "PostgreSQL supports full-text search."
    assert result[0].chunk_id == "abc123"


def test_multiple_sentences_with_different_citations() -> None:
    answer = (
        "PostgreSQL supports full-text search. [cite:chunk-a] "
        "It also supports vector similarity via pgvector. [cite:chunk-b]"
    )
    result = parse_cited_sentences(answer)
    assert [s.chunk_id for s in result] == ["chunk-a", "chunk-b"]
    assert result[0].text == "PostgreSQL supports full-text search."
    assert result[1].text == "It also supports vector similarity via pgvector."


def test_cite_none_marker_is_dropped_not_returned_as_a_claim() -> None:
    answer = "I don't have enough information to answer this question. [cite:none]"
    assert parse_cited_sentences(answer) == []


def test_text_with_no_citation_markers_yields_no_sentences() -> None:
    assert parse_cited_sentences("Just some prose with no citations at all.") == []


def test_ignores_leading_or_trailing_whitespace_around_sentence() -> None:
    result = parse_cited_sentences("  PostgreSQL is great.   [cite:xyz]")
    assert result[0].text == "PostgreSQL is great."


def test_tolerates_whitespace_between_cite_colon_and_chunk_id() -> None:
    """Not every LLM formats the marker exactly [cite:ID] with no space, even when
    explicitly prompted for that exact form — [cite: ID] must still parse."""
    result = parse_cited_sentences("Redis keeps data primarily in RAM. [cite: abc123]")
    assert len(result) == 1
    assert result[0].chunk_id == "abc123"


def test_strips_stray_leading_punctuation_from_a_misplaced_citation_marker() -> None:
    """Some LLMs place the citation marker before a sentence's own trailing period
    rather than after it ("...data [cite:a]. Next sentence [cite:b]" instead of
    "...data. [cite:a] Next sentence [cite:b]"). The stray period must not leak
    onto the front of the next claim's text."""
    answer = "First sentence [cite:a]. Second sentence [cite:b]."
    result = parse_cited_sentences(answer)
    assert [s.text for s in result] == ["First sentence", "Second sentence"]
    assert [s.chunk_id for s in result] == ["a", "b"]
