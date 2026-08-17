# Manual Steps

Things only you can do — account setup, credentials, and other steps outside
what a Claude session can automate. Updated as each phase surfaces new ones;
compiled here rather than scattered across phase notes.

## Blocking Phase 5 (threshold tuning + real README/benchmark numbers)

- [ ] **Fund an Anthropic API account** and add `ANTHROPIC_API_KEY` to your
  local `.env`. `POST /eval/run` needs a real LLM call — nothing else in the
  pipeline costs money (retrieval, embedding, and the verifier's similarity
  checks are all local). Once funded: `make eval-seed && make eval-run`, and
  the real numbers can go into `README.md`/`benchmark_report.md`, and the
  verifier threshold can be tuned from what's actually measured (see
  `docs/private/ARCHITECTURE_LEDGER.md`'s open Recall/faithfulness hypothesis
  from the temporary Gemini validation run, if you have access to that file).

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
