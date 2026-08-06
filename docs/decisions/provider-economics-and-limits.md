# Provider economics, limits, and scaling boundaries

**Status:** Current launch recommendation and future-provider watchlist
**Last reviewed:** 2026-08-06

This page records the current limits that affect a Talven source from download
through transcription, persistence, and email. Prices and provider quotas are
time-sensitive. Recheck the linked primary sources and the account dashboards
before a migration or capacity promise.

The deeper reliability decision for sources longer than two hours remains in
[Long-audio and transcription decision](./long-audio-and-transcription.md).

## Current recommendation

- Use Groq Whisper Large V3 Turbo synchronously for the initial release.
- Keep Talven's two-hour and 100,000,000-byte boundaries.
- Use Supabase Pro for a public/paid beta.
- Use Railway for web, API, and worker until measured load justifies a split.
- Configure Resend Free as Supabase Auth's custom SMTP provider.
- Add a lifecycle rule/sweeper for temporary audio and per-job cost telemetry.
- Benchmark Cloudflare Workers AI, but do not migrate for a saving of roughly
  one cent per audio hour without quality, timestamp, latency, and failure
  evidence.
- Defer self-hosting; the operational effort dominates the early savings.

## End-to-end file boundaries

| Boundary | Current limit or behavior | Consequence |
| --- | --- | --- |
| Talven product | 2 hours | Longer YouTube sources are rejected before processing. |
| Talven downloader | 100,000,000 bytes, about 95.4 MiB | A high-bitrate two-hour source can still be rejected. |
| Worker temporary disk | One local file per active cold job | At concurrency 10, audio alone can approach 1 GB plus process overhead. Start hosted concurrency at 1-2 and measure. |
| Supabase Free upload | At most 50 MB | Cannot fulfill Talven's current 100 MB contract. |
| Supabase Pro plan maximum | Global limit configurable up to 500 GB | Set the project global limit to 100 MB and optionally the private audio bucket to the same or a slightly smaller explicit value. |
| Supabase standard upload method | Supports up to 5 GB; resumable/S3 recommended above 6 MB | The current standard upload of files up to 100 MB needs real staging reliability evidence. |
| Groq Free STT | 25 MB | Too small for Talven's existing promise. |
| Groq Developer STT | 100 MB per request, including URL inputs | No separate duration limit is documented; bitrate determines how many hours fit. |
| Cloudflare Worker request | 100 MB on Cloudflare Free/Pro account plans | Not an unlimited-file escape from Groq's boundary. |
| Cloudflare Worker memory | 128 MB | Fetching a near-100 MB file and base64-encoding it in one isolate can exceed safe memory; chunk/stream outside the isolate. |

The Supabase buckets are private but do not currently set a bucket-level
`file_size_limit`; the hosted project's global Storage setting therefore
matters. Supabase allows a Pro global maximum up to 500 GB, but Talven should
set 100 MB rather than expose that entire provider maximum.

References:

- [Supabase Storage file limits](https://supabase.com/docs/guides/storage/uploads/file-limits)
- [Supabase upload-size settings](https://supabase.com/docs/guides/troubleshooting/upload-file-size-restrictions-Y4wQLT)
- [Supabase standard uploads](https://supabase.com/docs/guides/storage/uploads/standard-uploads)
- [Groq speech-to-text](https://console.groq.com/docs/speech-to-text)
- [Cloudflare Worker limits](https://developers.cloudflare.com/workers/platform/limits/)

## Duration versus file size

Groq does not publish a separate maximum number of hours for one Developer STT
request. The 100 MB request limit is the practical boundary. Approximate audio
represented by 100 MB is:

| Bitrate | Approximate duration |
| ---: | ---: |
| 24 kbps | 9.3 hours |
| 32 kbps | 6.9 hours |
| 48 kbps | 4.6 hours |
| 64 kbps | 3.5 hours |
| 96 kbps | 2.3 hours |
| 128 kbps | 1.7 hours |

Talven selects the smallest audio-only YouTube stream, but it must still
measure the resulting bytes. Normalizing to 16 kHz mono and implementing
durable chunks is the safe route to longer inputs.

Groq Developer's published base Turbo limits are 400 requests/minute and
400,000 audio-seconds/hour, or about 111 source-audio hours submitted per wall
hour. These are organization consumption limits rather than a per-file duration
limit. The Groq account Limits page is authoritative.

## Synchronous and asynchronous transcription

- **Synchronous:** Talven sends a request and waits for that request to return
  the transcript. It supports the current “create briefing and watch progress”
  experience.
- **Asynchronous/batch:** Talven submits a job, persists its provider ID, and
  later polls or receives completion. It can be cheaper and more resilient for
  delayed work, but the user must accept a queue instead of an immediate result.

Groq's normal endpoint and direct Cloudflare Workers AI inference are
synchronous. Groq Batch is asynchronous, costs about `$0.02/audio-hour`, and
uses a completion window between 24 hours and seven days. It is suitable only
for a clearly labeled economy/background mode.

This provider distinction is separate from Talven's web architecture. The API
already creates a durable job and returns while the background worker performs
the synchronous provider request; the browser watches progress over SSE. Thus a
synchronous Groq or Cloudflare call does **not** block the browser request
thread. Calling Python code `async` also does not turn a provider request into a
provider batch job: it only lets Talven wait without monopolizing the event
loop and run a bounded number of independent jobs concurrently.

## Transcription-provider comparison

| Provider | Approximate price/hour | Timing and limits | Decision |
| --- | ---: | --- | --- |
| Groq Batch | $0.02 | Asynchronous; 24h-7d completion window | Optional future economy queue. |
| Cloudflare Whisper Large V3 Turbo | $0.030-$0.031 | Synchronous direct inference; 100 MB surrounding Worker request limit; timed segments/VTT; 720 ASR RPM | Benchmark challenger. |
| Groq Whisper Large V3 Turbo | $0.04 | Synchronous; 100 MB Developer request; word/segment timestamps; advertised 216x real time | Keep for launch. |
| Fireworks Whisper Turbo | $0.054 | Hosted open-weight model | No cost advantage. |
| Together Whisper/Parakeet | $0.09 | Hosted alternatives | No cost advantage. |
| AssemblyAI Universal-2 | $0.15, diarization +$0.02 | Up to 10 hours/5 GB; high paid concurrency | First simple long-file/diarization fallback. |
| Mistral Voxtral Transcribe | $0.18 | Up to three hours; diarization and word timestamps | Quality benchmark, not cost choice. |
| Deepgram Nova-3 | $0.288-$0.348 | Up to 2 GB; richer speech features | Use only for a proven quality/residency need. |

Cloudflare is cheaper, but the saving is only about `$9-$10` per 1,000 audio
hours. Cloudflare does not publish a Groq-equivalent 216x benchmark or latency
SLA for this model. Its direct result is synchronous and likely usable, but
Talven must benchmark real-time factor, cold starts, timestamp shape, proper
names, accents, failures, and chunk-merging behavior. Cloudflare's own tutorial
chunks large audio to work around memory and execution limits.

References:

- [Cloudflare Whisper Large V3 Turbo](https://developers.cloudflare.com/workers-ai/models/whisper-large-v3-turbo/)
- [Cloudflare Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)
- [Cloudflare large-audio chunking tutorial](https://developers.cloudflare.com/workers-ai/guides/tutorials/build-a-workers-ai-whisper-with-chunking/)
- [Cloudflare Workers AI limits](https://developers.cloudflare.com/workers-ai/platform/limits/)
- [Groq Batch](https://console.groq.com/docs/batch)
- [Groq rate limits](https://console.groq.com/docs/rate-limits)

## Open-source and self-hosted watchlist

The strongest initial candidates are:

- [NVIDIA Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3):
  25 European languages, language detection, word/segment timestamps, and up
  to three-hour local-attention inputs; no native diarization.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper): the safest
  Whisper-compatible self-host path with batching, VAD, INT8, and word
  timestamps.
- [WhisperX](https://github.com/m-bain/whisperX): alignment and diarization at
  the cost of more models and infrastructure.
- [whisper.cpp](https://github.com/ggml-org/whisper.cpp): attractive for local,
  private, or Apple Silicon processing, not the first hosted SaaS path.

Efficiently batched GPU inference can theoretically reach about
`$0.01-$0.03/audio-hour`. That excludes idle capacity, cold starts, decoding,
storage, egress, queues, retries, monitoring, quality regressions, and owner
time. At 1,000 hours/month, replacing `$40` of Groq with `$15` of theoretical
self-hosted GPU time saves only `$25`. Revisit around 5,000-10,000 measured
monthly hours, or earlier for privacy/data-residency/vendor-resilience reasons.

## What egress means

**Egress is data leaving a provider.** The allowance is measured per billing
month and resets with the billing cycle. It is unrelated to how long an object
remains stored.

For a cold Talven source:

```text
YouTube -> Railway worker             Railway ingress
Railway worker -> Supabase Storage    Railway egress / Supabase ingress
Supabase signed URL -> Groq            Supabase egress / Groq ingress
```

Deleting the temporary object prevents storage accumulation but does not undo
the bytes already transferred to Groq.

A database read is not automatically the same thing as egress. PostgreSQL may
scan pages internally without those scanned bytes leaving Supabase. The result
bytes returned to the API/browser do count as Supabase database or pooler
egress. Other Talven examples are:

| Action | Egress charged by |
| --- | --- |
| Worker uploads temporary audio to Supabase | Railway; the bytes are ingress to Supabase |
| Groq fetches the private signed audio URL | Supabase Storage |
| API fetches a transcript/query result from Supabase | Supabase database/pooler |
| Browser downloads a generated PDF | Supabase Storage |
| Browser signs in and receives Auth data | Supabase Auth |

Supabase combines those uncached outbound bytes into the 250 GB Pro quota for
the billing cycle. Cached egress has a separate 250 GB quota. Uploading data to
Supabase is ingress and does not consume its outbound quota.

A **cold source** is a cache miss: Talven has no compatible stored transcript
for that source/provider/version and must download and transcribe it. A cache
hit reuses the stored transcript and avoids the temporary audio and Groq
transfer.

The small-number arithmetic is:

```text
100 sources x 50 MB = 5,000 MB = about 5 GB, not 500 GB
200 sources x 25 MB = 5,000 MB = about 5 GB
250 GB / 50 MB       = about 5,000 cold sources
250 GB / 25 MB       = about 10,000 cold sources
```

Therefore Supabase Pro's 250 GB monthly egress is substantial early headroom,
but not unlimited. At 30-50 MB/audio-hour it represents roughly 5,000-8,300
cold audio hours/month before other database/Auth/PDF egress.

There is no separate daily Supabase quota; `250 GB / 30` is an average planning
pace of about `8.3 GB/day`. At 50 MB per cold source, 100 cold sources/day use
about 150 GB/month. At the maximum 100 MB, 100/day use about 300 GB/month; the
50 GB Supabase overage would currently be only about `$4.50`, before other
egress. The same 300 GB upload path costs about `$15` of Railway egress. At that
volume, transcription and compute are normally more important than bandwidth,
but the bytes should still be measured rather than guessed.

The current double-hop through Supabase is useful for Groq URL ingestion but
creates both Railway and Supabase egress. A future scale experiment may stream
the worker's local file directly to Groq's multipart endpoint or use a cheaper
temporary object store. That is an optimization, not an initial-release
requirement, and must preserve bounded memory, retries, cancellation, and
cleanup.

## Supabase capacity

| Resource | Free | Pro |
| --- | ---: | ---: |
| Database disk | 500 MB total | 8 GB total, then paid expansion/overage |
| File Storage | 1 GB average | 100 GB average, then $0.0213/GB-month |
| Uncached egress | 5 GB/month | 250 GB/month, then $0.09/GB |
| Cached egress | 5 GB/month | 250 GB/month, then $0.03/GB |
| MAU | 50,000 | 100,000 |
| Maximum configured file size | 50 MB | Up to 500 GB |
| Backups | No automatic production backup | Daily database backup, seven days |

The database is **8 GB, not 800 GB**, and it does not reset monthly. It is the
included provisioned disk available at one time. On paid projects Supabase can
expand the disk when it reaches 90%, if the Spend Cap allows overage; the first
automatic step is normally 8 GB to 12 GB. Current general-purpose disk overage
is `$0.125/GB-month`, so storage growth itself is gradual:

| Provisioned disk | Approximate disk overage above Pro |
| ---: | ---: |
| 8 GB | $0 |
| 12 GB | $0.50/month |
| 20 GB | $1.50/month |
| 50 GB | $5.25/month |
| 100 GB | $11.50/month |

This is recurring provisioned-capacity billing, not a one-time expansion fee.
For example, keeping a 100 GB general-purpose disk provisioned for a complete
month adds about `$11.50` to every monthly bill above the `$25` Pro base, for a
rough `$36.50/month` Supabase total before compute upgrades or other overage.
Disk is metered in GB-hours, so a mid-cycle expansion is prorated. Provisioned
disk does not automatically shrink during ordinary operation merely because
rows are deleted.

Those figures exclude larger database compute, extra IOPS/throughput, egress,
and other services. Keep operating headroom rather than deliberately filling
the disk to 100%.

Postgres has no useful fixed “rows per 8 GB” answer because row width and
indexes matter. A rough intuition, before WAL/system headroom, dead tuples, and
page overhead, is:

```text
1,000,000 rows x 1 KB effective bytes/row  = about 1 GB
1,000,000 rows x 4 KB effective bytes/row  = about 4 GB
1,000,000 rows x 10 KB effective bytes/row = about 10 GB
```

So one million small billing rows can fit, while one million rows containing
large transcript or JSON text cannot. In Talven the important multipliers are
hundreds of `transcript_segments` per unique episode and multiple sparse
`job_events` per user job. `transcripts.transcript_text` and segment text also
intentionally retain overlapping textual evidence. At an estimated 0.2-0.5 MB
of database data per unique audio hour, ten thousand one-hour episodes could
add about 2-5 GB before indexes and general billing/user data. That can fit
once in 8 GB but cannot accumulate every month indefinitely.

Persistent growth includes full transcripts, duplicated timestamp-segment
text, summaries, jobs, durable events, and billing evidence. Generated PDFs
are separate Storage objects and are created only on request. Temporary audio
is deleted in a `finally` block with three attempts, but hard process death or
repeated deletion failure can leave orphaned objects.

Retention must distinguish disposable data from legal/financial evidence:

- run a bounded, paginated sweeper that lists private `groq-audio/*` objects
  and deletes objects older than a conservative window such as 24 hours, while
  excluding any object referenced by an active job;
- retain billing orders, settlements, refund, and webhook evidence for the
  required accounting/audit period;
- measure per-table/index bytes before setting a transcript/summary TTL;
- propose pruning ordinary `job_events` 90 days after their job becomes
  terminal, while retaining any explicitly selected audit milestones; never
  prune events for queued/running/recoverable jobs;
- physically purge eligible soft-deleted jobs and unreferenced derivatives;
- preserve shared cache entries while they still save more than they cost;
- back up durable PDF objects or make restore clear missing PDF-cache metadata
  so PDFs regenerate from Markdown.

The 90-day event period is a proposal, not implemented behavior. It must be
checked against support needs, SSE replay semantics, privacy policy, and the
foreign-key restrictions that preserve usage-settlement evidence. The current
`ttl_expires_at` columns also do not prove that a scheduled purge exists.

Measure real table and index sizes before redesigning anything:

```sql
select
  io.relname as table_name,
  stats.n_live_tup as estimated_rows,
  pg_size_pretty(pg_relation_size(io.relid)) as table_bytes,
  pg_size_pretty(pg_indexes_size(io.relid)) as index_bytes,
  pg_size_pretty(pg_total_relation_size(io.relid)) as total_bytes
from pg_catalog.pg_statio_user_tables as io
join pg_catalog.pg_stat_user_tables as stats using (relid)
order by pg_total_relation_size(io.relid) desc;
```

Do not compact `transcript_segments` merely to reduce row count: their
timestamp evidence enables cited briefings and episode Q&A. Event history is a
safer first retention target because it is numerous, append-only, and becomes
less useful after a job is terminal and old.

Official references:

- [Supabase pricing](https://supabase.com/pricing)
- [Supabase egress](https://supabase.com/docs/guides/platform/manage-your-usage/egress)
- [Supabase disk usage](https://supabase.com/docs/guides/platform/manage-your-usage/disk-size)
- [Supabase database and disk size](https://supabase.com/docs/guides/platform/database-size)
- [Supabase Storage pricing](https://supabase.com/docs/guides/storage/pricing)
- [Supabase backups](https://supabase.com/docs/guides/platform/backups)

## Infrastructure billing behavior

Railway Pro is a `$20` minimum that includes the first `$20` of measured
resource usage; it is not unlimited compute for a fixed `$20`. Railway meters
RAM, CPU, egress, and volume storage. If measured usage is below `$20`, the
bill remains `$20`; if it is `$47`, the bill is approximately `$47`, not `$67`.
Current published rates include `$10/GB-month` RAM, `$20/vCPU-month`,
`$0.05/GB` egress, and `$0.15/GB-month` volume storage.

Railway does not give Pro a fixed included quantity of RAM, CPU, or egress.
Its published 1 TB RAM, 1,000 vCPU, 100 GB ephemeral storage, and up-to-1-TB
volume figures are ceilings, including replicas—not prepaid resources. The
first `$20` of the following combined meter is covered:

```text
average RAM GB x $10
+ average vCPU x $20
+ outbound GB x $0.05
+ average volume GB x $0.15
```

For intuition, 1 GB of always-on RAM ($10), an average 0.25 vCPU ($5), and 100
GB egress ($5) exactly consume the $20 credit. Talven will run separate web,
API, and continuous-worker services, so their combined idle RAM matters even
with no users. Railway's own metrics and first full-cycle invoice are the only
reliable forecast.

Talven does not currently need a Railway persistent volume. Its audio lives in
a per-job temporary directory and is copied to private object storage before
transcription; crash recovery comes from Postgres and object storage, not a
local filesystem. A volume would add cost and single-service attachment
constraints without becoming an authoritative store. Ephemeral storage is
still needed for active downloads and scales with worker concurrency.

### Low-traffic Talven estimate

No hosted invoice exists yet, so this is a capacity-planning envelope rather
than a measurement:

| Service | Expected average RAM | Expected low-traffic CPU |
| --- | ---: | ---: |
| Next.js web | 0.25-0.50 GB | 0.01-0.05 vCPU |
| FastAPI API | 0.25-0.50 GB | 0.01-0.05 vCPU |
| Continuous Python worker | 0.25-0.50 GB | 0.03-0.05 vCPU |
| **Combined** | **0.75-1.50 GB** | **0.05-0.15 vCPU** |

At Railway's current rates, that is roughly `$7.50-$15` RAM plus `$1-$3`
CPU each month. Initial application/API egress should be small; even 10 GB is
only `$0.50`. The likely low-traffic meter is therefore about `$8.50-$18.50`,
which remains inside the Pro plan's `$20` credit. The resulting Railway bill is
still `$20`, not `$20` plus those amounts. Peaks can be higher during source
download, PDF rendering, deploys, or concurrent work, so set service resource
ceilings and replace the estimate after one exact-topology staging week.

Railway Serverless may let the web or API sleep, but any open database pool,
telemetry, or outbound packet can prevent sleep. The continuous worker must
remain awake because it listens for database notifications and owns recovery;
do not enable sleeping on it merely to reduce its RAM bill.

### Host recommendation

- **Keep all three processes on Railway for launch.** It runs the existing
  containers without a framework rewrite, and the forecast already fits the
  Pro floor.
- **Railway Hobby is the credible cost-saving option for a private pilot.** It
  has a `$5` minimum but still bills actual usage above `$5`; this workload may
  therefore cost roughly `$9-$19`, not necessarily `$5`. Upgrade when the
  production/team/support boundary justifies Pro.
- **Cloudflare for only the frontend does not remove the Railway minimum.** A
  complete move is now technically possible through Workers/Containers, but
  it adds a Worker routing layer and explicit container lifecycle. Talven's
  continuously listening worker would need to remain active or be redesigned
  around Queues/Workflows; that migration is not justified by a likely saving
  of a few dollars.
- **Fly.io can be cheaper for small shared-CPU Machines**, potentially around
  `$10-$15` for three small always-on processes, but requires more explicit VM,
  sizing, wake/sleep, network, and deployment ownership. Revisit if Railway's
  measured bill exceeds its convenience/support value.

References:

- [Railway Serverless behavior](https://docs.railway.com/deployments/serverless)
- [Cloudflare Containers pricing](https://developers.cloudflare.com/containers/pricing/)
- [Cloudflare Container scaling](https://developers.cloudflare.com/containers/platform-details/scaling-and-routing/)
- [Fly.io resource pricing](https://fly.io/docs/about/pricing/)

Supabase Pro similarly includes quotas rather than unlimited use. The base is
`$25`; database disk, Storage, egress, MAU, larger compute, custom domains, and
other add-ons can create overage. If Talven remains inside Pro's included
quotas, it remains `$25`.

The requested early planning stack is:

| Item | Early monthly assumption |
| --- | ---: |
| Railway Pro | $20-$40 |
| Supabase Pro | $25-$35 |
| Resend Auth SMTP | $0 |
| Domain, monthly equivalent | about $1 |
| Optional Supabase Auth custom domain | $0 or $10 |
| Basic monitoring/backup reserve | $0-$5 |
| Production infrastructure cash floor | about $46 / €40 at the planning exchange rate |
| Sensible zero-customer budget | about €50 |
| Scenario allowance | use €80 in the owner model |

At tens of thousands of audio hours/month, recalculate from measured bytes;
do not carry the €80 constant into a capacity promise.

The infra-only floor is not the whole no-revenue business floor. Once the owner
is registered as an autónomo, the current planning model adds a €70 gestor and
eligible €88.64 reduced contribution, making the first-year cash floor about
€199/month from the exact converted infrastructure estimate, or €208.64 using
the rounded €50 infrastructure budget. See
[Unit economics and owner cash model](../product/unit-economics.md#zero-customer-monthly-floor).

References:

- [Railway plans and usage pricing](https://docs.railway.com/pricing/plans)
- [Railway bill behavior](https://docs.railway.com/pricing/understanding-your-bill)
- [Supabase billing](https://supabase.com/docs/guides/platform/billing-on-supabase)

## Email boundary

Supabase Pro's “email support” means customer support for the project. It does
not include a production outbound email service. Supabase's built-in Auth SMTP
is limited to team addresses and two messages/hour. Configure Resend Free as
custom SMTP before public signup. It currently provides 3,000 emails/month and
100/day; a channel digest to thousands of users will eventually require a paid
email tier.

References:

- [Supabase custom SMTP](https://supabase.com/docs/guides/auth/auth-smtp)
- [Resend pricing](https://resend.com/pricing)

## Required telemetry and lifecycle work

Before paid public traffic, record or derive:

- source duration, downloaded bytes, normalized bitrate, and cold/cache-hit
  status;
- provider, model, provider request ID, retry count, latency, and billed audio
  seconds;
- OpenRouter model, input/output tokens, retry count, and billed cost;
- temporary object key, created/deleted timestamps, cleanup attempts, and
  orphan count/bytes;
- PDF generated bytes and retained bytes;
- Supabase and Railway egress estimates per job;
- business contribution per briefing and per user; and
- daily/monthly provider spend, error rate, and p50/p95 stage latency.

Use application events as the durable source, then expose an owner dashboard
with plan, user, provider, and cache-hit breakdowns. Polar's Cost Insights can
receive summarized cost events later, but it should not replace Talven's own
auditable provider telemetry.
