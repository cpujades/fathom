# Fathom

Fathom turns long-form YouTube audio/video into structured briefings with streaming progress, usage-aware billing, and reusable transcript/summary caching.

## Stack

- Backend: FastAPI, Supabase, Polar, Groq, OpenRouter
- Frontend: Next.js 16, React 19, Supabase Auth
- Worker: separate Python process for download, transcription, summarization, and job progress updates

## Repo Layout

- `apps/backend/fathom`: FastAPI app, application logic, worker, integrations
- `apps/web`: Next.js frontend
- `packages/api-client`: generated API client used by the frontend
- `supabase`: migrations and local Supabase config

## Current Product Flow

1. User signs in with Supabase Auth.
2. Frontend creates a briefing session via `POST /briefing-sessions`.
3. Backend reuses existing work when possible, or queues a new job.
4. Worker downloads the source, transcribes it with Groq, summarizes it with OpenRouter, and streams progress through job updates.
5. Frontend subscribes to session events and renders the evolving briefing.
6. Billing uses Polar checkout, portal sessions, refunds, and webhooks.

## Local Setup

### Requirements

- Python 3.11-3.13
- Node 24+
- `pnpm`
- `ffmpeg`
- WeasyPrint system dependencies

### Install backend dependencies

```bash
uv venv
source .venv/bin/activate
uv sync
```

### Install frontend dependencies

```bash
pnpm install
```

## Environment

### Backend

Copy the backend example file:

```bash
cp env.example .env
```

Root `.env` is for the FastAPI API and the worker only.

Required backend variables are defined in [env.example](./env.example). The main ones are:

- `OPENROUTER_API_KEY`
- `GROQ_API_KEY`
- `POLAR_ACCESS_TOKEN`
- `POLAR_WEBHOOK_SECRET`
- `POLAR_SUCCESS_URL`
- `POLAR_PORTAL_RETURN_URL`
- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`
- `SUPABASE_SECRET_KEY`
- `SUPABASE_DB_PASSWORD`
- `SUPABASE_DB_HOST`

Optional backend deployment variables:

- `APP_ENV`
- `CORS_ALLOW_ORIGINS`
- `RATE_LIMIT`
- `WORKER_MAX_CONCURRENT_JOBS`
- `WORKER_JOB_NOTIFY_TIMEOUT_SECONDS`
- `BILLING_DEBT_CAP_SECONDS`
- `POLAR_CHECKOUT_RETURN_URL`
- `POLAR_SERVER`

### Frontend

Copy the frontend example file:

```bash
cp apps/web/env.example apps/web/.env.local
```

Required frontend public variables:

- `NEXT_PUBLIC_API_BASE_URL`
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`

Recommended frontend public variable:

- `NEXT_PUBLIC_SITE_URL`

## Run Locally

### API

```bash
uvicorn --app-dir apps/backend fathom.api.app:app --host 127.0.0.1 --port 8080 --reload
```

### Worker

Run the worker in a separate shell:

```bash
PYTHONPATH=apps/backend python -m fathom.orchestration.runner
```

### Frontend

```bash
pnpm --filter @fathom/web dev
```

## Main API Routes

### Meta

- `GET /meta/health`
- `GET /meta/ready`
- `GET /meta/status`

### Briefing sessions

- `POST /briefing-sessions`
- `GET /briefing-sessions/{session_id}`
- `GET /briefing-sessions/{session_id}/events`
- `DELETE /briefing-sessions/{session_id}`

### Briefings

- `GET /briefings`
- `GET /briefings/{briefing_id}`
- `POST /briefings/{briefing_id}/pdf`

### Billing

- `POST /billing/checkout`
- `POST /billing/portal`
- `POST /billing/packs/{polar_order_id}/refund`
- `GET /billing/plans`
- `GET /billing/usage`
- `GET /billing/briefings`
- `GET /billing/account`

### Webhooks

- `POST /webhooks/polar`

## Quality Checks

### Backend

```bash
uv sync --group dev
uv run ruff check .
uv run ruff format --check .
uv run ty check apps/backend/fathom
PYTHONPATH=apps/backend ./.venv/bin/python -m unittest discover -s apps/backend/tests
```

### Frontend

```bash
pnpm --filter @fathom/web lint
pnpm --filter @fathom/web typecheck
pnpm --filter @fathom/web build
```

## Production Notes

- The worker is required in production. `RUN_WORKER_IN_API=1` is for local development only.
- The frontend must set `NEXT_PUBLIC_API_BASE_URL`. It no longer falls back to localhost.
- Polar webhooks should target your public backend URL at `/webhooks/polar`.
- Supabase migrations are managed from `supabase/` and deployed through GitHub Actions.

## Release Flow

This repository uses Release Please on `main` to manage version bumps and changelog updates.
