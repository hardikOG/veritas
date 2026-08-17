"""Anthropic-backed LLMClient — the real implementation POST /ask uses in production."""

from functools import lru_cache

import anthropic

from core.config import Settings, get_settings
from llm.base import ContextChunk

_SYSTEM_PROMPT = (
    "You answer questions using ONLY the numbered context chunks provided. "
    "Write your answer as complete sentences. Immediately after EVERY sentence, "
    "add a citation marker in the exact form [cite:CHUNK_ID], using one of the "
    "chunk ids shown in the context. Never cite a chunk id that was not shown to "
    "you. Do not combine multiple unrelated facts into one sentence — one claim "
    "per sentence, one citation per sentence. If the context does not contain "
    "enough information to answer the question, respond with exactly one "
    'sentence: "I don\'t have enough information to answer this question." '
    "followed by [cite:none]."
)


class AnthropicLLMClient:
    """Wraps the Anthropic Messages API behind the LLMClient protocol.

    Purpose: the production answer-generation backend. See llm/base.py for the
        exact output contract the verifier depends on.
    Inputs: api_key — Anthropic API key; model — model id (e.g.
        "claude-sonnet-4-6").
    Outputs: n/a (stateful wrapper around the Anthropic client).
    Complexity: O(1) to construct; each call is one network round-trip.
    Failure cases: raises whatever the `anthropic` SDK raises (auth error, rate
        limit, network failure) — the caller (POST /ask) does not catch these,
        so they surface as a 500, since an LLM failure is not a "refuse" case
        (refuse means the LLM answered but wasn't well-supported, not that it
        couldn't be reached at all).
    """

    def __init__(self, api_key: str, model: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def generate_cited_answer(self, question: str, context: list[ContextChunk]) -> str:
        """Ask Claude to answer `question`, grounded in `context`, with citations.

        Purpose: the real LLMClient.generate_cited_answer implementation.
        Inputs: question, context — see llm/base.py's LLMClient protocol.
        Outputs: raw answer text with [cite:CHUNK_ID] markers, per the system
            prompt's contract.
        Complexity: one network call.
        Failure cases: propagates the Anthropic SDK's own exceptions unchanged.
        """
        context_block = "\n\n".join(f"[{c.chunk_id}]: {c.content}" for c in context)
        user_message = f"Context:\n{context_block}\n\nQuestion: {question}"
        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


@lru_cache
def _load(api_key: str, model: str) -> AnthropicLLMClient:
    """Process-wide cached client, keyed by (api_key, model) so tests/config
    changes can construct a distinct client without restarting the process."""
    return AnthropicLLMClient(api_key=api_key, model=model)


def get_llm_client(settings: Settings | None = None) -> AnthropicLLMClient:
    """Return the process-wide Anthropic LLM client for the configured model.

    Purpose: dependency-injectable accessor mirroring get_embedder()/get_settings().
    Inputs: settings — optional Settings override (defaults to get_settings()).
    Outputs: an AnthropicLLMClient for settings.llm_model.
    Complexity: O(1) amortized after first call.
    Failure cases: none at construction time — the `anthropic` SDK does not
        validate the API key until the first real request.
    """
    settings = settings or get_settings()
    return _load(settings.anthropic_api_key or "", settings.llm_model)
