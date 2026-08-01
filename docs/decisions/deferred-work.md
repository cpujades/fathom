# Deferred work register

**Status:** Accepted deferrals
**Last reviewed:** 2026-08-01

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
| Permanent account/source erasure | Users can archive and restore briefings; archive is reversible and is not physical deletion | User-owned records, reusable source processing, billing evidence, security logs, and legal retention have different owners and lifetimes. A single cascading delete could break another user's briefing or erase required audit evidence. | Before paid public launch, before promising deletion in policy or marketing, or earlier if a pilot user makes an erasure request | Approved data inventory and per-category retention schedule; separate user-owned versus reusable derived data; authenticated request and cooling-off flow; transactional deletion/anonymization; billing/legal exceptions; provider/storage cleanup; audit proof without retained private content |

## Processing, cache, and scale

| Deferred item | Current pilot decision | Why it is deferred | Revisit trigger | Minimum safe future design |
| --- | --- | --- | --- | --- |
| Global source producer before transcription | Separate user jobs may duplicate transcription when two users submit the same uncached source at nearly the same time | Current unique cache rows, summary ownership tokens, tenant isolation, and one settlement per user keep results correct. A shared producer adds cross-tenant lifecycle and fairness rules. | Duplicate provider cost is measurable in pilot data | Tenant-neutral `source_work` identity; producer/follower lifecycle; fenced takeover; failure propagation; retention/privacy/fairness policy |
| Videos longer than two hours | Keep the two-hour and 100 MB pilot limits | Raising a number alone risks provider rejection, excessive memory, long retries, and losing the whole job after a late failure | Target users need longer sources and representative provider tests pass | Streaming download; bounded chunks; per-chunk retry/checkpointing; timestamp offsets; deterministic merge; progress, cost, and quality evaluation |
| Shared event wake-ups and event retention | Persist events and poll once per second per open session; snapshots reconcile state; expiring database leases cap active streams per user/IP | It is simple and bounded for a small pilot. Shared notification infrastructure adds lifecycle and fan-out complexity. | Database event-query load, connection count, or event-table growth becomes material | Load measurement first; bounded shared wake-up mechanism; event retention/compaction; snapshot fallback retained |
| Cache retention and invalidation redesign | Key transcripts and summaries by their processing/model contract; retain ready shared work | Current versioned identities prevent incompatible reuse. Time-based retention and user-facing freshness have not yet been product-defined. | Models/prompts change often, storage growth matters, sources are removed, or users request freshness controls | Explicit freshness/retention policy; versioned invalidation; source-availability handling; operator metrics; deletion/privacy compatibility |

## Decision detail: archive, account deletion, and retention

This decision is deliberately visible because an apparently simple “Delete my
account” button affects product access, shared cache correctness, billing,
security, support, and privacy promises.

### Current pilot behavior

- Archiving changes a user-owned `jobs` row from the active library state to an
  archived state. Restore reverses it.
- Archive does not delete the job, transcript, summary, usage, billing, or log
  records.
- There is no self-service permanent account-erasure button.
- A privacy request is handled manually and must be reviewed by data category;
  the product does not promise an automatic deletion deadline yet.

### What “shared transcript or summary” means

The transcript and briefing text are reusable processing results for a public
YouTube source. They are not placed in one user's private library as the sole
copy.

Example:

1. Ana submits video X. Talven creates Ana's private `jobs` row, one transcript,
   and one summary.
2. Bruno later submits the same video under the same processing contract.
3. Talven creates Bruno's separate private job and usage settlement but may
   point it to the already-ready summary.
4. Ana cannot see Bruno's job, history, billing, or account, and Bruno cannot
   see Ana's. Each user may read the summary only because their own successful
   or archived job grants access.

The transcript and summary are therefore **shared derived records**, while the
submission history, library state, access link, usage charge, and billing data
are **user-owned records**.

### Risk of implementing deletion too early

- Cascading from Ana's job into the shared summary could break Bruno's saved
  briefing even though Bruno did not request deletion.
- Keeping the summary but deleting only Ana's job may satisfy library removal
  but not a broader account-erasure promise unless the policy clearly separates
  public-source derivatives from account-linked data.
- Deleting orders or ledger evidence can make refunds, charge disputes, tax,
  fraud investigation, and balance reconciliation impossible.
- Deleting the Auth user before dependent records are anonymized or removed can
  leave orphaned rows that support cannot explain or safely access.
- Deleting database rows without deleting PDFs, temporary storage objects,
  backups, provider-held data, and logs creates a false “everything is gone”
  promise.
- Immediate irreversible deletion creates account-takeover abuse: an attacker
  could erase evidence and the real user's library before recovery.

### Second-order product decisions

Before implementation, decide:

- whether deletion means close account, delete private library, anonymize usage,
  remove reusable source derivatives, or all of those;
- whether a shared transcript/summary remains while another active job depends
  on it;
- retention periods for Auth/account data, private jobs, shared derivatives,
  PDFs and temporary audio, billing/audit records, security logs, and backups;
- legal and payment exceptions by country and provider;
- whether account closure has a short recovery/cooling-off period;
- how identity is verified before a destructive request;
- what users see while deletion is pending and what can no longer be restored;
  and
- how completion is proven without keeping the data that was meant to be
  erased.

### Minimum safe future behavior

1. Inventory every data category and external processor.
2. Approve a retention and legal-exception schedule.
3. Define shared-record reference counting or dependency checks.
4. Authenticate the request strongly and consider a short cancellation window.
5. Stop new work and revoke sessions.
6. Delete or anonymize user-owned records transactionally.
7. Delete shared derivatives only when policy allows and no retained dependency
   requires them.
8. Clean storage and schedule deletion from backups/provider systems according
   to their real capabilities.
9. Record minimal non-content audit proof and give the user an honest result.

Archive remains the correct pilot action until those decisions are approved.
This is a public-launch decision, not a reason to hide or forget the work.

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
PDF work, sanitized subprocess exports, and user-visible failure/recovery states. Changes
to those boundaries require regression tests and migration proof.

## Changing a decision

When an item is activated:

1. Record the user problem and evidence that triggered it.
2. Define the visible behavior, billing/privacy effects, and migration needs.
3. Replace the row with a focused decision document or implementation plan.
4. Add deterministic tests before enabling it for users.
5. Re-run the applicable local, database, authenticated-flow, and human UX
   gates described in the pre-production register.
