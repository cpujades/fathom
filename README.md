# Talven

Talven turns public YouTube videos into private, evidence-backed written
briefings with timestamp links to the source.

The repository and package namespace remains `fathom`.

## Stack

- FastAPI API and Python worker
- Next.js web application
- Supabase Auth, Postgres, and Storage
- Groq transcription
- OpenRouter briefing generation
- Polar billing

## Repository

| Path | Purpose |
| --- | --- |
| `apps/backend` | API, worker, provider adapters, and backend tests |
| `apps/web` | Product and public web application |
| `packages/api-client` | Generated OpenAPI TypeScript client |
| `supabase` | Migrations, database tests, and local configuration |
| `scripts` | Generation and operator commands |
| `docs` | Owner and developer documentation |

## Documentation

Start with [Talven documentation](./docs/00-reading-guide.md).

Recommended owner path:

1. [Product](./docs/01-product.md)
2. [Architecture](./docs/02-architecture.md)
3. [Data model reference](./docs/reference/data-model.md)
4. [Processing and providers](./docs/03-processing-and-providers.md)
5. [Billing and money](./docs/04-billing-and-money.md)
6. [Performance reference](./docs/reference/performance.md)
7. [Deployment and operations](./docs/06-deployment-and-operations.md)
8. [Launch plan](./docs/07-launch-plan.md)
9. [Roadmap](./docs/08-roadmap.md)

Developer entry points:

- [Architecture](./docs/02-architecture.md)
- [Processing and providers](./docs/03-processing-and-providers.md)
- [Development](./docs/05-development.md)
- [API reference](./docs/reference/api.md)
- [Configuration reference](./docs/reference/configuration.md)
- [Data model reference](./docs/reference/data-model.md)
- [Performance reference](./docs/reference/performance.md)

## Local setup

Requirements:

- Python 3.11–3.13
- `uv`
- Node.js 24
- `pnpm`
- Supabase CLI
- Docker Desktop or a Docker-compatible runtime

Install:

    uv venv
    uv sync --group dev
    pnpm install
    supabase start
    supabase db reset

The clean database still needs the internal plan catalogue before free or paid
briefing admission works. See [Development](./docs/05-development.md#local-billing).

Create local configuration:

    cp env.example .env
    cp apps/web/env.example apps/web/.env.local

Run three processes.

API:

    uvicorn --app-dir apps/backend fathom.api.app:app \
      --host localhost \
      --port 8080 \
      --reload

Worker:

    PYTHONPATH=apps/backend python -m fathom.orchestration.runner

Web:

    pnpm --filter @fathom/web dev

Open `http://localhost:3000`.

See [Development](./docs/05-development.md) for Supabase values, billing
sandbox setup, migrations, API generation, and troubleshooting.

## Checks

Backend:

    uv run ruff check .
    uv run ruff format --check .
    uv run ty check apps/backend/fathom
    PYTHONPATH=apps/backend ./.venv/bin/python \
      -m unittest discover -s apps/backend/tests

Frontend:

    pnpm --filter @fathom/web lint
    pnpm --filter @fathom/web test
    pnpm --filter @fathom/web typecheck
    pnpm --filter @fathom/web build

Generated API contract:

    pnpm check:api-contract

Database:

    supabase db reset
    supabase test db supabase/tests/database
    supabase db lint --local --fail-on warning

## Production state

The application is not currently deployed. Database release workflows exist,
but web, API, and worker hosting is still an owner decision.

Do not call the product launch-ready from local or CI checks alone. Follow the
[Launch plan](./docs/07-launch-plan.md) and
[Deployment and operations](./docs/06-deployment-and-operations.md).
