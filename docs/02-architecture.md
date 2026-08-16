# Architecture

**Status:** Current system design.

**Read this to understand:** where code belongs, how one briefing moves through
the system, and which boundaries protect data and money.

## Contents

- [System map](#system-map)
- [Repository map](#repository-map)
- [Backend dependency direction](#backend-dependency-direction)
- [Frontend structure](#frontend-structure)
- [Briefing lifecycle](#briefing-lifecycle)
- [Progress delivery](#progress-delivery)
- [Cache and reuse](#cache-and-reuse)
- [Data and security boundaries](#data-and-security-boundaries)
- [Publication boundary](#publication-boundary)
- [API contract](#api-contract)
- [Where new code belongs](#where-new-code-belongs)

## System map

    Browser
      -> Next.js web application
      -> FastAPI API
          -> Supabase Auth, Postgres, and Storage
          -> Polar
      -> server-sent event stream from FastAPI

    Worker
      -> Postgres job queue
      -> YouTube audio acquisition
      -> temporary private Storage object
      -> Groq transcription
      -> OpenRouter briefing generation
      -> Postgres result and usage settlement

The browser never receives Groq, OpenRouter, Polar, or Supabase secret
credentials.

## Repository map

| Path | Responsibility |
| --- | --- |
| `apps/backend/fathom/api` | HTTP routes, authentication dependencies, request and response translation |
| `apps/backend/fathom/application` | User use cases and business rules |
| `apps/backend/fathom/orchestration` | Background job claiming and execution |
| `apps/backend/fathom/crud/supabase` | Database queries and RPC calls |
| `apps/backend/fathom/services` | External providers and low-level I/O |
| `apps/backend/fathom/schemas` | Pydantic transport and structured-content contracts |
| `apps/backend/fathom/core` | Configuration, errors, logging, middleware, and runtime primitives |
| `apps/web` | Next.js routes, authentication UX, product UI, and browser state |
| `packages/api-client` | Generated OpenAPI schema, types, and authenticated client |
| `supabase` | Database migrations, tests, seed, and local configuration |
| `scripts` | Cross-application generation and operator commands |
| `docs` | Owner and developer explanation |

Talven is the product name. Fathom remains the repository, Python import, and
JavaScript package namespace.

## Backend dependency direction

The normal direction is:

    api -> application -> crud/services
    orchestration -> application/crud/services
    api/application -> schemas

Rules:

- Routers own HTTP behavior. They stay thin.
- Application modules own user-visible rules.
- CRUD modules own persistence operations.
- Services translate external provider behavior into Talven concepts.
- Orchestration owns job stages, leases, retries, and shutdown.
- Deep layers raise domain errors, not FastAPI `HTTPException`.

## Frontend structure

Important routes:

| Route | Responsibility |
| --- | --- |
| `/` | Public landing page |
| `/signin`, `/signup`, `/auth/**` | Authentication and recovery |
| `/app` | Authenticated workspace |
| `/app/briefings/new` | Source validation and session creation |
| `/app/briefings/sessions/{id}` | Progress, reader, exports, and publication controls |
| `/app/briefings` | Private library |
| `/app/billing` | Plans, balances, usage history, orders, and refunds |
| `/b/{publicSlug}` | Public Unlisted or Listed briefing |
| `/explore` | Curated Listed catalogue |

Feature-specific components, controllers, and styles stay near their route.
Cross-feature UI belongs in `components`; cross-feature data and browser
utilities belong in `lib`.

## Briefing lifecycle

### 1. Create or reuse

`POST /briefing-sessions`:

1. authenticates the user;
2. normalizes the source;
3. reads source duration;
4. checks usage admission;
5. joins the user's active matching job, restores their ready job, uses
   compatible cached work, or creates a new queued job; and
6. returns a session snapshot.

Every user owns a separate job. Shared processing does not create shared
account, library, or billing state.

### 2. Claim work

Postgres is the durable queue. The worker claims a runnable job through a
database command that assigns a renewable lease and ownership token.

`LISTEN/NOTIFY` wakes workers quickly. The database row remains authoritative
because notifications can be missed or duplicated. A bounded safety sweep
recovers missed wake-ups.

An expired worker cannot overwrite a newer worker because writes require the
current lease token.

### 3. Resolve the transcript

The worker:

1. checks for a compatible ready transcript;
2. downloads bounded audio when needed;
3. uploads it to a private temporary Storage location;
4. creates a short-lived URL for Groq;
5. validates transcript text and timestamp segments;
6. persists the transcript and segments; and
7. deletes temporary audio.

### 4. Resolve the briefing

The summary identity includes the transcript, prompt/processing version, and
model. One producer token controls a compatible summary:

- `pending`: one producer owns generation;
- `ready`: validated Markdown is reusable; and
- `failed`: later valid work may take over.

The model returns structured JSON. Talven validates evidence references and
renders Markdown deterministically. Partial model text never becomes the
authoritative briefing.

### 5. Settle usage

After a valid briefing exists, one atomic database command:

- consumes subscription credit first;
- consumes eligible pack credit second;
- records any permitted debt;
- updates the entitlement snapshot; and
- creates the unique `usage_settlements` row for the job.

The settlement row is also the immutable usage-history entry. Replaying the
command returns the existing row and does not charge twice.

The job becomes ready only after settlement succeeds.

## Progress delivery

The browser first reads an authoritative snapshot and then opens a server-sent
event stream.

Progress events are persisted in `job_events`. Postgres notifications wake
one coordinator per API process. The coordinator fetches persisted events and
fans them out to local streams.

Recovery rules:

- 15-second keepalives show transport health;
- a stale or disconnected client reconnects with `Last-Event-ID`;
- bounded persisted events replay;
- a snapshot converges the final state;
- overflow uses reconciliation instead of dropping truth; and
- renewable database leases cap simultaneous streams.

The event stream improves responsiveness. The database snapshot remains the
source of truth.

## Cache and reuse

| Layer | Identity includes | Reuse rule |
| --- | --- | --- |
| Source/job | Normalized source and user rules | One matching active or ready job per user |
| Transcript | Source plus transcription provider contract | Reuse only compatible validated segments |
| Briefing | Transcript plus prompt/version and model | Reuse only compatible ready Markdown |
| PDF | Briefing plus PDF cache version | Reuse only the current renderer contract |

A cache never grants authorization. API ownership checks and database RLS still
decide whether a user may read the result.

## Data and security boundaries

Talven uses two Supabase identities:

- the browser identity carries the signed-in user's token and has narrow
  tenant-scoped reads;
- the backend service identity can perform privileged commands only after the
  API has checked authentication and the request.

Key rules:

- private reads require an owned job;
- most mutations are server-only;
- public publication reads expose an approved public projection;
- publication mutations require the owner;
- Listed visibility also requires an operator user ID;
- billing updates require verified Polar events or server reconciliation;
- Storage buckets are private;
- PDF and temporary-audio access uses short-lived server-mediated URLs; and
- RLS and grants are both tested.

Exact tables and policies are in [Data model reference](./reference/data-model.md).

The current list queries, hydration, caches, indexes, and pagination decisions
are in [Performance reference](./reference/performance.md).

## Publication boundary

`briefing_publications` connects a public page to:

- one owner job;
- one ready summary;
- one immutable normalized source key; and
- one stable unguessable slug.

Private records never appear through public routes. Explore queries add the
stricter requirements of Listed visibility, clear moderation state, topic, and
listing time.

Saving a public briefing executes one protected database command. It creates
or returns the viewer's private job without a provider call or usage
settlement.

## API contract

FastAPI routes and Pydantic models own the REST contract.

    pnpm generate:api-client

regenerates the committed OpenAPI document and TypeScript schema.

    pnpm check:api-contract

fails when generated artifacts do not match the backend. SSE event payloads use
an explicit runtime-validated contract because OpenAPI does not describe a
long-lived event stream.

See [API reference](./reference/api.md).

## Where new code belongs

Ask these questions in order:

1. Is it an HTTP concern? Use `api`.
2. Is it a user or business rule? Use `application`.
3. Is it a database operation? Use `crud/supabase`.
4. Is it an external provider or low-level I/O adapter? Use `services`.
5. Is it background stage execution? Use `orchestration`.
6. Is it a transport or structured-content model? Use `schemas`.
7. Is it feature-specific UI? Keep it beside the route.
8. Is it reusable across workspace applications? Use `packages`.

Avoid generic `utils`, `helpers`, or `common` folders unless the contents
have one precise responsibility.

## Next read

[Data model reference](./reference/data-model.md)
