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
| Summary | Transcript ID + `briefing-v6-evidence-links` + `deepseek/deepseek-v4-flash-0731` | Summary is `ready` and contains non-empty Markdown | `summaries` |
| PDF | Summary ID plus `PDF_CACHE_VERSION = 3` | Object key and stored version are current | `summaries` + private `fathom` bucket |

The prompt key and model names are part of the cache contract. If the prompt,
model, transcript format, or renderer security version changes, use a new key
or version so old output is not silently presented as new output.

Example: changing only the OpenRouter prompt from `briefing-v6-evidence-links`
to `briefing-v7-evidence-links` creates a new summary identity for the same
transcript. Changing the renderer increments the PDF cache version; a ready
summary remains valid, but its old PDF is treated as stale and regenerated.

Ready summaries are globally reusable processing results, but a new user still
gets a new `jobs` row and a new usage settlement. Authenticated browser clients
have no `SELECT` grant on `summaries`. The API first proves access through the
caller's successful or archived `jobs` row, then its server-only client reads
the shared summary. Cache reuse therefore does not share account history or
bypass billing.

### Concrete two-user example

Assume Ana and Bruno submit the same public video under the same transcript,
prompt, and model contract. These are fake but structurally realistic IDs:

| Person or record | Example ID |
| --- | --- |
| Ana | `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa` |
| Bruno | `bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb` |
| Charlie | `cccccccc-cccc-4ccc-8ccc-cccccccccccc` |
| Shared transcript | `11111111-1111-4111-8111-111111111111` |
| Shared summary | `22222222-2222-4222-8222-222222222222` |
| Ana's job | `aaaa1111-1111-4111-8111-111111111111` |
| Bruno's job | `bbbb2222-2222-4222-8222-222222222222` |

The reusable transcript row is shared processing data. Long text is shortened
only to keep the example readable:

| `transcripts` column | Example value | Meaning |
| --- | --- | --- |
| `id` | `11111111-1111-4111-8111-111111111111` | Shared transcript identity |
| `url_hash` | `sha256-of-canonical-video-url` | Stable source lookup value |
| `video_id` | `video-42` | YouTube video identity |
| `transcript_text` | `Welcome to the episode...` | Reusable provider output |
| `provider_model` | `groq:whisper-large-v3-turbo:segments-v1` | Transcript cache contract |
| `source_keywords` | `{Talven,caching}` | Source metadata used by generation |
| `created_at` | `2026-08-03T09:00:00Z` | Creation time |
| `ttl_expires_at` | `NULL` | No active time-based expiry |

The one shared summary row contains both reusable content and internal
coordination fields. This lists every current `summaries` column so the privacy
boundary is explicit:

| `summaries` column | Example value | Browser needs it? |
| --- | --- | --- |
| `id` | `22222222-2222-4222-8222-222222222222` | Returned as `briefing_id` |
| `transcript_id` | `11111111-1111-4111-8111-111111111111` | No |
| `prompt_key` | `briefing-v6-evidence-links` | No |
| `summary_model` | `deepseek/deepseek-v4-flash-0731` | No |
| `summary_markdown` | `# Key ideas\n...` | Returned as `markdown` |
| `pdf_object_key` | `briefings/22222222-2222-4222-8222-222222222222/v3/33333333-3333-4333-8333-333333333333.pdf` | No; API returns a short-lived signed URL instead |
| `created_at` | `2026-08-03T09:02:00Z` | No |
| `ttl_expires_at` | `NULL` | No |
| `user_id` | `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa` | No; historical producer metadata from Ana |
| `status` | `ready` | No; API validates it server-side |
| `status_updated_at` | `2026-08-03T09:04:00Z` | No |
| `ready_at` | `2026-08-03T09:04:00Z` | No |
| `failed_at` | `NULL` | No |
| `generation_job_id` | `aaaa1111-1111-4111-8111-111111111111` | No; points to Ana's producing job |
| `generation_token` | `NULL` | No; a completed generation has released its fence |
| `pdf_cache_version` | `3` | No |
| `pdf_generation_token` | `NULL` | No; PDF rendering is complete |
| `pdf_generation_cache_version` | `NULL` | No |
| `pdf_generation_expires_at` | `NULL` | No |

Ana and Bruno have separate private job rows even though both rows point to the
same summary:

| `jobs` column | Ana's row | Bruno's row |
| --- | --- | --- |
| `id` | `aaaa1111-1111-4111-8111-111111111111` | `bbbb2222-2222-4222-8222-222222222222` |
| `user_id` | `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa` | `bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb` |
| `source_key` | `youtube:video-42` | `youtube:video-42` |
| `status` | `succeeded` | `succeeded` |
| `summary_id` | `22222222-2222-4222-8222-222222222222` | `22222222-2222-4222-8222-222222222222` |
| `duration_seconds` | `3600` | `3600` |
| `stage` | `completed` | `completed` |
| `progress` | `100` | `100` |

Their billing evidence is separate too:

| `usage_settlements` column | Ana's row | Bruno's row |
| --- | --- | --- |
| `job_id` | `aaaa1111-1111-4111-8111-111111111111` | `bbbb2222-2222-4222-8222-222222222222` |
| `user_id` | `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa` | `bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb` |
| `duration_seconds` | `3600` | `3600` |
| `subscription_seconds` | `3600` | `3600` |
| `pack_seconds` | `0` | `0` |
| `debt_incurred_seconds` | `0` | `0` |

The result is one Groq transcript and one OpenRouter summary, but two private
access records and two usage settlements. Global cache reuse saves provider
work; it does not merge the users' accounts, libraries, or billing histories.

The important authorization sequence for
`GET /briefings/22222222-2222-4222-8222-222222222222` is:

1. Bruno's bearer token queries `jobs` through RLS for a settled row whose
   `user_id = bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb` and
   `summary_id = 22222222-2222-4222-8222-222222222222`. It finds job
   `bbbb2222-2222-4222-8222-222222222222`.
2. Only after that proof succeeds, the backend service client reads summary
   `22222222-2222-4222-8222-222222222222` and returns the documented briefing
   response: `briefing_id`, `markdown`, and an optional short-lived `pdf_url`.
3. Those response fields do not include `user_id`, `generation_job_id`,
   transcript/model keys, PDF object keys, generation tokens, or lifecycle
   timestamps.
4. Charlie, who has no matching job, receives `404 Briefing not found`. The
   backend never reads the summary for Charlie's request.

Before migration `20260803120000_server_mediate_shared_summary_reads.sql`, an
authenticated user with a settled job could query the shared `summaries` row
directly. That correctly hid the row from unrelated users, but `SELECT *`
also revealed internal columns such as the historical `user_id`,
`generation_job_id`, `pdf_object_key`, `pdf_generation_token`, and lifecycle
timestamps. With a shared row, Bruno could therefore see metadata originating
from Ana's production of the cache entry. The new boundary revokes browser
`SELECT` completely. The browser receives only API response fields; internal
cache and PDF coordination columns stay server-only.

In concrete terms, Bruno could previously run a direct browser-client query
equivalent to:

```sql
select id, user_id, generation_job_id, pdf_object_key, pdf_generation_token
from summaries
where id = '22222222-2222-4222-8222-222222222222';
```

RLS allowed that one shared row because Bruno owned a successful job pointing
to it. It did not leak Ana's job row or billing row, but it did return Ana's
historical producer ID and server-only summary/PDF coordination metadata.
After the fix, the authenticated database role has no table-level `SELECT`
permission, so Postgres rejects the browser query with `permission denied for
table summaries` before any row policy can expose columns. Bruno's normal
Talven page still works because FastAPI performs the owned-job check and returns
only the three public response fields.

The PDF object key is also tenant-neutral. It contains the summary ID, renderer
version, and random generation token—not a user's ID or the source video ID.
Changing this path increments `PDF_CACHE_VERSION`, so old paths are regenerated
and cleaned up without invalidating the ready summary.

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
the initial release. The database has TTL-shaped columns from earlier design, but
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
