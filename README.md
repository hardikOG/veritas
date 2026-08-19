# Veritas

Veritas is a self-verifying Retrieval-Augmented Generation (RAG) engine built to answer questions from documents without hallucinating.

Unlike conventional RAG systems that trust the model's output once retrieval succeeds, Veritas verifies every generated claim against the exact source chunk it cites. Unsupported claims are removed automatically, and if too much of an answer cannot be verified, the system refuses to answer rather than guess.

## Key Features

* **Hybrid retrieval** — dense vector search + PostgreSQL full-text search fused with Reciprocal Rank Fusion (RRF)
* **Citation-enforced generation** — every answer sentence must cite supporting source material
* **Self-verification pipeline** — cited claims are independently checked before being returned
* **Refusal over hallucination** — answers that fail verification are withheld
* **Built-in evaluation harness** — measures retrieval quality and answer faithfulness against a labeled golden dataset
* **Production-ready architecture** — FastAPI, Celery, PostgreSQL + pgvector, Redis, Docker, and Render deployment support

## Why Veritas?

Most RAG systems focus on retrieval quality alone.

Veritas adds a second layer of defense: **verification**.

After retrieval, the model generates a cited answer. Each cited sentence is then checked against the exact chunk it references. Claims that cannot be substantiated are removed. If verification confidence drops below a configurable threshold, Veritas refuses the response entirely.

> Better to return no answer than a confident but unsupported one.

---

## Requirements

* Docker + Docker Compose
* Python 3.11 (optional for local testing and tooling)

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
| `worker`   | Celery ingestion pipeline                    |
| `postgres` | Storage, full-text search, and vector search |
| `redis`    | Task broker and result backend               |

Once the API health check passes, the service is available at:

```text
http://localhost:8000
```

---

## Migrations

Schema changes are managed with Alembic:

```bash
make migrate
```

This applies all pending migrations inside the API container, including enabling the `pgvector` extension on first startup.

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

Veritas intentionally keeps the architecture simple:

* **API (FastAPI)** — document uploads, search, question answering, and evaluation
* **Worker (Celery)** — extraction, chunking, embedding, and ingestion
* **PostgreSQL + pgvector** — single datastore for metadata, vectors, and full-text search
* **Redis** — task broker and result backend

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

Veritas combines two retrieval strategies:

1. **Dense vector search** using `pgvector` HNSW indexes
2. **PostgreSQL full-text search** using `tsvector` and `ts_rank`

Results are merged using **Reciprocal Rank Fusion (RRF)**, allowing semantic and keyword retrieval to complement one another without requiring a separate search engine.

### Verification Pipeline

The verification stage is Veritas's defining feature.

1. Retrieve supporting chunks.
2. Generate a cited answer.
3. Re-embed each answer sentence.
4. Compare it against the specific chunk it cites.
5. Remove unsupported claims.
6. Refuse the entire answer if too many claims fail verification.

This ensures citations are not merely displayed—they are actively enforced.

---

## API Surface

### Upload a document

```bash
curl -X POST http://localhost:8000/documents \
  -F "file=@document.pdf"
```

Supported formats:

* TXT
* Markdown
* PDF

### Check ingestion status

```bash
curl http://localhost:8000/documents/{id}
```

### Search documents

```bash
curl "http://localhost:8000/search?q=your+query"
```

Returns hybrid retrieval results with provenance information.

### Ask a question

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"your question"}'
```

Returns either:

* A verified, cited answer
* An explicit refusal when verification requirements are not met

### Run evaluation

```bash
curl -X POST http://localhost:8000/eval/run
```

### Health check

```bash
curl http://localhost:8000/health
```

---

## Running the Evaluation Harness

The evaluation harness measures retrieval quality and answer faithfulness against a version-controlled golden dataset.

```bash
cp .env.example .env
# add your ANTHROPIC_API_KEY

make up
make eval-seed
make eval-run
```

The benchmark uses the same answer-generation pipeline exposed through `POST /ask`; it is not a simulation or separate evaluation path. Reported metrics therefore reflect actual runtime behavior.

### Tuning Verification

Two environment variables control verification behavior:

| Variable                    | Purpose                                                                 |
| --------------------------- | ----------------------------------------------------------------------- |
| `VERIFIER_THRESHOLD`        | Minimum cosine similarity required for a claim to count as supported    |
| `VERIFIER_MAX_FAILED_RATIO` | Refuse an answer if more than this fraction of claims fail verification |

After changing either value:

```bash
docker compose up -d --build api
make eval-run
```

Compare the resulting metrics against previous runs before deciding whether the change improved performance.

---

## Performance

Measured using the built-in evaluation harness against the version-controlled golden dataset.

> **Provisional benchmark:** These results were measured using a temporary free-tier LLM substitute rather than the documented production backend (`claude-sonnet-4-6`). They are real measurements but should be considered preliminary until reproduced with Claude.

| Metric            | Value                     |
| ----------------- | ------------------------- |
| Recall@8          | 1.0000                    |
| MRR               | 1.0000                    |
| Mean Faithfulness | 0.6250                    |
| p95 Latency       | Not meaningfully measured |

Retrieval performance is currently perfect on the golden dataset. The primary open question is answer faithfulness: 3 of 4 generated answers were refused despite successful retrieval, suggesting verification behavior may be more restrictive than intended.

See `benchmark_report.md` for methodology, environment details, and analysis.

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

### Remaining

* Re-run benchmarks using the documented Anthropic backend
* Verify whether the faithfulness pattern reproduces on Claude
* Tune verifier thresholds only if benchmark evidence supports doing so

See `MANUAL_TODO.md` for remaining work.
