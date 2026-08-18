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

## Phase 3 — Answer + cite-or-refuse verifier

**Builder:** `POST /ask` retrieves context via Phase 2's `hybrid_search`, asks the
LLM (`llm/anthropic_client.py`, real Anthropic client; `llm/fake.py`'s
`FakeLLMClient` in every test — no network calls in CI, per this project's testing
rule) for a per-sentence-cited answer, parses it (`verifier/parse.py`), and checks
each claim's embedding against its cited chunk's *stored* embedding
(`verifier/verify.py`) — stripping unsupported claims, refusing the whole answer if
more than `verifier_max_failed_ratio` fail. New `queries` table logs every call
(answered or refused) via `core/config.py`'s already-existing
`verifier_threshold`/`verifier_max_failed_ratio` settings (added in Phase 0, unused
until now). `ruff`/`black`/`isort`/`mypy` clean, and — after fixing one real bug
found along the way (below) — 41/41 tests passed at the time of that Phase 3-only
run; the code is unchanged since, and a later full-suite run (59/59, including
Phase 4) re-confirms it. Cold-rebuild target for the verifier written to
`docs/private/rebuild_targets.md`.

**Bug found and fixed (Loop A, logged in `BUGJOURNAL.md`):** writing a claim's
verification debug info to the `queries.retrieval_debug` JSONB column raised
`TypeError: Object of type float32 is not JSON serializable`. Root cause:
`retrieval/hybrid.py`'s `SearchResult.embedding` was built with `list(chunk.embedding)`
— pgvector.sqlalchemy returns a numpy array, and plain `list()` on a numpy array
yields `numpy.float32` scalars, not native floats, invisibly (equality, arithmetic,
and `mypy`'s `list[float]` check all pass on `numpy.float32` — only JSON
serialization exposes it). Fixed with `_to_float_list()`, using `.tolist()`
(numpy's own recursive native-type conversion) instead.

**Skeptic:**
1. *Does the verifier check the claim against the chunk it actually cited, or just
   the best-matching chunk in the retrieved set?* — Specifically the cited one
   (`verify_claims`'s `chunk_embeddings.get(sentence.chunk_id)`) — a claim citing
   the wrong (but real) chunk fails exactly like a claim citing a fabricated
   chunk_id, both via the same `None` → similarity 0.0 path
   (`test_verify_claims_treats_hallucinated_citation_as_unsupported_not_an_error`).
   See the Architecture Ledger for why the alternative (grade against the
   best-matching chunk) was rejected — it would hide real citation errors.
2. *A five-sentence answer with one fabricated sentence — does it get diluted into
   a passing average, or does that one bad sentence get caught?* — Each sentence is
   an independent claim with its own similarity check; nothing here average-pools
   across sentences before deciding pass/fail per claim.
   `test_verify_claims_strips_individual_failing_claims_without_refusing` proves the
   converse case explicitly: one bad claim (1/3) survives as "stripped" without
   sinking the two good ones or refusing the whole answer, while
   `test_verify_claims_refuses_when_too_many_claims_fail` proves the threshold
   (>40%) does trigger a full refuse once enough claims fail.
3. *Known limitation, not a bug: what about a single compound sentence mixing one
   true and one false claim?* — Verification is sentence-granular, not
   clause-granular; a compound sentence gets one similarity score for the whole
   thing. Documented explicitly in the Architecture Ledger ("Verifier granularity")
   with the mitigation (the system prompt asks the LLM for one claim per sentence)
   and why the alternative (LLM self-splits into sub-clauses) was rejected — it
   would push unverified complexity onto the LLM's own decomposition.
4. *Was this actually exercised against the deployed Docker images, not just the
   host venv?* — Yes: rebuilt after adding the missing `docker/Dockerfile.api`
   `COPY retrieval ./retrieval` line (from Phase 2's gate) plus new `COPY llm ./llm`
   and `COPY verifier ./verifier` lines this phase required; the api container
   booted healthy and served `GET /health` after the rebuild.
5. *Does POST /ask ever silently swallow an LLM failure and call it a "refuse"?* —
   No — `answer_question()`'s docstring states this explicitly and
   `llm_client.generate_cited_answer()` is called with no try/except around it:
   a network/auth failure propagates as an unhandled exception (500), not a
   refuse. Refuse is reserved for "the LLM answered but the answer wasn't
   well-supported," a materially different failure mode from "the LLM couldn't be
   reached at all," and conflating them would misreport the eval harness's
   faithfulness numbers in Phase 4.

No unresolved objections. Gate green.

## Phase 4 — Eval harness

**Builder:** `eval/golden_set.py` is a small, human-authored, version-controlled
question spec (4 questions) grounded in `eval/fixtures/` (4 short, distinct
documents). `eval/seed.py` (`python -m eval.seed`, run in the **worker** image —
see Architecture Ledger for why, not the api image) ingests the fixtures and
populates the new `eval_golden` table with each question's *real* chunk id(s),
resolved after ingestion rather than hardcoded. `eval/metrics.py` is pure
(`recall_at_k`, `reciprocal_rank`, `faithfulness_ratio`, `p95`) — no DB/network
dependency, hand-tested with fixed lists. `eval/runner.py`'s `run_eval()` scores
every `eval_golden` row by calling the *exact same* `api.ask.answer_question()`
that `POST /ask` uses (extracted from the route in this phase specifically so the
harness can't drift from what production actually does — see Architecture Ledger),
plus a separate `hybrid_search` call per question for Recall@8/MRR. `POST
/eval/run` (`api/eval.py`) returns the aggregate `EvalReport` as JSON, 409 if
`eval_golden` is empty. `ruff`/`black`/`isort`/`mypy` clean; full suite (59/59,
Phases 1-4 together) passes against a freshly-migrated database, including all of
`test_eval_metrics.py`, `test_eval_seed.py`, and `test_eval_run.py`. Cold-rebuild
target for the metric functions written to `docs/private/rebuild_targets.md`.

**Skeptic:**
1. *Does the eval harness score the real answer pipeline, or a parallel
   reimplementation that could silently diverge from what POST /ask actually
   does?* — The real one: `eval/runner.py` imports and calls `api.ask.
   answer_question()` directly, in-process (no HTTP self-call). This is the whole
   reason that function was extracted from the route handler this phase — see the
   Architecture Ledger entry, which also names the tradeoff (a bit more coupling
   between `api/ask.py` and `api/eval.py`/`eval/runner.py`) explicitly rather than
   pretending the refactor was free.
2. *Recall@k could look artificially perfect if it's checked against retrieval
   output that wasn't independently capped/ranked.* — `recall_at_k` takes an
   explicit `k` and slices `retrieved_chunk_ids[:k]` itself; `reciprocal_rank`
   deliberately does *not* cap to k — it searches the whole retrieved ranking, so a
   relevant chunk that ranks 9th (outside Recall@8's window) still registers in MRR
   instead of vanishing from both metrics. `test_reciprocal_rank_uses_earliest_
   matching_rank_with_multiple_expected` confirms rank, not just presence, is what
   drives the score.
3. *A badly-seeded golden entry (empty `expected_chunk_ids`) could quietly inflate
   the reported average.* — Checked directly:
   `test_recall_at_k_empty_expected_is_a_miss_not_a_free_pass` asserts 0.0, not a
   skip/NaN that `sum()/len()` would silently exclude from the denominator.
4. *Does seeding actually need to run inside the worker container, or was that an
   unnecessary complication?* — Traced the real import chain:
   `eval.seed` → `ingestion.tasks` → `ingestion.extract` → `pypdf` (module-level,
   unconditional import regardless of whether a PDF is ever processed). Running
   seeding inside the api process would force `pypdf` into that image, undoing a
   boundary Phase 1 and Phase 2 each deliberately drew. Confirmed empirically too:
   `eval/__init__.py` only imports from `eval.metrics`, never `eval.seed` or
   `eval.runner` — importing the `eval` package from either image never pulls in
   the other side's dependencies.
5. *Does `POST /eval/run` fail loudly or silently produce a misleading "perfect"
   report when nothing has been seeded yet?* — Loudly: `run_eval()` raises
   `ValueError` on an empty `eval_golden`, which `api/eval.py` turns into an
   HTTP 409 pointing at `python -m eval.seed` — `test_eval_run_returns_409_when_
   golden_set_is_empty` confirms this rather than assuming it.
6. *Was `POST /eval/run` verified against the real Anthropic API, or only
   FakeLLMClient?* — Only FakeLLMClient so far, same as `POST /ask` in Phase 3 —
   no `ANTHROPIC_API_KEY` is available in this environment (a manual step for the
   user, tracked for Phase 6). This is consistent with the project's own testing
   rule ("FakeLLM in tests for determinism," CLAUDE.md), not a gap specific to this
   phase — the harness's retrieval scoring (Recall@8/MRR) is fully real either way,
   since it never touches the LLM.

**Live Docker verification:** rebuilt both images (new `eval/`, `llm/`, `verifier/`
packages), brought up the full 4-container stack fresh. `make eval-seed`-equivalent
(`docker compose run --rm worker python -m eval.seed`) ran in the real worker
container and reported `seeded 4 eval_golden rows`. `GET /search?q=pgvector` against
the live api container correctly ranked the seeded `pgvector.txt` fixture chunk
first on both signals (`bm25_rank: 1, dense_rank: 1`), confirming ingestion,
migrations 0002/0003, and retrieval all work end to end against the real deployed
images, not just host-venv tests. `POST /eval/run` returned `Internal Server Error`
(500) as expected/designed — no `ANTHROPIC_API_KEY` is configured in this
environment, and per Phase 3's Skeptic point 5, an LLM failure is deliberately
*not* caught and reinterpreted as a refuse. Confirms Skeptic point 6 above is a real
environment gap (missing key), not a masked code bug.

No unresolved objections. Gate green.

## Phase 5 — Threshold tuning + public docs (provisional)

**Builder:** `README.md` gained Architecture, API surface, "Running the eval
harness," and a tuning-workflow section; `benchmark_report.md` was created,
structured exactly like the harness's real output. No `ANTHROPIC_API_KEY` was
available (tracked in `MANUAL_TODO.md`) — with the user's explicit direction,
real numbers were measured using a temporary Gemini free-tier `LLMClient`
(same throwaway-script pattern as Phase 3/4's validation runs, not committed
to the repo) rather than left as `_pending_` indefinitely. Published in
`README.md`/`benchmark_report.md`, both explicitly and prominently labeled
provisional: measured against a temporary stand-in, not the documented
production backend (`claude-sonnet-4-6`), pending re-verification. Along the
way, found and fixed two real parser bugs in already-shipped Phase 3 code
(`verifier/parse.py`) that synthetic unit tests never exercised — see
`BUGJOURNAL.md`. `VERIFIER_THRESHOLD` itself was **not** retuned — the
Architecture Ledger's open dilution hypothesis remains open, gated on a real
Anthropic-backed measurement per `CLAUDE.md`'s PERFORMANCE rule; four
questions on a non-production LLM isn't enough signal to retune a shipped
default, publishing provisional numbers is not the same as acting on them.

**Skeptic:**
1. *Does labeling something "provisional" in a portfolio README actually
   protect against misrepresenting the project, or is it a fig leaf?* — The
   label states the exact model used (`gemini-3.6-flash`), the exact reason
   (no funded key yet), and points at the reproduction steps against the real
   backend (`benchmark_report.md`'s "How to reproduce") — a reader can verify
   or reproduce, not just take the number on faith. This is different from
   silently publishing Gemini numbers under an unlabeled "Performance"
   heading, which would have been a real misrepresentation.
2. *Was `p95_latency_ms` reported, and is it real?* — Deliberately **not**
   reported as a number — the measurement script's own retry-with-backoff
   (added to survive Gemini free-tier `503`s) inflated it with artificial
   wait time unrelated to Veritas's actual processing. Reporting a
   contaminated number would have been worse than reporting none; the gap is
   stated explicitly rather than hidden or hand-waved with a caveat-free
   number.
3. *Is `refused_count=3/4` a red flag being glossed over?* — No — it's
   reported prominently, with the specific evidence (first-sentence vs.
   later-sentence similarity gap) and the working hypothesis for *why*,
   not just the raw number. A suspiciously perfect result with no explanation
   would be less trustworthy than an honest, well-explained imperfect one.
4. *Did this actually close the loop, or just move the "pending" label
   around?* — Real progress, explicitly bounded: retrieval quality
   (Recall@8/MRR) is now genuinely measured and unlikely to change
   meaningfully with a different LLM, since it doesn't depend on which model
   answers. Faithfulness/refusal and latency remain explicitly open pending
   Claude — `MANUAL_TODO.md` states precisely what's still needed and why,
   not a vague "come back later."

No unresolved objections given the explicit provisional framing. Gate green
for what's honestly measurable without a funded Anthropic key; final,
non-provisional numbers remain a tracked manual step.

## Phase 6 — Render deploy scaffolding

**Builder:** `render.yaml` (Blueprint) defines `veritas-api` (web, Docker,
`preDeployCommand: alembic upgrade head` on every deploy), `veritas-worker`
(background worker, Docker), `veritas-redis` (Key Value), and
`veritas-postgres` (managed Postgres, pgvector-capable — verified via Render's
own docs before writing this, not assumed). `docs/DEPLOY.md` walks through the
one-time setup and the manual steps that can't be automated (funding
Anthropic, connecting the repo, setting the secret, seeding the eval set).
`MANUAL_TODO.md` consolidates every manual step discovered across phases so
far.

Along the way, found and fixed a real architectural gap before it could ship
broken: Render disks are never shared between services, but the existing
design had `api` write uploads to a local path and `worker` read them from
that same path — works locally (shared Docker volume), silently breaks the
moment the two become separate Render services. Fixed by moving file storage
into a new `documents.content bytea` column (migration 0004), so both
processes reach it through the database connection they already share — see
Architecture Ledger for the alternatives considered and why they lost.

Verified live against the real, rebuilt Docker images (not just host-venv
tests): uploaded a document through the live `api` container, confirmed
`chunk_count > 0` and the content is retrievable via `GET /search`, and
re-ran `eval/seed.py` through the real `worker` container end to end. Full
suite: 61/61. `render.yaml` validated as parseable YAML.

**Skeptic:**
1. *Does `preDeployCommand: alembic upgrade head` actually run before every
   deploy, or only the first one?* — Per Render's own docs (fetched directly,
   not recalled from training data, since this is exactly the kind of
   platform-specific fact that goes stale): it runs on every deploy, after the
   build and before the new version starts serving traffic — "recommended for
   running database migrations." Confirmed this is the right field for the
   job before committing to it, not the first plausible-looking one found.
2. *Is `pgvector` actually available on Render's managed Postgres, or was that
   assumed?* — Checked directly rather than assumed, given the entire schema
   depends on it: confirmed as a supported extension, enabled the same way
   locally (`CREATE EXTENSION IF NOT EXISTS vector`, already in migration
   0001) — no special dashboard toggle needed.
3. *The storage fix touches `models/document.py`, `api/documents.py`,
   `ingestion/extract.py`, `ingestion/tasks.py`, and `eval/seed.py` — was
   every call site actually updated, or does something still reference the
   dropped `storage_path` column?* — Grepped the whole repo for
   `storage_path`/`storage_dir`/`STORAGE_DIR`/`/data/uploads` after the
   change; the only remaining hits are migration 0001 (historical record,
   never edited) and migration 0004 itself (the `storage_path` name appears
   only in its `downgrade()` path, which recreates the column deliberately).
4. *Did the schema migration silently corrupt or orphan any existing data?* —
   Yes, in a specific, understood way: 9 pre-migration rows across the shared
   dev database ended up with `content IS NULL` (the dropped column's data
   had nowhere to go, no backfill was written). One of them made
   `test_upload_ingests_and_reupload_is_idempotent` fail for real — traced,
   confirmed via a direct Postgres query (not guessed), and resolved by
   deleting the 9 stale rows rather than patching around them in application
   code, since a genuinely fresh database (any real first deploy) would never
   have this problem — see `BUGJOURNAL.md`'s Phase 6 entry. Re-ran the full
   suite after cleanup to confirm no other stale rows were hiding elsewhere.
5. *Is `ANTHROPIC_API_KEY` handled safely in `render.yaml`?* — `sync: false`
   with no `value` — Render requires it be set manually in the dashboard,
   never reads a default, and it is never written to this file or committed
   anywhere.
6. *Was Render's actual Blueprint deploy exercised for real, or only
   scaffolded?* — Only scaffolded — no Render account exists yet to deploy
   to (tracked in `MANUAL_TODO.md`). `render.yaml`'s syntax is validated and
   its Postgres/pgvector and `preDeployCommand` claims are checked against
   Render's current documentation, but an actual Render deploy is real,
   necessarily-manual verification this phase cannot complete on its own.

No unresolved objections given what's verifiable without a live Render
account; the one genuine gap (an actual deploy) is explicit, not hidden.
Gate green for the automatable scope.
