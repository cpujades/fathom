# Talven documentation

These pages describe the product as it behaves now. Start here after time away
from the repository:

- [System and job lifecycle](./architecture/system-and-job-lifecycle.md):
  services, request flow, database queue, workers, leases, retries, shutdown,
  events, and recovery.
- [Security and data access](./architecture/security-and-data-access.md):
  browser permissions, backend privileges, RLS, server commands, storage,
  billing, and export boundaries.
- [Runtime safety, in plain language](./architecture/runtime-safety-explained.md):
  account-scoped browser caching, password recovery, worker and stream leases,
  billing recovery, refund concurrency, debt, URLs, and retention.
- [Briefing product behavior](./product/briefing-behavior.md): what a user sees,
  duplicate submissions, caching, charging, archive/restore, output quality,
  limits, and deliberately deferred features.
- [Long-audio and transcription decision](./decisions/long-audio-and-transcription.md):
  the current YouTube-to-Groq pipeline, the reason for the two-hour pilot limit,
  provider options, and the safe path to longer videos.
- [Deferred work register](./decisions/deferred-work.md): accepted product and
  technical deferrals, why they are not pilot blockers, and their revisit
  triggers.
- [Pre-production review register](./decisions/pre-production-review-register.md):
  product decisions and operational evidence still required before an
  invite-only pilot or paid public launch.
- [Briefing quality evaluation](./quality/briefing-evaluation.md): deterministic
  and opt-in paid evaluation.
- [Worker and billing incidents](./runbooks/worker-and-billing-incidents.md):
  operator diagnosis and reconciliation.
- [Hosted Auth and service probes](./runbooks/hosted-auth-and-service-probes.md):
  Supabase Dashboard configuration, real recovery-email proof, liveness,
  readiness, rate limits, and proxy behavior.
- [Release automation](./runbooks/release-automation.md): token ownership,
  protected-main behavior, rotation, failure diagnosis, and security tradeoffs.
- [Local recovery rehearsal](./runbooks/local-recovery-rehearsal.md): the
  project-specific Gate A, Gate B, and Gate C checks.
- [Storage access boundary](./security/storage-access.md): intended Supabase
  Storage access patterns.

The names Gate A, Gate B, and Gate C are Talven project conventions, not
industry standards:

- Gate A is deterministic, provider-free application testing.
- Gate B is a fully migrated disposable database and concurrency test.
- Gate C is an authenticated product journey using test-only fake providers.

All three prove code behavior. They do not replace human UX review, real
provider validation, privacy decisions, backups, or an exact-candidate staging
rehearsal.

## Where checks run

- The pre-commit hook stays fast: syntax, accidental-secret/large-file checks,
  Ruff, formatting, and backend type checking.
- Pull-request CI is the mandatory shared gate: backend tests, frontend lint,
  type checking, unit/browser accessibility tests, and production build.
- A PR that changes `supabase/**` also starts a clean local database, applies
  every migration, runs the database suites, and lints the resulting schema.
- Gate C remains an explicit local/staging rehearsal because it needs an
  authenticated disposable user and several running services.

Do not put the full database or browser rehearsal in pre-commit. Slow hooks are
often bypassed and require Docker or a browser on every contributor machine.
The local hook gives quick feedback; protected CI is what prevents an
unverified change from being merged.
