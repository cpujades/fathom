# Talven (repository: Fathom)

Talven turns long-form YouTube audio/video into structured, source-linked briefings with streaming progress, usage-aware billing, and reusable transcript/summary caching. The repository and Python/package namespace remain `fathom`.

## Stack

- Backend: FastAPI, Supabase, Polar, Groq, OpenRouter
- Frontend: Next.js 16, React 19, Supabase Auth
- Worker: separate Python process for download, transcription, summarization, and job progress updates

## Repo Layout

- `apps/backend/fathom`: deployable FastAPI API and worker code
- `apps/web`: deployable Next.js frontend
- `packages/api-client`: generated REST contract shared across the app boundary
- `scripts`: repository-wide generation and provider administration
- `supabase`: database migrations, tests, seed, and local infrastructure
- `docs`: architecture, product decisions, and operational runbooks

This is intentionally one monorepo: backend contracts, the generated client,
the web application, and database migrations are reviewed and tested together.
See the [repository and code map](./docs/architecture/repository-and-code-map.md)
for the rationale, root-file responsibilities, and placement rules.

## Current Product Flow

1. User signs in with Supabase Auth.
2. Frontend creates a briefing session via `POST /briefing-sessions`.
3. Backend reuses existing work when possible, or queues a new job.
4. Worker downloads the source, transcribes it with Groq, summarizes it with OpenRouter, and streams progress through job updates.
5. Frontend subscribes to session events and renders the evolving briefing.
6. Billing uses Polar checkout, portal sessions, refunds, and webhooks.

See [frontend, authentication, and user flows](./docs/architecture/frontend-auth-and-user-flows.md)
for the browser route map, safe redirect rules, account-scoped caches, and each
end-to-end user journey.

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
- `SUPABASE_DB_USER`
- `SUPABASE_DB_NAME`
- `SUPABASE_DB_HOST`

Optional backend runtime variables:

- `APP_ENV`
- `CORS_ALLOW_ORIGINS`
- `RATE_LIMIT`
- `TRUST_PROXY_HEADERS`
- `TRUSTED_PROXY_NETWORKS`
- `SUPABASE_DB_PORT`
- `POLAR_CHECKOUT_RETURN_URL`
- `POLAR_SERVER`
- `BILLING_DEBT_CAP_SECONDS`
- `WORKER_MAX_CONCURRENT_JOBS`
- `WORKER_SHUTDOWN_GRACE_SECONDS`
- `SOURCE_DOWNLOAD_DEADLINE_SECONDS`
- `SOURCE_METADATA_DEADLINE_SECONDS`
- `PROVIDER_TRANSCRIPTION_DEADLINE_SECONDS`
- `PROVIDER_SUMMARY_DEADLINE_SECONDS`
- `SSE_MAX_STREAMS_PER_USER`
- `SSE_MAX_STREAMS_PER_IP`
- `SSE_STREAM_LEASE_SECONDS`
- `SSE_STREAM_MAX_LIFETIME_SECONDS`

`APP_ENV` accepts `local`, `test`, `staging`, or `production` and defaults to
`local`. Hosted modes fail closed unless rate limiting and exact HTTPS CORS
origins are configured. If proxy headers are enabled, set
`TRUSTED_PROXY_NETWORKS` to the ingress IPs or CIDR ranges; forwarded client
addresses are ignored for every other peer.

Optional backend logging variables:

- `LOG_FORMAT`

Leave logging variables unset locally unless you need JSON logs. For hosted production logs, set `LOG_FORMAT=json` so platforms can index fields like `request_id`, `job_id`, `status_code`, and `duration_ms`.

### Frontend

Copy the frontend example file:

```bash
cp apps/web/env.example apps/web/.env.local
```

For local Supabase, run `supabase start`, then use `supabase status -o env` to
copy its URL and public publishable key into `.env.local`. The tracked example
uses `localhost` consistently with the browser/Auth redirect configuration.

For the meaning of each backend and frontend variable, and the distinction
between local Supabase, hosted staging, and production targets, see
[Environment configuration](./docs/reference/environment.md).

For a literal first-run sequence—including database reset safety, backend key
mapping, the local database port, plan provisioning, email confirmation,
readiness checks, and the first briefing—follow [local development from a fresh
clone](./docs/getting-started/local-development.md).

### Billing catalog

`scripts/polar/plan_contract.json` is the tracked, non-secret source of truth
for public plan codes, prices, quotas, and expiry rules. Frontend contract tests
read this file in local and CI environments.

`scripts/polar/plans.json` remains ignored and optional. It may contain only
environment-specific `polar_product_id` overrides for the same plan code and
version. The Polar sync script rejects attempts to redefine public plan fields
through that private file, preventing local provider identifiers from becoming
a second pricing source of truth.

Required frontend public variables:

- `NEXT_PUBLIC_API_BASE_URL`
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`

Recommended frontend public variable:

- `NEXT_PUBLIC_SITE_URL`

## Run Locally

### API

```bash
uvicorn --app-dir apps/backend fathom.api.app:app --host localhost --port 8080 --reload
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

The [HTTP API reference](./docs/reference/http-api.md) documents authentication,
inputs, results, errors, rate-limit pointers, and example requests. The list
below is the compact route inventory.

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

The backend suite includes deterministic, offline briefing-quality fixtures. See
[Briefing quality evaluation](./docs/quality/briefing-evaluation.md) for the checks and fixture rules.

For a durable product and architecture map, start with the
[Talven documentation index](./docs/README.md).

### Frontend

```bash
pnpm --filter @fathom/web lint
pnpm --filter @fathom/web typecheck
pnpm --filter @fathom/web test
pnpm --filter @fathom/web test:browser
pnpm --filter @fathom/web build
```

### API contract

After changing FastAPI routes or Pydantic request/response models, regenerate
the committed OpenAPI contract and TypeScript client:

```bash
pnpm generate:api-client
pnpm check:api-contract
```

See [API contract and client generation](./docs/architecture/api-contract.md)
for ownership rules and the separate SSE runtime contract.

## Production Notes

- The API and worker should run as separate processes in every environment.
- The worker should be configured to restart automatically on failure.
- The frontend must set `NEXT_PUBLIC_API_BASE_URL`. It no longer falls back to localhost.
- Hosted frontend builds must set the exact `NEXT_PUBLIC_SITE_URL`; missing it fails the build instead of generating localhost Auth links.
- Rate limiting uses shared Postgres buckets keyed by client IP. Only enable `TRUST_PROXY_HEADERS=true` when the app is behind a trusted ingress/proxy that normalizes forwarded headers.
- Polar webhooks and `/meta/health` bypass ordinary request throttling. SSE opens and readiness checks are rate-limited; active SSE connections also use expiring database leases with per-user/IP caps and a hard lifetime.
- Staging and production require HTTPS Supabase/Polar URLs, a non-loopback database host, certificate-verified Postgres TLS, and exact HTTPS CORS origins. Production additionally requires `POLAR_SERVER=production`; staging may use the Polar sandbox.
- `supabase/config.toml` configures the local Auth stack; hosted Supabase Auth settings and SMTP must be mirrored and verified in the Dashboard because database migrations do not deploy them.
- Polar webhooks should target your public backend URL at `/webhooks/polar`.
- Supabase migrations are managed from `supabase/` and deployed through GitHub Actions.
- Incident notes live in [docs/runbooks/worker-and-billing-incidents.md](./docs/runbooks/worker-and-billing-incidents.md).
- The bounded, no-provider recovery rehearsal lives in
  [docs/runbooks/local-recovery-rehearsal.md](./docs/runbooks/local-recovery-rehearsal.md).
- Plain-language explanations of leases, stream limits, billing recovery,
  refund concurrency, and Auth configuration live in
  [docs/architecture/runtime-safety-explained.md](./docs/architecture/runtime-safety-explained.md).
- Hosted Supabase Auth, SMTP, health/readiness probes, and rate-limit setup are
  configured with [the hosted-operations runbook](./docs/runbooks/hosted-auth-and-service-probes.md).
- The future host topology, public-signup controls, observability, retention,
  backups, ingress/WAF, and storage-provider decision are tracked in the
  [first deployment checklist](./docs/runbooks/first-deployment-checklist.md).
- Release credential rotation and protected-branch behavior are documented in
  [the release automation runbook](./docs/runbooks/release-automation.md).
