# Talven documentation

This file is the index for Talven's documentation. It points you to the right
chapter; the detailed explanations live in the linked files.

Use the owner path when you want to learn or make a decision. Use the topic
index when you already know what you are looking for.

## Start here

If this is your first pass through the project, read:

1. [Product and user workflows](./product/user-workflows.md) to see what a user
   experiences.
2. [Repository and code map](./architecture/repository-and-code-map.md) to learn
   where each responsibility lives.
3. [System and job lifecycle](./architecture/system-and-job-lifecycle.md) to
   follow one briefing through API, worker, providers, storage, and settlement.
4. [Briefing product behavior](./product/briefing-behavior.md) for the visible
   rules, limits, reuse, charging, recovery, and exports.

After those four chapters, use the owner path below instead of reading every
file in alphabetical order.

## Remaining owner reading path

### Chapter 1: Polar, plans, payments, and webhooks

Read in this order:

1. [Polar environments and testing](./runbooks/polar-environments-and-testing.md#talven-plans-and-polar-products):
   plan fields, tracked versus private/generated files, sandbox/production
   separation, catalog generation, create/reuse behavior, partial-failure
   recovery, checkout, refunds, and live proof.
2. [Billing and Polar webhooks](./architecture/billing-and-webhooks.md#what-a-webhook-is): what a
   webhook is, example payload and handler, signatures, event ordering,
   idempotency, entitlements, refunds, and reconciliation.
3. [Worker and billing incidents](./runbooks/worker-and-billing-incidents.md):
   diagnosis and safe recovery when billing or settlement fails.
4. [Unit economics](./product/unit-economics.md): base price, customer tax,
   Polar fees, processing cost, business contribution, autónomo cost, and IRPF
   planning.

Finish this chapter able to explain which plan file to edit, when to run the
generator, which commands mutate providers, why checkout return is not payment
proof, and why duplicate webhooks are safe.

### Chapter 2: Supabase schema and security

Read in this order:

1. [Database, RLS, and persistence](./architecture/database-and-persistence.md):
   the 17-table map, primary/foreign keys, deletion behavior, RLS, grants,
   functions/RPCs, CRUD modules, and read-only queries for exact columns.
2. [Security and data access](./architecture/security-and-data-access.md): what
   the browser, API, service role, worker, and Storage layer may access.
3. [Performance, queries, and caching](./architecture/query-performance-and-caching.md):
   the full browser, API, database, worker, provider, Storage, SSE, query,
   caching, load-test, and performance roadmap.
4. [Supabase environments and migrations](./runbooks/supabase-environments-and-migrations.md):
   local, CI, staging, and production databases; migration deployment;
   connection modes; and backup boundaries.
5. [Storage access boundary](./security/storage-access.md): private buckets,
   signed access, and server-mediated object operations.

For exact implementation detail, continue into `supabase/migrations/`,
`supabase/tests/database/`, and `apps/backend/fathom/crud/supabase/` as directed
by the database chapter.

Finish this chapter able to explain how RLS and grants work together, which
tables the browser can read, why most mutations are server-only, how an RPC
protects a multi-row rule, and why database backups do not restore Storage
objects.

### Chapter 3: what blocks launch and what can wait

Read in this order:

1. [Pre-production review register](./decisions/pre-production-review-register.md#how-to-sort-a-decision):
   the short launch checklist and the meaning of accepted, code-verified,
   external-proof, paid-launch, deferred, and optional work.
2. [Deferred work register](./decisions/deferred-work.md): why larger changes
   are postponed, what evidence would reactivate them, and what a safe future
   version needs.
3. [Future billing options](./product/future-billing-options.md): the launch
   billing contract and the evidence required before subscriber discounts,
   custom packs, or metered pay as you go.
4. [First deployment checklist](./runbooks/first-deployment-checklist.md):
   hosting topology, HTTPS/origins, public signup, SMTP, Polar webhook,
   retention, backups, support, and release proof.
5. [Operational metrics and provider review](./runbooks/operational-metrics-and-provider-review.md):
   Grafana versus provider dashboards, alerts, review cadence, capacity
   thresholds, and provider-change evidence.

Use the pre-production register as the checklist. Use deferred work for the
reasoning behind “not now.” An item may remain deferred after review; launch
does not require building every possible improvement.

### Chapter 4: launch feature scope

Read in this order:

1. [Paid launch action plan](./product/paid-launch-action-plan.md): the accepted
   six-feature boundary, execution order, plain-language product contracts,
   minimum acceptance criteria, staging beta, production rehearsal, marketing,
   and free-access decision.
2. [Growth and product feature roadmap](./product/growth-feature-roadmap.md#current-launch-scope-decision):
   the deeper feature proposals, reward values, evaluation ideas, metrics, and
   later extensions.

Together they cover:

- Markdown/clipboard export;
- private-by-default unlisted/public sharing;
- referrals and promotional credits;
- the cited “Ask this episode” MVP;
- curated Explore and saving to a library;
- later identity, follows, digests, and advanced research.

Use the action plan to decide what happens next. Use the roadmap when designing
one specific feature. Sharing is the common foundation for saving, referrals,
and Explore; Ask this episode is an independent workstream. Do not treat either
document as proof that proposed behavior is already implemented.

### Chapter 5: operate and release

Once hosting and feature scope are chosen, read:

1. [First deployment checklist](./runbooks/first-deployment-checklist.md).
2. [Hosted Auth and service probes](./runbooks/hosted-auth-and-service-probes.md).
3. [Quality gates and GitHub Actions](./runbooks/quality-gates-and-github-actions.md).
4. [Local recovery rehearsal](./runbooks/local-recovery-rehearsal.md).
5. [Release automation](./runbooks/release-automation.md).
6. [Operational metrics and provider review](./runbooks/operational-metrics-and-provider-review.md).

Passing code checks is not the complete launch proof. The pre-production and
deployment chapters identify the real-provider, staging, human UX, privacy,
backup, alerting, capacity, and support evidence that remains external.

## Full topic index

### Product and business

- [Product and user workflows](./product/user-workflows.md): complete
  user-facing journey.
- [Briefing product behavior](./product/briefing-behavior.md): current product
  rules and limits.
- [Unit economics](./product/unit-economics.md): revenue, cost, margin, and
  Spanish owner-cash model.
- [Future billing options](./product/future-billing-options.md): current launch
  contract and evidence-gated subscriber discounts, custom packs, and PAYG.
- [Paid launch action plan](./product/paid-launch-action-plan.md): accepted MVP
  scope, execution order, acceptance criteria, beta, rehearsal, and launch.
- [Growth feature roadmap](./product/growth-feature-roadmap.md): staged export,
  sharing, referral, episode Q&A, Explore, and later social/research work.

### Architecture and security

- [Repository and code map](./architecture/repository-and-code-map.md).
- [Frontend, authentication, and user flows](./architecture/frontend-auth-and-user-flows.md).
- [System and job lifecycle](./architecture/system-and-job-lifecycle.md).
- [Cache and versioning](./architecture/cache-and-versioning.md).
- [Performance, queries, and caching](./architecture/query-performance-and-caching.md).
- [Database, RLS, and persistence](./architecture/database-and-persistence.md).
- [Billing and Polar webhooks](./architecture/billing-and-webhooks.md).
- [API contract and client generation](./architecture/api-contract.md).
- [Security and data access](./architecture/security-and-data-access.md).
- [Runtime safety, in plain language](./architecture/runtime-safety-explained.md).
- [Storage access boundary](./security/storage-access.md).

### Providers, sources, and scale decisions

- [Polar environments and testing](./runbooks/polar-environments-and-testing.md).
- [Supabase environments and migrations](./runbooks/supabase-environments-and-migrations.md).
- [Provider economics and limits](./decisions/provider-economics-and-limits.md).
- [Audio acquisition and temporary delivery](./decisions/audio-acquisition-and-delivery.md).
- [Long-audio and transcription decision](./decisions/long-audio-and-transcription.md).
- [Operational metrics and provider review](./runbooks/operational-metrics-and-provider-review.md).

### Launch decisions and operations

- [Pre-production review register](./decisions/pre-production-review-register.md).
- [Deferred work register](./decisions/deferred-work.md).
- [First deployment checklist](./runbooks/first-deployment-checklist.md).
- [Hosted Auth and service probes](./runbooks/hosted-auth-and-service-probes.md).
- [Worker and billing incidents](./runbooks/worker-and-billing-incidents.md).
- [Quality gates and GitHub Actions](./runbooks/quality-gates-and-github-actions.md).
- [Local recovery rehearsal](./runbooks/local-recovery-rehearsal.md).
- [Release automation](./runbooks/release-automation.md).

### Setup, API, and quality reference

- [Local development](./getting-started/local-development.md).
- [Environment variables](./reference/environment.md).
- [HTTP API reference](./reference/http-api.md).
- [Briefing quality evaluation](./quality/briefing-evaluation.md).

## How to interpret the documentation

- Architecture and product pages describe current intended behavior.
- Runbooks explain actions, environments, proof, and incident recovery.
- Decision pages record accepted trade-offs, triggers, and launch gates.
- Product roadmap pages are proposals unless current workflow documentation
  explicitly says the feature exists.
- Migrations, tests, runtime code, and deployed provider settings remain the
  executable or external sources of truth.
