# Manual Steps

Things only you can do — account setup, credentials, and other steps outside
what a Claude session can automate. Updated as each phase surfaces new ones;
compiled here rather than scattered across phase notes.

## Blocking Phase 5's real, final numbers (currently provisional)

`README.md`/`benchmark_report.md` currently show real, measured numbers from
a temporary Gemini free-tier stand-in (Recall@8=1.0, MRR=1.0, mean
faithfulness=0.625, 3/4 answers refused) — not fabricated, but not the
documented production backend either, and latency wasn't measured cleanly
(contaminated by retry backoff against Gemini's free-tier rate limits).

- [ ] **Fund an Anthropic API account** and add `ANTHROPIC_API_KEY` to your
  local `.env`. Nothing else in the pipeline costs money (retrieval,
  embedding, and the verifier's similarity checks are all local). Once
  funded: `make eval-seed && make eval-run`, and replace the provisional
  numbers in `README.md`/`benchmark_report.md` with real Claude-measured
  ones — including a real `p95_latency_ms`, which the Gemini run couldn't
  report cleanly.
- [ ] **Check whether the faithfulness/refusal pattern reproduces with
  Claude**: does the second sentence of a multi-sentence answer score
  consistently lower than the first, same as it did with Gemini? If so, that
  supports acting on the chunk-embedding-dilution hypothesis (see
  `docs/private/ARCHITECTURE_LEDGER.md`, if you have access to that file) —
  either lowering `VERIFIER_THRESHOLD` or shrinking `DEFAULT_CHUNK_SIZE`, and
  actually tuning from real data rather than a 4-question free-tier sample.

## Deploying (Phase 6)

- [ ] **Create a Render account** and connect this GitHub repo.
- [ ] **New > Blueprint** in the Render dashboard, pointing at `render.yaml` —
  this creates `veritas-api`, `veritas-worker`, `veritas-redis`, and
  `veritas-postgres` automatically.
- [ ] **Set `ANTHROPIC_API_KEY`** on the `veritas-api` service in Render's
  dashboard (Environment tab) — `render.yaml` leaves it unset (`sync: false`)
  on purpose; it's a secret and was never going to be committed.
- [ ] **Seed the eval harness** once, after the first deploy: Render dashboard
  > `veritas-worker` > Shell > `python -m eval.seed` (or the Render CLI
  equivalent — see `docs/DEPLOY.md`).
- [ ] **Verify**: `curl https://<your-app>.onrender.com/health` and
  `POST /eval/run` once seeded.

Full walkthrough: `docs/DEPLOY.md`.

## Not blocking anything, just worth knowing

- Render's free-tier web services spin down after inactivity — the first
  request after idle will be slow (cold start). Fine for a portfolio demo,
  worth mentioning if a reviewer's first impression matters.
- No file-size limit is currently enforced on `POST /documents` uploads (see
  `docs/private/ARCHITECTURE_LEDGER.md`'s Phase 6 storage entry) — worth
  adding before accepting uploads from anyone other than you.
