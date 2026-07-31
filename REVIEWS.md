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
