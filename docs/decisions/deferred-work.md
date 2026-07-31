# Deferred work register

**Status:** Accepted deferrals
**Last reviewed:** 2026-07-31

This register records work Talven has deliberately chosen not to include in
the first invite-only pilot. A deferred item is not forgotten or assumed to be
unimportant. It means the current behavior is understood, the pilot has a
bounded safe path, and implementing the larger design now would create more
risk than value.

If a trigger below occurs, move that item into the implementation backlog and
write or update a focused decision before changing product behavior.

## Product and billing

| Deferred item | Current pilot decision | Why it is deferred | Revisit trigger | Minimum safe future design |
| --- | --- | --- | --- | --- |
| Cancel a running briefing | Do not offer cancellation after work starts | Cancellation needs precise charging, provider-call, worker, and recovery semantics. Redis is not required, but a durable cancel state is. | Users regularly abandon long jobs, provider cost becomes material, or product policy requires cancellation | Durable cancel request; checkpoints before expensive stages; fenced terminal transition; documented charge/refund policy; clear UI states |
| Upfront usage reservations | Check estimated affordability at admission; charge atomically after a valid briefing | Reservations change when credits disappear and require expiry, cancellation, crash recovery, and refund rules | Concurrent usage produces unacceptable debt or paid launch requires a strict no-debt guarantee | Atomic reserve/commit/release ledger; expiry and reconciliation; visible pending balance; concurrency tests |
| Content-suitability guardrail | Accept supported public YouTube sources within current limits | Simple rules can wrongly reject useful lectures, interviews, and technical videos | Pilot evidence shows abuse or a material share of low-value inputs | Labeled evaluation set; transcript-based suitability signal; explainable rejection; appeal/retry path; explicit charging policy |
| Podcast question and answer chat | Keep the product focused on evidence-backed briefings | Chat adds retrieval, citation, privacy, latency, cost, and evaluation surfaces before the core workflow is proven | Briefing retention and interviews show repeated demand for follow-up questions | Timestamp-aware hybrid retrieval; reranking; grounded citations; abstention; evaluation set; bounded cost and retention |
| Permanent account/source erasure | Users can archive and restore briefings; archive is not physical deletion | Shared cache, billing records, fraud evidence, and legal retention need an explicit policy before destructive behavior is offered | Before public launch, or earlier if pilot policy promises account deletion | Data inventory and retention schedule; separate user-owned versus shared-derived data; irreversible deletion workflow; billing/legal exceptions; audit proof |

## Processing, cache, and scale

| Deferred item | Current pilot decision | Why it is deferred | Revisit trigger | Minimum safe future design |
| --- | --- | --- | --- | --- |
| Global source producer before transcription | Separate user jobs may duplicate transcription when two users submit the same uncached source at nearly the same time | Current unique cache rows, summary ownership tokens, tenant isolation, and one settlement per user keep results correct. A shared producer adds cross-tenant lifecycle and fairness rules. | Duplicate provider cost is measurable in pilot data | Tenant-neutral `source_work` identity; producer/follower lifecycle; fenced takeover; failure propagation; retention/privacy/fairness policy |
| Videos longer than two hours | Keep the two-hour and 100 MB pilot limits | Raising a number alone risks provider rejection, excessive memory, long retries, and losing the whole job after a late failure | Target users need longer sources and representative provider tests pass | Streaming download; bounded chunks; per-chunk retry/checkpointing; timestamp offsets; deterministic merge; progress, cost, and quality evaluation |
| Shared event wake-ups and event retention | Persist events and poll once per second per open session; snapshots reconcile state | It is simple and bounded for a small pilot. Shared notification infrastructure adds lifecycle and fan-out complexity. | Database event-query load, connection count, or event-table growth becomes material | Load measurement first; bounded shared wake-up mechanism; event retention/compaction; snapshot fallback retained |
| Cache retention and invalidation redesign | Key transcripts and summaries by their processing/model contract; retain ready shared work | Current versioned identities prevent incompatible reuse. Time-based retention and user-facing freshness have not yet been product-defined. | Models/prompts change often, storage growth matters, sources are removed, or users request freshness controls | Explicit freshness/retention policy; versioned invalidation; source-availability handling; operator metrics; deletion/privacy compatibility |

## Platform and operations

| Deferred item | Current pilot decision | Why it is deferred | Revisit trigger | Minimum safe future design |
| --- | --- | --- | --- | --- |
| Strict nonce-based Content Security Policy | Keep the current restrictive CSP, including the narrowly documented inline-script allowance required by the current Next.js build | Nonces affect static rendering and caching and should be designed with the selected hosting path | Before paid public launch, or if the rendering/hosting model changes | Verify framework support; remove avoidable inline code; nonce or hash policy; browser regression suite; preserve caching intentionally |
| Dedicated alerting/observability platform | Keep structured, privacy-safe application logs and reconciliation diagnostics | Platform choice depends on hosting, traffic, retention, and privacy requirements | Before unattended pilot operation or when an on-call owner is assigned | Central log destination; alerts for stuck/retried work and billing/webhook failures; redaction tests; retention/access policy |
| Public hosting, domain, and provider selection | Reassess the application first, then choose infrastructure | These are intentionally later business and operating decisions, not application defects | Application gates pass and an invite-only candidate is chosen | Exact-candidate staging proof; secrets and origin configuration; backups/restore; capacity and cost envelope; deliberate production promotion |

## Not deferred

The following are current correctness boundaries, not future ideas: tenant RLS,
server-only mutation commands, fenced job and summary ownership, idempotent
settlement and webhook handling, persisted event replay, bounded provider and
PDF work, isolated exports, and user-visible failure/recovery states. Changes
to those boundaries require regression tests and migration proof.

## Changing a decision

When an item is activated:

1. Record the user problem and evidence that triggered it.
2. Define the visible behavior, billing/privacy effects, and migration needs.
3. Replace the row with a focused decision document or implementation plan.
4. Add deterministic tests before enabling it for users.
5. Re-run the applicable local, database, authenticated-flow, and human UX
   gates described in the pre-production register.
