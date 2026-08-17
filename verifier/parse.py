"""Parses an LLM's [cite:CHUNK_ID]-marked answer into individual cited sentences."""

import re
from dataclasses import dataclass

_CITATION_PATTERN = re.compile(r"(.+?)\s*\[cite:\s*([^\]\s]+)\]", re.DOTALL)


@dataclass(frozen=True)
class CitedSentence:
    """One sentence from the LLM's answer, with the chunk id it claims to cite."""

    text: str
    chunk_id: str


def parse_cited_sentences(raw_answer: str) -> list[CitedSentence]:
    """Split a raw LLM answer into (sentence, cited chunk_id) pairs.

    Purpose: the LLM's output contract (see llm/base.py's LLMClient protocol) marks
        every sentence with a trailing `[cite:CHUNK_ID]` marker; this turns that raw
        text into structured claims the verifier can check one at a time.
    Inputs: raw_answer — LLM output text, zero or more `<sentence> [cite:ID]`
        segments in sequence. Tolerates whitespace between `cite:` and the id
        (`[cite: ID]`, not just `[cite:ID]`) — different LLMs format this
        inconsistently even when explicitly prompted for the exact form.
    Outputs: ordered list of CitedSentence. A sentence marked `[cite:none]` (the
        LLM's own "insufficient context" signal) is dropped, not included as a
        claim — an empty result list means the LLM found nothing to cite, which the
        caller treats as an immediate refuse. Leading sentence-ending punctuation
        (`.`, `!`, `?`) is stripped from each captured text — when an LLM places a
        citation marker before a sentence's own trailing period rather than after
        it (`"...data [cite:ID]. In this role..."` instead of the prompted
        `"...data. [cite:ID] In this role..."`), that stray period would otherwise
        leak onto the front of the *next* claim's text, degrading its embedding
        similarity for a reason that has nothing to do with whether the claim is
        actually supported.
    Complexity: O(n) in the length of raw_answer (single regex scan).
    Failure cases: none — malformed text with no citation markers at all yields an
        empty list, not an error.
    """
    sentences = []
    for match in _CITATION_PATTERN.finditer(raw_answer):
        text = match.group(1).strip().lstrip(".!? ").strip()
        chunk_id = match.group(2).strip()
        if text and chunk_id.lower() != "none":
            sentences.append(CitedSentence(text=text, chunk_id=chunk_id))
    return sentences
