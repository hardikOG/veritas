# Deploying Veritas to Render

`render.yaml` (repo root) is a [Render Blueprint](https://render.com/docs/blueprint-spec).
As checked in, it deploys three resources, **all on Render's free tier, no
card required**: the `veritas-api` web service, a `veritas-redis` Key Value
instance, and a `veritas-postgres` managed Postgres database. `veritas-api`
builds directly from `docker/Dockerfile.api` — the same image used locally
via `docker compose`.

## Current deployment shape: portfolio/demo, no worker

`veritas-worker` (the async ingestion process) is present in this repo —
`docker/Dockerfile.worker`, `worker/`, `ingestion/` are all fully built and
tested — but is **commented out** in `render.yaml`, not deployed. Render has
no free plan for background workers at all (confirmed against Render's own
docs); creating one requires payment info on file and bills at the `starter`
rate (currently ~$7/mo, prorated by the second) once created.

**What this means for the deployed instance:**
- `GET /health`, `GET /search`, `POST /ask` (correctly refuses on an empty
  index — no worker or LLM key needed to prove that path works), and the
  live URL itself are all fully functional.
- `POST /documents` accepts uploads and enqueues them, but nothing ever
  processes the queue — new documents stay at `status: "queued"`
  indefinitely. There's no data to search or ask about beyond whatever
  existed before the worker was last running.
- `POST /eval/run` will 409 (`eval_golden` empty) — seeding it requires
  `eval/seed.py`, which needs the worker (see below).

This is a deliberate tradeoff for a free, card-free demo deployment, not a
bug. Enable the worker below when moving past a portfolio/demo deployment.

### Enabling the worker later

1. In `render.yaml`, uncomment the `veritas-worker` block (kept in place,
   commented, specifically for this).
2. Push, then sync the Blueprint again in the Render dashboard (or push
   triggers it automatically if auto-deploy is on). Render will prompt for
   payment info at this point — that's the worker's paid plan, not a config
   error.
3. Once it's up, follow "Seeding the eval harness" below.

Render's free Postgres also expires 30 days after creation (14-day grace
period, then deletion, no backups on the free tier) — fine for an actively
maintained demo, a real problem if you deploy and walk away for a month.

## One-time setup

1. Push this repo to GitHub (if it isn't already).
2. In the Render dashboard: **New > Blueprint**, connect the repo. Render
   reads `render.yaml` and shows a preview of the resources above (three,
   with the worker commented out) — confirm and deploy. No payment info
   should be requested at this stage.
3. **Set `ANTHROPIC_API_KEY`** on the `veritas-api` service (Render dashboard
   > veritas-api > Environment). `render.yaml` deliberately leaves this
   unset (`sync: false`) — it's a secret, never committed, never inferred.
   Needed for `POST /ask` on a non-empty index and for `POST /eval/run`;
   `GET /health`/`GET /search` work without it.
4. Wait for the first deploy. `docker/Dockerfile.api`'s `CMD` runs `alembic
   upgrade head` automatically before starting the server, on every container
   start — this creates the schema and enables the `vector` extension
   (`CREATE EXTENSION IF NOT EXISTS vector`, in `migrations/versions/
   0001_initial.py`), which Render's managed Postgres supports natively. No
   manual migration step needed. (Not Render's `preDeployCommand`: Render's
   validator rejects that field on free-tier services, and free web services
   don't get Shell access to run it manually either — baking it into the
   image's own startup is the approach that actually works on the free
   tier. It's idempotent, so re-running it on every restart is harmless.)

## Seeding the eval harness (requires the worker enabled)

`eval/seed.py` needs to run in the **worker** environment specifically (it
imports `ingestion.tasks`, which needs `pypdf` — deliberately not installed
in the api image; see `docs/private/ARCHITECTURE_LEDGER.md` if you have
access to that file, or `eval/seed.py`'s own module docstring). On Render,
once the worker is enabled:

- Render dashboard > `veritas-worker` > **Shell**, run:
  ```
  python -m eval.seed
  ```
- Or use the Render CLI: `render exec veritas-worker -- python -m eval.seed`

Re-running it is safe (idempotent) — it only does anything for fixtures that
aren't already ingested.

## Verifying the deploy

```bash
curl https://<veritas-api>.onrender.com/health
curl -X POST https://<veritas-api>.onrender.com/ask \
  -H "Content-Type: application/json" -d '{"question": "anything"}'
# {"refused": true, ...} on an empty index -- confirms the app is live and
# the cite-or-refuse path works, without needing a worker or LLM key.
```

`POST /eval/run` only works once the worker is enabled and seeded (above).

## Why there's no shared-disk step

Locally, `docker-compose` ran `api` and `worker` with a shared Docker volume
for uploaded files. Render gives every service its own persistent disk —
disks are never shared between services — so that scheme couldn't carry over
directly. As of this phase, `documents.content` stores the raw uploaded
bytes in Postgres itself (see `docs/private/ARCHITECTURE_LEDGER.md`'s Phase 6
entry), which both services already reach through `DATABASE_URL` — no disk,
no object storage, no new account to set up.
