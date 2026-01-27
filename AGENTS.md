## Project overview

**Fathom** is a FastAPI service that turns a long-form audio URL into:
- a transcript (Deepgram)
- a structured Markdown summary (OpenRouter via the OpenAI Python SDK)
- a PDF export (WeasyPrint)

Entry point: `app/api/app.py`

## Quickstart (local)

For full setup details (including system deps like `ffmpeg` and WeasyPrint requirements), see `README.md`.

```bash
# Use Python 3.11–3.13 (3.14 is currently unsupported by some compiled deps like `pydantic-core`)
uv venv
source .venv/bin/activate
uv sync
uvicorn app.api.app:app --host 127.0.0.1 --port 8000 --reload
```

## Request flow (high level)

- **HTTP layer**: `app/api/router.py`
 - `POST /summarize` creates a job row and returns a `job_id`.
 - `GET /jobs/{job_id}` returns job status (and `summary_id` when ready).
 - `GET /summaries/{summary_id}` returns the summary and a signed `pdf_url` when available.
- **Orchestration**: `app/orchestration/pipeline.py`
 - Used by a separate worker process: downloads audio → transcribes → summarizes → renders PDF bytes → uploads to Supabase Storage.
- **Integrations**: `app/services/*`
  - `downloader.py` (yt-dlp), `transcriber.py` (Deepgram), `summarizer.py` (OpenRouter via OpenAI SDK), `pdf.py` (WeasyPrint).

## Configuration (env vars)

Configuration is read from environment variables via `app/core/config.py:get_settings()`.

```bash
cp env.example .env
```

- **Required**
  - `DEEPGRAM_API_KEY`
  - `OPENROUTER_API_KEY`
  - `SUPABASE_URL`
  - `SUPABASE_PUBLISHABLE_KEY`
  - `SUPABASE_SECRET_KEY`
- **Optional**
  - `OPENROUTER_MODEL` (default: `openai/gpt-4.1-mini`)
  - `OPENROUTER_SITE_URL` (sent as `HTTP-Referer` header; recommended by OpenRouter)
  - `OPENROUTER_APP_NAME` (sent as `X-Title` header; default: `fathom`)
  - `SUPABASE_BUCKET` (default: `fathom`)
  - `SUPABASE_SIGNED_URL_TTL_SECONDS` (default: `3600`)

Use `env.example` as the source of truth for local `.env` setup. Do not commit secrets.

## Running checks (same as CI)

Install dev dependencies:

```bash
uv sync --group dev
```

Run checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run ty check app  # informational (non-blocking)
```

Git hooks (recommended):

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

## Conventions

- **Architecture boundaries**
  - `app/api/*` owns HTTP concerns (request/response models, status codes, file responses).
  - `app/services/*` owns IO/integrations and should stay small and composable.
  - `app/orchestration/pipeline.py` coordinates services; keep orchestration readable and linear.
- **Error handling**
  - Raise domain errors (`AppError` and subclasses) from services/pipeline.
  - `app/api/app.py` maps `AppError` to the API error shape; avoid raising `HTTPException` from deep layers.
- **Configuration**
  - Read config via `get_settings()`; avoid implicit global state.
  - Keep secrets out of logs and out of the repo.

## Packaging & tooling

- Build backend: `hatchling`
- The importable Python package is `app/` (distribution name is `fathom`).
- `uv.lock` is committed for reproducible installs.

## Principles

- Prefer explicit, readable code over clever abstractions.
- Keep functions small and composable.
- Errors should never pass silently (unless explicitly handled).
