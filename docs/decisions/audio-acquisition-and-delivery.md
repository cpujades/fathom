# Audio acquisition and temporary delivery decision

**Status:** Accepted for the bounded initial release; alternative source
adapters and delivery paths remain proposed experiments

**Date:** 2026-08-06

## Context

Talven currently accepts a YouTube URL, downloads an audio-only stream on the
worker, places the private temporary object in Supabase Storage, and gives Groq
a short-lived signed URL. This decision separates two questions that are easy
to mix together:

1. **Acquisition:** how Talven obtains permitted audio bytes from a source.
2. **Provider delivery:** how those bytes reach the transcription provider.

Replacing the downloader does not remove provider file limits. Replacing
Supabase Storage does not make YouTube extraction more reliable. Both layers
need independent evidence and rollback.

Long-input normalization, provider selection, and durable chunk merging are
covered in [Long-audio and transcription decision](./long-audio-and-transcription.md).
Provider prices and quotas are in
[Provider economics, limits, and scaling boundaries](./provider-economics-and-limits.md).

## Current implementation

For a cold source, the implemented path is:

```text
YouTube URL
  -> bounded pytubefix subprocess
  -> smallest advertised audio-only stream
  -> Railway temporary directory
  -> private Supabase fathom_groq object
  -> short-lived signed URL
  -> synchronous Groq request inside the background worker
  -> immediate deletion with three bounded attempts
```

The path rejects sources above the two-hour product limit before processing.
The downloader then enforces a 100,000,000-byte limit, a five-minute source
deadline, cancellation, response-size limits, and restricted subprocess
environment inheritance. This is materially safer than calling an unbounded
downloader in an API request, although provider breakage and source-policy risk
remain.

## Decision drivers

- Do not block the browser while downloading or transcribing.
- Keep source bytes private and signed URLs short-lived.
- Bound bytes, time, memory, redirects, concurrency, and retries.
- Preserve timestamp evidence for citations and future episode Q&A.
- Retry only the smallest failed unit once durable chunking exists.
- Avoid adding a provider before measured reliability or cost justifies it.
- Support source types that are more stable than arbitrary YouTube extraction.
- Keep copyright, platform-policy, privacy, and deletion claims honest.

## Considered acquisition options

| Option | Strengths | Weaknesses | Decision |
| --- | --- | --- | --- |
| Keep bounded `pytubefix` | Already integrated; simple Python surface; current limits and cancellation are tested | YouTube changes can break extraction; fewer operational controls than `yt-dlp`; no policy improvement | **Keep for the bounded initial release.** |
| Replace with `yt-dlp` | Extensive format selection, fragment retries, subtitle support, throttling detection, and active release channel | Larger dependency/CLI surface; often needs FFmpeg; still tracks undocumented YouTube behavior; migration needs regression tests | Benchmark as the first downloader challenger; switch only on representative reliability evidence. |
| Try YouTube captions before audio | Near-zero transcription cost and latency when good captions exist | Official caption download requires permission to edit the video; unofficial public-caption extraction is incomplete, variable quality, and has the same brittleness/policy boundary | Optional quality experiment, not a dependable primary path. |
| Resolve publisher podcast RSS enclosures | Stable publisher-provided audio URL; avoids YouTube extraction; natural fit for actual podcasts | Requires a new source resolver, redirect/SSRF controls, feed parsing, duplicate identity, and publisher-rights rules | **Recommended next source-adapter experiment.** |
| User uploads audio | Supports private/non-YouTube content and gives explicit file-size validation | Upload UX, malware/content-type checks, ownership terms, storage lifecycle, and quota abuse become product responsibilities | Valuable later source adapter, especially for professional users. |
| Give Groq a YouTube media URL directly | Avoids Talven's temporary object | Media URLs expire and may require headers/ranges/cookies; provider retries become uncontrollable; byte/deadline checks and audit evidence are lost | Reject. |

`yt-dlp` is not automatically “better” merely because it has more features.
Talven's current `pytubefix` call already runs in a disposable subprocess with
application-owned limits. A fair comparison should run both implementations
against the same 20-50 permitted sources and record success rate, selected
bitrate/bytes, metadata correctness, time, failure category, and update burden.
Do not silently fall back between two downloaders in production until source
identity and output compatibility are proved; two hidden behaviors make
failures harder to reproduce.

## Considered provider-delivery options

| Option | Network path | Strengths | Weaknesses | Decision |
| --- | --- | --- | --- | --- |
| Supabase signed URL | Railway -> Supabase -> Groq | Implemented, private, retryable provider URL, shared service identity | Railway egress plus Supabase audio egress; temporary-object cleanup; standard uploads over 6 MB need staging proof | **Keep for launch.** |
| Direct multipart to Groq | Railway -> Groq | Removes temporary object and Supabase audio egress | Groq caps direct attachments at 25 MB; every retry reuploads; does not fulfill the current 100 MB contract without compression/chunking | Use only for small normalized chunks after benchmarking. |
| Cloudflare R2 signed URL | Railway -> R2 -> Groq | S3-compatible, presigned GET, free Internet egress, inexpensive temporary storage, native lifecycle rules | New credentials/adapter/monitoring/recovery surface; Railway egress remains | Best measured scale alternative for temporary audio. |
| Worker proxy stream | YouTube -> Railway proxy -> Groq | Avoids object storage | Long-lived connection, duplicate source download on retry, range/header complexity, hard cancellation/recovery, more SSRF surface | Reject for the first release. |
| R2 plus Cloudflare Workers AI | Railway -> R2/Workers AI | Keeps temporary object and inference in one vendor; cheap ASR | New transcription contract; 128 MB Worker memory; chunking and timestamp quality still require proof | Benchmark provider alternative, not an acquisition shortcut. |

R2 can make sense even though Talven is not short of object-storage capacity.
Its value for this path is **zero R2 egress to Groq plus lifecycle rules**, not
more space. Standard R2 currently includes 10 GB-month, one million Class A
operations, ten million Class B operations, and free Internet egress each
month; additional Standard storage is `$0.015/GB-month`. A 24-hour temporary
audio lifecycle would normally make stored GB-month tiny.

Do not move PDFs to R2 merely for symmetry. Supabase Pro already includes 100
GB of Storage and Talven already has private signed-PDF behavior. Evaluate PDF
migration separately if measured download egress, backup, or recovery needs
become material.

## Decision

Use the following staged path:

1. Keep the current bounded `pytubefix` -> Supabase signed URL -> Groq path for
   the first launch.
2. Add the documented 24-hour orphan-audio sweeper and per-job byte/cost
   telemetry before claiming that temporary storage always cleans itself.
3. Benchmark `yt-dlp` against `pytubefix`; migrate only if it materially
   improves success rate or maintainability on Talven's source set.
4. Design a provider-independent source adapter. Evaluate podcast RSS
   enclosures first, then direct user uploads, while keeping YouTube as one
   source type rather than the entire ingestion architecture.
5. When Supabase audio egress or standard-upload reliability becomes material,
   compare the current bridge with R2 signed URLs. Do not add R2 only to save a
   few euros inside the included Supabase quota.
6. Normalize and chunk before promising files beyond the current boundary.
   Direct multipart becomes viable for chunks under Groq's 25 MB attachment
   limit; R2/Supabase URL delivery remains viable for larger provider inputs.

## Synchronous provider, asynchronous product

The product can remain responsive while using a synchronous transcription
provider:

```text
Browser submits source
  -> API persists job and returns session
  -> background worker claims job
  -> worker awaits one synchronous provider result
  -> browser receives persisted progress over SSE
```

This is already Talven's architecture. “Make it async” at the application layer
means durable queueing, bounded worker concurrency, cancellation, and progress;
it does not mean selecting a 24-hour provider batch product. For chunked audio,
each provider call can remain synchronous while the durable manifest schedules
several bounded independent chunks and retries only failures.

## Lifecycle consequences

Immediate deletion is the primary cleanup. A scheduled sweeper is the recovery
layer for process death or repeated provider/storage errors:

1. list `groq-audio/*` with pagination;
2. ignore objects newer than 24 hours;
3. exclude any object referenced by an active manifest/job;
4. delete in bounded batches with idempotent not-found handling;
5. emit scanned/deleted/failed object counts and bytes; and
6. alert on repeated failures or growing orphan bytes.

R2 could enforce the age rule with a bucket lifecycle. Supabase still needs an
application-owned scheduled sweep unless a verified hosted lifecycle feature
provides equivalent behavior. In either case, never use a broad bucket delete:
temporary audio and durable PDFs have different lifetimes.

## Security and policy boundary

Adding RSS or arbitrary media URLs expands the current allowlisted YouTube
fetch into a general server-side fetcher. It therefore requires HTTPS-only
URLs, DNS/IP validation before and after redirects, private/link-local address
blocking, redirect and byte caps, content-type validation, deadlines, and
audit-safe error messages.

This document is not legal advice. YouTube's official developer policy says API
clients must not download, cache, or store YouTube audiovisual content without
prior written approval, and the official Captions API requires permission to
edit a video to download its caption track. A third-party downloader does not
remove those conditions. Before public launch, counsel should review the exact
source flow, user representations/rights, retention, attribution, takedown, and
whether publisher RSS/user-upload inputs should be the primary supported path.

## Revisit triggers

- More than 1% of permitted sources fail because of extractor behavior.
- A downloader update is required repeatedly to keep ordinary sources working.
- Supabase standard uploads above 6 MB are unreliable in exact-candidate
  staging.
- Temporary-audio Supabase egress reaches 50% of the monthly quota: alert and
  improve the forecast, but do not migrate solely because of that warning.
- Forecast egress reaches 70%: run the Supabase-versus-R2 delivery benchmark
  and estimate the complete migration/operation cost.
- Forecast egress repeatedly exceeds 80%, or staging proves an upload
  reliability problem: make the R2 migration decision before hitting the
  quota. A small overage such as 300 GB total costs only about `$4.50`, so
  crossing 250 GB once is not by itself an economic reason to migrate.
- Orphan audio survives longer than the approved cleanup window.
- Product demand justifies podcast RSS, uploads, or sources longer than two
  hours.
- A provider benchmark shows material timestamp, quality, latency, or total
  cost improvement.

## References

- [yt-dlp options and behavior](https://github.com/yt-dlp/yt-dlp/blob/master/README.md)
- [YouTube Captions download authorization](https://developers.google.com/youtube/v3/docs/captions/download)
- [YouTube API Services developer policies](https://developers.google.com/youtube/terms/developer-policies)
- [Groq speech-to-text file limits](https://console.groq.com/docs/speech-to-text)
- [Supabase standard uploads](https://supabase.com/docs/guides/storage/uploads/standard-uploads)
- [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/)
- [Cloudflare R2 presigned URLs](https://developers.cloudflare.com/r2/api/s3/presigned-urls/)
- [Cloudflare R2 object lifecycles](https://developers.cloudflare.com/r2/buckets/object-lifecycles/)
- [Cloudflare Worker limits](https://developers.cloudflare.com/workers/platform/limits/)
