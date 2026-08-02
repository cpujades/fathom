# API contract and client generation

Talven uses two browser/backend contracts: generated OpenAPI types for ordinary
HTTP requests and an explicitly validated event contract for SSE streaming.

## REST contract

The source of truth is the FastAPI routes and Pydantic response models.
Generation has two committed outputs:

1. `scripts/export_openapi.py` creates `packages/api-client/openapi.json`.
2. `packages/api-client/scripts/generate.mjs` creates
   `packages/api-client/src/schema.ts` with `openapi-typescript`.
3. `packages/api-client/src/types.ts` gives frequently used schema types short,
   stable names.
4. `packages/api-client/src/client.ts` creates the authenticated
   `openapi-fetch` client used by the web application.

From the repository root, regenerate both artifacts after changing a route,
query parameter, request model, or response model:

```bash
pnpm generate:api-client
```

Verify that neither artifact is stale without modifying files:

```bash
pnpm check:api-contract
```

Pull-request CI checks the OpenAPI JSON in the backend job and the generated
TypeScript in the frontend job. A backend contract change therefore cannot be
merged with an old browser client.

Do not edit `openapi.json` or `schema.ts` by hand. A surprising generated diff
should be traced back to the FastAPI route or Pydantic model that produced it.

## SSE contract

OpenAPI documents the streaming endpoint but cannot express each named SSE
event payload. The server produces those payloads in
`application/briefings/sessions/streaming.py`; the browser parses and validates
them in `app/app/briefings/sessionStream.ts`.

Supported event names are:

| Event | Payload |
| --- | --- |
| `session.snapshot`, `session.updated`, `session.ready`, `session.failed` | Complete `BriefingSessionResponse` |
| `session.status` | Status/progress fields without the complete source contract |
| `session.content_delta` | Appended Markdown plus status/progress fields |
| `session.event` | Persisted diagnostic event metadata |

The parser accepts LF and CRLF framing, handles chunk boundaries and comments,
and rejects invalid JSON or payload shapes before they enter React state. When
an SSE payload changes, update the producer, validator, reducer types, and
`sessionStream.test.mjs` together.

## Boundary rules

- Use `createApiClient` for documented REST routes instead of raw `fetch`.
- Raw `fetch` is appropriate for SSE because `openapi-fetch` does not own the
  event-stream lifecycle.
- Re-export generated schema types; do not recreate manual lookalike types in
  the web app.
- Runtime validation is still required for data that OpenAPI generation cannot
  describe, such as named SSE frames or browser storage.
