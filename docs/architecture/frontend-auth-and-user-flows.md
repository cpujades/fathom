# Frontend, authentication, and user flows

This page maps what happens between a browser route, Supabase Auth, the Talven
API, and the worker. It complements the backend-focused
[system and job lifecycle](./system-and-job-lifecycle.md).

For the product-language version of these journeys, read
[Product and user workflows](../product/user-workflows.md). For exact browser
cache TTL, keys, and invalidation rules, read
[Cache and versioning](./cache-and-versioning.md).

## Route map

| Route | Responsibility |
| --- | --- |
| `/`, `/privacy`, `/terms` | Public product and legal pages |
| `/signin`, `/signup` | Password, magic-link, and Google authentication entry points |
| `/auth/callback` | Verifies an email token or exchanges an OAuth/PKCE code, then restores a safe app destination |
| `/auth/recovery` | Displays the password-reset form only after a verified recovery callback |
| `/auth/recovery/callback` | Verifies the recovery token and sets a short-lived, HTTP-only recovery marker |
| `/auth/recovery/complete` | Clears the recovery marker after the password update |
| `/app` | Authenticated workspace and briefing entry form |
| `/app/briefings/new` | Validates the submitted source and creates or reuses a briefing session |
| `/app/briefings/sessions/{sessionId}` | Session progress, reconnectable event stream, reader, and exports |
| `/app/briefings` | Searchable library, processing refresh, open, and archive actions |
| `/app/billing` | Plans, checkout, portal, pack refund, balance, and billing history |
| `/app/account` | Supabase Auth profile metadata |

`apps/web/proxy.ts` asks Supabase for the current user at both sides of the auth
boundary. It protects every `/app/**` request and redirects a signed-in request
for `/signin` or `/signup` to its validated app destination before an auth form
can render. The `AppShellProvider` then owns browser session state, the API
access token, sign-out, and the small account-scoped usage cache used by the
authenticated shell.

## Authentication boundaries

Authentication has two related checks:

1. The Next.js proxy prevents an unauthenticated request from rendering an app
   route and preserves its intended `/app/**` destination in `next`. The same
   server-verified check prevents an authenticated user from rendering either
   authentication entry route.
2. The backend verifies the Supabase bearer token on every private API request.
   A frontend route being visible is never treated as API authorization.

Only local `/app/**` destinations are accepted after authentication. Absolute
URLs, protocol-relative URLs, and non-app paths fall back to `/app`. The only
preserved commercial intent is `intent=paid` with a bounded plan code. These
rules live in `apps/web/app/lib/url.ts` and prevent open redirects or arbitrary
query propagation.

The ordinary sign-in and sign-up paths support password, magic link, and Google
OAuth. `/auth/callback` accepts either a verified email token or an exchanged
authorization code, establishes the Supabase session cookie, and redirects to
the validated destination. Signup is public rather than invitation-only; the
`invite` token type accepted by the callback is a Supabase OTP protocol value,
not a Talven invitation gate.

A valid paid intent resolves against the hard-coded public pricing catalog and
adds product, price, included-time, and cadence context to both auth pages.
Unknown plans never become display copy. When password sign-up returns an
explicit existing-account result, the adjacent sign-in action carries only the
validated navigation context in its URL. The email is transferred through
`sessionStorage`, consumed once on sign-in, and never accompanied by the
proposed password. Magic-link sign-up retains its safe callback and describes
the combined behavior accurately: the link signs in an existing user and
creates an account only for a new user.

Password recovery is intentionally separate from ordinary authentication:

1. `/signin` asks Supabase to email a link to `/auth/recovery/callback`.
2. The callback verifies a recovery token or code.
3. A short-lived HTTP-only marker allows `/auth/recovery` to show the reset
   form.
4. The client updates the password through Supabase Auth and calls
   `/auth/recovery/complete` to clear the marker.

Hosted callback URLs, email behavior, and real-flow proof are documented in the
[hosted Auth runbook](../runbooks/hosted-auth-and-service-probes.md).

## Briefing journey

```text
/app form
  -> /app/briefings/new?url=...
  -> POST /briefing-sessions
  -> session snapshot cached for this user
  -> /app/briefings/sessions/{sessionId}
  -> GET snapshot + GET event stream
  -> worker progress and final briefing
  -> Markdown download or POST PDF generation
```

The create response says whether work is new, joined, or reused. The session
page first has an authoritative snapshot, then applies runtime-validated SSE
events. Received bytes and keepalive comments track transport health separately
from visible state changes. After 30 seconds without transport activity, or on
a dropped stream, the page reads one recovery snapshot and reconnects with
`Last-Event-ID` so bounded persisted events replay without duplicating content.
Invalid event payloads do not enter React state. Detailed cache, charging, and archive behavior is in
[briefing product behavior](../product/briefing-behavior.md); event ownership is
in [API contract and client generation](./api-contract.md).

The library uses `GET /briefings` for initial, filtered, and paginated reads. It
refreshes while entries are still processing. `DELETE /briefing-sessions/{id}`
archives the user-owned job; it does not delete shared transcript or summary
work. Re-submitting the same source can restore that ready job without another
charge.

## Billing journey

The billing page loads plans, usage, account state, and history through the
generated API client:

- checkout returns a Polar URL and the browser navigates to it;
- the customer portal returns a separate Polar URL;
- a pack-refund request immediately marks the visible pack as pending and
  holds its remaining seconds from the displayed balance;
- signed Polar webhooks and worker reconciliation make local billing state
  converge after redirects, retries, or missed delivery.

The browser never calls Polar with the server access token and never mutates
billing tables directly. See [security and data access](./security-and-data-access.md)
and the [worker and billing incident runbook](../runbooks/worker-and-billing-incidents.md).

## Browser data and cache ownership

Authenticated caches are keyed by the Supabase user ID. An auth transition
increments the session generation, clears in-memory account data, and prevents
responses started under the old user from committing. Usage snapshots may be
shared across tabs through `BroadcastChannel` and `localStorage`, but both the
channel and storage key are user-scoped. A backend `401` or `403` clears the
session and returns to sign-in.

Use these ownership points when changing frontend behavior:

- `apps/web/proxy.ts`: server-side app-route protection;
- `apps/web/app/components/AppShellProvider.tsx`: browser auth and usage shell;
- `apps/web/app/lib/appDataCache.ts`: account-scoped request and cache rules;
- `apps/web/app/lib/url.ts`: redirect and authentication intent validation;
- `apps/web/app/app/briefings/useBriefingSession.ts`: session snapshot, stream,
  retry, and export controller;
- `apps/web/app/app/billing/useBillingController.ts`: billing reads and actions;
- `packages/api-client`: generated, authenticated REST client.

When one of these flows changes, update its focused unit or browser test and
the corresponding architecture or product page. Authentication changes also
require the hosted callback rehearsal; stream changes require both server and
browser contract tests.
