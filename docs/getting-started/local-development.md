# Local development from a fresh clone

This guide reaches a working authenticated briefing flow with local Supabase.
Run commands from the repository root unless a step says otherwise. The full
explanation of every variable and the local/staging/production boundary is in
[Environment configuration](../reference/environment.md).

## 1. Install prerequisites

Install Python 3.11-3.13, Node 24+, pnpm, uv, the Supabase CLI, Docker or
Colima, ffmpeg, and the WeasyPrint system libraries for your platform.

Install repository dependencies:

```bash
uv venv
source .venv/bin/activate
uv sync --group dev
pnpm install
```

## 2. Start and migrate local Supabase

Start the local stack:

```bash
supabase start
```

For a new or deliberately disposable local database, apply every migration and
the tracked seed:

```bash
supabase db reset
```

`db reset` deletes local database data. Never point it at staging, production,
or a shared database. See [the Supabase workflow](../../supabase/README.md)
for Colima and migration troubleshooting.

Print the local connection values:

```bash
supabase status -o env
```

Depending on the CLI version, public/service credentials may be labelled
`PUBLISHABLE_KEY` and `SECRET_KEY` or `ANON_KEY` and `SERVICE_ROLE_KEY`. Map
them as follows:

| Talven variable | Local Supabase value |
| --- | --- |
| `SUPABASE_URL` | `API_URL`, with the hostname written as `http://localhost:54321` |
| `SUPABASE_PUBLISHABLE_KEY` | publishable or anon key |
| `SUPABASE_SECRET_KEY` | secret or service-role key; backend only |
| `SUPABASE_DB_HOST` | `localhost` |
| `SUPABASE_DB_PORT` | `54322` |
| `SUPABASE_DB_USER` | `postgres` |
| `SUPABASE_DB_NAME` | `postgres` |
| `SUPABASE_DB_PASSWORD` | local database password, normally `postgres` |

Never copy the secret/service-role key into the frontend environment.

## 3. Configure the backend and frontend

Create local, ignored environment files:

```bash
cp env.example .env
cp apps/web/env.example apps/web/.env.local
```

Fill `.env` with the local Supabase values above and real development keys for
Groq, OpenRouter, and Polar sandbox. For the standard local ports, retain:

```dotenv
APP_ENV=local
CORS_ALLOW_ORIGINS=http://localhost:3000
SUPABASE_DB_PORT=54322
POLAR_SERVER=sandbox
```

Fill `apps/web/.env.local` with the same public Supabase URL and public key.
Keep `NEXT_PUBLIC_API_BASE_URL=http://localhost:8080` and
`NEXT_PUBLIC_SITE_URL=http://localhost:3000`.

## 4. Provision the billing catalog

Usage admission needs the active free plan even when no payment is made. First
validate the tracked public catalog without contacting Polar or Supabase:

```bash
uv run python scripts/polar/generate_polar_plans.py --dry-run
```

Then sync the plans to local Supabase and create or verify matching products in
Polar sandbox:

```bash
uv run python scripts/polar/generate_polar_plans.py --server sandbox
```

The public names, prices, quotas, and versions come only from
`scripts/polar/plan_contract.json`. The ignored `scripts/polar/plans.json` may
hold environment-specific Polar product IDs; never commit it. Paid checkout
also requires a reachable backend webhook at `/webhooks/polar` and the matching
Polar sandbox webhook secret. Free briefing creation does not require a paid
checkout.

For an exact `plans.json` example, automatic create/reuse rules, generated
output, partial-failure recovery, and the production-safe command sequence, see
[Polar environments and testing](../runbooks/polar-environments-and-testing.md#talven-plans-and-polar-products).

## 5. Run all three processes

API shell:

```bash
uvicorn --app-dir apps/backend fathom.api.app:app --host localhost --port 8080 --reload
```

Worker shell:

```bash
PYTHONPATH=apps/backend python -m fathom.orchestration.runner
```

Web shell:

```bash
pnpm --filter @fathom/web dev
```

## 6. Verify the first journey

Confirm the API process and its dependencies:

```bash
curl --fail http://localhost:8080/meta/health
curl --fail http://localhost:8080/meta/ready
```

Then:

1. Open `http://localhost:3000/signup` and create a disposable account.
2. Open local Inbucket at `http://localhost:54324` and follow the confirmation
   link. Local Auth requires confirmation by default.
3. Submit a public YouTube URL from `/app/briefings/new`.
4. Watch the API accept the session, the worker claim it, and the reader receive
   progress over SSE.
5. Confirm the completed briefing appears in `/app/briefings`, opens again
   without reprocessing, and can generate a PDF.

If readiness fails, inspect the response and the API logs before testing the
UI. If a session stays queued, verify that the worker is running against the
same `.env` and database. Use the [worker and billing incident
runbook](../runbooks/worker-and-billing-incidents.md) for deeper diagnosis.

## 7. Stop local infrastructure

Stop the app processes normally, then stop Supabase:

```bash
supabase stop
```

Use `supabase stop --no-backup` only for a disposable project whose local data
you deliberately want to discard.
