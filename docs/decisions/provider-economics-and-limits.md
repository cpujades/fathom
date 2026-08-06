# Provider economics, limits, and scaling boundaries

**Status:** Current launch recommendation and future-provider watchlist
**Last reviewed:** 2026-08-05

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

The database is **8 GB, not 800 GB**, and it does not reset monthly. Ten
thousand audio hours means ten thousand one-hour episodes, not 166. At an
estimated 0.2-0.5 MB of database data per unique audio hour, those ten thousand
hours could add about 2-5 GB before indexes and general billing/user data.
That can fit once in 8 GB but cannot accumulate every month indefinitely.

Persistent growth includes full transcripts, duplicated timestamp-segment
text, summaries, jobs, durable events, and billing evidence. Generated PDFs
are separate Storage objects and are created only on request. Temporary audio
is deleted in a `finally` block with three attempts, but hard process death or
repeated deletion failure can leave orphaned objects.

Retention must distinguish disposable data from legal/financial evidence:

- delete temporary `groq-audio/*` objects after a conservative safety window;
- retain billing orders, settlements, refund, and webhook evidence for the
  required accounting/audit period;
- measure per-table/index bytes before setting a transcript/summary TTL;
- compact or prune old high-volume job events under a documented retention
  policy;
- physically purge eligible soft-deleted jobs and unreferenced derivatives;
- preserve shared cache entries while they still save more than they cost;
- back up durable PDF objects or make restore clear missing PDF-cache metadata
  so PDFs regenerate from Markdown.

Official references:

- [Supabase pricing](https://supabase.com/pricing)
- [Supabase egress](https://supabase.com/docs/guides/platform/manage-your-usage/egress)
- [Supabase Storage pricing](https://supabase.com/docs/guides/storage/pricing)
- [Supabase backups](https://supabase.com/docs/guides/platform/backups)

## Infrastructure billing behavior

Railway Pro is a `$20` minimum that includes the first `$20` of measured
resource usage; it is not unlimited compute for a fixed `$20`. Railway meters
RAM, CPU, egress, and volume storage. If measured usage is below `$20`, the
bill remains `$20`; if it is `$47`, the bill is approximately `$47`, not `$67`.
Current published rates include `$10/GB-month` RAM, `$20/vCPU-month`,
`$0.05/GB` egress, and `$0.15/GB-month` volume storage.

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
| Planning total | approximately €50-€100; use €80 in the owner model |

At tens of thousands of audio hours/month, recalculate from measured bytes;
do not carry the €80 constant into a capacity promise.

References:

- [Railway plans and usage pricing](https://docs.railway.com/pricing/plans)
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
