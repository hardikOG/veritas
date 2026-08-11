# Adversarial Reviews

Loop B log: Builder/Skeptic review rounds at each phase gate, before it's marked
green. One section per phase.

<!-- Entries are appended below as they occur. -->

## Phase 0 — Scaffold & infra

**Builder:** All four services (`api`, `worker`, `postgres`, `redis`) build and boot
via `docker compose up`, all reporting `healthy`. `alembic upgrade head` runs cleanly
against the `pgvector/pgvector:pg16` image, creating `documents` and `chunks` with
the specified HNSW (cosine) and GIN indexes, and the `vector` extension confirmed
installed (`\dx` → `vector 0.8.6`). `GET /health` performs a real `SELECT 1` and a
real `PING` per request — verified against the live containers (not just unit tests):
stopping the `postgres` container flips `/health` to `503` with
`{"database":"failed","redis":"ok"}` within one request, and restarting it recovers
to `200` on the next request with no process restart needed. `ruff`, `black`,
`isort`, and `mypy` are all clean; 3/3 tests pass (the positive case against live
containers, two negative cases via `app.dependency_overrides` simulating a failing
DB/Redis independently).

**Skeptic:**
1. *Does `/health` actually fail, or does it cache a stale "ok"?* — Addressed above
   with a real container stop/start, not just the mocked unit tests. Confirmed no
   caching: the very next request after the container died reported `503`.
2. *Does the worker container actually run Celery, or does compose just report it
   "up" because the process hasn't crashed yet?* — The worker's Docker healthcheck is
   `celery -A worker.celery_app inspect ping`, which requires a live broker
   round-trip, not just "the process exists." It reports `healthy`, which only
   happens if Celery genuinely connected to Redis and answered an inspect ping.
3. *Are the HNSW/GIN indexes real, or just declared in the ORM and silently absent
   from the DB?* — Checked via `\di` against the live database, not inferred from the
   migration source: both `ix_chunks_embedding_hnsw` and `ix_chunks_tsv_gin` are
   present.
4. *Is the embedding dimension actually configurable, or hardcoded despite the
   Settings field existing?* — `Vector(_settings.vector_dim)` is read from Settings at
   migration-authorship time, not hardcoded to `384` as a literal; changing
   `VECTOR_DIM` before the initial migration is generated changes the column. (After
   the migration exists, the column is fixed until a new migration changes it — noted
   explicitly in both the model and migration docstrings, not silently assumed.)
5. *Are these host ports (5544, 6380) reproducible on someone else's machine, or an
   artifact of this machine's port collisions?* — The remap exists specifically
   because this machine has native Postgres/Redis processes squatting on the standard
   ports (see BUGJOURNAL.md); a clean machine wouldn't need it, but the compose file
   works either way since only host-side publish ports changed — container-to-
   container traffic still uses the standard 5432/6379 internally, which is what
   Render's managed services will also use in Phase 6. Not a portability risk.

No unresolved objections. Gate green.

## Phase 1 — Ingestion pipeline

**Builder:** `POST /documents` accepts txt/md/pdf, computes a SHA-256 checksum,
stores the file, and enqueues `ingestion.tasks.ingest_document` via
`celery_app.send_task()` (dispatch by name — the api image never installs
torch/sentence-transformers/pypdf). The worker extracts text, chunks it on a
sliding window bounded by `min(DEFAULT_CHUNK_SIZE, embedder.max_seq_length)` (not a
blind constant), embeds each chunk with a real `sentence-transformers` model, and
writes chunk + embedding + tsvector. Verified against the live rebuilt stack, not
just host-venv tests: uploaded a real file through `curl`, watched the actual worker
log show model load + embedding + task success, confirmed the DB row directly
(`embedding IS NOT NULL`, `tsv IS NOT NULL`, correct token_count), then re-uploaded
the identical file and got the same document id back with no re-enqueue. Crash
safety: `task_acks_late` + `task_reject_on_worker_lost` mean an unacked task gets
redelivered, and `_run_ingestion` deletes-then-rewrites a document's chunks in one
transaction, so redelivery can't duplicate or corrupt rows — proven directly by a
test that invokes the task body twice for the same document. `ruff`/`black`/`isort`/
`mypy` clean, 11/11 tests pass.

**Skeptic:**
1. *What happens if the worker dies mid-chunk — does the checksum get marked done
   prematurely?* — No: `status` moves to `processing` in its own committed
   transaction *before* any chunk work starts, and only reaches `ready` after every
   chunk is written. A crash mid-run leaves it at `processing`; Celery's redelivery
   re-runs the whole task, which is safe because it re-does the work idempotently
   (delete-then-rewrite) rather than assuming prior partial state. Proven by
   `test_ingest_document_is_safe_to_rerun_after_simulated_crash`, not just reasoned
   about.
2. *Does re-ingesting the same file actually skip re-processing, or does it just
   look idempotent because the second run happens to produce the same result?* —
   Checked directly: the second upload's response came back with the *existing*
   document's current status with no new Celery task ever dispatched (the checksum
   lookup short-circuits before `send_task` is reached) — not a coincidentally
   identical re-computation.
3. *Is the `send_task`-by-name dispatch mechanism fragile?* — Was fragile (a bare
   string literal in `api/documents.py` with no shared source of truth against the
   task's actual registered name) until a `/simplify` pass on this diff caught it;
   fixed by introducing `core.constants.TASK_INGEST_DOCUMENT`, used by both the
   dispatch call and the task's own `name=` argument, so a rename can't silently
   desync them.
4. *Does the api image actually stay free of torch/sentence-transformers, or does
   something still import them transitively?* — Was NOT actually true at one point:
   `api/documents.py` originally imported `SUPPORTED_MIME_TYPES` from
   `ingestion.extract`, which imports `pypdf` — and the api Dockerfile never copies
   `ingestion/` at all, so the api container would have crashed on startup. Caught
   during the same `/simplify` pass (deduplicating a mime-type constant surfaced the
   dependency), fixed by moving the shared mime mapping to `core/constants.py`,
   which both sides can import cheaply.
5. *Chunk size of ~512 tokens per the original spec — does that match what the
   actual embedding model can consume?* — No: `all-MiniLM-L6-v2`'s real
   `max_seq_length` is 256, so a naive 512-token chunker would silently truncate half
   of every long chunk in the embedding while full-text search still saw all of it.
   Fixed at the design stage (not caught late): `ingestion/tasks.py` clamps to
   `min(DEFAULT_CHUNK_SIZE, embedder.max_seq_length)`, read from the embedder's
   actual property, not assumed.

No unresolved objections. Gate green.

## Phase 2 — Hybrid retrieval + RRF fusion

**Builder:** `GET /search` runs BM25 (`ts_rank`/`plainto_tsquery`) and dense
(pgvector `cosine_distance`) candidate retrieval independently, then fuses with
`reciprocal_rank_fusion` (k=60, unit-tested on hand-built rankings). Verified live
against the rebuilt Docker stack, not just host-venv tests: ingested a PostgreSQL
document and an unrelated weather document, then queried "relational database
system" — the PostgreSQL chunk correctly ranked first with `bm25_rank=1,
dense_rank=1` (matched both signals), and the weather chunk still surfaced second
with `bm25_rank=null, dense_rank=2` (matched only the dense signal, no keyword
overlap) — real proof the fusion combines two independent signals rather than
silently collapsing to one. `ruff`/`black`/`isort`/`mypy` clean, 22/22 tests pass.
Cold-rebuild target for RRF fusion + its key test written to
`docs/private/rebuild_targets.md`.

**Skeptic:**
1. *Is the fusion secretly just re-ranking by one signal because the other returned
   empty?* — This is the exact scenario `test_one_empty_ranking_does_not_zero_out_the_result`
   covers directly (an empty BM25 ranking still surfaces the dense results), and the
   live verification above shows a real case of an item present in only one signal
   still ranking correctly. `test_fusion_is_not_just_one_signal_passed_through` goes
   further: hand-computed RRF scores for a case where the fused order equals neither
   input ranking, asserting the exact expected order rather than a vague "differs
   from input" check.
2. *Does `GET /search` actually query the real Postgres operators
   (`tsvector`/`ts_rank`, pgvector `<=>`), or something that only looks equivalent in
   the ORM?* — Confirmed via the live stack: the response's `bm25_rank`/`dense_rank`
   fields came from real, separate Postgres queries against the actual ingested
   chunk rows (not mocked), and the weather chunk's `bm25_rank: null` is only
   possible if the real `tsvector @@ plainto_tsquery` predicate genuinely excluded
   it (no keyword overlap) while the real cosine-distance ordering still included it.
3. *Does the API image actually stay lean, or does adding embedding capability there
   silently reopen the door to pulling in ingestion's PDF-parsing dependency too?* —
   Checked directly: `docker/Dockerfile.api` copies `embedding/` and `retrieval/` but
   not `ingestion/`; `requirements-embedding.txt` (torch + sentence-transformers, no
   pypdf) is what the api image installs, `requirements-worker.txt` (embedding +
   pypdf) stays worker-only. This is a revised boundary from Phase 1, not the same
   one — see the Architecture Ledger entry explaining why Phase 1's "api never needs
   ML deps" assumption had to change for Phase 2's synchronous read path.
4. *Was this actually tested against the deployed images, or just assumed to work
   because the host-venv tests passed?* — Caught a real gap this way: the first
   Docker rebuild crash-looped the api container with `ModuleNotFoundError: No
   module named 'retrieval'` — `docker/Dockerfile.api` was missing a `COPY retrieval
   ./retrieval` line, invisible from host-venv tests (which run against the plain
   filesystem, no Docker COPY manifest to miss) — a second concrete case, after
   Phase 1's api/pypdf leak, of why the Docker-level gate matters and isn't
   redundant with the venv-level one.

No unresolved objections. Gate green.
