# Configuration reference

**Authority:** `apps/backend/fathom/core/config.py`, `env.example`, and
`apps/web/env.example`.

Keep secrets out of Git and logs.

## Contents

- [Backend files](#backend-files)
- [Frontend file](#frontend-file)
- [Minimal local example](#minimal-local-example)
- [Hybrid local-to-staging use](#hybrid-local-to-staging-use)
- [Test variables](#test-variables)
- [API generation variables](#api-generation-variables)
- [GitHub environment secrets](#github-environment-secrets)

## Backend files

The API and worker both read the root `.env`.

### Required provider settings

| Variable | Secret | Purpose |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | Yes | Briefing generation |
| `GROQ_API_KEY` | Yes | Audio transcription |
| `SUPABASE_URL` | No | Supabase project API URL |
| `SUPABASE_PUBLISHABLE_KEY` | No | User-scoped Supabase client |
| `SUPABASE_SECRET_KEY` | Yes | Privileged backend Supabase client |

### Direct Postgres

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `SUPABASE_DB_PASSWORD` | Staging/production | None | Direct database connection |
| `SUPABASE_DB_USER` | No | `postgres` | Database user |
| `SUPABASE_DB_NAME` | No | `postgres` | Database name |
| `SUPABASE_DB_HOST` | Staging/production | None | Direct database host |
| `SUPABASE_DB_PORT` | No | `5432` | Direct database port |

Local Supabase commonly uses port `54322`.

The direct connection supports worker notifications, readiness, database-backed
rate limiting, and coordination. A pooled HTTP Supabase client does not replace
this connection.

### Runtime

| Variable | Default | Rule |
| --- | --- | --- |
| `APP_ENV` | `local` | `local`, `test`, `staging`, or `production` |
| `CORS_ALLOW_ORIGINS` | Empty | Comma-separated exact origins or JSON array |
| `RATE_LIMIT` | `0` | Requests/minute base; must be positive when hosted |
| `TRUST_PROXY_HEADERS` | `false` | Enable only behind a known proxy |
| `TRUSTED_PROXY_NETWORKS` | Empty | IP/CIDR list; must match proxy-header setting |
| `EXPLORE_OPERATOR_USER_IDS` | Empty | Supabase user UUIDs allowed to List their own publications |
| `WORKER_MAX_CONCURRENT_JOBS` | `10` | Allowed 1–64 |

Hosted validation:

- CORS origins must be exact HTTPS origins;
- wildcards, credentials, paths, queries, and fragments are rejected;
- loopback origins and database hosts are rejected;
- direct database password and host are required;
- service and Polar return URLs must be HTTPS and non-loopback; and
- production requires `POLAR_SERVER=production`.

`TRUST_PROXY_HEADERS` and `TRUSTED_PROXY_NETWORKS` must be enabled or
disabled together.

### Polar

| Variable | Secret | Purpose |
| --- | --- | --- |
| `POLAR_ACCESS_TOKEN` | Yes | Checkout, portal, refund, reconciliation, and catalogue operations |
| `POLAR_WEBHOOK_SECRET` | Yes | Raw webhook signature verification |
| `POLAR_SUCCESS_URL` | No | Checkout success destination |
| `POLAR_CHECKOUT_RETURN_URL` | No | Explicit checkout return destination |
| `POLAR_PORTAL_RETURN_URL` | No | Customer portal return destination |
| `POLAR_SERVER` | No | `sandbox` or `production`; default `sandbox` |

Sandbox and production values are different. A webhook secret belongs to one
endpoint in one Polar environment.

## Frontend file

The web application reads `apps/web/.env.local`.

| Variable | Required | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | Yes | Browser-visible API origin |
| `NEXT_PUBLIC_SUPABASE_URL` | Yes | Browser-visible Supabase URL |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Yes | Browser-safe project key |
| `NEXT_PUBLIC_SITE_URL` | Hosted builds | Canonical web origin for Auth and metadata |

Anything prefixed with `NEXT_PUBLIC_` is exposed to the browser. Never place a
Supabase secret key, Polar token, webhook secret, Groq key, OpenRouter key, or
database password there.

## Minimal local example

Root `.env`:

    OPENROUTER_API_KEY=...
    GROQ_API_KEY=...
    SUPABASE_URL=http://localhost:54321
    SUPABASE_PUBLISHABLE_KEY=...
    SUPABASE_SECRET_KEY=...
    SUPABASE_DB_PASSWORD=postgres
    SUPABASE_DB_USER=postgres
    SUPABASE_DB_NAME=postgres
    SUPABASE_DB_HOST=localhost
    SUPABASE_DB_PORT=54322
    APP_ENV=local
    CORS_ALLOW_ORIGINS=http://localhost:3000
    RATE_LIMIT=0

`apps/web/.env.local`:

    NEXT_PUBLIC_API_BASE_URL=http://localhost:8080
    NEXT_PUBLIC_SUPABASE_URL=http://localhost:54321
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=...
    NEXT_PUBLIC_SITE_URL=http://localhost:3000

## Hybrid local-to-staging use

A local API using hosted staging credentials still uses `APP_ENV=local`.
This is a hybrid developer workflow. It does not prove hosted staging security,
origins, TLS, ingress, probes, or proxy behavior.

Use staging credentials only for a deliberate task. Never run reset commands
against the hosted project.

## Test variables

| Variable | Purpose |
| --- | --- |
| `FATHOM_TEST_DATABASE_URL` | Direct URL for Python database integration tests |
| `FATHOM_RUN_E2E=1` | Enable the authenticated E2E product journey |
| `FATHOM_E2E_SUPABASE_URL` | Isolated E2E Supabase URL |
| `FATHOM_E2E_PUBLISHABLE_KEY` | Isolated E2E publishable key |
| `FATHOM_E2E_SECRET_KEY` | Isolated E2E secret key |
| `FATHOM_E2E_DATABASE_URL` | Isolated E2E direct database URL |

These variables are test-only. Integration and E2E tests must use disposable
local services because they create and delete test identities and data.

## API generation variables

| Variable | Purpose |
| --- | --- |
| `OPENAPI_SCHEMA_PATH` | Override the local committed schema input |
| `OPENAPI_SCHEMA_URL` | Generate from an explicit schema URL |

Normal repository commands use the committed schema path. A URL override
changes the source and should be deliberate.

## GitHub environment secrets

Database deployment workflows use environment-scoped values such as:

- `SUPABASE_ACCESS_TOKEN`;
- `SUPABASE_PROJECT_REF`; and
- `SUPABASE_DB_PASSWORD`.

Release automation uses `RELEASE_AUTOMATION_TOKEN` to push the generated
release commit and tag through the protected `main` ruleset.

Store staging and production values in their matching GitHub environments.
Repository documentation must never contain the values.

## Next read

[Development](../05-development.md)
