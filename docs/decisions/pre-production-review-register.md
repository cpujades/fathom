# Pre-production review register

**Status:** Active review register
**Last reviewed:** 2026-08-03

This is the short list of product decisions and real-environment proof Talven
still needs before wider use. It separates a code defect from a deliberate
product choice or an operational prerequisite. Passing automated tests is
necessary, but it does not prove provider quality, human usability, policy, or
production recovery.

As of this review, the application is not deployed. Application web/API/worker
traffic is local; Supabase and Polar use development, staging, or sandbox
credentials for realistic tests. Missing host-specific files are therefore not
a current code defect. They become mandatory configuration and proof at the
external public-beta boundary below.

## Status meanings

- **Accepted:** current behavior is intentional for the current pre-launch candidate.
- **Verified in code:** deterministic tests or disposable local integration
  proof cover the boundary.
- **External proof needed:** exercise the exact candidate with real
  configuration or human review before enabling public signup.
- **Public-launch decision:** may be deferred while the app is local only, but
  must be resolved before the public URL is announced.

### How to sort a decision

Use the label and evidence requirement, not how interesting the work sounds:

| Kind of item | What to do |
| --- | --- |
| Public-launch prerequisite | Resolve and prove it before unattended external signup. Origins, SMTP/Auth, logs/alerts, privacy/retention, support, and backup/restore belong here. |
| External or candidate proof | The code may already be correct; prove the real provider, staging, capacity, or human experience on the exact candidate. |
| Paid-launch decision | It may wait during local work or a private pilot, but explicitly accept or change it before public payment. |
| Trigger-based deferral | Leave it alone until its measurable trigger occurs. R2, Redis, shared source production, and cache-retention redesign are examples. |
| Optional product experiment | Build it only to test a clear acquisition, activation, or retention hypothesis. |

The [deferred work register](./deferred-work.md) owns the trigger and future-safe
shape of deferred technical/product work. The
[growth roadmap](../product/growth-feature-roadmap.md) owns optional feature
experiments. An item may remain deferred after review; the goal is to make that
choice deliberate, not to empty every list before launch.

## Owner review queue

These are explicit follow-up reviews requested by the product owner. They are
not approvals to change behavior. Each should be handled in a separate task
that first explains the current implementation in plain language, then checks
the evidence and records any resulting decision.

| Review task | Current scope to explain and inspect | Decision or evidence expected | Status |
| --- | --- | --- | --- |
| Local/staging security configuration | Environment validation; FastAPI middleware order; CORS allowlists and rejected wildcards; credentialed requests; trusted proxy/client-IP handling; local-development exceptions; Next.js CSP and other security headers; HSTS and HTTPS behavior; Supabase/Auth/Polar redirect origins | An environment-by-environment origin and proxy matrix; confirmation that local development remains usable; confirmation that staging/production fail closed; a plain-language before/after explanation of every header and middleware change; any hosting-dependent CSP decision recorded separately | Owner review requested before external configuration |
| Supabase query and connection load | One dedicated job-event listener per API process; coalesced persisted-event fetches per active job and replica; four bounded per-job dispatchers; overflow-triggered convergence; a 45-second reconciliation only while the listener is unhealthy; API rate-limit bucket writes; history/detail queries; database connections used by API and workers | Measured query/connection load for realistic early concurrency; the safe capacity envelope; listener health and notification latency; thresholds that would justify retention, pooling, or query/index changes | Owner review requested; measure before scaling changes |
| Content-suitability guardrails | Public YouTube inputs that are technically processable but may produce low-value briefings, including Shorts, gaming footage, silent/low-speech videos, clips, lectures, and interviews | Product definition of a suitable source; labeled examples; false-positive tolerance; charging/refund behavior; whether guidance, warnings, or rejection is appropriate before selecting an implementation | Owner review requested; implementation deferred |
| Provider retry and timeout budgets | Per-request versus per-stage deadlines; up to three classified attempts; whole-job retries; long-source behavior; user-facing waiting/recovery states; provider cost after interrupted attempts | Capped real-provider latency data by source length and failure type; chosen request, stage, and end-to-end budgets; confirmation of which failures retry and what the user sees | Owner review requested before tuning |
| PDF rendering design and capacity | Current isolated WeasyPrint subprocess; two concurrent renders per API process; five-second queue wait; 30-second render deadline; cache/single-flight behavior; CPU and memory isolation | Benchmark current memory, CPU, latency, and output fidelity; compare safe alternatives such as a dedicated export worker or another renderer; choose per-process capacity and scaling rules without weakening fetch/HTML/resource protections | Owner review requested before increasing concurrency or changing renderer |

A review is complete only when its explanation, measurements or examples,
trade-offs, chosen behavior, and follow-up actions are written down. An item
may remain deferred after review; the purpose is to make that deferral
deliberate and easy to revisit.

## Product and user journey

| Area | Current decision or evidence | Remaining proof or decision | Status |
| --- | --- | --- | --- |
| Supported source | Public YouTube URLs, with honest YouTube-specific copy | Human-test invalid, private, removed, age/region-restricted, short, silent, and non-podcast sources; keep messages useful rather than technical | External proof needed |
| Authentication intent | Preserve the submitted URL and safe destination through sign-in, recovery, and payment redirects; password recovery validates a verified recovery session and the 12-character-plus-digit contract | Test real Supabase email/OAuth/recovery links and real Polar return URLs on the exact candidate origins; confirm hosted Auth policy matches code | Verified in code; external proof needed |
| Duplicate submission | Same user joins active work or reuses ready/archived work without a second charge; different users own separate jobs and settlements | Confirm wording and perceived fairness in human testing | Accepted |
| Archive and deletion | Archive removes a briefing from the active library and restore returns it; it is not permanent deletion | Define account/data erasure and retention promises before publishing privacy terms | Public-launch decision |
| Credit order | Consume subscription allowance first, then packs, then permitted debt | Confirm this order in pricing/account copy and test the real billing catalog | Accepted |
| Debt | A known source must fit the current positive balance. The 600-second default threshold is a settlement safety buffer for races or small finalization differences, not intentionally spendable credit; reaching it blocks later work until credits pay it down | Measure how often real concurrency or metadata differences create debt and keep the balance/recovery copy clear | Accepted for early release |
| Finalization | A generated briefing stays hidden until its single atomic settlement succeeds; retryable failures say the account update is pending | Human-test delayed settlement and exhausted-retry language | Verified in code; external UX proof needed |
| Streaming and recovery | Validate the complete briefing, then reveal it progressively; replay bounded persisted events after reconnect; reconcile with snapshots; cap active streams using renewable database leases | Test weak-network, forced one-hour reconnect, cap behavior, and mobile recovery with real candidate latency | Verified in code; external UX proof needed |
| Exports | Markdown and the sanitized PDF subprocess use the same ready briefing; PDF overload returns a stable retryable message | Human-test export naming, timestamp links, layout, and the busy/retry experience | Verified in code; external UX proof needed |
| Tone and accessibility | Route, loading, empty, error, keyboard, focus, announcement, contrast, and reduced-motion behavior have focused tests | Complete a human authenticated desktop/mobile screen-reader and visual pass for brand voice, overflow, and comprehension | External proof needed |

## Technical and operational review

| Area | What is already true | Remaining proof or decision | Status |
| --- | --- | --- | --- |
| Database migrations and RLS | Disposable fully migrated database tests cover service commands, roles, storage access, tenant isolation, concurrency, and migration invariants | Re-run the database gate on the exact PR candidate and review its schema diff; never test by resetting a shared database | Verified in code; candidate proof needed |
| Browser/server boundary | Authenticated clients have narrow tenant reads and route all privileged mutations through the backend service role | Verify deployed public keys versus secret keys and inspect Supabase advisors on the selected project | Verified in code; environment proof needed |
| Cache identity | Transcript and summary uniqueness includes the source and processing/model contract; ready cache reuse does not share user jobs or settlement | Decide later on freshness, retention, removed-source behavior, and whether measured duplicate transcription justifies shared `source_work` | Accepted; later product decision |
| Provider quality and privacy | Groq transcription and OpenRouter summary calls are bounded, classified, retried, and tested through fake adapters | Run a capped representative real-provider set; measure latency, cost, timestamp quality, refusal/failure behavior, and verify provider retention/privacy settings | External proof needed |
| Polar sandbox contract | Billing transactions, signature checks, replay safety, ordering, and recovery are covered with fixtures and disposable database tests | On a taxable sandbox order, verify the provider's total-versus-net refund amount contract; also verify country/currency/tax inference because checkout is created server-side without forwarding the user's IP address | External proof needed before paid launch |
| Retry deadlines | Retries occur only for transient/rate-limit failures, with bounded backoff and an overall stage deadline | Tune from measured provider percentiles rather than guesses; specifically review the summary 600-second request and 1,805-second stage ceilings after the real-provider rehearsal | Accepted for proof; metrics decision follows |
| Briefing quality | Structured output, evidence validation, timestamp links, deterministic rendering, injection canaries, and free structural evaluations are automated | Run the capped paid evaluation and human rubric when the prompt/model/contract changes and before a release candidate | Verified in code; candidate proof needed |
| Event load | Postgres notifications wake one coordinator per API process; persisted events are fetched once per active job and fanned out through four bounded dispatchers; overflow reconciles all local jobs and the 45-second sweep runs only while the listener is unhealthy; renewable database leases cap simultaneous streams | Measure concurrent viewers, notification latency, listener reconnects, queue depth/overflow, fallback use, and database load on the chosen staging topology | Verified in code; external capacity proof needed |
| API rate limiting | Database-backed per-IP/scope limits protect sensitive endpoints, including stream opens and readiness; only liveness and signed Polar webhooks are exempt | Configure trusted proxies correctly and load-test effective client-IP handling on the chosen ingress | Verified in code; environment proof needed |
| PDF capacity | A per-process semaphore allows two concurrent renders, with caching, single-flight generation, denied resource fetches, a secret-minimized subprocess, and a short busy response | Measure CPU, memory, render time, and busy rate in the chosen container; run non-root with platform CPU/memory/network/filesystem controls | Accepted default; environment proof needed |
| Logs and incidents | Correlation IDs and structured lifecycle logs cover request, job, lease, listener reconnect, summary, settlement, webhook, shutdown, and recovery; field and free-text redaction protect sensitive values | Select a log destination, access/retention policy, alerts, and an operator before unattended use. At minimum alert on listener reconnect loops, stuck/old queued jobs, exhausted retries, billing/webhook failures, repeated API 5xx, and PDF saturation | Public-launch prerequisite |
| Backups and recovery | Local recovery and reconciliation workflows are documented and tested | Enable database/storage backups and prove a restore in the selected environment | Public-launch prerequisite |
| CORS and site origins | Configuration validates explicit frontend/API/Supabase origins; production must not rely on localhost defaults | Set and verify the exact candidate origins, redirect allowlist, cookies, and payment URLs | Candidate configuration prerequisite |
| Content Security Policy | Security headers are present and dangerous export inputs are isolated; the current Next.js policy retains a documented inline-script allowance | Revisit nonce/hash CSP with hosting and caching design before paid launch | Accepted for early release; paid-launch decision |
| Release workflows | PR validation, staging migration deployment, and deliberate production promotion exist; third-party actions and the Supabase CLI are immutable-version pinned; release authentication falls back to the scoped repository token | Review the exact candidate workflow run, branch-protection compatibility, migration output, artifact provenance, and rollback/restore steps; application hosting remains intentionally unselected | Verified in code; candidate operational proof |

## Gates for the next candidate

### Pull-request gate

- Required CI is green: backend lint, format, type and tests; frontend lint,
  type, tests/accessibility, and production build.
- Migration changes start a clean disposable database, apply every migration,
  run role/concurrency/storage suites, and lint the resulting schema.
- The diff contains no secrets, unrelated generated churn, or accidental
  changes to release/provider/domain decisions.

### External public-beta gate

- Pull-request gate passes on the exact candidate.
- A disposable authenticated fake-provider journey covers create, reconnect,
  read, Markdown/PDF, archive/restore, billing fixtures, and representative
  failures with clean teardown.
- A capped real-provider rehearsal covers representative short and long
  sources and records quality, latency, cost, and provider failure behavior.
- Human desktop/mobile accessibility and user-language review passes.
- Exact origins, redirects, secrets, logs, alerts, backups, restore, privacy,
  and support ownership are configured and verified.
- Hosted Supabase Auth matches the tracked local password policy, exact callback
  URLs are allowed, production SMTP is configured, and a real confirmation and
  password-reset email both complete on the candidate domain.
- Ordinary visitors may sign up; there is no invitation allowlist. Configure
  Supabase email confirmation, production SMTP, bot/CAPTCHA controls, and
  published support/privacy paths for that public behavior.

### Paid public-launch gate

- Early public-beta evidence supports capacity, product value,
  retry/deadline tuning, and pricing assumptions.
- Privacy/terms, retention/erasure, provider data handling, billing/refund, tax,
  support, and incident responsibilities are approved.
- The selected infrastructure has measured capacity, restore and rollback
  proof, and an intentionally promoted release candidate.
- Deferred items whose revisit trigger occurred are resolved; otherwise their
  early-release acceptance is explicitly renewed.

## How to use this register

Review it when a release candidate is cut, a provider/model/prompt changes, a
schema or billing rule changes, or real evidence contradicts an accepted
assumption. Put evidence next to the relevant release or issue; do not mark an
environment or human item complete merely because a fake-provider test passed.

See also the [deferred work register](./deferred-work.md),
[briefing product behavior](../product/briefing-behavior.md),
[system and job lifecycle](../architecture/system-and-job-lifecycle.md), and
[security and data access](../architecture/security-and-data-access.md).
