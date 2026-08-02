# Security and data access

Talven uses two distinct Supabase identities:

- The browser/user identity carries a signed Supabase access token. It is
  intentionally weak and tenant-scoped.
- The backend service identity holds the Supabase secret key. It may perform
  trusted server commands and storage operations after the API has checked the
  user and request.

The service key must never be sent to the browser, embedded in frontend
configuration, or logged.

For the table-by-table schema, foreign keys, RLS boundary, server RPCs, and
Python CRUD modules, see [Database, RLS, and persistence](./database-and-persistence.md).

## Browser data boundary

The final migration revokes inherited/default privileges first, then grants
the authenticated role `SELECT` on only three application tables:

| Table | Browser operation | RLS condition |
| --- | --- | --- |
| `jobs` | Read | `user_id` equals the signed-in user |
| `summaries` | Read | Summary is non-empty and `ready`, and an owned job referencing it is `succeeded` or `deleted` |
| `job_events` | Read | The referenced job belongs to the signed-in user |

The browser has no direct insert, update, or delete permission on application
tables. It also cannot directly read transcripts, plans, entitlements, usage
ledger rows, settlements, Polar records, rate-limit buckets, or transcript
segments.

Anonymous users have no application-table privileges.

RLS is enabled on all 16 current public application tables. `FORCE ROW LEVEL
SECURITY` is intentionally not enabled because trusted table owners and the
service role run server operations. Security therefore depends on keeping
server credentials server-only.

## Why a user can still use the product normally

Read-only browser permission does not make the product read-only. It changes
where mutations happen:

- The browser asks the authenticated FastAPI endpoint to create, archive,
  restore, pay, refund, or export.
- The API checks ownership and input.
- The API uses the service client or a narrowly scoped database command.
- RLS still protects direct browser reads and blocks cross-tenant access.

This is a standard trusted-server pattern: the user may request an action, but
cannot invent privileged database changes with browser developer tools.

## Server command boundary

Sensitive multi-row operations are database functions with:

- `SECURITY DEFINER`;
- a fixed `search_path`;
- strict input validation;
- explicit grants to `service_role`; and
- no execution grant for `anon` or `authenticated`.

The active server commands cover lease-aware job and stream claims, idempotent
session creation, summary ownership, usage settlement, atomic refund admission,
ordered webhook application, billing-maintenance ownership, and PDF generation
claims.

Two settlement-exempt compatibility functions remain because the newer
wrappers call them internally, but direct `service_role` execution is revoked.
This prevents current application code from accidentally creating or claiming
work that bypasses settlement.

## Settlement boundary

A worker may attach a ready summary before usage settlement, but neither the
API nor summary RLS exposes it yet. The result becomes visible only after:

1. one immutable job-level settlement has committed; and
2. the same current lease marks the job `succeeded`.

This prevents a signed-in user from bypassing the UI and reading a result in
the short finalization window before usage is recorded.

## Storage boundary

Both `fathom` and `fathom_groq` buckets converge to `public = false`, even if
an earlier environment accidentally created one as public.

- The browser cannot list, read, upload, change, or delete objects directly.
- The API first proves application ownership through RLS, then the service
  client creates a short-lived signed URL or uploads a PDF.
- The worker uses the service client for temporary audio.

Database tests exercise actual authenticated-role insert, update, delete, and
list attempts. See [Storage access boundary](../security/storage-access.md).

## PDF and outbound HTTP boundaries

PDF input is untrusted. Rendering:

- escapes raw HTML;
- permits a small Markdown-produced HTML allowlist;
- removes unsafe link targets and disallows local/private destinations;
- denies all external and local resource fetching;
- runs in a disposable subprocess;
- limits input and output size;
- has a hard deadline and a process-local concurrency cap; and
- uses a database claim so only one API instance renders one summary/version.

The renderer subprocess receives a minimal environment without application
secrets. This is application-level containment, not a separate operating-system
security boundary: production must still run the API as a non-root identity in
a constrained container/service, with bounded CPU and memory and no unnecessary
network or filesystem access.

Polar requests require HTTPS. Automatic redirects are disabled; only a bounded
307/308 redirect to the same origin is accepted, so the bearer token cannot be
forwarded to another host. Responses are size-bounded, and provider IDs are
encoded as one URL path segment.

## Verification evidence

These are dated evidence records, not a permanent guarantee for every later
commit. The repository’s prior evidence includes a July 30, 2026 full
clean-database run and a July 31 focused billing run. The current `main` is
`b8c7b02` (`v0.20.4`) and has had later refactoring after those records, so an
exact release candidate must repeat the clean-database gate before it is called
verified.

- The July 30 baseline applied all then-current migrations from an empty
  disposable local Supabase database and passed all then-current pgTAP suites.
- The July 31 refund/recovery migration passed 51 focused pgTAP assertions and
  five live concurrency tests.
- The suites cover RLS/ACLs, cross-tenant reads, storage denial, job leases,
  idempotent creation, summary lifecycle, settlement, webhook ordering, event
  replay, and PDF generation fencing.
- During the July 31 exact-candidate retry, only the stopped disposable database
  container was removed and recreated; its persisted local volume was preserved.
  Docker Desktop then stalled while starting the replacement container, so the
  full clean-database gate remains explicitly pending.
- No shared or hosted database was reset or deleted.

Important remaining non-code controls include service-key management, hosted
backup and restore proof, retention/privacy approval, real-provider data
settings, CAPTCHA/bot controls, and operator access controls.
