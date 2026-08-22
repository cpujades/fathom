# Performance reference

**Status:** Current performance design and measured-risk register.

**Read this to understand:** current query paths, indexes, hydration, browser
caches, pagination choices, and the evidence required before adding more
infrastructure.

## Contents

- [Current conclusion](#current-conclusion)
- [Request map](#request-map)
- [Query and index assessment](#query-and-index-assessment)
- [Pagination decision](#pagination-decision)
- [Current browser and server caches](#current-browser-and-server-caches)
- [Hydration and frontend behavior](#hydration-and-frontend-behavior)
- [Search design](#search-design)
- [Improvement order](#improvement-order)
- [Measurement and targets](#measurement-and-targets)

## Current conclusion

The current design is suitable for the invite-only beta:

- list pagination is server-side;
- page sizes are bounded;
- related records are loaded in batches, without per-row requests;
- query-driven indexes support the main ordering and ownership filters;
- private browser caches are short, account-scoped, and invalidated after
  changes; and
- public pages do not cache private save state.

The first scale risk is private-library text search. It scans database pages,
hydrates them, and filters in Python. The first useful public cache is a short
Explore response cache. Neither change needs to block a small beta.

## Request map

| Surface | Current reads | Page behavior | Main concern |
| --- | --- | --- | --- |
| Private library | Jobs page, then batched summaries and transcripts | Offset, default 24, exact count | Filtered search scans in batches of 200 |
| Usage history | Settlement page, then jobs, summaries, and transcripts | Offset, 10, `limit + 1` | Four sequential database reads per page |
| Billing page | Plans, usage, account, and first history page in parallel | First ten history rows | Optional history failure stays inside its section |
| Explore | Publication page, jobs and summaries in parallel, then transcripts | Offset, web page requests up to 48, exact count | Public result is rebuilt on each request |
| Public briefing | Publication, job and summary, then transcript | One item | Deliberate `no-store` protects visibility freshness |
| Explore save state | One batch request for all visible slugs | Up to the visible page | Kept separate from public content |

These are bounded multi-query hydration paths. They are not N+1 query loops.
Combine them into SQL functions or views only after request tracing shows that
network round trips are material.

## Query and index assessment

The hardening migration adds these main indexes:

| Query | Index | Assessment |
| --- | --- | --- |
| Private library | `jobs_briefing_library_idx` | Matches user, active statuses, created time, and ID order |
| Saved compatible work | `jobs_user_summary_access_idx` | Matches owner and summary lookup for reusable jobs |
| Parallel job admission | `jobs_one_active_source_per_user_idx` plus the settlement primary key | Bounds the user-scoped active-job and unsettled-duration check |
| Usage history | `usage_settlements_user_settled_idx` | Matches user, settlement time, and stable job-ID order |
| Explore by topic | `briefing_publications_explore_idx` | Matches public state, topic, listing time, and ID |
| Explore all | `briefing_publications_explore_all_idx` | Matches public state, listing time, and ID |
| Billing history | `billing_orders_user_id_idx` | Matches owner and newest-order reads |
| Pending refunds | `billing_orders_refund_pending_idx` | Restricts recovery scans to pending user orders |

A local rollback-only benchmark used 5,000 library jobs and settlements plus
2,000 public entries. PostgreSQL used the intended indexes. First-page reads
were below 0.03 ms in the database plan. Offsets near 4,000 were still below
0.6 ms, but PostgreSQL scanned about 4,000 earlier index rows. These figures
measure local database execution only. They do not include PostgREST, network,
serialization, or application hydration.

Do not add indexes for every foreign key or column. Add one when a real query,
deletion path, or constraint check needs it. Each index adds storage and write
cost.

## Pagination decision

### Current choice: offset

Offset pagination is appropriate now because:

- the UI uses simple numbered positions or Load more;
- page sizes are small;
- expected launch histories and libraries are small;
- the API contract is easy to inspect; and
- the current indexes make low offsets cheap.

Its two limits are important:

1. the database still walks past earlier rows, so deep-page cost grows with the
   offset; and
2. a new row inserted before the next offset can shift rows, causing a repeat
   or omission.

### Cursor migration trigger

Move one endpoint to cursor pagination when any of these is measured:

- p95 list latency exceeds the accepted target because of deep offsets;
- users regularly reach thousands of rows;
- inserts during paging cause visible repeats or omissions;
- exact counts are slow and the UI does not need them; or
- database plans show large skipped-row work.

Use the full stable sort key in the cursor:

| Surface | Cursor fields |
| --- | --- |
| Library | `created_at`, `id` |
| Usage history | `settled_at`, `job_id` |
| Explore | `listed_at`, `id` |

The next-page predicate for descending order is conceptually:

    sort_time < cursor.sort_time
      OR (sort_time = cursor.sort_time AND id < cursor.id)

Make cursors opaque at the HTTP boundary. Keep the current offset contract
until one surface reaches its trigger. The endpoints do not need to migrate
together.

### Exact counts

The library and Explore request exact totals. Usage history requests one extra
row and returns `has_more`.

Prefer `limit + 1` when the interface needs only Load more. Keep an exact count
only when the number has clear product value. This removes a count query from
the critical path as data grows.

## Current browser and server caches

| Data | Current cache | Decision |
| --- | --- | --- |
| Private library default page | In-memory, account-scoped, 30 seconds | Keep for beta |
| Billing snapshot | In-memory, account-scoped, 30 seconds | Keep; optional history failure is isolated |
| Cross-tab private changes | `localStorage` invalidation signal | Keep; it stores no private result payload |
| Explore public content | No cross-request cache | Add 30–60 seconds before broad marketing if traffic warrants it |
| Explore save state | No public cache; authenticated batch read | Keep separate from public content |
| Public briefing | Dynamic and `no-store` | Keep until unpublish freshness is explicit |
| Transcript and summary | Permanent versioned database cache | Keep; authorization still uses user-owned jobs |
| PDF | Versioned object cache | Keep |

An Explore cache key must include environment, topic, limit, offset, and a
response-contract version. Invalidate it after publication, unpublication,
moderation, or topic changes, or use a short TTL that meets the promised
freshness.

Do not cache authenticated responses by URL alone. Include the user identity
or keep the data inside an account-scoped client cache. Clear it on sign-out
and account change.

## Hydration and frontend behavior

- Explore and public briefing content render on the server. Authentication and
  save controls hydrate in the browser.
- Explore loads save state for visible slugs in one request.
- The private library waits 300 ms after the latest search input before it
  requests results. This reduces requests while a user types.
- The Explore grid is one client component with a current maximum of 48 cards.
  Split or virtualize it only after browser metrics show a problem.
- Authenticated application pages load through the browser because they use the
  Supabase session. The short client cache avoids immediate repeat requests.

The debounce reduces request frequency. The durable scale fix is database-side
normalized search or full-text search with a matching index. Keep authorization
and stable ordering inside that query.

## Search design

**Current:** private-library search loads database pages in bounded batches and
filters hydrated title, author, source URL, and source host values in Python. It
is correct for a small beta but does not scale with a large library.

**Proposed trigger:** move search into Postgres when a representative hosted
test reaches either condition:

- private-library search p95 exceeds 500 ms; or
- a typical active user has more than 500 searchable briefings.

The first database design should use:

1. a maintained per-user search projection with `user_id`, `job_id`, stable
   ordering fields, and a stored `tsvector`;
2. a GIN index on that vector plus a B-tree index for owner and result order;
3. `websearch_to_tsquery` for familiar user syntax;
4. the owner predicate inside the database query; and
5. a forward migration, RLS tests, ranking tests, and `EXPLAIN (ANALYZE,
   BUFFERS)` evidence.

A generated `tsvector` on one table cannot directly include text from joined
`jobs`, `summaries`, and `transcripts`. Use a projection maintained by the
write path or a protected function over deliberately denormalized text. Do not
add separate GIN indexes to every source table without a measured query plan.

PostgreSQL documents GIN as the preferred text-search index. See
[text-search types](https://www.postgresql.org/docs/current/datatype-textsearch.html),
[`websearch_to_tsquery`](https://www.postgresql.org/docs/current/functions-textsearch.html),
and [preferred indexes](https://www.postgresql.org/docs/current/textsearch-indexes.html).

## Improvement order

### Before invite-only beta

1. Run authenticated browser proof for library, usage history, Explore save,
   publication, archive, and account switching.
2. Measure complete API response time, database time, and frontend loading on
   the hosted candidate.

### Before broad marketing

1. Add a short public Explore cache if traffic or traces justify it.
2. Remove Explore exact count if the UI still shows only the first page.
3. Add an Explore next-page control when the catalogue exceeds 48 useful
   entries.
4. Move private search into Postgres when library size or p95 latency reaches
   the trigger.

### After measured scale

- Replace offset with a surface-specific cursor.
- Combine hydration reads with a protected SQL function when database network
  latency is material.
- Reuse a backend Supabase transport across requests only after connection and
  TLS setup appears in traces. Never share mutable user bearer state.
- Add Redis or an external queue only at the triggers in
  [Roadmap](../08-roadmap.md).

## Measurement and targets

Measure before optimizing. Use these launch dashboards:

| Area | Minimum signals |
| --- | --- |
| Browser | LCP, INP, CLS, route-load time, JavaScript errors, failed API calls |
| API | Request rate, p50/p95/p99 duration, error rate, response bytes by bounded route/status/environment/release labels |
| Worker | Queue depth, oldest queued age, claim delay, duration and failure by stage/provider, retries, exhausted jobs |
| Database | Query duration, rows scanned, slow queries, active connections, pool pressure, lock waits |
| Cache | Hit, miss, age, invalidation reason, and origin duration |
| Billing | Webhook age/failures, reconciliation backlog, settlement failures, refund recovery |
| Product | Signup-to-first-ready, completion rate, publish/save adoption, paid conversion, D7/D30 retention |

The first six areas belong in operational telemetry. Product funnels can use a
product analytics system or a privacy-safe warehouse instead of metric labels.

Initial targets for the staged launch candidate:

| Signal | Target | Status |
| --- | ---: | --- |
| LCP | At most 2.5 s at p75 | Web Vitals standard |
| INP | At most 200 ms at p75 | Web Vitals standard |
| CLS | At most 0.1 at p75 | Web Vitals standard |
| Interactive API latency, excluding long provider work | p95 at most 500 ms | Proposed Talven launch target |
| Interactive database work | p95 at most 100 ms | Proposed Talven launch target |
| Core interactive API error rate | Below 1% | Proposed Talven launch target |
| Queue start with an awake worker | p95 at most 5 s | Proposed Talven launch target |
| First SSE progress event after connection | p95 at most 2 s | Proposed Talven launch target |
| Supported-source completion rate | At least 95%, with failure causes separated | Proposed Talven launch target |

The Core Web Vitals thresholds come from
[web.dev](https://web.dev/articles/vitals) and should be evaluated at the 75th
percentile, separated by mobile and desktop. The Talven targets are starting
guardrails. Replace them only after staging and beta evidence gives a better
baseline.

Measure the complete user journey, and also record:

- PostgREST request count per route;
- list depth and search use;
- cache origin latency; and
- provider time and Talven overhead separately.

Use `EXPLAIN (ANALYZE, BUFFERS)` with representative data in a local or
dedicated staging database. Never run an unbounded experimental plan against
production. Compare the complete request before and after a change; a faster
single SQL statement can still produce a slower user journey.

The proposed telemetry stack and privacy rules are in
[Deployment and operations](../06-deployment-and-operations.md#observability-decision).

The architecture boundary is in [Architecture](../02-architecture.md). Launch
measurement and operations are in
[Deployment and operations](../06-deployment-and-operations.md).

## Next read

Owner path: [Deployment and operations](../06-deployment-and-operations.md).
Developer path: [Development](../05-development.md).
