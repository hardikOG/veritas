# Veritas

Veritas is a self-verifying Retrieval-Augmented Generation (RAG) engine built to answer questions from documents with measurable grounding.

Unlike conventional RAG systems that stop after retrieval and generation, Veritas verifies every generated claim against the source material it cites. Unsupported claims are removed automatically, and if too much of an answer cannot be verified, the system refuses to answer rather than guess.

## Key Features

* **Hybrid retrieval** — dense vector search and PostgreSQL full-text search fused with Reciprocal Rank Fusion (RRF)
* **Citation-enforced answers** — generated responses must cite supporting source chunks
* **Self-verification pipeline** — cited claims are independently checked before being returned
* **Refusal over hallucination** — unsupported answers are withheld rather than shown
* **Built-in evaluation harness** — measures retrieval quality and answer faithfulness against a labeled dataset
* **Simple deployment model** — FastAPI, Celery, PostgreSQL, pgvector, Redis, Docker, and Render support

---

## Why Veritas?

Most RAG systems treat retrieval as the final safeguard against hallucinations.

Veritas adds a second safeguard: verification.

After retrieval, the model generates a cited answer. Each cited claim is then checked against the exact source chunk it references. Claims that cannot be substantiated are removed. If verification confidence falls below a configurable threshold, the system refuses the answer entirely.

> Better to return no answer than a confident but unsupported one.

---

## Requirements

* Docker + Docker Compose
* Python 3.11 (for local testing and development tooling)

---

## Quickstart

```bash
cp .env.example .env
make up
```

This starts four services:

| Service    | Purpose                                      |
| ---------- | -------------------------------------------- |
| `api`      | FastAPI application                          |
| `worker`   | Async ingestion pipeline                     |
| `postgres` | Storage, vector search, and full-text search |
| `redis`    | Task queue and result backend                |

Once the API health check passes:

```text
http://localhost:8000
```

---

## Migrations

Schema changes are managed with Alembic:

```bash
make migrate
```

This applies all pending migrations, including enabling the `pgvector` extension on first startup.

---

## Tests

```bash
pip install -r requirements-dev.txt
make test
```

Health-check tests require reachable PostgreSQL and Redis instances, either through `make up` or a CI services configuration.

---

## Health Endpoint

```bash
curl http://localhost:8000/health
```

Returns:

```json
{
  "status": "healthy",
  "database": "ok",
  "redis": "ok",
  "version": "..."
}
```

when all dependencies are reachable, or `503 Service Unavailable` with the failing dependency identified.

---

## Architecture

Veritas intentionally keeps the architecture simple.

### Components

* **API (FastAPI)** — document uploads, search, question answering, and evaluation
* **Worker (Celery)** — extraction, chunking, embedding, and ingestion
* **PostgreSQL + pgvector** — metadata, vectors, and full-text search in a single datastore
* **Redis** — task broker and result backend

### Data Flow

```text
upload
  │
  ▼
api ── enqueue ──► worker ──► extract/chunk/embed ──► postgres
                                                          │
                                                          ▼
question ──► hybrid retrieval (BM25 + dense + RRF)
                    │
                    ▼
              answer generation
                    │
                    ▼
                verification
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
      verified            refused
       answer             answer
```

### Retrieval

Veritas combines:

1. Dense vector retrieval using `pgvector`
2. PostgreSQL full-text search using `tsvector` and `ts_rank`

Results are merged using Reciprocal Rank Fusion (RRF), allowing semantic and keyword retrieval to complement one another without requiring a separate search engine.

### Verification

Verification is the core differentiator.

1. Retrieve supporting chunks.
2. Generate a cited answer.
3. Re-embed each answer claim.
4. Compare it against the specific chunk it cites.
5. Remove unsupported claims.
6. Refuse the answer if too many claims fail verification.

This makes citations enforceable rather than merely decorative.

---

## API Surface

### Upload a Document

```bash
curl -X POST http://localhost:8000/documents \
  -F "file=@document.pdf"
```

Supported formats:

* TXT
* Markdown
* PDF

### Check Ingestion Status

```bash
curl http://localhost:8000/documents/{id}
```

### Search

```bash
curl "http://localhost:8000/search?q=your+query"
```

Returns hybrid retrieval results with provenance information.

### Ask a Question

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"your question"}'
```

Returns either:

* A verified, cited answer
* An explicit refusal when verification requirements are not met

### Run Evaluation

```bash
curl -X POST http://localhost:8000/eval/run
```

### Health Check

```bash
curl http://localhost:8000/health
```

---

## Evaluation Harness

Veritas includes a built-in evaluation harness for measuring retrieval quality and answer faithfulness against a version-controlled golden dataset.

```bash
cp .env.example .env

make up
make eval-seed
make eval-run
```

The evaluation pipeline uses the same retrieval, generation, and verification path exposed through the public API, ensuring benchmark results reflect actual runtime behavior.

### Verification Configuration

| Variable                    | Purpose                                                                 |
| --------------------------- | ----------------------------------------------------------------------- |
| `VERIFIER_THRESHOLD`        | Minimum cosine similarity required for a claim to count as supported    |
| `VERIFIER_MAX_FAILED_RATIO` | Refuse an answer if more than this fraction of claims fail verification |

After changing either value:

```bash
docker compose up -d --build api
make eval-run
```

Re-run the evaluation harness and compare results before adopting new settings.

---

## Performance

Veritas includes a reproducible benchmark suite for measuring:

* Recall@K
* Mean Reciprocal Rank (MRR)
* Answer faithfulness
* Refusal rate
* Latency

Benchmark reports, methodology, and experimental results are documented in `benchmark_report.md`.

Because model choice, dataset size, and verification thresholds can materially affect results, benchmark data is reported separately from the README and should be interpreted within the context of the specific evaluation configuration used.

---

## Deployment

`render.yaml` deploys:

* API
* Worker
* Redis
* PostgreSQL with pgvector

as a single Render Blueprint.

See `docs/DEPLOY.md` for deployment instructions.

---

## Status

### Completed

* Infrastructure and containerization
* Async document ingestion
* Hybrid retrieval (dense + full-text + RRF)
* Citation-enforced answer generation
* Claim verification and refusal logic
* Evaluation harness
* Render deployment scaffolding

### Future Work

* Expand the evaluation dataset
* Benchmark across multiple model backends
* Refine verification behavior using evaluation-driven tuning
* Add additional retrieval and ranking experiments

See `MANUAL_TODO.md` for the current roadmap.
