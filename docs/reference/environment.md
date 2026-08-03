# Environment configuration

This is the personal operating guide for the Talven/Fathom repository. The
backend reads the root `.env`; the frontend reads `apps/web/.env.local`.
The API process and the worker must use the same root `.env`. The browser must
receive only the `NEXT_PUBLIC_*` values.

A private repository is not a substitute for secret handling. Do not commit
`.env` or `apps/web/.env.local`, and rotate a provider or Supabase secret if it
ever enters Git history, a screenshot, or a client-side bundle.

## The three environments

There are two separate ideas here:

- `APP_ENV` describes the safety mode in which the backend process runs.
- The Supabase and Polar values decide which data and payment system that
  process can reach.

Those are related, but they are not the same setting. The current code supports
these combinations as follows:

| Use | Backend `APP_ENV` | Supabase target | Polar target | Status |
| --- | --- | --- | --- | --- |
| Local app and local Supabase | `local` | local CLI project | sandbox or omitted | Supported; safest for schema and destructive testing |
| Local app against hosted staging | `local` today | staging project | sandbox/staging account | Hybrid workflow; usable, but see the warning below |
| Local app against production | `local` today | production project | production account | Technically possible, but dangerous and not a normal test mode |
| Hosted staging API/worker | `staging` | staging project | sandbox/staging account | Supported deployment mode |
| Hosted production API/worker | `production` | production project | production account | Supported deployment mode |

For your normal development workflow, use local code against staging only after
accepting the hybrid warning. With `APP_ENV=local`, the backend permits local
HTTP origins and uses the local JWT-validation path. It also currently disables
TLS for the direct Postgres connection because TLS is tied to strict hosted
runtime modes. That means this is not yet equivalent to hosted staging. Do not
describe it as a production-like security check.

`APP_ENV=staging` or `APP_ENV=production` cannot be used with a browser running
at `http://localhost:3000`: strict modes require exact HTTPS CORS origins and
reject loopback service/database URLs. To make a local browser a first-class
staging client, the application needs a separate local-process/remote-target
configuration decision rather than overloading `APP_ENV`.

Never use production Supabase or production Polar merely to test the UI. The
local app can create, change, charge, refund, and delete real production data.
If a production probe is genuinely required, use a disposable account and
document the exact operation before running it.

## Local hostnames

This project uses `localhost` as the local browser origin:

```text
Frontend: http://localhost:3000
API:      http://localhost:8080
Supabase: http://localhost:54321
Postgres: localhost:54322
```

`localhost` and `127.0.0.1` both point to the local machine, but they are not
the same web origin. Supabase Auth redirect allowlists, browser cookies, CSP,
and CORS compare the origin string exactly. Use one spelling consistently; for
this repository, use `localhost`. A value printed by `supabase status -o env`
may contain `127.0.0.1`; keep the key but replace that hostname in the URL or
database host when putting it into your local files.

## Backend variables: daily configuration

### Provider secrets

| Variable | Meaning |
| --- | --- |
| `OPENROUTER_API_KEY` | Secret used by the worker to request summaries from OpenRouter. |
| `GROQ_API_KEY` | Secret used by the worker to transcribe audio with Groq. |

These are real provider credentials even in local development, so local
briefings can incur provider usage or rate limits.

### Supabase URL, keys, and database connection

| Variable | Meaning |
| --- | --- |
| `SUPABASE_URL` | Supabase project API URL used by backend clients and JWT key discovery. |
| `SUPABASE_PUBLISHABLE_KEY` | Public/anon-style key. It is needed by the backend configuration and is also safe to expose to the browser through `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`. |
| `SUPABASE_SECRET_KEY` | Backend-only secret/service-role key. Never put it in `apps/web/.env.local`. |
| `SUPABASE_DB_PASSWORD` | Password for the direct Postgres connection used for notifications, readiness, and database-backed coordination. Required when `APP_ENV` is `staging` or `production`. |
| `SUPABASE_DB_USER` | Postgres user; defaults to `postgres`. |
| `SUPABASE_DB_NAME` | Postgres database; defaults to `postgres`. |
| `SUPABASE_DB_HOST` | Postgres hostname. Use `localhost` for the local CLI database; use the provider's non-loopback host for hosted projects. |
| `SUPABASE_DB_PORT` | Postgres port in the range 1-65,535. Defaults to `5432`; local Supabase CLI normally uses `54322`. |

The Supabase URL/key pair powers HTTP/Auth/Storage access. The DB variables
are a separate direct Postgres path; having a valid Supabase URL does not make
the DB connection work.

### Runtime safety and browser access

| Variable | Meaning |
| --- | --- |
| `APP_ENV` | One of `local`, `test`, `staging`, or `production`. `local` permits loopback HTTP services and skips hosted fail-closed checks. `staging` and `production` require HTTPS origins, a non-loopback database host, positive rate limiting, and other hosted settings. Production also requires `POLAR_SERVER=production`. |
| `CORS_ALLOW_ORIGINS` | Comma-separated exact browser origins allowed to call the API, such as `http://localhost:3000`. Do not add paths, wildcards, credentials, or a trailing route. Hosted modes require HTTPS. |
| `RATE_LIMIT` | Base requests per client IP per 60-second window. `0` disables the base limiter for local-only use; hosted modes reject zero. Some expensive operations have stricter limits, while Polar webhooks and `/meta/health` are exempt. |
| `TRUST_PROXY_HEADERS` | Whether the API trusts forwarded client-IP/protocol headers from an ingress or reverse proxy. Keep `false` when the API is reached directly. |
| `TRUSTED_PROXY_NETWORKS` | Comma-separated IPs/CIDR ranges of proxies allowed to supply those headers. It must be empty when proxy trust is off and non-empty when it is on. |

The rate limiter uses the client IP. Enabling proxy trust without restricting
the trusted networks lets a client influence the identity used for throttling,
so do not enable it just because a platform mentions forwarded headers.

### Polar billing

| Variable | Meaning |
| --- | --- |
| `POLAR_ACCESS_TOKEN` | Backend bearer token for Polar checkout, portal, catalog, and related API calls. |
| `POLAR_WEBHOOK_SECRET` | Secret used to verify incoming `POST /webhooks/polar` events. It must match the webhook endpoint in the same Polar account. |
| `POLAR_SERVER` | `sandbox`, `production`, or an absolute HTTPS API URL. Use `sandbox` for local/staging billing and `production` only with production billing. |
| `POLAR_SUCCESS_URL` | Required checkout success destination sent to Polar after a successful payment. It must be reachable by the browser. |
| `POLAR_CHECKOUT_RETURN_URL` | Optional checkout cancellation/back destination sent as Polar's `return_url`. |
| `POLAR_PORTAL_RETURN_URL` | Required destination to which Polar's customer portal returns the browser. |

Checkout and portal URLs are browser destinations, not API endpoints. A local
checkout can open in the browser, but Polar webhooks still need a publicly
reachable endpoint (or a deliberate tunnel) to settle local data. Sandbox
webhooks must never point at a production database.

For the hybrid local-code/staging-target workflow, the shape is approximately:

```dotenv
# .env — local process, hosted staging services
APP_ENV=local
CORS_ALLOW_ORIGINS=http://localhost:3000
SUPABASE_URL=https://<staging-project>.supabase.co
SUPABASE_DB_HOST=<staging-postgres-host>
SUPABASE_DB_PORT=5432
POLAR_SERVER=sandbox
POLAR_SUCCESS_URL=http://localhost:3000/billing
POLAR_CHECKOUT_RETURN_URL=http://localhost:3000/billing
POLAR_PORTAL_RETURN_URL=http://localhost:3000/billing
```

The frontend uses the same staging `NEXT_PUBLIC_SUPABASE_URL` and publishable
key, but keeps `NEXT_PUBLIC_API_BASE_URL=http://localhost:8080` and
`NEXT_PUBLIC_SITE_URL=http://localhost:3000`. The staging Supabase secret,
database password, Polar token, and webhook secret go only in the backend file.
Do not copy these placeholders literally, and do not use this pattern for
production until the remote-target/TLS boundary is made explicit in code.

## Backend variables: advanced tuning

These have safe defaults and normally stay unset in the personal `.env`:

| Variable | Default | Meaning |
| --- | ---: | --- |
| `BILLING_DEBT_CAP_SECONDS` | `600` | Maximum billing debt window used by usage admission. Accepted range: 0-86,400 seconds. |
| `WORKER_MAX_CONCURRENT_JOBS` | `10` | Maximum jobs the worker processes concurrently. Accepted range: 1-64; lower it if provider or machine capacity is limited. |
| `WORKER_SHUTDOWN_GRACE_SECONDS` | `30` | Time for the worker to stop claiming and drain before cancellation. |
| `SOURCE_DOWNLOAD_DEADLINE_SECONDS` | `600` | Total deadline for downloading source audio. |
| `SOURCE_METADATA_DEADLINE_SECONDS` | `30` | Total deadline for source metadata/admission. |
| `PROVIDER_TRANSCRIPTION_DEADLINE_SECONDS` | `190` | Total time allowed across bounded Groq attempts. |
| `PROVIDER_SUMMARY_DEADLINE_SECONDS` | `1805` | Total time allowed across bounded OpenRouter attempts. |
| `SSE_MAX_STREAMS_PER_USER` | `3` | Maximum simultaneous briefing event streams per user across API replicas. |
| `SSE_MAX_STREAMS_PER_IP` | `12` | Maximum simultaneous event streams per client IP. |
| `SSE_STREAM_LEASE_SECONDS` | `90` | Lease duration used to recover abandoned streams. |
| `SSE_STREAM_MAX_LIFETIME_SECONDS` | `3600` | Maximum lifetime of one stream before the client reconnects. |
| `LOG_FORMAT` | `console` | Backend log output format: `console` or `json`. JSON is useful for hosted log indexing. |

Changing these changes capacity, cost, or recovery behavior. Treat them as
operational settings, not ordinary feature flags.

## Frontend variables

These belong in `apps/web/.env.local` or the frontend deployment settings:

| Variable | Meaning |
| --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | Base URL of the FastAPI API, for example `http://localhost:8080`. The frontend has no safe production fallback; set it explicitly. |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase API URL used by the browser Auth client. It must point to the same project as the backend. |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Browser-safe Supabase publishable/anon-style key. |
| `NEXT_PUBLIC_SITE_URL` | Canonical frontend origin used for metadata and auth/recovery destinations. Set `http://localhost:3000` locally. Hosted production builds require the exact HTTPS origin and fail when it is missing. |

The `NEXT_PUBLIC_` prefix means Next.js may embed the value in browser code.
Only publishable URLs/keys belong there.

## Test and tooling variables

These are not part of the normal API/worker `.env`:

| Variable | Used by | Meaning |
| --- | --- | --- |
| `FATHOM_TEST_DATABASE_URL` | Integration test modules | Direct database URL for opt-in integration tests. |
| `FATHOM_RUN_GATE_C` | Gate C tests | Set to `1` to enable the authenticated fake-provider rehearsal. |
| `FATHOM_GATE_C_SUPABASE_URL` | Gate C tests | Supabase URL for the disposable Gate C project. |
| `FATHOM_GATE_C_PUBLISHABLE_KEY` | Gate C tests | Public key for Gate C. |
| `FATHOM_GATE_C_SECRET_KEY` | Gate C tests | Backend-only secret key for Gate C. |
| `FATHOM_GATE_C_DATABASE_URL` | Gate C tests | Direct database URL for Gate C. |
| `OPENAPI_SCHEMA_PATH` | API-client generation | Local OpenAPI JSON path override. |
| `OPENAPI_SCHEMA_URL` | API-client generation | Remote OpenAPI source override; use only when intentionally generating from a reachable API. |

`CI` and `NODE_ENV` are normally supplied by the test/build environment rather
than manually configured for the application.

## Minimal local files

For local Supabase, the meaningful local values are:

```dotenv
# .env
APP_ENV=local
CORS_ALLOW_ORIGINS=http://localhost:3000
SUPABASE_URL=http://localhost:54321
SUPABASE_DB_HOST=localhost
SUPABASE_DB_PORT=54322
POLAR_SERVER=sandbox
```

```dotenv
# apps/web/.env.local
NEXT_PUBLIC_API_BASE_URL=http://localhost:8080
NEXT_PUBLIC_SUPABASE_URL=http://localhost:54321
NEXT_PUBLIC_SITE_URL=http://localhost:3000
```

Keep the real keys and secrets in the ignored files; the snippets show only
the values that establish the local topology.
