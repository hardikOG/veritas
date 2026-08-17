"""LLMClient interface — lets the answer-generation model be swapped without
touching the verifier or the /ask endpoint. Mirrors embedding/base.py's Embedder
protocol.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ContextChunk:
    """One retrieved chunk, as shown to the LLM for grounding its answer."""

    chunk_id: str
    content: str


class LLMClient(Protocol):
    """Anything that can generate a per-sentence-cited answer from context."""

    def generate_cited_answer(self, question: str, context: list[ContextChunk]) -> str:
        """Generate an answer to `question`, grounded only in `context`.

        Purpose: the sole LLM operation the verifier depends on. The returned text
            must mark every sentence with a citation in the exact form
            `[cite:CHUNK_ID]` immediately after that sentence, referencing one of
            `context`'s chunk_ids — see verifier/parse.py, which parses this format.
        Inputs: question — the user's question; context — retrieved chunks to
            ground the answer in, in no particular required order.
        Outputs: raw answer text with inline `[cite:CHUNK_ID]` markers. If the
            context is insufficient to answer, implementations should say so in a
            single sentence marked `[cite:none]` rather than fabricating a citation.
        Complexity: implementation-defined (network call for a real LLM).
        Failure cases: implementation-defined.
        """
        ...
