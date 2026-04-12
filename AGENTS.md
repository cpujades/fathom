## Project overview

**Talven** is a FastAPI + Next.js application for turning long-form YouTube content into reusable written briefings.

Repository/package namespace remains `fathom`; the current product and web branding is `Talven`.

Current stack:

- transcript: Groq audio transcription
- summary: OpenRouter via the OpenAI Python SDK
- auth: Supabase Auth
- billing: Polar checkout, portal, refunds, and webhooks
- storage/data: Supabase

Backend entry point: `apps/backend/fathom/api/app.py`
Frontend app: `apps/web`

## Quickstart (local)

For full setup details, see `README.md`.

### Backend

```bash
uv venv
source .venv/bin/activate
uv sync
uvicorn --app-dir apps/backend fathom.api.app:app --host 127.0.0.1 --port 8080 --reload
```

### Worker

```bash
PYTHONPATH=apps/backend python -m fathom.orchestration.runner
```

### Frontend

```bash
pnpm install
pnpm --filter @fathom/web dev
```

## Request flow (high level)

- **Frontend**
  - `apps/web` handles auth, billing UI, briefing creation, and briefing session streaming.
- **HTTP layer**
  - `POST /briefing-sessions` creates or reuses a session.
  - `GET /briefing-sessions/{session_id}` returns the current session snapshot.
  - `GET /briefing-sessions/{session_id}/events` streams session updates over SSE.
  - `GET /briefings` and `GET /briefings/{briefing_id}` expose saved briefings.
  - `POST /billing/checkout` and `POST /billing/portal` start Polar flows.
  - `POST /webhooks/polar` receives Polar webhooks.
- **Worker orchestration**
  - `apps/backend/fathom/orchestration/runner.py` claims jobs, downloads audio, transcribes with Groq, summarizes with OpenRouter, and updates progress.

## Configuration (env vars)

Configuration is read from environment variables via `apps/backend/fathom/core/config.py:get_settings()`.

### Backend env

Copy `env.example` to `.env`.

Required backend variables include:

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

### Frontend env

Copy `apps/web/env.example` to `apps/web/.env.local`.

Required frontend public variables:

- `NEXT_PUBLIC_API_BASE_URL`
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`

Recommended frontend public variable:

- `NEXT_PUBLIC_SITE_URL`

Use `env.example` and `apps/web/env.example` as the tracked source of truth. Do not commit secrets.

## Running checks (same as current local validation)

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

## Conventions

- **Architecture boundaries**
  - `apps/backend/fathom/api/*` owns HTTP concerns.
  - `apps/backend/fathom/application/*` owns orchestration and business rules.
  - `apps/backend/fathom/services/*` owns external IO/integrations and should stay small.
  - `apps/backend/fathom/orchestration/runner.py` owns background job execution.
  - `apps/web` owns presentation, auth UX, billing UX, and session streaming UX.
- **Error handling**
  - Raise domain errors (`AppError` and subclasses) from backend layers.
  - Avoid raising `HTTPException` from deep layers.
- **Configuration**
  - Read backend config via `get_settings()`.
  - Keep secrets out of logs and out of the repo.
  - Frontend public env vars must be explicit; do not rely on localhost defaults in production.

## Packaging & tooling

- Backend build system: `hatchling`
- Backend package root: `apps/backend/fathom`
- Frontend package: `apps/web`
- API client package: `packages/api-client`
- `uv.lock` and `pnpm-lock.yaml` are committed for reproducible installs.

## Principles

- Prefer explicit, readable code over clever abstractions.
- Keep functions small and composable.
- Keep docs and env examples aligned with the current code.
- Errors should never pass silently unless explicitly handled.
