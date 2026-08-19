# Manual Steps

Things only you can do — account setup, credentials, and real-money decisions
outside what a Claude session can automate. Kept current as of the release
readiness audit below; stale items are removed, not just checked off.

## 1. Cost decision: Render's background worker has no free tier

**Read this before deploying.** `render.yaml`'s `veritas-worker` service is
set to `plan: starter` (Render's cheapest paid tier, currently ~$7/mo),
**not** free — confirmed directly against Render's own docs: background
workers are not available on Render's free plan at all, only web services,
static sites, Postgres, and Key Value are. `veritas-api`, `veritas-redis`,
and `veritas-postgres` are all still on `plan: free`.

- [ ] **Decide whether you want to pay for the worker service**, or run
  ingestion some other way (there's no free path to a hosted, always-on
  Celery worker on Render as this project is architected).

**Also worth knowing:** Render's **free Postgres expires 30 days after
creation** (14-day grace period, then deletion — including all data, no
backups on the free tier). Fine for a demo you'll actively maintain; a real
problem if you deploy and walk away. If you want the deployment to stay up
indefinitely, that's another cost decision (a paid Postgres plan).

## 2. Deploying to Render (nothing here can be automated without your account)

- [ ] **Create a Render account** and connect this GitHub repo.
- [ ] **New > Blueprint** in the Render dashboard, pointing at `render.yaml` —
  creates `veritas-api`, `veritas-worker`, `veritas-redis`, and
  `veritas-postgres`.
- [ ] **Set `ANTHROPIC_API_KEY`** on the `veritas-api` service (Render
  dashboard > veritas-api > Environment) — `render.yaml` leaves it unset
  (`sync: false`) on purpose; it's a secret and was never going to be
  committed.
- [ ] **Seed the eval harness** once, after the first deploy: Render
  dashboard > `veritas-worker` > Shell > `python -m eval.seed`.
- [ ] **Verify**: `curl https://<your-app>.onrender.com/health`, then
  `POST /eval/run` once seeded and `ANTHROPIC_API_KEY` is set.

Full walkthrough: `docs/DEPLOY.md`.

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
  eval-run` (or the deployed equivalent) and replace `benchmark_report.md`'s
  numbers with real ones, including `p95_latency_ms`.
- [ ] **Check whether the faithfulness/refusal pattern reproduces with the
  real backend** — does a later sentence in a multi-sentence answer keep
  scoring lower than the first, same as it did with Gemini? If so, that's
  real signal for whether `VERIFIER_THRESHOLD` or `DEFAULT_CHUNK_SIZE` are
  worth revisiting — not done yet, deliberately, since one small free-tier
  sample isn't enough to retune a shipped default.

## Not blocking anything, just worth knowing

- Render's free-tier **web service** (`veritas-api`) spins down after
  inactivity — first request after idle is slow (cold start). The worker,
  being paid, doesn't have this behavior.
- No file-size limit is currently enforced on `POST /documents` uploads —
  worth adding before accepting uploads from anyone other than you, now that
  upload content lives in Postgres itself rather than a disk.
