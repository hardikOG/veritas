"""sentence-transformers-backed Embedder — the concrete implementation Phase 1 ingestion uses."""

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from core.config import Settings, get_settings


class SentenceTransformerEmbedder:
    """Wraps a local `sentence-transformers` model behind the Embedder protocol.

    Purpose: offline, free, deterministic dense embeddings — no network calls once
        the model is downloaded/cached, unlike an API-based embedder.
    Inputs: model_name — a sentence-transformers model id (default from Settings).
    Outputs: n/a (stateful wrapper around the loaded model).
    Complexity: model load is O(model size), done once per process at construction.
    Failure cases: raises whatever `SentenceTransformer(...)` raises if the model
        can't be loaded (bad name, no network on first-ever run with no local cache).
    """

    def __init__(self, model_name: str) -> None:
        self._model = SentenceTransformer(model_name)

    @property
    def dimension(self) -> int:
        return self._model.get_sentence_embedding_dimension()  # type: ignore[return-value]

    @property
    def max_seq_length(self) -> int:
        return int(self._model.max_seq_length)

    @property
    def tokenizer(self):
        """The model's underlying HuggingFace tokenizer (encode/decode), used by
        ingestion/chunk.py to size chunk windows in the same tokens the model
        actually consumes — not part of the Embedder protocol since it's specific to
        this implementation.
        """
        return self._model.tokenizer

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts with the loaded sentence-transformers model.

        Purpose: the sole embedding operation used by ingestion (Phase 1) and later
            retrieval/verification (Phase 2/3).
        Inputs: texts — list of strings to embed, may be empty (returns []).
        Outputs: list of embedding vectors, one per input, each `self.dimension` long.
        Complexity: O(n) in len(texts), batched internally by sentence-transformers.
        Failure cases: none beyond what the underlying model raises on malformed input
            (in practice, arbitrary strings are always accepted).
        """
        if not texts:
            return []
        return self._model.encode(texts, convert_to_numpy=True).tolist()  # type: ignore[union-attr]


@lru_cache
def _load(model_name: str) -> SentenceTransformerEmbedder:
    """Process-wide cached model load, keyed by model name (so tests can swap models)."""
    return SentenceTransformerEmbedder(model_name)


def get_embedder(settings: Settings | None = None) -> SentenceTransformerEmbedder:
    """Return the process-wide embedder for the configured model, loaded once.

    Purpose: dependency-injectable accessor mirroring get_settings() — avoids
        reloading the (relatively expensive to load) model on every call while still
        avoiding a bare module-level singleton.
    Inputs: settings — optional Settings override (defaults to get_settings()).
    Outputs: a SentenceTransformerEmbedder for settings.embed_model.
    Complexity: O(1) amortized after first load per distinct model name.
    Failure cases: propagates SentenceTransformer's load errors on first call.
    """
    settings = settings or get_settings()
    return _load(settings.embed_model)
