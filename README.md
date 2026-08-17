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

## Architecture

Two Python processes, no more:

- **`api`** (FastAPI) — the synchronous read/write surface: accepts uploads,
  serves hybrid search, generates and verifies answers, runs the eval harness.
  Embeds query text in-process (small local model, no network dependency at
  request time).
- **`worker`** (Celery, Redis as broker + result backend) — the async write
  path: extracts text, chunks it, embeds it, writes it. Kept separate from
  `api` so PDF parsing and embedding never block a request, and so the two
  processes can be scaled independently.
- **Postgres + `pgvector`** — the only datastore. Full-text search
  (`tsvector`/`ts_rank`) and dense vector search (`pgvector`'s HNSW index)
  both live in the same database, queried independently and fused with
  Reciprocal Rank Fusion — no separate search engine.

```
upload ──> api ──(enqueue)──> worker ──> extract/chunk/embed ──> postgres
                                                                     │
question ──> api ──(hybrid search: BM25 + dense, RRF-fused)─────────┘
                 └──(LLM answer, per-sentence cited)──> verifier ──> cite-or-refuse
```

**Cite-or-refuse**, the core differentiator: the LLM is asked to cite every
sentence of its answer against a specific retrieved chunk. Each cited sentence
is independently re-embedded and checked (cosine similarity) against the
chunk it actually cited — not the best-matching chunk in context, the one it
named. Sentences that fail are stripped; if too many fail, the whole answer is
withheld rather than shown degraded.

## API surface

```bash
# Upload a document (txt/md/pdf) for async ingestion
curl -X POST http://localhost:8000/documents -F "file=@doc.txt"

# Poll ingestion status
curl http://localhost:8000/documents/{id}

# Hybrid search — fused BM25 + dense retrieval, with per-result provenance
curl "http://localhost:8000/search?q=your+query"

# Ask a question — cited answer, or an explicit refusal
curl -X POST http://localhost:8000/ask -H "Content-Type: application/json" \
  -d '{"question": "your question"}'

# Score the golden set (requires `make eval-seed` first)
curl -X POST http://localhost:8000/eval/run

# Liveness/readiness
curl http://localhost:8000/health
```

## Running the eval harness

The eval harness scores retrieval quality and answer faithfulness against a
small, version-controlled golden Q&A set (`eval/golden_set.py` +
`eval/fixtures/`) — the same numbers reported below.

```bash
cp .env.example .env   # add your ANTHROPIC_API_KEY
make up
make eval-seed         # ingests eval/fixtures/, populates eval_golden (worker image)
make eval-run           # POST /eval/run, pretty-printed
```

`POST /eval/run` calls the exact same answer-generation path `POST /ask` uses
(not a separate simulation of it), so the reported numbers reflect what the
deployed system actually does.

**Tuning the verifier:** `VERIFIER_THRESHOLD` (minimum cosine similarity for a
claim to count as supported) and `VERIFIER_MAX_FAILED_RATIO` (refuse if more
than this fraction of claims fail) are both plain env vars — see
`.env.example`. To tune: change one, `docker compose up -d --build api`
(Settings are read at process startup), re-run `make eval-run`, and compare
`mean_faithfulness`/`refused_count` against the previous run. A lower
threshold raises faithfulness by accepting looser matches (more false
positives slip through); a higher one raises `refused_count` (fewer false
positives, but more true answers withheld too) — there's no single correct
value independent of what the measured numbers actually show.

## Performance

Measured via the eval harness above, against `eval/golden_set.py`'s golden
questions — never asserted ahead of measurement. **Pending a funded Anthropic
API key**; this section will report real numbers once available.

| Metric | Value |
| --- | --- |
| Recall@8 | _pending_ |
| MRR | _pending_ |
| Mean faithfulness | _pending_ |
| p95 latency | _pending_ |

## Deploying

`render.yaml` deploys `api`, `worker`, `redis`, and `postgres` (with
`pgvector`) to Render as a single Blueprint. See `docs/DEPLOY.md`.

## Status

Phases 0-4 and 6 complete: infrastructure, async ingestion, hybrid retrieval,
cite-or-refuse verification, the eval harness, and Render deploy scaffolding
are all built, tested, and verified against the real Docker images. Phase 5
(threshold tuning from real eval measurements, and the numbers above) is
blocked on a funded `ANTHROPIC_API_KEY` — see `MANUAL_TODO.md`.
