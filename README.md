# Veritas

Veritas is a self-verifying Retrieval-Augmented Generation (RAG) engine. Its
differentiator: every claim in every generated answer is checked against the
retrieved source chunks before it reaches the caller. Claims that can't be
substantiated are stripped; if too many fail, the engine refuses to answer rather
than guess. Hybrid retrieval (dense + full-text, fused with Reciprocal Rank Fusion)
feeds the answer stage, and a built-in eval harness scores retrieval quality and
answer faithfulness against a labeled Q&A set.

## Requirements

- Docker + Docker Compose
- Python 3.11 (only needed for running tests/tooling outside containers)

## Quickstart

```bash
cp .env.example .env
make up
```

This builds and starts four services: `api` (FastAPI), `worker` (Celery), `postgres`
(with the `pgvector` extension), and `redis`. The API is available at
`http://localhost:8000` once `api`'s healthcheck passes.

## Migrations

Schema changes are managed with Alembic:

```bash
make migrate
```

This runs `alembic upgrade head` inside the `api` container, applying all pending
migrations (including enabling the `vector` Postgres extension on first run).

## Tests

```bash
pip install -r requirements-dev.txt
make test
```

Health-check tests require a reachable Postgres/Redis (either via `make up` or a CI
services block — see `.github/workflows/ci.yml`).

## Health endpoint

```bash
curl http://localhost:8000/health
```

Returns `200` with `{"status": "healthy", "database": "ok", "redis": "ok", "version": "..."}`
when both dependencies are reachable, or `503` with the specific failing dependency
named if not.

## Status

Under active development. See `CHANGELOG`-equivalent progress in commit history —
Phase 0 (this commit) is infrastructure scaffolding only; ingestion, retrieval, the
verifier, and the eval harness land in subsequent phases.
