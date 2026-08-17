"""Deterministic FakeLLMClient — no network calls, used in all tests per the
project's testing rule (only the LLM gets a Fake; the embedder uses the real
small local model, per embedding/sentence_transformer.py).
"""

from llm.base import ContextChunk


class FakeLLMClient:
    """Returns a canned or deterministically-derived cited answer.

    Purpose: lets the verifier, the /ask endpoint, and DB logging be tested without
        a network call or an ANTHROPIC_API_KEY. Default behavior cites the first
        context chunk's content verbatim, which is guaranteed to pass verification
        (a chunk's content trivially has cosine similarity ~1.0 with itself) —
        construct with `canned_answer` to exercise other paths, e.g. an answer that
        cites real chunk_ids but with unrelated text, to test the refuse path.
    """

    def __init__(self, canned_answer: str | None = None) -> None:
        self._canned_answer = canned_answer

    def generate_cited_answer(self, question: str, context: list[ContextChunk]) -> str:
        """Return the canned answer if set, else a trivially-supported default.

        Purpose: see class docstring.
        Inputs: question — ignored by the default behavior; context — used to build
            the default verbatim-citation answer.
        Outputs: raw answer text in the same `[cite:CHUNK_ID]` format a real
            LLMClient must produce.
        Complexity: O(1).
        Failure cases: none.
        """
        if self._canned_answer is not None:
            return self._canned_answer
        if not context:
            return "I don't have enough information to answer this question. [cite:none]"
        first = context[0]
        return f"{first.content} [cite:{first.chunk_id}]"
