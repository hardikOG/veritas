"""Environment-driven settings for all Veritas processes (api, worker)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, validated view of Veritas's environment configuration.

    Purpose: single source of truth for every deployment-tunable value in Veritas,
        loaded from environment variables (or a local .env file) so nothing is
        hardcoded. Values that are algorithmic constants rather than deployment knobs
        (chunk size, max query length) live in core/constants.py instead.
    Inputs: none directly — populated by pydantic-settings from the process environment.
    Outputs: n/a (this is a data container).
    Complexity: O(1) — read once per process via get_settings().
    Failure cases: pydantic raises a ValidationError at process startup if a required
        variable is missing or malformed; there is no silent fallback for connection URLs.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Core infra
    app_name: str = "veritas"
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://veritas:veritas@localhost:5432/veritas"
    redis_url: str = "redis://localhost:6379/0"

    # Embedding (Phase 1 onward)
    embed_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    # Must match the embedder's actual output dimension: baked into the pgvector
    # column at migration time (see migrations/versions/0001_initial.py), so changing
    # this after the initial migration has run requires a new migration, not just an
    # env var change.
    vector_dim: int = 384

    # Hybrid retrieval (Phase 2 onward)
    rerank_top_k: int = 8
    rrf_k: int = 60

    # Cite-or-refuse verifier (Phase 3 onward)
    verifier_threshold: float = 0.62
    verifier_max_failed_ratio: float = 0.4

    # LLM (Phase 3 onward)
    anthropic_api_key: str | None = None
    llm_model: str = "claude-sonnet-4-6"

    # Async ingestion (Phase 1 onward)
    celery_concurrency: int = 2
    storage_dir: str = "/data/uploads"
    ingest_max_retries: int = 5


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings instance, constructed once and cached.

    Purpose: dependency-injectable settings accessor — avoids a module-level mutable
        singleton while still avoiding re-parsing the environment on every call.
    Inputs: none.
    Outputs: a Settings instance.
    Complexity: O(1) amortized (cached after first call).
    Failure cases: propagates pydantic ValidationError on first call if env is invalid.
    """
    return Settings()
