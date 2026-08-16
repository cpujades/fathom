# Development

**Status:** Current local workflow.

**Read this to understand:** how to run Talven, make a safe change, and prove
that the change is ready for review.

## Contents

- [Prerequisites](#prerequisites)
- [First setup](#first-setup)
- [Run the application](#run-the-application)
- [Local billing](#local-billing)
- [Quality checks](#quality-checks)
- [Database changes](#database-changes)
- [API changes](#api-changes)
- [Common change checklist](#common-change-checklist)
- [Pull-request flow](#pull-request-flow)
- [Local Supabase with Colima](#local-supabase-with-colima)
- [Source-of-truth order](#source-of-truth-order)

## Prerequisites

- Python 3.11–3.13
- `uv`
- Node.js 24
- `pnpm`
- Supabase CLI
- Docker Desktop or another Docker-compatible runtime such as Colima

## First setup

From the repository root:

    uv venv
    uv sync --group dev
    pnpm install

Start the local Supabase stack:

    supabase start
    supabase db reset

Copy configuration:

    cp env.example .env
    cp apps/web/env.example apps/web/.env.local

Use:

    supabase status -o env

to obtain the local Supabase URL and publishable/secret keys.

The root `.env` belongs to the API and worker. The frontend file may contain
only `NEXT_PUBLIC_*` values.

Exact variables are in [Configuration reference](./reference/configuration.md).

## Run the application

Use three terminals.

### API

    uvicorn --app-dir apps/backend fathom.api.app:app \
      --host localhost \
      --port 8080 \
      --reload

### Worker

    PYTHONPATH=apps/backend python -m fathom.orchestration.runner

### Web

    pnpm --filter @fathom/web dev

Open:

- web: `http://localhost:3000`
- API health: `http://localhost:8080/meta/health`
- Supabase Studio: `http://localhost:54323`
- local email inbox: `http://localhost:54324`

Use `localhost` consistently. Browsers treat `localhost` and
`127.0.0.1` as different origins for cookies, Auth redirects, and CORS.

## Local billing

Free briefing processing does not require a Polar checkout. It still requires
the internal Free plan in Supabase. A clean `supabase db reset` does not create
the plan catalogue.

Validate the catalogue without provider or database changes:

    uv run python scripts/polar/generate_polar_plans.py --dry-run

Then synchronize the intended local or sandbox catalogue deliberately. This
command uses the configured Polar server and writes the matching plan rows to
Supabase:

    uv run python scripts/polar/generate_polar_plans.py --server sandbox

When testing checkout:

1. use Polar sandbox credentials;
2. set `POLAR_SERVER=sandbox`;
3. validate the catalogue;
4. synchronize the sandbox deliberately; and
5. forward a sandbox webhook to the local API.

Never point a sandbox webhook at production data.

## Quality checks

### Backend

    uv run ruff check .
    uv run ruff format --check .
    uv run ty check apps/backend/fathom
    ./.venv/bin/python -m unittest discover \
      -s apps/backend/tests/unit -t apps/backend

Backend tests are grouped by scope:

- `unit/` mirrors the backend package and does not require local services.
- `integration/database/` tests Python code against the migrated database.
- `e2e/` tests the authenticated API-to-worker product journey.
- `fixtures/` contains stable test input data.

CI runs all three scopes on every pull request. Integration and E2E tests use
disposable local Supabase services. They never use a hosted project.

### Frontend

    pnpm --filter @fathom/web lint
    pnpm --filter @fathom/web test
    pnpm --filter @fathom/web typecheck
    pnpm --filter @fathom/web build

### Generated API contract

    pnpm check:api-contract

### Database

    supabase db reset
    supabase test db supabase/tests/database
    supabase db lint --local --fail-on warning

Run targeted tests while editing. Run the complete relevant gates before
requesting review.

## Database changes

Committed migrations are immutable after they have been applied.

Create a forward migration:

    supabase migration new <name>

Apply the complete history locally:

    supabase db reset

Generate a reviewed diff when useful:

    supabase db diff -f <name>

Do not edit an old migration to repair a deployed schema. Add a new timestamped
migration.

Supabase migrations are forward-only. A later migration is not a down migration
for the one before it. It is the next linear schema and data change.

Normal staging and production migration deployment runs through GitHub Actions.
`supabase db pull` and direct remote `db push` are exceptional reconciliation
commands. Confirm the linked project before using either.

## API changes

When a route, query, request model, or response model changes:

    pnpm generate:api-client
    pnpm check:api-contract

Review these generated files:

- `packages/api-client/openapi.json`;
- `packages/api-client/src/schema.ts`; and
- stable aliases or client helpers when the new contract needs them.

Do not edit generated schema output by hand.

## Common change checklist

### Backend feature

- Keep the router thin.
- Put business behavior in `application`.
- Put provider I/O in `services`.
- Put persistence in `crud/supabase` or a protected RPC.
- Raise a domain error from deep layers.
- Add focused tests for behavior and failure.

### Frontend feature

- Keep route-specific code beside the route.
- Use the generated API client.
- Validate long-lived SSE payloads at runtime.
- Cover loading, empty, error, keyboard, mobile, and reduced-motion states.
- Do not place private credentials in public variables.

### Database feature

- Add a forward migration.
- Decide ownership, foreign keys, deletion behavior, RLS, grants, and RPC
  privileges.
- Add database tests for browser and service roles.
- Run from a clean local database.

### Billing feature

- Define idempotency and replay behavior.
- Separate browser return state from provider proof.
- Cover delayed, duplicate, out-of-order, refund, and reconciliation paths.
- Keep all amounts and time units explicit.

### Documentation

Update the one chapter that owns the changed behavior. Update a reference page
only when an exact route, variable, or table changed.

## Pull-request flow

1. Keep the change focused.
2. Run targeted checks.
3. Run the complete relevant gates.
4. Review generated files and migrations.
5. Use Conventional Commits.
6. Explain risk, rollout, and rollback in the pull request.

Pull-request CI repeats backend, frontend, generated-contract, database, commit
message, dependency, and security checks on clean runners.

## Local Supabase with Colima

On macOS:

    colima start --cpu 4 --memory 8 --disk 40 \
      --vm-type vz \
      --vz-rosetta \
      --mount-type virtiofs
    docker context use colima
    supabase start

If Supabase cannot reach Docker:

- confirm the active Docker context;
- remove a stale `DOCKER_HOST` override; and
- confirm the Colima VM is running.

Stop in this order:

    supabase stop
    colima stop

## Source-of-truth order

When documentation and behavior disagree:

1. tests and observed behavior;
2. current code and migrations;
3. tracked configuration;
4. generated API schema; and
5. documentation.

Fix the owning documentation after confirming the executable behavior.

## Next read

[Deployment and operations](./06-deployment-and-operations.md)
