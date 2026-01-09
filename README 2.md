# Fathom

Fathom helps you explore long-form audio faster by turning podcasts into searchable, chat-friendly knowledge.

## MVP flow
1) Paste a YouTube link
2) Transcribe the episode
3) Generate a focused summary + action items
4) Export a PDF

## Local setup

### Requirements
- Python 3.11–3.13 (Python 3.14 is currently unsupported by some compiled deps like `pydantic-core`)
- `ffmpeg` (recommended for best audio downloads)
- WeasyPrint system dependencies (for PDF export)

### Install
```bash
# Option A (recommended): uv + a supported interpreter
# If you use pyenv:
#   pyenv install 3.13.11
#   pyenv local 3.13.11
uv venv
source .venv/bin/activate
uv sync

# Option B: plain venv (not recommended if you want reproducibility)
# python -m venv .venv
# source .venv/bin/activate
# pip install -r requirements.txt
```

### Dev tooling (recommended)
Install dev dependencies and enable git hooks:

```bash
uv sync --group dev
uv run pre-commit install
```

Run all hooks manually:

```bash
uv run pre-commit run --all-files
```

### Configure
```bash
cp env.example .env
```
Fill in:
- `DEEPGRAM_API_KEY`
- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL` (e.g. `openai/gpt-4.1-mini` or `google/gemini-3-flash-preview`)

### Run
```bash
uvicorn app.main:app --reload
```

### Use
```bash
curl -X POST http://127.0.0.1:8000/summarize \
  -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=VIDEO_ID"}'
```

This returns a `job_id`. Poll:

```bash
curl http://127.0.0.1:8000/jobs/$JOB_ID \
  -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN"
```

When the job succeeds, it will include a `summary_id`. Fetch the summary (includes a signed `pdf_url` if the PDF is ready):

```bash
curl http://127.0.0.1:8000/summaries/$SUMMARY_ID \
  -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN"
```

## Versioning & releases
This repo uses **Release Please** on `main`. If you use **Conventional Commits** (e.g. `feat: ...`, `fix: ...`), it will open a release PR that:
- bumps the version in `pyproject.toml`
- updates `CHANGELOG.md`
- creates a git tag when the release PR is merged

### Error format
Errors use a consistent shape:
```json
{
  "error": {
    "code": "invalid_request",
    "message": "Invalid summary id"
  }
}
```
