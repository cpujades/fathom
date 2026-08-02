# Briefing product behavior

This page describes what Talven does today, including duplicate requests,
caching, charging, failures, archive/restore, and intentionally deferred
features.

For the shorter user-facing walkthrough, start with
[Product and user workflows](./user-workflows.md). This page is the deeper
behavior and trade-off reference behind that walkthrough.

## Supported input and output

Talven currently accepts public YouTube URLs. Product copy no longer promises
that the source must be a podcast, because the code accepts other long-form
YouTube videos as well.

A successful evidence-backed briefing contains a validated structure, then a
deterministic Markdown renderer adds important timestamp ranges. Each displayed
timestamp links to the matching moment on YouTube. The link formatting itself
does not call an AI provider and adds negligible latency.

The same ready briefing can be read in the app, downloaded as Markdown, or
exported through the bounded PDF subprocess path.

If timestamped transcript segments are missing or empty, Talven fails the
attempt and retries transcription. It never falls back to publishing an
uncited plain-Markdown briefing.

## Create, join, reuse, and restore

The words below describe the API's resolution, not different products:

| Situation | Resolution | What the user sees | Charge |
| --- | --- | --- | --- |
| This user has no matching session | `new` | A new queued job | Once, after successful finalization |
| This user submits the same video while their job is active | `joined_existing` | The same session and progress | No second charge |
| This user submits the same video after their briefing is ready | `reused_ready` | The existing ready session | No second charge |
| This user submits a source whose session they archived | `reused_ready` plus restore | The archived session returns to the library | No regeneration and no second charge |
| Another user submits a source with an already ready global cache | New user-owned session from cache | Fast finalization using the ready work | That user is charged once |

For one user, two matching requests converge to one job. “Joined existing”
means both browser requests point to the same job ID, progress, result, and
settlement. “Reused ready” is that user's cache hit: Talven returns work they
already paid for.

Archive is a library state, not deletion of the shared source work. Restoring
changes the user's job from archived back to successful and reuses the same
summary.

Talven does not currently expose permanent briefing or account-data erasure to
the user. That is a separate privacy and retention decision because shared
derived work and billing/audit records cannot all follow the same deletion
rule.

## Two different users submitting at the same moment

Current behavior is safe but not maximally efficient:

- each user gets a separate tenant-owned job and each successful job settles
  usage once;
- if user A's cache is already ready when user B submits, B skips provider
  generation and completes quickly;
- if A and B submit before any transcript exists, both jobs can download and
  transcribe the audio;
- after both converge on the same persisted transcript, the summary-generation
  token permits only one active summary producer and the other job waits for
  it.

The database prevents corrupted duplicate rows, double settlement per job, and
two writers publishing the same summary. It does not yet provide a global
source-level producer/follower state before transcription, so simultaneous
first submissions can duplicate download/transcription cost.

The preferred later design is a tenant-neutral `source_work` record keyed by
video, transcription model, and processing version. User jobs would follow
that producer while retaining separate ownership and separate billing. It
needs explicit retention, failure propagation, takeover, privacy, and fairness
rules, so it should not be inserted as a quick pre-pilot change.

## Charging and debt

Talven performs two different checks:

1. **Admission:** before queuing, it reads the YouTube duration and estimates
   whether the user's current subscription and pack credits can cover the job.
   A known video duration must fit the current positive balance; Talven does
   not intentionally sell or advertise the debt allowance as extra usage.
2. **Settlement:** after a valid briefing exists, one transaction consumes
   subscription seconds first, then pack seconds, then records any uncovered
   remainder as debt.

The default debt threshold is 600 seconds. It is a finalization safety buffer,
not admission credit. It protects a completed briefing if two jobs passed the
same earlier balance snapshot or a refund removed credit after admission.
Reaching the threshold blocks later work until a renewal or purchase pays debt
down.

Talven rejects a source when it cannot determine a positive duration. A known
video longer than the current balance is rejected even when the separate debt
threshold remains unused.

There is no upfront reservation today. Two concurrent jobs can both pass the
admission snapshot before either settles. Settlement is still atomic and each
job is charged once, but aggregate debt can exceed the threshold in that race.
Upfront reservation was deliberately deferred because it changes visible
credit timing, cancellation/refund rules, and concurrency behavior.

`usage_settlements.job_id` is a unique, non-null foreign key to `jobs.id`. This
makes settlement one-to-one from the settlement side: an unfinished job may
have no settlement, but a job can never have two settlements. Retrying the
same settlement returns the existing result instead of charging again.

If settlement fails, the briefing remains hidden and the job returns to a
visible retryable `finalizing` state. A worker retries it; the user does not
need to submit or pay again.

## Summary states

- `pending`: one live producer owns generation. Another job waits rather than
  writing competing content.
- `ready`: non-empty, validated, cacheable, and eligible for finalization.
- `failed`: not cacheable. A later valid submission may atomically take over
  and regenerate it.

“A later valid submission” means an authenticated user submits the supported
source again, passes URL/duration/usage checks, and the server creates or claims
legitimate work. It does not mean any browser can directly flip the row or
force regeneration.

## Streaming and recovery

Evidence-backed output is validated in full before it becomes a ready result.
The frontend can still reveal that complete text progressively with a
controlled visual typing effect. This preserves the feeling of streaming
without exposing malformed JSON, ungrounded partial text, or content that may
later fail validation. Reduced-motion preferences show it immediately.

If the event stream disconnects, the browser reconnects using `Last-Event-ID`,
replays a bounded persisted history, and reconciles with an authoritative full
snapshot. Replay truncation skips directly to that snapshot rather than
pretending every intermediate event was delivered. Active streams use expiring
database leases: the defaults allow three per user and twelve per client IP,
renew while connected, and close after one hour so a client must reconnect.
If the job is
ready but Markdown delivery remains temporarily unavailable, the UI explains
that the briefing is safe and offers a retry that does not create or charge a
new job.

## Current input limits

The current pilot guard accepts videos up to two hours, and the downloader
rejects audio over 100 MB. The worker chooses the smallest available
audio-only YouTube stream.

Raising only the duration constant to 300 minutes would be misleading. A
five-hour source can exceed provider/file/deadline limits and would restart too
much expensive work after one late failure. Longer sources need chunking,
per-chunk retry, timestamp offsetting, ordered merge, and progress/cost tests.
See [Long-audio and transcription decision](../decisions/long-audio-and-transcription.md).

## Deliberately deferred

The full rationale, revisit triggers, and minimum safe future designs live in
the [deferred work register](../decisions/deferred-work.md).

- User cancellation of running jobs: requires clear charging and remote-call
  semantics; Redis is not required, but a durable cancellation state and
  provider-aware checkpoints are.
- Upfront usage reservation: deferred to avoid changing credit timing before
  the current settlement policy is product-reviewed.
- Global first-producer sharing before transcription: valuable but a material
  cross-tenant work-orchestration feature.
- A 300+ minute limit: deferred until chunking and long-source evaluation.
- Automatic content-suitability rejection: a cheap heuristic could wrongly
  reject useful lectures, interviews, or technical videos. Validate a labeled
  set before adding a gate.
- Podcast Q&A/chat: post-core-hardening and outside the first launch.
- Shared SSE wake-ups and event retention: active stream leases bound clients,
  but measure pilot query load before changing the one-second polling design.
