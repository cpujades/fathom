# API reference

**Authority:** FastAPI routes and Pydantic models.

Default local base URL:

    http://localhost:8080

The interactive OpenAPI page is available at `/docs` when enabled by the
application.

## Contents

- [Authentication](#authentication)
- [Meta](#meta)
- [Briefing sessions](#briefing-sessions)
- [Saved briefings](#saved-briefings)
- [Publications and Explore](#publications-and-explore)
- [Billing](#billing)
- [Webhook](#webhook)
- [Error contract](#error-contract)
- [SSE contract](#sse-contract)
- [Generated client](#generated-client)

## Authentication

Private endpoints require:

    Authorization: Bearer <supabase-access-token>

The API verifies the token and passes a small authenticated identity into the
application layer. Public endpoints are marked below.

## Meta

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| GET | `/meta/health` | Public | Process liveness |
| GET | `/meta/ready` | Public, rate-limited when configured | Dependency and runtime readiness |
| GET | `/meta/status` | Public | Coarse version, uptime, and event-delivery state |

## Briefing sessions

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| POST | `/briefing-sessions` | Private | Create, join, restore, or reuse a session |
| GET | `/briefing-sessions/{session_id}` | Private owner | Read the current snapshot |
| GET | `/briefing-sessions/{session_id}/events` | Private owner | Open the SSE progress stream |
| DELETE | `/briefing-sessions/{session_id}` | Private owner | Archive the session; returns 204 |
| GET | `/briefing-sessions/{session_id}/publication` | Private owner | Read publication state |
| POST | `/briefing-sessions/{session_id}/publication` | Private owner | Set Private, Unlisted, or allowed Listed state |

The delete route archives. It does not permanently erase the account or all
related data.

## Saved briefings

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| GET | `/briefings` | Private | Search and page the active library |
| GET | `/briefings/{briefing_id}` | Private owner | Read one saved briefing |
| POST | `/briefings/{briefing_id}/pdf` | Private owner | Generate or reuse a signed PDF |

`GET /briefings` supports:

- `limit`: 1–100, default 24;
- `offset`: zero or greater;
- `query`: up to 120 characters;
- `sort`: supported newest/oldest behavior; and
- `sourceType`: supported source filter.

## Publications and Explore

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| GET | `/explore` | Public | Page clear Listed briefings |
| GET | `/publications/{public_slug}` | Public | Read an Unlisted or Listed briefing |
| GET | `/publications/source-match?url=...` | Private | Find a compatible Listed briefing for a source |
| POST | `/publications/library-entries` | Private | Read save state for several public slugs |
| GET | `/publications/{public_slug}/library-entry` | Private | Read one save state |
| POST | `/publications/{public_slug}/save` | Private | Save compatible ready work without audio-minute charge |

`GET /explore` supports:

- `limit`: 1–100, default 24;
- `offset`: zero or greater; and
- `topic`: one controlled topic value.

Public slugs are 32 lowercase hexadecimal characters.

## Billing

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| GET | `/billing/plans` | Private | List active local plans |
| GET | `/billing/usage` | Private | Read subscription, pack, debt, and block state |
| GET | `/billing/usage-history` | Private | Page immutable settlement entries in batches of up to 10 |
| GET | `/billing/account` | Private | Read subscription, packs, orders, and refunds |
| POST | `/billing/checkout` | Private | Create a Polar checkout URL |
| POST | `/billing/portal` | Private | Create a Polar customer portal URL |
| POST | `/billing/packs/{polar_order_id}/refund` | Private owner | Start one pack refund |
| GET | `/billing/operations/{operation_id}` | Private owner | Read bounded checkout/refund confirmation state |

`GET /billing/usage-history` supports:

- `limit`: 1–10, default 10;
- `offset`: zero or greater; and
- `has_more`: returned instead of an exact total count.

Results use `settled_at` and `job_id` descending. Each entry contains the
settled subscription, pack, and debt seconds. An archived job remains in the
history, but its `session_path` is `null`.

## Webhook

| Method | Path | Access | Purpose |
| --- | --- | --- | --- |
| POST | `/webhooks/polar` | Polar signature | Apply a signed provider event |

The webhook verifies the raw body signature. It does not use browser
authentication.

## Error contract

Expected application errors use:

    {
      "error": {
        "code": "insufficient_video_time",
        "message": "The source is longer than the available video time.",
        "details": {
          "required_seconds": 1800,
          "available_seconds": 1200
        }
      }
    }

`details` is optional and bounded to known numeric fields. Clients should use
`code` for behavior and use `message` for display. Do not branch on English
message text.

## SSE contract

`GET /briefing-sessions/{session_id}/events` returns
`text/event-stream`.

The client:

- consumes validated event envelopes;
- records event IDs;
- reconnects with `Last-Event-ID`;
- treats keepalives as transport health;
- performs an authoritative snapshot during recovery; and
- handles replay truncation by converging to the snapshot.

SSE is not generated from the OpenAPI schema. Its runtime validator and backend
event schema must change together.

## Generated client

After changing an HTTP route or Pydantic transport model:

    pnpm generate:api-client
    pnpm check:api-contract

Committed outputs:

- `packages/api-client/openapi.json`;
- `packages/api-client/src/schema.ts`; and
- stable aliases in `packages/api-client/src/types.ts`.

The web application uses the authenticated client in
`packages/api-client/src/client.ts`.

## Next read

[Configuration reference](./configuration.md)
