# Deploying the Veritas frontend to Vercel

`frontend/` is a standalone Next.js app (App Router, TypeScript, Tailwind) —
a static client for the Veritas API. It has no server-side logic of its own
and does not touch Postgres, Redis, or Celery directly; it only calls the
already-deployed API over HTTP (`GET /health`, `GET /search`, `POST /ask`).
See `docs/private/ARCHITECTURE_LEDGER.md`'s "Post-P6: frontend (Vercel)"
entry for why this exists as a scoped exception to the project's no-React
rule, rather than a rule change to the whole stack.

## One-time setup

1. Push this repo to GitHub (if it isn't already) — `frontend/` lives inside
   the same repo as the API, not a separate one.
2. In the Vercel dashboard: **Add New > Project**, import this repo.
3. Set **Root Directory** to `frontend` — this is the one non-default
   setting Vercel needs; everything else (framework, build command, output)
   is auto-detected from `frontend/package.json` and `next.config.ts`.
4. Set the environment variable `NEXT_PUBLIC_API_BASE_URL` to the deployed
   API's URL, currently `https://veritas-api-jrre.onrender.com` (no trailing
   slash). This is a build-time value baked into the static output — the
   frontend has no server runtime to read env vars at request time.
5. Deploy. Vercel gives you a `*.vercel.app` URL.

## Required follow-up: enable CORS on the API for this origin

The API installs no CORS middleware at all unless `CORS_ALLOWED_ORIGINS` is
set (see `core/config.py`'s `cors_allowed_origins_list`), so by default the
browser blocks every cross-origin call the frontend makes — this is
intentional (no origin is trusted until explicitly configured), not a bug.

Once the Vercel deploy has a real URL:

1. Render dashboard > `veritas-api` > **Environment**, set
   `CORS_ALLOWED_ORIGINS` to the Vercel URL, e.g.
   `https://veritas-frontend.vercel.app`. Comma-separate multiple origins
   (useful for also allowing `http://localhost:3000` during local frontend
   development).
2. Render redeploys `veritas-api` automatically on an env var change.

Until this is set, the frontend loads and renders correctly, but every API
call fails with a CORS error in the browser console and the UI shows its
built-in "API unreachable" / "Could not reach the Veritas API" states —
this was verified locally against the live Render API before that origin
was added, specifically to confirm the frontend degrades gracefully rather
than crashing when the API is unreachable for any reason.

## Verifying the deploy

Open the Vercel URL and:
- The health badge in the header should read "API live · db ok · redis ok".
- Typing a question into **Ask** and submitting should return
  `{"refused": true, ...}`-shaped output ("Refused." banner) against an
  empty index — this proves the frontend, the CORS config, and the API's
  cite-or-refuse path are all genuinely wired together end to end, without
  needing a worker or an LLM key.
- **Search** on an empty index should return "No matching chunks." rather
  than erroring.

## Local development

```bash
cd frontend
cp .env.example .env.local   # or point NEXT_PUBLIC_API_BASE_URL at localhost:8000
npm install
npm run dev
```

`.env.local` defaults to the live Render API URL so the frontend is
immediately testable without running the backend locally — but the Render
API must have `http://localhost:3000` in its `CORS_ALLOWED_ORIGINS` for
that to work from a browser (see above). Point it at
`http://localhost:8000` instead to develop against a local `docker compose`
stack, which needs no CORS config since Render's CORS restriction doesn't
apply to the local API.
