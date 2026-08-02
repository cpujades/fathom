# HTTP API reference

This is the human navigation layer for Talven's current API. FastAPI routes and
Pydantic models remain the source of truth; the committed
`packages/api-client/openapi.json` contains the complete machine-readable
request and response schemas.

## Discovery and base URL

Locally, the default base URL is `http://localhost:8080`. Interactive API
documentation is available at `/docs`, `/redoc`, and `/openapi.json` in local
and test modes. Those discovery endpoints are disabled in staging and
production; use the committed OpenAPI file there.

All JSON and event-stream responses include `X-Request-Id`. A caller may send a
bounded `X-Request-ID` value to correlate its logs; otherwise the API creates
one.

## Authentication

Private routes require a Supabase access token:

```http
Authorization: Bearer <supabase-access-token>
```

The three `/meta/**` routes are public. `/webhooks/polar` is authenticated by
the raw-body Polar webhook signature, not by a user bearer token. Every other
route in the table below requires the bearer token and enforces user ownership
server-side.

## Endpoint inventory

| Method and path | Purpose | Main input | Main result |
| --- | --- | --- | --- |
| `GET /meta/health` | Process liveness | None | Basic healthy response |
| `GET /meta/ready` | Dependency/config readiness | None | Readiness state and checks |
| `GET /meta/status` | Bounded service snapshot | None | Version and service status |
| `POST /briefing-sessions` | Create, join, reuse, or restore work | JSON `url` | Session snapshot and resolution type |
| `GET /briefing-sessions/{session_id}` | Reconcile one owned session | Session UUID | Current session snapshot |
| `GET /briefing-sessions/{session_id}/events` | Stream progress and result events | Session UUID; optional `Last-Event-ID` | `text/event-stream` |
| `DELETE /briefing-sessions/{session_id}` | Archive one owned session | Session UUID | `204 No Content` |
| `GET /briefings` | List the user's library | `limit`, `offset`, `query`, `sort`, `sourceType` | Page of library entries |
| `GET /briefings/{briefing_id}` | Read a ready briefing | Briefing UUID | Markdown and any current PDF URL |
| `POST /briefings/{briefing_id}/pdf` | Generate or reuse the bounded PDF export | Briefing UUID | Signed PDF URL |
| `GET /billing/plans` | List active catalog plans | None | Subscription and pack plans |
| `GET /billing/usage` | Read spendable time and debt | None | Subscription, pack, total, and block state |
| `GET /billing/briefings` | Read usage history | None | Up to 50 settlement/history entries |
| `GET /billing/account` | Read subscription, packs, and orders | None | Billing account snapshot |
| `POST /billing/checkout` | Start Polar checkout | JSON `plan_id` UUID | Polar checkout URL |
| `POST /billing/portal` | Open Polar customer portal | None | Portal URL |
| `POST /billing/packs/{polar_order_id}/refund` | Request a refundable pack refund | Polar order ID | Pending/refund resolution |
| `POST /webhooks/polar` | Apply a signed provider event | Raw signed JSON body | `{ "status": "ok" }` |

The library query defaults are `limit=24`, `offset=0`, `sort=newest`, and
`sourceType=all`. `limit` is bounded from 1 to 100, `query` to 120 characters,
and `sort` to `newest` or `oldest`.

## Error contract

Application and validation failures use one stable envelope:

```json
{
  "error": {
    "code": "invalid_request",
    "message": "Invalid request"
  }
}
```

Common statuses are:

| Status | Meaning |
| --- | --- |
| `400` | Invalid URL, identifier, body, query, or domain request |
| `401` | Missing, expired, or invalid Supabase token |
| `403` | Authenticated but not permitted |
| `404` | Owned resource does not exist or is not visible to this user |
| `413` | Request body exceeds the API's 64 KB limit |
| `429` | Shared rate limit exceeded |
| `500` | Configuration or unexpected server failure |
| `502` | Supabase, Polar, Groq, OpenRouter, or another upstream failed |
| `503` | Dependency or bounded service capacity is temporarily unavailable |

The exact documented responses for each route live in OpenAPI. Rate-limit
scopes, exemptions, and proxy requirements are in the
[hosted service runbook](../runbooks/hosted-auth-and-service-probes.md#application-rate-limits).

## Example: create and follow a session

Set shell variables without committing them:

```bash
export TALVEN_API_URL="http://localhost:8080"
export TALVEN_ACCESS_TOKEN="<supabase-access-token>"
```

Create a session:

```bash
curl --fail-with-body \
  --request POST \
  --header "Authorization: Bearer ${TALVEN_ACCESS_TOKEN}" \
  --header "Content-Type: application/json" \
  --data '{"url":"https://www.youtube.com/watch?v=VIDEO_ID"}' \
  "${TALVEN_API_URL}/briefing-sessions"
```

Use the returned `session_id` for a snapshot or event stream:

```bash
curl --fail-with-body \
  --header "Authorization: Bearer ${TALVEN_ACCESS_TOKEN}" \
  "${TALVEN_API_URL}/briefing-sessions/SESSION_ID"

curl --no-buffer --fail-with-body \
  --header "Authorization: Bearer ${TALVEN_ACCESS_TOKEN}" \
  --header "Accept: text/event-stream" \
  --header "Last-Event-ID: OPTIONAL_PREVIOUS_EVENT_ID" \
  "${TALVEN_API_URL}/briefing-sessions/SESSION_ID/events"
```

Do not log or commit the access token. Browser code should use
`createApiClient` from `@fathom/api-client` instead of building these requests
manually. The raw-fetch exception is the SSE lifecycle, whose event payloads
are runtime validated as described in
[API contract and client generation](../architecture/api-contract.md).

## Changing the API

After changing a route, query, Pydantic request, or response model:

```bash
pnpm generate:api-client
pnpm check:api-contract
```

Update this table only when endpoint purpose, authentication, or operator-facing
behavior changes. Schema field details belong in the generated contract, not in
a second hand-maintained copy.
