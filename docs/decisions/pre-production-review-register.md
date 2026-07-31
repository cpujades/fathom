# Pre-production review register

**Status:** Active review register
**Last reviewed:** 2026-07-31

This is the short list of product decisions and real-environment proof Talven
still needs before wider use. It separates a code defect from a deliberate
product choice or an operational prerequisite. Passing automated tests is
necessary, but it does not prove provider quality, human usability, policy, or
production recovery.

## Status meanings

- **Accepted:** current behavior is intentional for the invite-only pilot.
- **Verified in code:** deterministic tests or disposable local integration
  proof cover the boundary.
- **Pilot proof needed:** exercise the exact candidate with real configuration
  or human review before inviting users.
- **Public-launch decision:** may be deferred during a supervised pilot, but
  must be resolved before a paid public launch.

## Owner review queue

These are explicit follow-up reviews requested by the product owner. They are
not approvals to change behavior. Each should be handled in a separate task
that first explains the current implementation in plain language, then checks
the evidence and records any resulting decision.

| Review task | Current scope to explain and inspect | Decision or evidence expected | Status |
| --- | --- | --- | --- |
| Local/staging security configuration | Environment validation; FastAPI middleware order; CORS allowlists and rejected wildcards; credentialed requests; trusted proxy/client-IP handling; local-development exceptions; Next.js CSP and other security headers; HSTS and HTTPS behavior; Supabase/Auth/Polar redirect origins | An environment-by-environment origin and proxy matrix; confirmation that local development remains usable; confirmation that staging/production fail closed; a plain-language before/after explanation of every header and middleware change; any hosting-dependent CSP decision recorded separately | Owner review requested before pilot configuration |
| Supabase query and connection load | One-second event polling per open in-progress briefing; periodic snapshot reconciliation; API rate-limit bucket writes; history/detail queries; database connections used by API and workers | Measured query/connection load for realistic pilot concurrency; the safe capacity envelope; thresholds that would justify shared event wake-ups, retention, pooling, or query/index changes | Owner review requested; measure before scaling changes |
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
| Supported source | Public YouTube URLs, with honest YouTube-specific copy | Human-test invalid, private, removed, age/region-restricted, short, silent, and non-podcast sources; keep messages useful rather than technical | Pilot proof needed |
| Authentication intent | Preserve the submitted URL and safe destination through sign-in and payment redirects | Test real Supabase email/OAuth links and real Polar return URLs on the exact candidate origins | Pilot proof needed |
| Duplicate submission | Same user joins active work or reuses ready/archived work without a second charge; different users own separate jobs and settlements | Confirm wording and perceived fairness in human testing | Accepted |
| Archive and deletion | Archive removes a briefing from the active library and restore returns it; it is not permanent deletion | Define account/data erasure and retention promises before publishing privacy terms | Public-launch decision |
| Credit order | Consume subscription allowance first, then packs, then permitted debt | Confirm this order in pricing/account copy and test the real billing catalog | Accepted |
| Debt | Default maximum is 600 seconds; reaching it blocks later uncovered work until credits pay it down | Confirm whether debt should remain at paid public launch and expose balance clearly enough for support | Accepted for pilot |
| Finalization | A generated briefing stays hidden until its single atomic settlement succeeds; retryable failures say the account update is pending | Human-test delayed settlement and exhausted-retry language | Verified in code; pilot UX proof needed |
| Streaming and recovery | Validate the complete briefing, then reveal it progressively; replay persisted events after reconnect and fall back to snapshots | Test weak-network and mobile reconnect behavior with real candidate latency | Verified in code; pilot UX proof needed |
| Exports | Markdown and isolated PDF use the same ready briefing; PDF overload returns a stable retryable message | Human-test export naming, timestamp links, layout, and the busy/retry experience | Verified in code; pilot UX proof needed |
| Tone and accessibility | Route, loading, empty, error, keyboard, focus, announcement, and reduced-motion behavior have focused tests | Complete a human desktop/mobile screen-reader and visual pass for brand voice, contrast, overflow, and comprehension | Pilot proof needed |

## Technical and operational review

| Area | What is already true | Remaining proof or decision | Status |
| --- | --- | --- | --- |
| Database migrations and RLS | Disposable fully migrated database tests cover service commands, roles, storage access, tenant isolation, concurrency, and migration invariants | Re-run the database gate on the exact PR candidate and review its schema diff; never test by resetting a shared database | Verified in code; candidate proof needed |
| Browser/server boundary | Authenticated clients have narrow tenant reads and route all privileged mutations through the backend service role | Verify deployed public keys versus secret keys and inspect Supabase advisors on the selected project | Verified in code; environment proof needed |
| Cache identity | Transcript and summary uniqueness includes the source and processing/model contract; ready cache reuse does not share user jobs or settlement | Decide later on freshness, retention, removed-source behavior, and whether measured duplicate transcription justifies shared `source_work` | Accepted; later product decision |
| Provider quality and privacy | Groq transcription and OpenRouter summary calls are bounded, classified, retried, and tested through fake adapters | Run a capped representative real-provider set; measure latency, cost, timestamp quality, refusal/failure behavior, and verify provider retention/privacy settings | Pilot proof needed |
| Retry deadlines | Retries occur only for transient/rate-limit failures, with bounded backoff and an overall stage deadline | Tune from measured provider percentiles rather than guesses; specifically review the summary 600-second request and 1,805-second stage ceilings after the real-provider rehearsal | Accepted for proof; metrics decision follows |
| Briefing quality | Structured output, evidence validation, timestamp links, deterministic rendering, injection canaries, and free structural evaluations are automated | Run the capped paid evaluation and human rubric when the prompt/model/contract changes and before a release candidate | Verified in code; candidate proof needed |
| Event load | Each open in-progress session performs about one event query per second and periodic snapshot reconciliation | Measure concurrent viewers and database load; introduce shared wake-ups only if the pilot shows pressure | Accepted for bounded pilot |
| API rate limiting | Database-backed per-IP/scope limits protect sensitive endpoints | Configure trusted proxies correctly and load-test effective client-IP handling on the chosen ingress | Environment proof needed |
| PDF capacity | A per-process semaphore allows two concurrent renders, with caching, single-flight generation, strict resource isolation, and a short busy response | Measure CPU, memory, render time, and busy rate in the chosen container size before raising the limit; scale processes/pods deliberately | Accepted default; environment proof needed |
| Logs and incidents | Correlation IDs and structured lifecycle logs cover request, job, lease, summary, settlement, webhook, shutdown, and recovery; diagnostics avoid transcript content | Select a log destination, access/retention policy, alerts, and an operator before unattended use | Pilot operational prerequisite |
| Backups and recovery | Local recovery and reconciliation workflows are documented and tested | Enable database/storage backups and prove a restore in the selected environment | Pilot operational prerequisite |
| CORS and site origins | Configuration validates explicit frontend/API/Supabase origins; production must not rely on localhost defaults | Set and verify the exact candidate origins, redirect allowlist, cookies, and payment URLs | Candidate configuration prerequisite |
| Content Security Policy | Security headers are present and dangerous export inputs are isolated; the current Next.js policy retains a documented inline-script allowance | Revisit nonce/hash CSP with hosting and caching design before public launch | Accepted for pilot; public-launch decision |
| Release workflows | PR validation, staging deployment after merge, and deliberate production promotion exist | Review the exact candidate workflow run, migration output, artifact provenance, and rollback/restore steps; rebuild nothing without evidence of a defect | Candidate operational proof |

## Gates for the next candidate

### Pull-request gate

- Required CI is green: backend lint, format, type and tests; frontend lint,
  type, tests/accessibility, and production build.
- Migration changes start a clean disposable database, apply every migration,
  run role/concurrency/storage suites, and lint the resulting schema.
- The diff contains no secrets, unrelated generated churn, or accidental
  changes to release/provider/domain decisions.

### Invite-only pilot gate

- Pull-request gate passes on the exact candidate.
- A disposable authenticated fake-provider journey covers create, reconnect,
  read, Markdown/PDF, archive/restore, billing fixtures, and representative
  failures with clean teardown.
- A capped real-provider rehearsal covers representative short and long pilot
  sources and records quality, latency, cost, and provider failure behavior.
- Human desktop/mobile accessibility and user-language review passes.
- Exact origins, redirects, secrets, logs, alerts, backups, restore, privacy,
  and support ownership are configured and verified.

### Paid public-launch gate

- Pilot evidence supports capacity, product value, retry/deadline tuning, and
  pricing assumptions.
- Privacy/terms, retention/erasure, provider data handling, billing/refund, tax,
  support, and incident responsibilities are approved.
- The selected infrastructure has measured capacity, restore and rollback
  proof, and an intentionally promoted release candidate.
- Deferred items whose revisit trigger occurred are resolved; otherwise their
  pilot acceptance is explicitly renewed.

## How to use this register

Review it when a release candidate is cut, a provider/model/prompt changes, a
schema or billing rule changes, or pilot evidence contradicts an accepted
assumption. Put evidence next to the relevant release or issue; do not mark an
environment or human item complete merely because a fake-provider test passed.

See also the [deferred work register](./deferred-work.md),
[briefing product behavior](../product/briefing-behavior.md),
[system and job lifecycle](../architecture/system-and-job-lifecycle.md), and
[security and data access](../architecture/security-and-data-access.md).
