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

# Supported upload types (Phase 1). Lives here, not in ingestion/extract.py, so both
# api (upload validation) and worker (extraction) can import it without the api
# process pulling in ingestion's heavier dependencies (pypdf, sentence-transformers).
EXTENSION_TO_MIME: dict[str, str] = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
}
SUPPORTED_MIME_TYPES = frozenset(EXTENSION_TO_MIME.values())

# Celery task name, shared by the api (dispatches via send_task by name, without
# importing the task itself — see worker/celery_app.py) and the worker (registers
# under this exact name). A single source of truth avoids the two silently drifting
# if the task is ever renamed or moved.
TASK_INGEST_DOCUMENT = "ingestion.tasks.ingest_document"
