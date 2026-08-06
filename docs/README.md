# Talven documentation

These pages describe the product as it behaves now. Read them in the order
below when taking ownership of the project. The first section builds the user
mental model; the second follows the request through the system; the remaining
sections explain the contracts, data, operations, and deliberate trade-offs.

## Recommended reading order

1. [Product and user workflows](./product/user-workflows.md): what a person
   sees from landing page through sign-up, first briefing, library, billing,
   refund, recovery, and failure states.
2. [Local development from a fresh clone](./getting-started/local-development.md):
   how to run the complete authenticated journey locally.
3. [Environment configuration](./reference/environment.md): what each process
   can reach, every application variable, and the local/staging/production
   boundary.
4. [Repository and code map](./architecture/repository-and-code-map.md): where
   each responsibility lives and where new code belongs.
5. [Frontend, authentication, and user flows](./architecture/frontend-auth-and-user-flows.md):
   the browser route map, auth boundaries, navigation, SSE client, and browser
   cache ownership.
6. [System and job lifecycle](./architecture/system-and-job-lifecycle.md):
   the API, queue, worker, transcript, summary, settlement, and event path.
7. [Cache and versioning](./architecture/cache-and-versioning.md): exactly
   what is reusable, which keys protect compatibility, and what “cache hit”
   means for a user and for billing.
8. [Database, RLS, and persistence](./architecture/database-and-persistence.md)
   and [Supabase environments and migrations](./runbooks/supabase-environments-and-migrations.md):
   the 17 application tables, foreign keys, row-level security, server RPCs,
   and how the schema moves through local development, PR CI, staging, and
   production.
9. [Billing and Polar webhooks](./architecture/billing-and-webhooks.md):
   signature verification, normalized events, idempotency, ordering, refund
   behavior, and reconciliation.
10. [API contract and client generation](./architecture/api-contract.md) and
    the [HTTP API reference](./reference/http-api.md): request/response
    contracts, SSE frames, auth, errors, and practical examples.
11. [Security and data access](./architecture/security-and-data-access.md)
    and [Runtime safety, in plain language](./architecture/runtime-safety-explained.md):
    why the boundaries exist and what they do under failure or concurrency.
12. [Briefing product behavior](./product/briefing-behavior.md), the
    [quality evaluation](./quality/briefing-evaluation.md), and the
    [decisions](./decisions/deferred-work.md): current limits, quality rules,
    and what is intentionally not built yet.
13. [Unit economics](./product/unit-economics.md),
    [provider economics and limits](./decisions/provider-economics-and-limits.md),
    [audio acquisition and delivery](./decisions/audio-acquisition-and-delivery.md),
    and the [growth feature roadmap](./product/growth-feature-roadmap.md): the
    current commercial assumptions, provider/source boundaries, and staged
    product options that remain proposals rather than implemented behavior.
14. Finish with the [runbooks](#runbooks) when you are ready to operate or
    release the system.

## Reference pages

- [Product and user workflows](./product/user-workflows.md): the user-facing
  walkthrough linked above.
- [User workflow improvement register](./product/user-workflow-improvement-register.md):
  known experience gaps, why they matter, and the implementation and evidence
  needed to close them.
- [Cache and versioning](./architecture/cache-and-versioning.md): server,
  browser, and PDF cache behavior.
- [Database, RLS, and persistence](./architecture/database-and-persistence.md):
  tables, relationships, grants, RPCs, and CRUD modules.
- [Billing and Polar webhooks](./architecture/billing-and-webhooks.md): the
  provider-event lifecycle and repair path.
- [Security and data access](./architecture/security-and-data-access.md):
  browser permissions, backend privileges, RLS, server commands, storage,
  billing, and export boundaries.
- [Runtime safety, in plain language](./architecture/runtime-safety-explained.md):
  account-scoped browser caching, shared-cache privacy, password recovery,
  worker and stream admission, downloader cleanup, hosted configuration,
  billing recovery, PDF/download UX, launch evidence, debt, and retention.
- [Briefing product behavior](./product/briefing-behavior.md): what a user sees,
  duplicate submissions, caching, charging, archive/restore, output quality,
  limits, and deliberately deferred features.
- [Unit economics and owner cash model](./product/unit-economics.md): Polar
  Early Member fees, tax-exclusive price arithmetic, provider costs, explicit
  user scenarios, first-year autónomo treatment, and IRPF reserve boundaries.
- [Growth and product feature roadmap](./product/growth-feature-roadmap.md):
  proposed Markdown/clipboard export, public sharing, referrals, cited episode
  chat, discovery, follows, digests, and advanced research layers.
- [Long-audio and transcription decision](./decisions/long-audio-and-transcription.md):
  the current YouTube-to-Groq pipeline, the reason for the initial two-hour limit,
  provider options, and the safe path to longer videos.
- [Audio acquisition and temporary delivery](./decisions/audio-acquisition-and-delivery.md):
  the current bounded YouTube path, `pytubefix` versus `yt-dlp`, podcast RSS and
  upload alternatives, Supabase versus R2 delivery, cleanup, and the source
  policy boundary.
- [Provider economics, limits, and scaling boundaries](./decisions/provider-economics-and-limits.md):
  end-to-end file-size limits, synchronous versus batch transcription, Groq,
  Cloudflare and open-source options, Supabase/Railway billing, egress,
  retention, email, and the required cost dashboard.
- [Deferred work register](./decisions/deferred-work.md): accepted product and
  technical deferrals, why they are not current blockers, and their revisit
  triggers.
- [Pre-production review register](./decisions/pre-production-review-register.md):
  product decisions and operational evidence still required before an
  external public beta or paid public launch.
- [Briefing quality evaluation](./quality/briefing-evaluation.md): deterministic
  and opt-in paid evaluation.
- [Worker and billing incidents](./runbooks/worker-and-billing-incidents.md):
  operator diagnosis and reconciliation.
- [Polar environments and testing](./runbooks/polar-environments-and-testing.md):
  sandbox versus production identities, plan/product mapping, local webhook
  setup, provider proof boundaries, and official references.
- [Hosted Auth and service probes](./runbooks/hosted-auth-and-service-probes.md):
  Supabase Dashboard configuration, real recovery-email proof, liveness,
  readiness, rate limits, and proxy behavior.
- [Supabase environments and migrations](./runbooks/supabase-environments-and-migrations.md):
  the separate local, CI, staging, and production databases; safe migration
  commands; worker connection modes; and official provider references.
- [First deployment checklist](./runbooks/first-deployment-checklist.md): the
  future web/API/worker topology, HTTPS/origins, public signup, ingress/WAF,
  webhook, observability, retention, backups, and R2 decision in plain terms.
- [Release automation](./runbooks/release-automation.md): token ownership,
  protected-main behavior, rotation, failure diagnosis, and security tradeoffs.
- [Local recovery rehearsal](./runbooks/local-recovery-rehearsal.md): the
  project-specific Gate A, Gate B, and Gate C checks.
- [Quality gates and GitHub Actions](./runbooks/quality-gates-and-github-actions.md):
  exact local checks, pre-commit behavior, every PR workflow, post-merge
  release/staging/promotion automation, and what remains manual.
- [Storage access boundary](./security/storage-access.md): intended Supabase
  Storage access patterns.

## Runbooks

The operational pages are intentionally last in the learning path. They assume
you already understand the user workflow and the state model.

The names Gate A, Gate B, and Gate C are Talven project conventions, not
industry standards:

- Gate A is deterministic, provider-free application testing.
- Gate B is a fully migrated disposable database and concurrency test.
- Gate C is an authenticated product journey using test-only fake providers.

All three prove code behavior. They do not replace human UX review, real
provider validation, privacy decisions, backups, or an exact-candidate staging
rehearsal.

## Where checks run

The complete command and workflow inventory is in
[Quality gates and GitHub Actions](./runbooks/quality-gates-and-github-actions.md).

- The pre-commit hook stays fast: syntax, accidental-secret/large-file checks,
  Ruff, formatting, and strict backend type checking.
- Pull-request CI is the mandatory shared gate: it runs the direct backend
  checks and every CI-suitable pre-commit hook again, then backend tests,
  frontend lint/type checks, unit tests, and the
  production build. Only the local `no-commit-to-branch` hook is skipped in CI.
- A PR that changes `supabase/**` also starts a clean local database, applies
  every migration, runs the database suites, and lints the resulting schema.
- Gate C remains an explicit local/staging rehearsal because it needs an
  authenticated disposable user and several running services.

Do not put the full database rehearsal in pre-commit. Slow hooks are often
bypassed and require Docker on every contributor machine.
The local hook gives quick feedback; protected CI is what prevents an
unverified change from being merged.
