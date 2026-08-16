# Processing and providers

**Status:** Current pipeline plus launch decisions that still need real
evidence.

**Read this to understand:** how Talven turns a source into a briefing, why the
current providers were chosen, and what would justify a change.

## Contents

- [Current provider map](#current-provider-map)
- [Processing pipeline](#processing-pipeline)
- [Retry model](#retry-model)
- [Quality contract](#quality-contract)
- [Provider launch decisions](#provider-launch-decisions)
- [Changes that should wait](#changes-that-should-wait)
- [Evidence record](#evidence-record)

## Current provider map

| Need | Current choice | Authority |
| --- | --- | --- |
| Source acquisition | `pytubefix` in a killable Python subprocess | Talven worker |
| Temporary audio | Private Supabase Storage object | Talven service role |
| Transcription | Groq, `whisper-large-v3-turbo` | Groq API |
| Briefing generation | OpenRouter through the OpenAI Python SDK | OpenRouter API |
| Summary model | `deepseek/deepseek-v4-flash-0731` | OpenRouter request |
| Authentication | Supabase Auth | Supabase |
| Database and durable queue | Supabase Postgres | Supabase migrations |
| PDF rendering | Isolated WeasyPrint subprocess | Talven API |
| Billing | Polar | Polar plus Talven's local ledger |

These are current implementation choices. They are not permanent commitments.
The paid launch requires a fresh real-provider rehearsal and an explicit
keep/change decision.

## Processing pipeline

### 1. Source admission

The API normalizes a supported YouTube URL and asks the isolated YouTube worker
for metadata. The source must:

- be a supported public YouTube video;
- have a known positive duration;
- be no longer than 7,200 seconds; and
- fit the user's current spendable time after other unsettled work.

One user can have up to three billable jobs in progress. Admission and
settlement lock the same user billing boundary. The unsettled durations of
simultaneous requests cannot commit more source time than the current balance.

Metadata has a 30-second deadline.

### 2. Download

The worker selects the smallest audio-only stream by advertised or estimated
file size. Audio bitrate breaks a size tie. It does not download the highest
quality stream by default.

Current bounds:

| Boundary | Value |
| --- | ---: |
| Audio size | 100,000,000 bytes |
| Complete source-download deadline | 300 seconds |
| Worker response envelope | 64,000 bytes |

The downloader runs in a separate process so timeout or cancellation can kill
the work without leaving the API or main worker process stuck.

The 100 MB limit is checked before download when stream metadata provides a
size, during download, and after download. An oversized source is a permanent
input error: Talven does not retry it and does not charge video time.

### 3. Temporary delivery

The worker uploads the audio to the private `fathom_groq` bucket and creates a
short-lived URL for Groq. It deletes the object after transcription.

The browser never gets direct bucket access. Immediate deletion has bounded
retry, but a hosted launch still needs an orphan cleanup schedule and alert.

### 4. Transcription

Groq must return:

- non-empty text;
- non-empty timestamped segments;
- valid numeric start and end times;
- ordered segments; and
- non-empty segment text.

The transcription request has a 120-second attempt timeout and up to three
classified attempts. Rate limits, timeouts, connection failures, and selected
provider 5xx responses are retryable. Rejected requests and permanent response
errors fail explicitly.

The transcript cache identity is:

    source + groq:whisper-large-v3-turbo:segments-v1

Changing provider, model, or segment contract must create a new identity.

### 5. Briefing generation

OpenRouter receives a JSON envelope of timestamped transcript segments.
Transcript text is untrusted source data and cannot replace the system
instructions.

The current contract uses:

| Item | Value |
| --- | --- |
| Prompt key | `briefing-v6-evidence-links` |
| Model | `deepseek/deepseek-v4-flash-0731` |
| Temperature | 0 |
| Response | Strict JSON schema |
| Attempt timeout | 300 seconds |
| Attempts | Up to three |

Talven validates the structured response and every evidence reference. It then
renders Markdown itself. Invalid or unsupported evidence causes failure rather
than an uncited fallback.

The summary cache identity is:

    transcript + prompt key + summary model

### 6. PDF

The API converts the ready Markdown through a restricted subprocess. It denies
external resource fetching, bounds input, output, deadline, and concurrency,
and caches by briefing and PDF renderer version.

PDF generation is an export path. It does not change the saved briefing.

## Retry model

There are two retry layers:

1. A provider operation can retry a bounded transient failure.
2. A durable job can retry a failed worker attempt.

Retries never create a second user job or a second settlement. An expired
worker lease cannot publish over a newer worker.

Deterministic input failures, including audio above 100 MB, are not retried.

The launch rehearsal must measure the combined time and cost of both layers.
Local timeout constants are safety bounds, not proof that users will accept
the wait.

## Quality contract

A release candidate must prove:

- the briefing is useful, not only structurally valid;
- citations refer to correct transcript segments;
- timestamp links open the intended source moments;
- the model abstains when evidence is missing;
- transcript prompt injection does not change system behavior;
- Spanish and English sources work;
- short and near-limit sources work;
- cost and latency are recorded; and
- failure copy is understandable.

Deterministic tests protect the schema and evidence rules. A capped paid
provider evaluation and human review protect usefulness.

Run the paid evaluation when:

- the transcript provider or model changes;
- the summary provider or model changes;
- the prompt key or structured contract changes;
- long-source processing changes; or
- a release candidate depends on new provider behavior.

## Provider launch decisions

### Groq

Current position: keep for the first staging rehearsal.

Before accepting it for public launch, measure:

- transcription accuracy and timestamps;
- latency by source length;
- rate-limit and retry behavior;
- audio size and duration limits;
- cost per source hour;
- data retention and training settings;
- regional and privacy requirements; and
- support and incident response.

Change only if measured quality, reliability, privacy, limits, or total cost
fails the launch target.

### OpenRouter and the summary model

Current position: keep the integration boundary and test the current model.

Measure:

- briefing usefulness;
- citation precision;
- refusals and invalid structured responses;
- input and output tokens;
- p50 and p95 latency;
- retry cost;
- model availability and version stability;
- provider routing and data policy; and
- cost per completed briefing.

The OpenRouter boundary makes model comparison easier. A model change still
requires a new cache identity and the complete evaluation set.

### Supabase Storage versus another object store

Current position: keep private Supabase Storage for temporary audio and PDFs.

Evaluate Cloudflare R2 or another store only when measured egress, reliability,
recovery, or Supabase limits become material. Temporary audio and PDFs have
different access and retention needs, so evaluate them separately.

### `pytubefix` versus `yt-dlp`

Current position: keep `pytubefix`.

Reconsider when extraction failures become material, maintenance stalls, or a
representative staging comparison proves another adapter more reliable.
Preserve the subprocess, bounds, metadata contract, cleanup, and rollback path.

## Changes that should wait

| Change | Trigger |
| --- | --- |
| Sources longer than two hours | Repeated target-user need plus chunked provider proof |
| Podcast RSS | Demand for publisher feeds plus safe URL and lifecycle design |
| Direct audio upload | Demand plus abuse, ownership, privacy, and cleanup rules |
| Shared producer before transcription | Measurable duplicate provider cost |
| Vector database | Multi-episode or large-library retrieval |
| Redis or another queue | Measured Postgres notification, cache, rate-limit, or claim bottleneck |
| Dedicated export worker | Measured PDF CPU, memory, queue, or isolation problem |

User count alone is not a trigger. Measure the failing resource or product
need.

## Evidence record

For each provider rehearsal, keep:

- release tag and configuration;
- source set and language;
- source duration and bytes;
- provider/model;
- attempts and error type;
- stage and total latency;
- provider usage and cost;
- cache hit or cold path;
- quality result;
- privacy/retention settings checked; and
- decision: keep, tune, replace, or defer.

Provider prices and limits can change. Recheck official provider information
when the decision is made instead of preserving old prices as permanent facts.

## Next read

[Billing and money](./04-billing-and-money.md)
