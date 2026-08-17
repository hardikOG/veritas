"""The golden Q&A spec — human-authored, stable across runs.

Each entry names the fixture document (in eval/fixtures/) that grounds its answer,
not a chunk id directly — chunk ids don't exist until that document is ingested.
eval/seed.py resolves `source_fixture` to real chunk ids after ingesting
eval/fixtures/ into the database.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GoldenSpecEntry:
    """One golden question, before ingestion has assigned it real chunk ids."""

    question: str
    source_fixture: str  # filename under eval/fixtures/
    expected_answer: str


GOLDEN_SET: list[GoldenSpecEntry] = [
    GoldenSpecEntry(
        question="What is PostgreSQL primarily used for?",
        source_fixture="postgresql.txt",
        expected_answer=(
            "PostgreSQL is primarily used as a durable, transactional store for "
            "structured application data."
        ),
    ),
    GoldenSpecEntry(
        question="Where does Redis keep data, and why does that make it fast?",
        source_fixture="redis.txt",
        expected_answer=(
            "Redis keeps data primarily in RAM, which makes reads and writes "
            "extremely fast compared to a disk-backed database."
        ),
    ),
    GoldenSpecEntry(
        question="How does a Celery worker get the tasks it executes?",
        source_fixture="celery.txt",
        expected_answer=(
            "A producer enqueues a task by name onto a message broker, and "
            "worker processes pull tasks off the broker and execute them."
        ),
    ),
    GoldenSpecEntry(
        question="What does the pgvector extension add to PostgreSQL?",
        source_fixture="pgvector.txt",
        expected_answer=(
            "pgvector adds a native vector data type with distance operators for "
            "cosine similarity, L2 distance, and inner product, plus approximate "
            "nearest neighbor indexing such as HNSW."
        ),
    ),
]
