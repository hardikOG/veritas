"""Fixed algorithmic parameters — not deployment knobs.

These are design-time constants baked into how Veritas's algorithms behave, as
opposed to core/config.py's Settings, which holds values a deployer might reasonably
override per environment (connection strings, thresholds, model choice). Chunk size
and overlap here are the starting point for Phase 1's sliding-window chunker and may
be revisited when Phase 5 tunes the system, but they are not meant to vary between
dev/staging/prod the way an env var would.
"""

# Sliding-window chunker (Phase 1)
DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 64

# Input guard for /search and /ask (Phase 2/3)
MAX_QUERY_LENGTH = 2000
