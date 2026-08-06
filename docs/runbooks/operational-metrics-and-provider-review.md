# Operational metrics and provider review

**Status:** Required before unattended external signup; dashboard and alerts are
not implemented yet
**Last reviewed:** 2026-08-06

This runbook defines what Talven's owner should see, where each number is
authoritative, how often to review it, and when a number should trigger
investigation or a provider decision.

The operating model is deliberately simple:

- **Grafana is the daily cockpit.** It joins application, host, database, and
  provider trends; calculates ratios and forecasts; and sends alerts.
- **Provider dashboards and invoices are the billing and quota authority.** A
  Grafana estimate is useful for acting early, but it does not replace Railway,
  Supabase, Groq, OpenRouter, Polar, or Resend's own usage record.
- **Talven events are the business and workflow authority.** They explain which
  user action, job stage, cache decision, or billing transition caused the
  infrastructure usage.
- **Sentry is optional diagnosis.** Add it only if Grafana's exception workflow
  is insufficient; do not duplicate the whole metrics and logs pipeline.

The purpose is not to watch every chart every day. Alerts catch urgent failures,
the daily review catches drift, the weekly review explains trends, and the
monthly review supports spending and provider decisions.

## Source-of-truth map

| Question | First place to look | Authority and boundary |
| --- | --- | --- |
| Is Talven healthy right now? | Grafana owner overview | Joined operational view; underlying host/provider page confirms a suspected limit. |
| Why did a briefing fail or become slow? | Grafana workflow and logs | Talven stage events are authoritative; provider request history confirms the external attempt. |
| What will this month probably cost? | Grafana forecast | Early estimate only; compare it with each provider's projected usage. |
| What did Railway actually meter? | Railway usage and invoice | Authority for service RAM, CPU, outbound network, volume usage, and the Railway charge. |
| How close is Supabase to a quota? | Supabase Usage, Database, Reports, and Logs | Authority for database disk, Storage, egress, Auth usage, compute pressure, and Supabase billing. |
| How much transcription or LLM usage was billed? | Groq and OpenRouter usage | Provider billing authority; reconcile with Talven's audio seconds and tokens. |
| How much tax, fees, refunds, and payout cash exist? | Polar dashboard and exports | Payment authority; reconcile with Talven billing orders, settlements, refunds, and ledger. |
| Are Auth/application emails arriving safely? | Resend dashboard | Authority for sends, deliveries, bounces, complaints, and quota. |
| Which release introduced an exception? | Grafana logs/traces, optionally Sentry | Sentry may improve release-linked stack-trace diagnosis, but is not the cost or capacity authority. |

Provider numbers may arrive late or use a different billing boundary. Store the
provider timestamp or billing-cycle range beside every reconciliation rather
than forcing two temporarily different numbers to look identical.

## Grafana dashboards

### 1. Owner overview

This is the default daily page. It should fit on one screen and link to the
detailed dashboards below.

Show the current value, seven-day trend, billing-cycle total, and forecast for:

- accepted, completed, and failed briefings;
- unique active users, paying users, and paid conversion;
- cold sources, compatible cache hits, and cache-hit rate;
- processed audio hours and downloaded audio bytes;
- median and p95 end-to-end completion time;
- oldest runnable job and current runnable queue depth;
- Groq and OpenRouter estimated spend;
- estimated contribution after payment and processing cost;
- Railway and Supabase projected month-end usage, when those exports exist;
- unresolved billing recovery work and temporary-audio orphans; and
- active warnings, critical alerts, and last successful data ingestion time.

The page must identify stale data. A green chart whose collector stopped six
hours ago is not evidence that the service is healthy.

### 2. Briefing workflow and worker

Display the funnel:

```text
accepted
-> cache hit or cold source
-> download
-> temporary upload
-> transcription
-> summarization
-> settlement
-> completed
```

For the funnel and every stage, track:

- entered, succeeded, failed, cancelled, and retried counts;
- failure rate by stable error code and dependency;
- p50, p95, and p99 duration;
- queue depth, oldest runnable-job age, and claim latency;
- active jobs versus configured worker concurrency;
- worker liveness, restarts, lease expiry, stale requeues, and exhausted retries;
- Postgres notification listener state, reconnects, disconnected time, and
  notification-to-worker-wake latency;
- fallback reconciliation runs and jobs recovered without a notification; and
- completed work awaiting settlement or another terminal transition.

User count is not a queue-capacity signal. Queue age, claim latency, stage
latency, retry rate, and resource saturation are the signals that justify more
worker concurrency or a queue redesign.

### 3. API, SSE, and frontend journey

Track:

- request rate and p50/p95/p99 latency by route group, not raw URL;
- `2xx`, `4xx`, `429`, and `5xx` rates;
- active SSE streams, stream opens, reconnects, lifetime, replay count, and
  event-to-browser latency;
- briefing-session fallback snapshots and failures to resume after disconnect;
- sign-up, sign-in, create-briefing, completion, library, checkout, portal, and
  refund journey success/failure rates;
- frontend page performance and uncaught browser failures if browser telemetry
  is enabled; and
- release revision for every web, API, and worker process.

Do not use route labels containing briefing, session, job, or user IDs. Those
create unbounded metric cardinality and can disclose private identifiers.

### 4. Providers and unit cost

For Groq and OpenRouter, show:

- requests, successes, errors, rate limits, retries, and timeouts;
- provider/model name and deployed application version;
- billed audio seconds or input/output tokens;
- p50/p95 latency and transcription real-time factor;
- cost per completed briefing, cold audio hour, plan, and billing cycle;
- differences between Talven estimates and provider-reported usage; and
- cache savings: provider requests, audio hours, and cost avoided.

For every source, record source duration, downloaded bytes, normalized bitrate,
source type, and cold/cache-hit status. This makes file-size rejection,
temporary-storage use, egress, and transcription cost explainable from the same
job.

Use controlled owner reports for per-user cost investigation. Never put user
IDs, email addresses, source URLs, provider request IDs, or job IDs in metric
labels. Correlation IDs may appear in access-controlled logs with approved
retention.

### 5. Database and object lifecycle

Show:

- live database bytes versus provisioned database disk;
- seven- and 30-day database growth and estimated date to the next disk step;
- the largest table/index pairs and their weekly growth;
- row and byte growth for transcript segments and job events;
- full transcript and summary text bytes;
- dead tuples, vacuum activity, slow queries, locks/deadlocks, I/O pressure, and
  database CPU/memory when the integration exposes them;
- direct and pooled connections, busy/idle pools, pool wait time, and pool
  timeouts;
- Storage bytes, object count, cached/uncached egress, and egress forecast;
- temporary audio created, deleted, cleanup-retried, and orphaned; and
- PDF object count, new bytes, retained bytes, and downloads.

Track both table and index bytes. Counting rows alone cannot answer whether the
8 GB included database disk is sufficient. A small number of wide transcripts
or duplicate indexes can occupy more space than many narrow rows.

The proposed 90-day TTL applies only to ordinary `job_events` for terminal jobs
after support and SSE replay requirements are verified. It must never prune
active/recoverable job events or accounting, settlement, refund, and webhook
evidence.

### 6. Billing and growth

Show:

- Polar tax-exclusive base sales, customer tax, transaction/recurring fees,
  refunds, disputes, and payouts as distinct values;
- checkout starts, purchases, subscription starts/cancellations, and failed
  checkouts;
- webhook received/processed/failed/oldest-unresolved counts;
- completed work awaiting settlement, balance mismatches, reconciliation
  failures, and billing debt;
- free versus paid active users and conversion by plan;
- consumed included seconds, purchased seconds, promotional credits, and
  unused/expired/refunded credits; and
- contribution per briefing, paying user, plan, and month.

Grafana's contribution figure is an operating estimate. Polar and provider
exports close the month; the owner cash and Spanish tax treatment remain in the
[unit economics model](../product/unit-economics.md).

## Native provider checks

Grafana should reduce dashboard hopping, but the native pages remain essential.

### Railway

Check each of the web, API, and continuous-worker services separately:

- average and peak RAM, CPU, and configured resource limit;
- OOM terminations, restarts, crash loops, health-check failures, and deploy
  duration/failure;
- outbound network and its current/projected billing-cycle cost;
- ephemeral-disk pressure for active audio/PDF work;
- persistent volume usage, which should remain zero unless an explicit design
  decision adds a volume;
- replica count, sleep/serverless state, and worker liveness; and
- actual usage total, projected invoice, plan minimum, and service-level cost
  split.

Railway Pro includes the first `$20` of measured usage; it does not make CPU,
RAM, or egress free. The native usage page and first complete invoice replace
the pre-launch RAM/CPU estimate in the provider decision.

### Supabase

Check:

- live database size and provisioned disk separately;
- compute CPU/memory, direct/pooler connections, pool saturation, I/O, slow
  queries, locks, and database restarts;
- table and index size reports, especially transcripts, transcript segments,
  summaries, jobs, and job events;
- uncached egress, cached egress, Storage size, MAU, and any forecast/overage;
- Auth failures, rate limits, suspicious signup volume, and custom SMTP status;
- database backup success and retention; and
- database/security advisors after migrations or configuration changes.

Supabase database backups protect Postgres and Storage metadata, not the stored
file objects themselves. Keep object-retention/backup decisions explicit.

### Groq and OpenRouter

For each billing cycle, compare provider usage with Talven telemetry:

- request count and billed audio seconds or tokens;
- model breakdown, spend, credit balance, and projected exhaustion;
- rate-limit events, provider failures, and any organization-limit changes; and
- the largest reconciliation difference and its cause.

Do not migrate providers from price-table arithmetic alone. Benchmark output
quality, timestamp shape, latency, rate limits, failure/retry behavior, support,
and total integration complexity on representative Talven sources.

### Polar and Resend

In Polar, reconcile base sales, tax, fees, refunds/disputes, payout batches, and
the amount actually paid to the business. Investigate unresolved or replayed
webhooks from the Talven billing view.

In Resend, check sends, deliveries, bounces, complaints, rejected messages,
daily/monthly quota, and domain/DNS status. A successful API call does not prove
that a user received an Auth email.

## Review cadence

### Immediate alerts

Alerts—not a daily manual check—should cover:

- web, API, or worker unavailable, repeatedly restarting, or OOM-killed;
- stale Grafana/collector data;
- no worker liveness, a disconnected/reconnecting listener, growing runnable
  queue, or an old runnable/running job;
- any pool timeout, connection-exhaustion risk, sustained database saturation,
  deadlock, or abnormal lock wait;
- sustained `5xx`, `429`, core-journey, provider, or SSE failure spike;
- exhausted job retries or completed work that cannot settle;
- unresolved Polar webhook, refund, reconciliation, or balance mismatch;
- temporary audio older than the approved safety window, initially 24 hours,
  or repeated cleanup failure;
- provider balance/quota exhaustion risk; and
- database disk, egress, Storage, or host-resource forecast crossing an action
  threshold.

Every alert needs an owner, delivery channel, severity, first runbook link, and
a tested “resolved” condition. An alert that nobody receives is stored noise.

### Daily: five to ten minutes

1. Open the Grafana owner overview; confirm data freshness and no unresolved
   critical alert.
2. Check accepted/completed/failed jobs, oldest queue age, p95 completion time,
   provider errors, and billing recovery work against the recent baseline.
3. Check temporary-audio orphans and cleanup failures.
4. Check Railway for restarts/OOM events and an abnormal projected bill.
5. Check Supabase for a sudden quota, connection, disk, backup, or Auth anomaly.

No action is required merely because a chart moved. Record the suspected cause
when a change is material, then confirm it with the authoritative provider page.

### Weekly: about 30 minutes

1. Compare workflow and provider p50/p95 latency, failures, retries, cache-hit
   rate, cold audio hours, and cost per briefing with the previous four weeks.
2. Review Railway average/peak RAM and CPU, egress, restarts, and cost by service.
3. Review Supabase database growth, largest table/index pairs, connections,
   slow queries, cached/uncached egress, Storage, and MAU.
4. Reconcile Talven audio seconds/tokens/cost with Groq and OpenRouter totals.
5. Review Polar/Resend failures, refunds, bounces/complaints, and quota pace.
6. Review the 30-day capacity forecast and log any threshold, owner, and next
   action in the decision record template below.

### Monthly: close the billing cycle

1. Reconcile provider invoices/exports against Grafana and Talven events; record
   explained timing, currency, rounding, retry, or refund differences.
2. Calculate revenue, provider cost, contribution, fixed infrastructure, and
   owner-cash scenarios from the actual plan and usage mix.
3. Replace assumptions with measured Railway service cost, Supabase usage,
   provider cost per cold hour, and cache savings.
4. Review 30- and 90-day growth forecasts, retention cleanup evidence, backup
   success, alert noise/misses, and the capacity/provider triggers below.
5. Make a provider decision only when the evidence and migration rule are met;
   otherwise record “keep” and the next review date.

### Quarterly or before a major launch

- Load-test the exact staging topology and recalibrate resource, latency, queue,
  and connection thresholds.
- Run a database restore rehearsal and verify required object recovery.
- Benchmark the current transcription/LLM provider against the leading
  challenger on representative sources.
- Review telemetry retention, access, redaction, sampling, and spend.
- Confirm the alert receiver and incident/runbook ownership still work.

## Initial thresholds and decisions

These are starting guardrails, not production promises. Resource/latency/error
thresholds must be replaced after an exact-topology staging baseline and at
least one representative week. Use both a current percentage and a billing-cycle
forecast so a late-month spike is not hidden by an average.

| Signal | Warning / investigate | Decision / urgent action |
| --- | --- | --- |
| Railway monthly usage | Forecast reaches `$16`, 80% of the `$20` Pro credit | Explain before forecast exceeds `$20`; benchmark another host only after recurring materially higher cost or a reliability/support limitation. |
| Railway RAM per service | Sustained above 70% of its configured limit | Above 85%, memory errors, or any OOM: profile, right-size, or reduce concurrency immediately. |
| Railway CPU per service | Sustained above 70% for 15 minutes | Above 90% with latency/queue impact: profile, scale, or reduce bounded concurrency. |
| Supabase provisioned database disk | Live/useful bytes or growth forecast reaches 60% | Plan cleanup/expansion at 75%; act before 85%. Do not wait for automatic growth near 90%. |
| Supabase uncached egress | 125 GB or 50% forecast | Benchmark R2/direct upload around 175 GB or 70%; decide before a repeated 200 GB or 80% forecast. |
| Supabase connections/pool | Sustained above 70% or rising pool wait | Above 85%, any pool timeout, or exhaustion risk: tune/limit connections before adding traffic. |
| Temporary audio | Any cleanup retry or increasing retained bytes | Any unreferenced object older than 24 hours: investigate and sweep safely. |
| Provider error/rate limit | Sustained rate doubles the measured baseline with a meaningful sample, or any repeated `429` | Pause concurrency growth; retry/tune or use a proven fallback before customer-visible failures persist. |
| Queue | Oldest age or depth exceeds the staging/user promise baseline | If it grows while workers are saturated, tune/scale workers; redesign the broker only after Postgres/pool tuning fails. |
| Database table/index growth | 30-day forecast accelerates materially | Apply validated event TTL/index cleanup or add disk; database size alone is not a reason to leave Supabase. |

The Railway `$16` threshold is financial, not a capacity limit. Railway meters
actual RAM, CPU, egress, and volume use. Likewise, a Supabase quota percentage
does not prove performance pressure; database compute, connections, I/O, and
query latency must be reviewed separately.

### Provider-change rule

A threshold crossing starts investigation; it does not authorize a migration.
Prefer a change only when all are true:

1. the problem is confirmed in the authoritative provider dashboard/invoice;
2. it recurs for two review periods or the forecast shows it will become urgent;
3. reasonable cleanup, query/index, connection, concurrency, cache, or plan
   tuning does not solve it safely;
4. a representative benchmark proves cost, performance, quality, reliability,
   and support are acceptable; and
5. migration, privacy/security, rollback, and owner-time costs are documented.

Examples:

- **Supabase to R2:** decide for measured temporary-audio or PDF egress/storage
  economics, not because R2 advertises free egress in isolation.
- **Groq to Cloudflare:** decide after a quality, timestamp, latency, failure,
  and chunking benchmark, not for roughly one cent per audio hour alone.
- **Railway to Fly.io/Cloudflare:** decide from the measured three-service bill,
  reliability, deployment/support experience, and worker redesign cost.
- **Postgres queue to Redis/another broker:** decide from persistent queue age,
  connection, notification, or latency evidence after database tuning—not MAU.

## Decision record

Keep one row for every capacity warning, monthly “keep,” or migration study:

| Review date | Billing range | Signal/source | Current | 30/90-day forecast | Threshold | Finding and action | Owner | Next review | Evidence link |
| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- | --- |
| YYYY-MM-DD | YYYY-MM-DD to YYYY-MM-DD | Supabase uncached egress | 0 GB | 0 / 0 GB | 125 / 175 / 200 GB | Example only: keep Supabase | Owner | YYYY-MM-DD | Dashboard/export |

Do not paste secrets, transcripts, source URLs, emails, payment payloads, or
unredacted provider exports into the record.

## Implementation checklist

This document does not mean the metrics exist. Before unattended signup:

- define stable, bounded-cardinality metric names and labels;
- emit missing Talven counters, histograms, and lifecycle gauges;
- collect privacy-safe logs from web, API, and worker;
- connect Railway and Supabase metrics/logs where their actual integrations
  permit it, with a documented manual fallback for values that are not exported;
- import or periodically reconcile Groq, OpenRouter, Polar, and Resend usage;
- create the six Grafana views above and show collector freshness;
- route and test every immediate alert, including a synthetic failure and
  recovery;
- record the staging baseline and replace provisional resource thresholds;
- verify retention, redaction, access control, and telemetry cost; and
- perform one daily, weekly, and monthly review rehearsal.

See also:

- [Provider economics, limits, and scaling boundaries](../decisions/provider-economics-and-limits.md)
- [Minimum production observability and capacity evidence](../decisions/deferred-work.md#minimum-production-observability-and-capacity-evidence)
- [First deployment checklist](./first-deployment-checklist.md)
- [Worker and billing incidents](./worker-and-billing-incidents.md)
- [Growth feature roadmap](../product/growth-feature-roadmap.md#phase-0-owner-telemetry-and-cleanup)
