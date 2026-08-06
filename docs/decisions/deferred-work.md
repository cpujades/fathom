# Deferred work register

**Status:** Accepted deferrals
**Last reviewed:** 2026-08-04

This register records work Talven has deliberately chosen not to include in
the current pre-launch candidate. A deferred item is not forgotten or assumed
to be unimportant. It means the current behavior is understood and implementing
the larger design now would create more risk than value.

If a trigger below occurs, move that item into the implementation backlog and
write or update a focused decision before changing product behavior.

## Two kinds of deferral

These categories must not be mixed:

- **Optional feature deferral:** the product can remain complete without it.
  It may stay deferred indefinitely unless user evidence triggers it. Q&A/chat
  is the clearest example.
- **Boundary-bound deferral:** it is reasonable not to decide while everything
  runs only on `localhost`, but a named launch boundary ends the deferral.
  Hosting, HTTPS origins, observability, retention, backups, and support cannot
  remain undefined once external users can sign up.

“Deferred until hosting is selected” therefore does not mean “deferred
forever.” It means the decision belongs in the deployment task and must be
completed before the boundary in the table below.

## Product and billing

| Deferred item | Current decision | Why it is deferred | Revisit trigger | Minimum safe future design |
| --- | --- | --- | --- | --- |
| Cancel a running briefing | Do not offer cancellation after work starts | Cancellation needs precise charging, provider-call, worker, and recovery semantics. Redis is not required, but a durable cancel state is. | Users regularly abandon long jobs, provider cost becomes material, or product policy requires cancellation | Durable cancel request; checkpoints before expensive stages; fenced terminal transition; documented charge/refund policy; clear UI states |
| Upfront usage reservations | Check estimated affordability at admission; charge atomically after a valid briefing | Reservations change when credits disappear and require expiry, cancellation, crash recovery, and refund rules | Concurrent usage produces unacceptable debt or paid launch requires a strict no-debt guarantee | Atomic reserve/commit/release ledger; expiry and reconciliation; visible pending balance; concurrency tests |
| Event-driven billing recovery scheduler | Run the bounded, single-flight billing safety pass every five minutes; webhooks and normal job finalization remain the immediate paths | Recovery work should be rare, so five-minute polling is a simpler and cheaper launch safety net than maintaining another scheduler. Removing recovery entirely would leave missed webhooks, uncertain refunds, stale processing, or unsettled jobs dependent on manual repair. | Empty maintenance passes create measurable database load, five-minute repair latency becomes unacceptable, or billing recovery volume justifies dedicated scheduling | Give every recoverable item a durable `next_due_at`; query the earliest due time after startup and each completed pass; sleep until that time instead of checking every interval; publish a Postgres notification when new work is inserted or moved earlier so the scheduler recalculates immediately; follow the listener and priority contract below; retain the distributed lease, idempotent handlers, a slow safety sweep for missed notifications, restart/clock-change recovery, metrics, and failure tests. An external hosting cron or Supabase `pg_cron` task may trigger the same bounded maintenance entry point instead, but must use a secured server-side execution path with billing secrets and must preserve single-flight ownership. |
| Content-suitability guardrail | Accept supported public YouTube sources within current limits | Simple rules can wrongly reject useful lectures, interviews, and technical videos | Early usage shows abuse or a material share of low-value inputs | Labeled evaluation set; transcript-based suitability signal; explainable rejection; appeal/retry path; explicit charging policy |
| Podcast question and answer chat | Keep the product focused on source-linked briefings; do not introduce Redis or WebSockets in anticipation of chat | Chat adds retrieval, citation, privacy, latency, cost, and evaluation surfaces before the core workflow is proven | Optional and indefinite: activate only if repeated user evidence supports it | Preserve durable conversation/message state in Postgres. For an early chat, prefer private Supabase Realtime Broadcast channels and its managed WebSocket transport, with authorization/RLS, reconnect, retention, cost, and quota tests. Consider Postgres plus managed Redis and Talven-owned WebSocket servers only if chat becomes central and measured scale, protocol control, or Realtime cost/limits justify operating authentication, fan-out, backpressure, presence, reconnects, and observability ourselves. Keep timestamp-aware hybrid retrieval, reranking, grounded citations, abstention, an evaluation set, and bounded cost/retention in either design. |
| Automated self-service account/source erasure | Keep archive reversible; handle a verified privacy request manually under the approved policy required before external launch | User-owned records, reusable source processing, billing evidence, security logs, and legal retention have different owners and lifetimes. A single cascading delete could break another user's briefing or erase required audit evidence. | Request volume makes manual handling unsafe or too slow, or policy requires automation | Separate user-owned versus reusable derived data; authenticated request and cooling-off flow; transactional deletion/anonymization; billing/legal exceptions; provider/storage cleanup; audit proof without retained private content |

### Billing scheduler listener and priority contract

A Postgres notification channel is a named signal topic, not a table, queue, or
separate database connection. The future worker should normally reuse one
supervised physical Postgres connection and register both logical channels:

```sql
LISTEN job_available;
LISTEN billing_recovery_available;
```

The listener must route the channel names into separate in-process signals,
such as `job_wake_event` and `billing_wake_event`. The current single-channel
helper must therefore be extended rather than sending both channels into one
undifferentiated one-slot signal.

- `job_available` is the immediate path: wake job claiming without waiting for
  billing work.
- `billing_recovery_available` only cancels or recalculates the scheduler's
  current due-time wait; it must not execute billing work inside the listener
  callback.
- Repeated billing notifications may be coalesced into one recalculation
  because durable rows and their `next_due_at` values remain authoritative.
- Listener callbacks must remain constant-time and non-blocking. If measured
  notification volume causes interference despite those boundaries, isolate
  billing on a second supervised connection rather than weakening job
  priority.
- After startup or listener reconnection, recalculate durable job and billing
  state because notifications are wake-up hints and are not replayed.

## Processing, cache, and scale

| Deferred item | Current decision | Why it is deferred | Revisit trigger | Minimum safe future design |
| --- | --- | --- | --- | --- |
| Global source producer before transcription | Separate user jobs may duplicate transcription when two users submit the same uncached source at nearly the same time | Current unique cache rows, summary ownership tokens, tenant isolation, and one settlement per user keep results correct. A shared producer adds cross-tenant lifecycle and fairness rules. | Duplicate provider cost is measurable in real usage | Tenant-neutral `source_work` identity; producer/follower lifecycle; fenced takeover; failure propagation; retention/privacy/fairness policy |
| Videos longer than two hours | Keep the two-hour and 100 MB initial limits | Raising a number alone risks provider rejection, excessive memory, long retries, and losing the whole job after a late failure | Target users need longer sources and representative provider tests pass | Streaming download; bounded chunks; per-chunk retry/checkpointing; timestamp offsets; deterministic merge; progress, cost, and quality evaluation |
| YouTube extraction backend (`pytubefix` versus `yt-dlp`) | Keep `pytubefix` inside the current bounded, killable subprocess | `yt-dlp` was previously tried and did not work reliably for this application; `pytubefix` restored the workflow with less integration effort. Changing extractors without representative evidence would add packaging, output-contract, timeout, metadata, and deployment risk without proving better reliability. | YouTube extraction failures become material, `pytubefix` maintenance stalls, or a representative staging comparison proves `yt-dlp` materially more reliable | Keep the downloader interface and subprocess boundary; compare both implementations against representative public sources; preserve size/time limits, metadata, cleanup, safe subprocess environment, failure copy, packaging and hosting proof; migrate behind the interface with rollback rather than replacing it directly |
| Supabase Realtime as the SSE wake-up transport | Keep the implemented direct Postgres `LISTEN/NOTIFY` coordinator behind the existing backend SSE endpoint; do not add Realtime now | Supabase Realtime is a managed WebSocket service using Postgres Changes or Broadcast, not PostgreSQL `LISTEN/NOTIFY`. It may avoid a long-lived direct database listener, but adds channel authorization, RLS, reconnect behavior, quotas, and another transport that could duplicate the existing SSE contract. | The selected API host cannot reliably maintain a direct Postgres listener, listener connection budget becomes material, or a staging comparison proves a clear operational advantage | Compare direct `LISTEN/NOTIFY`, Realtime Postgres Changes, and Realtime Broadcast using representative concurrency. Keep `job_events` as the durable authority and preserve tenant isolation and replay. Choose one backend wake-up approach and one server-to-browser contract rather than two competing sources of truth; measure latency, reconnect recovery, connection/message quotas and cost, and retain a tested fallback and rollback path. |
| External queue or broker for worker wake-ups | Keep the Postgres `jobs` table as the durable queue authority and use `LISTEN/NOTIFY` only as a wake-up hint; do not add Redis or RabbitMQ without a measured trigger | The current design is durable, supports several workers, and has no measured queue bottleneck. A broker would add a second system and a database-to-broker delivery boundary requiring a transactional outbox and additional operations. RabbitMQ's advanced queue and routing semantics have no current Talven requirement. | Activate the Redis evaluation below only when notification lag/database overhead, shared-cache demand, rate-limit write contention, worker claim latency, or priority/routing requirements cross an agreed measured target. Reconsider RabbitMQ only if Redis and the selected host's managed queues cannot safely meet a newly demonstrated acknowledgement, routing, priority, or dead-letter requirement. | Prefer a managed Redis evaluation first: Pub/Sub only for disposable wake hints and Streams for durable consumption. Preserve Postgres as the durable product authority and use a transactional outbox for broker publication; keep consumers idempotent; tolerate missing and duplicate delivery; add reconciliation, retention, dead-letter handling where applicable, metrics, staged migration, and rollback proof. Do not deploy Redis and RabbitMQ together for the same role. |
| Cache retention and invalidation redesign | Key transcripts and summaries by their processing/model contract; retain ready shared work | Current versioned identities prevent incompatible reuse. Time-based retention and user-facing freshness have not yet been product-defined. | Models/prompts change often, storage growth matters, sources are removed, or users request freshness controls | Explicit freshness/retention policy; versioned invalidation; source-availability handling; operator metrics; deletion/privacy compatibility |

### Concrete triggers for evaluating managed Redis

Redis is not a planned requirement merely because Talven gains more registered
users. Evaluate it only when measurements show one of these specific problems:

- **Postgres notification throughput:** notification or callback lag grows
  materially under representative event volume, or database resources used for
  wake-up fan-out become material. Example: thousands of progress events per
  second across many jobs consistently arrive late. Redis Pub/Sub could move
  disposable backend wake-up fan-out away from Postgres; durable rows and replay
  would remain in Postgres.
- **Distributed caching:** several API replicas repeatedly fetch or calculate
  the same safe, reusable value. Example: every replica repeatedly loads the
  same public plan catalog or expensive derived lookup. Redis could hold one
  short-lived shared copy instead of each process maintaining a different
  in-memory copy. Do not cache private authorization or billing truth without
  explicit invalidation and failure semantics.
- **Rate-limit database cost:** high request volume makes updates to
  `api_rate_limit_buckets` a measurable source of database writes, row
  contention, latency, or connection-pool waits. Redis atomic counters with
  expiry could move this narrow, disposable state out of Postgres while
  preserving fail-closed hosted behavior.
- **Worker queue latency or routing:** Postgres claim queries or locks become
  measurably slow, queued-job wait exceeds the product target, or workers need
  explicit lanes such as paid/free priority, transcription/summary routing, or
  region-specific consumers. Redis Streams or a host-native managed queue could
  then be compared against the current Postgres queue.

An early chat feature alone does not trigger Redis. Start with Postgres for
durable chat state and Supabase Realtime Broadcast for managed browser
WebSockets. Redis plus Talven-owned WebSocket servers is the later control-
oriented option, not the default first chat architecture.

## Decision detail: archive, account deletion, and retention

This decision is deliberately visible because an apparently simple “Delete my
account” button affects product access, shared cache correctness, billing,
security, support, and privacy promises.

### Current pre-launch behavior

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

Archive remains the correct product action until those decisions are approved.
The retention schedule and manual request process are public-launch decisions;
automating them may remain deferred.

## Platform and operations

| Deferred item | Current decision | Why it is deferred | Revisit trigger | Minimum safe future design |
| --- | --- | --- | --- | --- |
| Strict nonce-based Content Security Policy | Keep the current restrictive CSP, including the narrowly documented inline-script allowance required by the current Next.js build | Nonces affect static rendering and caching and should be designed with the selected hosting path | Before paid public launch, or if the rendering/hosting model changes | Verify framework support; remove avoidable inline code; nonce or hash policy; browser regression suite; preserve caching intentionally |
| Dedicated alerting/observability platform | Keep the existing structured, privacy-safe lifecycle logs and read-only operability diagnostics while the product is local. These are useful evidence, but they are **not** a production metrics pipeline, dashboard, or automatic alerting system. | Collection and alert integrations depend on the selected frontend/API/worker hosts, Supabase compute and plan, traffic, retention, and privacy requirements. The measurements required are host-independent and are defined below. | **Must resolve before unattended external signup is enabled; establish the baseline on the exact staging topology before choosing capacity thresholds or replacing Postgres notifications.** | Central logs and time-series metrics; dashboards and alerts for Postgres/pools, worker queue/listeners, frontend/SSE/API, providers, billing, and host resources; tested redaction; retention/access policy; named operator and incident runbooks |
| Direct Postgres connection-pool sizing | Keep the current API rate-limit pool at `min_size=1`, `max_size=10` per API process as an unproven local/pilot default; dedicated listener connections are separate and neither number is a user cap | The safe value depends on the selected Supabase compute size, reserved Supabase service connections, API process/replica count, autoscaling ceiling, query latency, and measured concurrent requests | **Must resolve when the hosting topology and Supabase production size are selected, before enabling broad autoscaling or public paid traffic** | Inventory every direct pool and dedicated listener per process; calculate the worst-case connection budget across maximum replicas while reserving documented headroom for Supabase services and operations; configure an explicit replica ceiling; load-test rate-limit pool wait time, request latency, SSE concurrency, listener health, and database saturation; then reduce or raise `10` from evidence and monitor live connection usage and leaks. |
| Public hosting, domain, and provider selection | Reassess the application first, then choose infrastructure | These are intentionally later business and operating decisions, not application defects | **Must resolve before any external user can reach the app** | Exact-candidate staging proof; separate web/API/continuous-worker processes; secrets and origin configuration; backups/restore; capacity and cost envelope; deliberate production promotion |
| Retention schedule and manual privacy-request process | Do not invent deletion promises while testing only locally | Jobs, shared derivatives, PDFs, billing evidence, logs, backups, and provider-held data need different honest lifetimes | **Must resolve before public signup is enabled** | Written per-category periods and legal exceptions; provider/storage deletion behavior; verified request intake and identity check; owner and response target; privacy/terms alignment |
| Backups, restore, and rollback | Keep local recovery tests; no hosted system exists yet | The exact controls depend on the selected database, storage, and application host | **Must resolve before external users create data** | Enabled backups; one proved restore; storage recovery decision; application rollback steps; recorded recovery owner and expected recovery times |
| Ingress, abuse, and webhook edge controls | Keep application signature verification, request caps, rate limits, and strict origins; choose edge controls with the host | The public IP/proxy and available WAF/bot controls do not exist until hosting is selected | **Must resolve before the public URL is announced** | Trusted-proxy configuration; TLS; body and connection caps; Supabase signup abuse controls; Polar webhook route reachable without bypassing signature verification; load test using the real client IP |
| PDF/storage provider choice, including Cloudflare R2 | Keep private Supabase Storage for temporary audio and signed PDF downloads | R2 may reduce download egress cost, but moving now adds another credential, adapter, signed-URL policy, cleanup path, CORS policy, and recovery surface before real cost is known | Storage/download cost or Supabase limits become material | Private bucket; short-lived signed URLs; server-mediated authorization; least-privilege credentials; CORS; object cleanup/retention; migration and rollback proof; measured total cost |

### Minimum production observability and capacity evidence

Current application evidence includes correlated structured logs for requests,
jobs, provider attempts, listener reconnects, billing, webhooks, and recovery. The
read-only operability report also detects overdue jobs, expired leases, orphaned
summaries, incomplete settlement, balance mismatches, and unresolved webhooks.
This supports diagnosis after an operator looks, but it does not continuously
measure resource pressure or notify an operator automatically.

Before unattended use, connect the selected hosts and Supabase project to one
central observability destination and cover at least:

Prefer a **single operator view** over checking the Supabase, frontend, API, and
worker dashboards separately. During hosting selection, verify each provider's
actual metrics API or exporter, log-drain support, retention, granularity,
quotas, cost, authentication, and alert/webhook integration; do not assume that
every host exposes every useful signal through a complete API.

The first implementation should normally send provider metrics and logs, plus
Talven application telemetry, into an existing observability workspace such as
a managed Grafana service using native integrations, Prometheus/OpenTelemetry
exporters, or log drains. That gives one dashboard and
one alert-routing layer while provider dashboards remain available for detailed
diagnosis. Do not initially build and operate a Talven-specific monitoring UI
or alert engine: it would add another database, authentication, data retention,
visualization, availability, and notification-delivery system. A custom ad hoc
dashboard may later read the same APIs if established tools cannot express a
specific operator workflow or if their measured cost becomes unreasonable.

Initial platform shortlist:

1. **Default candidate — Grafana Cloud Free:** prefer this for the first hosted
   version if its then-current limits, retention, privacy terms, integrations,
   and alerting cover the measured staging workload. It provides the Grafana
   interface and managed metrics/log storage, upgrades, availability, and alert
   execution, which avoids creating another Talven-operated service.
2. **Fallback — self-hosted Grafana OSS:** choose this only when control,
   residency/privacy requirements, telemetry volume, Cloud limits/pricing, or
   an unsupported integration justifies the operating cost. The software is
   free, but Talven would own its hosting, security updates, backups, uptime,
   alert delivery, and the accompanying metrics/log data sources such as
   Prometheus and Loki.
3. **Optional future complement — Sentry:** consider Sentry alongside Grafana
   only if Grafana's frontend/backend exception workflow is insufficient for
   release-linked issue grouping, developer-focused stack traces, affected-user
   analysis, or session replay. Grafana remains the infrastructure, database,
   application-metrics, logs, dashboards, and alerting authority; Sentry would
   be a focused code-debugging tool, not a second general observability system.
   Define signal ownership to avoid paying to ingest the same logs and traces
   twice, and verify source-map access, sampling, quotas, retention, PII
   scrubbing, and replay masking before enabling it.

**New Relic is not in the planned Talven stack.** It substantially overlaps
with Grafana Cloud, and the owner has chosen not to operate and pay for two
general full-stack observability platforms. Reconsidering it requires a new
explicit decision supported by a concrete Grafana limitation; it must not be
added merely as another monitoring integration.

Either option should combine Supabase metrics, the selected frontend/API/worker
host metrics, and Talven-owned telemetry for queue age, SSE activity, briefing
latency, and Groq/OpenRouter/Polar outcomes. Those application signals are not
discovered automatically: Talven must emit them as structured logs or explicit
metrics, and the chosen collectors or integrations must deliver them to the
Grafana data sources. Re-check current product limits and total operating cost
at selection time rather than treating today's free tier as permanent.

- **Postgres and pools:** live connections versus the plan maximum, connection
  type, pool busy/idle counts, pool wait duration and timeouts, slow-query
  latency, locks/deadlocks, CPU, memory, storage, and I/O pressure. Include the
  database-backed rate-limit operation volume, latency, contention, and pool
  waits.
- **Worker and notifications:** runnable queue depth, oldest-job age, claim
  latency, stage duration, active concurrency, listener connected state,
  reconnect loops/downtime, notification volume, and notification-to-wake
  latency. Track fallback reconciliation so missed notifications are visible.
- **SSE and API:** active streams per replica, opens/reconnects, stream lifetime,
  event-to-browser latency, fallback snapshots, request rate and latency, `5xx`
  and `429` rates, CPU, memory, and process restarts.
- **Frontend:** uncaught browser errors, failed API/auth/payment requests, page
  performance, and completion or failure rates for the core briefing and billing
  journeys, without collecting private source or briefing content.
- **Providers and billing:** Groq/OpenRouter latency, attempts, errors, and rate
  limits; Polar webhook failures/age, refunds, settlement, and reconciliation
  failures.

Do not invent fixed production thresholds from local defaults. Load-test the
exact staging topology, record its normal and peak values, then set warning and
critical thresholds with enough headroom to act before exhaustion. Alerts must
at least cover connection or pool exhaustion risk, non-zero pool timeouts,
sustained database saturation or lock waits, growing/old queues, disconnected
or repeatedly reconnecting listeners, excessive notification or browser-update
latency, repeated API/provider failures, and billing recovery failures.
Also alert on sustained client-error or core-workflow-failure spikes.

The decision to introduce Redis, another broker, or Supabase Realtime must be
evidence-driven rather than based only on user count. Reconsider the current
Postgres design when its latency or capacity targets remain breached after
reasonable query/index, connection-pool, replica, and notification-coalescing
tuning. Record the measured before/after result, cost, migration plan, and
rollback path when activating that decision.

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
