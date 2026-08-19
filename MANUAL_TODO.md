# Manual Steps

Things only you can do — account setup, credentials, and real-money decisions
outside what a Claude session can automate. Kept current as of the release
readiness audit and the free-tier deploy decision below; stale items are
removed, not just checked off.

## 1. Deploying to Render (free tier, no worker — current decision)

Decided: deploy free-tier only for now (`veritas-api`, `veritas-redis`,
`veritas-postgres`), defer `veritas-worker` (no free tier exists for
background workers on Render at all — confirmed against Render's own docs,
and against an actual Blueprint deploy attempt, which asked for payment info
the moment the worker was included). `render.yaml` has the worker block
commented out, not deleted — full walkthrough in `docs/DEPLOY.md`.

- [ ] **Create a Render account** and connect this GitHub repo.
- [ ] **New > Blueprint** in the Render dashboard, pointing at `render.yaml`
  — creates `veritas-api`, `veritas-redis`, `veritas-postgres`. Should not
  ask for payment info at this stage (only `veritas-api`/`veritas-redis`/
  `veritas-postgres` are in the active Blueprint, all free).
- [ ] **Set `ANTHROPIC_API_KEY`** on the `veritas-api` service (Render
  dashboard > veritas-api > Environment) — needed for `POST /ask` on a
  non-empty index and `POST /eval/run`; `/health` and `/search` work
  without it.
- [ ] **Verify**: `curl https://<your-app>.onrender.com/health`, then
  `POST /ask` with any question — should return `{"refused": true}` on the
  empty index, confirming the app is live end to end without needing the
  worker or the LLM key at all.

**Known, accepted limitation of this deployment shape:** uploads via
`POST /documents` enqueue but are never processed (nothing consumes the
queue) — new documents stay `queued` forever, and `POST /eval/run` 409s
(nothing to seed it with). This is deliberate, not a bug — see
`docs/DEPLOY.md`.

## 2. Enabling the worker (when moving past portfolio/demo)

- [ ] **Decide you're ready to pay** — `starter` plan, ~$7/mo prorated by
  the second, no free alternative for a hosted background worker on Render.
- [ ] Uncomment the `veritas-worker` block in `render.yaml`, push, re-sync
  the Blueprint (Render will ask for payment info at this point — that's
  expected, not an error).
- [ ] **Seed the eval harness** once it's up: Render dashboard >
  `veritas-worker` > Shell > `python -m eval.seed`.
- [ ] **Verify**: upload a real document, confirm it reaches `status:
  "ready"`, then `POST /eval/run` should succeed (given a funded
  `ANTHROPIC_API_KEY` too — see below).

## 3. Real (non-provisional) Phase 5 numbers

`benchmark_report.md` currently holds real, measured numbers from a
temporary Gemini free-tier stand-in (Recall@8=1.0, MRR=1.0, mean
faithfulness=0.625, 3/4 answers refused), clearly labeled as provisional —
not the documented production backend, and `p95_latency_ms` wasn't
measurable cleanly (contaminated by retry backoff against Gemini's rate
limits). The README no longer surfaces these numbers directly; see
`benchmark_report.md` for the full picture.

- [ ] **Fund an Anthropic API account**, add `ANTHROPIC_API_KEY` to `.env`
  (local) or the Render dashboard (deployed), then `make eval-seed && make
  eval-run` (or the deployed equivalent, once the worker is enabled) and
  replace `benchmark_report.md`'s numbers with real ones, including
  `p95_latency_ms`.
- [ ] **Check whether the faithfulness/refusal pattern reproduces with the
  real backend** — does a later sentence in a multi-sentence answer keep
  scoring lower than the first, same as it did with Gemini? If so, that's
  real signal for whether `VERIFIER_THRESHOLD` or `DEFAULT_CHUNK_SIZE` are
  worth revisiting — not done yet, deliberately, since one small free-tier
  sample isn't enough to retune a shipped default.

## Not blocking anything, just worth knowing

- Render's free-tier **web service** (`veritas-api`) spins down after
  inactivity — first request after idle is slow (cold start).
- No file-size limit is currently enforced on `POST /documents` uploads —
  worth adding before accepting uploads from anyone other than you, now that
  upload content lives in Postgres itself rather than a disk.
