# Deploying Veritas to Render

`render.yaml` (repo root) is a [Render Blueprint](https://render.com/docs/blueprint-spec)
that defines everything Render can create automatically: the `veritas-api` web
service, `veritas-worker` background worker, `veritas-redis` Key Value
instance, and a `veritas-postgres` managed Postgres database. Both services
build directly from `docker/Dockerfile.api` and `docker/Dockerfile.worker` —
the same images used locally via `docker compose`.

## One-time setup

1. Push this repo to GitHub (if it isn't already).
2. In the Render dashboard: **New > Blueprint**, connect the repo. Render
   reads `render.yaml` and shows a preview of the four resources above —
   confirm and deploy.
3. **Set `ANTHROPIC_API_KEY`** on the `veritas-api` service (Render dashboard
   > veritas-api > Environment). `render.yaml` deliberately leaves this
   unset (`sync: false`) — it's a secret, never committed, never inferred.
4. Wait for the first deploy. `veritas-api`'s `preDeployCommand` runs
   `alembic upgrade head` automatically on every deploy, including this
   first one — this creates the schema and enables the `vector` extension
   (`CREATE EXTENSION IF NOT EXISTS vector`, in `migrations/versions/
   0001_initial.py`), which Render's managed Postgres supports natively. No
   manual migration step needed.

## Seeding the eval harness (manual, one-time)

`eval/seed.py` needs to run in the **worker** environment specifically (it
imports `ingestion.tasks`, which needs `pypdf` — deliberately not installed
in the api image; see `docs/private/ARCHITECTURE_LEDGER.md` if you have
access to that file, or `eval/seed.py`'s own module docstring). On Render,
run it as a one-off job:

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
curl -X POST https://<veritas-api>.onrender.com/eval/run
```

## Why there's no shared-disk step

Locally, `docker-compose` ran `api` and `worker` with a shared Docker volume
for uploaded files. Render gives every service its own persistent disk —
disks are never shared between services — so that scheme couldn't carry over
directly. As of this phase, `documents.content` stores the raw uploaded
bytes in Postgres itself (see `docs/private/ARCHITECTURE_LEDGER.md`'s Phase 6
entry), which both services already reach through `DATABASE_URL` — no disk,
no object storage, no new account to set up.
