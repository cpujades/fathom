# Cache and versioning

Talven has several caches. They solve different problems and must not be
confused with authorization. A cache hit saves work or improves responsiveness;
the user bearer token, API ownership checks, and RLS still decide whether data
may be read.

## Processing cache: reusable work, private access

The server normalizes a submitted source before looking for work:

| Layer | Identity/key | Reusable when | Stored in |
| --- | --- | --- | --- |
| Source/job | `youtube:<video_id>` for YouTube; `url:<sha256(canonical_url)>` for the generic source model | Same normalized source and user/job rules | `jobs.source_key` |
| Transcript | Video ID or canonical URL hash plus `groq:whisper-large-v3-turbo:segments-v1` | Same source and transcript provider contract, with non-empty timestamp segments | `transcripts` + `transcript_segments` |
| Summary | Transcript ID + `briefing-v6-evidence-links` + `x-ai/grok-4.3` | Summary is `ready` and contains non-empty Markdown | `summaries` |
| PDF | Summary ID plus `PDF_CACHE_VERSION = 2` | Object key and stored version are current | `summaries` + private `fathom` bucket |

The prompt key and model names are part of the cache contract. If the prompt,
model, transcript format, or renderer security version changes, use a new key
or version so old output is not silently presented as new output.

Example: changing only the OpenRouter prompt from `briefing-v6-evidence-links`
to `briefing-v7-evidence-links` creates a new summary identity for the same
transcript. Changing the renderer increments the PDF cache version; a ready
summary remains valid, but its old PDF is treated as stale and regenerated.

Ready summaries are globally reusable processing results, but a new user still
gets a new `jobs` row and a new usage settlement. The summary becomes readable
only through that user’s successful or archived job. Cache reuse therefore does
not share account history or bypass billing.

## What is cacheable

- `pending` summaries have one fenced producer and are not readable or
  cacheable.
- `ready` summaries must be non-empty and have passed evidence validation.
- `failed` summaries are never reused; a later valid job may take over the
  stable summary identity.
- Transcript rows without timestamp segments are not accepted for the current
  evidence-backed summary path.
- A PDF is reused only when its object key and cache version match the current
  renderer version.

There is no time-based expiration policy for ready transcript/summary work in
the current pilot. The database has TTL-shaped columns from earlier design, but
the active product decision is contract-versioned reuse. Retention, freshness,
removed-source behavior, and cache deletion remain deferred decisions.

## Browser cache: fast, account-scoped, and disposable

`apps/web/app/lib/appDataCache.ts` keeps short-lived in-memory values for the
briefing library, billing snapshot, session snapshots, and usage. The library,
billing, and session values use a 30-second freshness window; persisted usage
snapshots are accepted on session startup only while they are under the same
30-second age. In-flight requests are deduplicated within the current
authenticated scope.

The scope is `(user_id, generation)`. A generation changes on sign-in,
sign-out, or account switching. A response that started under an old scope is
discarded, and in-memory caches are cleared. Usage snapshots may be shared
between tabs through a user-specific `BroadcastChannel` and `localStorage`
key, but the access token is never stored there.

The library’s default query can be cached; filtered or paginated requests are
loaded from the API. Creating or archiving a briefing invalidates the library
cache and signals other tabs. A backend `401` or `403` clears the session and
returns to sign-in.

This browser cache is an optimization. It may be stale for up to the short TTL,
and a successful API response remains the authority. Never use a browser cache
check as permission to expose another user’s data.

## Cache decisions when changing code

When changing processing behavior, answer these questions in the same review:

1. Does the source identity change, or only the provider contract?
2. Should the transcript provider key, prompt key, summary model, or PDF cache
   version change?
3. Can an old row still be safely read, or must it be marked stale/failed?
4. Does the user’s `jobs`/billing behavior remain separate from shared work?
5. Which migration, cache test, quality fixture, and documentation example
   proves the decision?

The planned global `source_work` producer is intentionally not present yet. It
would reduce duplicate first-time transcription across users, but it would also
need cross-tenant retention, failure propagation, takeover, fairness, and
privacy rules. See [deferred work](../decisions/deferred-work.md).
