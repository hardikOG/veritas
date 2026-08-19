# Manual Steps

Things only you can do — account setup, credentials, and real-money decisions
outside what a Claude session can automate. Kept current as of the release
readiness audit and the free-tier deploy decision below; stale items are
removed, not just checked off.

## 1. Deployed — https://veritas-api-jrre.onrender.com (free tier, no worker)

**Live and verified**, 2026-08-20. `veritas-api`, `veritas-redis`,
`veritas-postgres` deployed and running, all free tier. `veritas-worker` is
deliberately deferred (no free tier exists for background workers on Render
at all — confirmed against Render's own docs, and against an actual
Blueprint deploy attempt, which asked for payment info the moment the
worker was included). `render.yaml` has the worker block commented out, not
deleted — full walkthrough in `docs/DEPLOY.md`.

Verified live against the real deployed instance:
- `GET /health` → `200 {"status":"healthy","database":"ok","redis":"ok"}`
- `POST /ask` on the empty index → `200 {"refused":true,...}` — confirms
  the cite-or-refuse pipeline is genuinely running, not a static response.
- `GET /search` → `200 {"results":[]}` (empty index, correct).
- `POST /eval/run` → `409` (`eval_golden` empty, no worker to seed it) —
  expected.

- [ ] **Set `ANTHROPIC_API_KEY`** on the `veritas-api` service (Render
  dashboard > veritas-api > Environment) if you want `POST /ask` to do
  anything beyond refuse on an empty index — not set yet.

**Known, accepted limitation of this deployment shape:** uploads via
`POST /documents` enqueue but are never processed (nothing consumes the
queue) — new documents stay `queued` forever, and `POST /eval/run` 409s
(nothing to seed it with). This is deliberate, not a bug — see
`docs/DEPLOY.md`.

## 2. Frontend deployed — https://veritas-tawny-chi.vercel.app (Vercel)

**Live and verified**, 2026-08-20. `frontend/` (Next.js, TypeScript,
Tailwind) imported as a Vercel project (Root Directory `frontend`),
`NEXT_PUBLIC_API_BASE_URL` set to the Render API, `CORS_ALLOWED_ORIGINS` set
on `veritas-api` to this Vercel URL. Full walkthrough:
`docs/DEPLOY_FRONTEND.md`.

Verified live, end to end, in a real browser against the real deployed API:
- Health badge reads "API live · db ok · redis ok".
- Asking a question returns a genuine `refused` response on the empty index
  (0% confidence, 0 citations, ~1s latency) — confirms the full chain
  (Vercel frontend → CORS → Render API → cite-or-refuse pipeline) is
  actually wired together, not a static mock.

## 3. Enabling the worker (when moving past portfolio/demo)

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

## 4. Real (non-provisional) Phase 5 numbers

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
