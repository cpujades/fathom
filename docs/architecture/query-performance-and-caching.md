# Performance, queries, and caching

**Status:** This is Talven's performance guide. It separates current behavior
from accepted follow-up work. A listed improvement is not implemented unless the
section says it is current.

This page covers the full Talven path: browser, Next.js, FastAPI, Supabase,
Railway, the worker, Groq, OpenRouter, Storage, SSE, and external services. Use
it to decide what to measure, what to change, and when to leave a provider.

The [operational metrics runbook](../runbooks/operational-metrics-and-provider-review.md)
defines dashboards, alerts, and review cadence. The
[cache and versioning guide](./cache-and-versioning.md) defines when processing
results are safe to reuse.

## Rules

1. Measure a real user path before and after a change.
2. Fix the slowest measured part first.
3. Keep access checks in the API and database. A cache is not authorization.
4. Bound every list, batch, retry, queue, upload, and concurrent operation.
5. Select only the fields needed for the response.
6. Prefer one simple improvement over several speculative systems.
7. Include cost, reliability, and owner time in each performance decision.
8. Keep a rollback path.

Do not add Redis, a new queue, table partitioning, search infrastructure, or a
new provider only because it may be useful later. Add it when measurements and
the trigger rules in this document support it.

## Critical user paths

Measure these paths separately because they have different limits:

| Path | Main latency sources | User result |
| --- | --- | --- |
| Landing, pricing, sign-in | Next.js, static assets, Supabase Auth | Page is usable and auth completes. |
| Open private library | Next.js, API, jobs, summaries, transcripts | First useful cards appear. |
| Search private library | API scan or database search | Matching cards appear. |
| Create briefing | source match, source metadata, usage checks, database | Existing work opens or a job is accepted. |
| Process cold source | download, temporary upload, Groq, OpenRouter, database | Ready briefing appears. |
| Follow active job | SSE, persisted events, snapshot recovery | Progress remains current after reconnects. |
| Read or save public briefing | public API, Markdown render, save RPC | Reader opens; save is immediate and free. |
| Explore | public API, database, images | Curated cards appear and filter correctly. |
| Checkout and portal | API, Polar, webhooks, database | Billing state becomes correct once. |
| PDF download | API, render queue, Storage, signed URL | Valid PDF downloads without duplicate work. |

Do not mix provider processing time with ordinary API latency. A 60-minute
source and a library read need different targets.

## Starting targets

These are initial targets for a production-like staging baseline. Replace them
with measured targets after the first representative week.

### Browser targets

Use the 75th percentile on mobile and desktop:

- Largest Contentful Paint: at most 2.5 seconds;
- Interaction to Next Paint: at most 200 milliseconds;
- Cumulative Layout Shift: at most 0.1;
- visible error-free completion for sign-in, create, save, archive, and billing;
- no large layout jump when auth or library state loads.

Measure public pages, authenticated pages, and slow mobile networks separately.
Lab tests help during development. Real-user measurements decide production
performance.

### API targets

- ordinary cached or database reads: p95 below 300 milliseconds;
- ordinary writes: p95 below 500 milliseconds;
- SSE event-to-browser delay: p95 below 1 second while connected;
- `5xx` and timeout rates close to zero under normal load;
- no unbounded response, scan, retry, or connection wait.

These targets exclude Groq, OpenRouter, Polar redirect time, PDF rendering, and
source downloads. Track each external stage separately.

### Worker targets

- oldest runnable-job age stays within the product promise;
- queue depth returns to its baseline after a traffic burst;
- no job is processed by two workers after a lease changes owner;
- retry and timeout rates stay near the measured provider baseline;
- transcription real-time factor and summary time remain stable by source size;
- temporary audio is deleted after success, failure, or cancellation.

## How to measure a change

For each material change, record:

1. route or workflow name and deployed revision;
2. production-like data size and request concurrency;
3. p50, p95, and p99 duration;
4. database time, provider time, and application time;
5. requests, rows, bytes, connections, CPU, and RAM used;
6. error, timeout, retry, and cache-hit rates;
7. cost per request, briefing, audio hour, or billing cycle when relevant;
8. the same measurements after the change; and
9. the rollback condition.

Use `EXPLAIN (ANALYZE, BUFFERS)` only on safe representative data. Do not run a
heavy analysis against production at peak traffic. A faster average is not
enough if the p95, error rate, memory use, or cost becomes worse.

## Frontend and perceived performance

### Current behavior

- Next.js owns public and authenticated pages.
- The private app has a short, account-scoped in-memory cache for its common
  library, billing, session, and usage reads.
- Account changes invalidate that private cache generation.
- Source images use `next/image` with bounded responsive sizes.
- Public briefing Markdown ignores raw HTML.
- Explore and public briefing pages are dynamic and use `no-store`.
- Explore currently renders at most 48 cards and has no next-page control.
- After sign-in, Explore loads saved state for all visible cards through one
  bounded endpoint instead of one request per card. Account changes clear that
  state before the next account is loaded.

### Improvement order

1. Measure Core Web Vitals for landing, pricing, library, reader, and Explore.
2. Keep server-rendered HTML useful before client auth checks finish.
3. Split large client components only when bundle analysis shows a material
   route cost.
4. Remove unused client JavaScript and avoid shipping server-only data.
5. Give images exact dimensions or a stable aspect ratio. Keep correct `sizes`.
6. Preload only the true Largest Contentful Paint image or font.
7. Avoid request waterfalls. Start independent reads together.
8. Keep loading, empty, error, and retry states stable to prevent layout shift.
9. Preserve keyboard, reduced-motion, and screen-reader behavior. A faster page
   that users cannot operate is not an improvement.

Do not add client-side state libraries only for performance. First use server
rendering, small local state, the existing account-scoped cache, and request
deduplication.

### Frontend checks

- route JavaScript and CSS bytes, including changes by release;
- server response time and hydration time;
- image bytes, image failures, and third-party image latency;
- React render count for streaming and frequently updated components;
- long browser tasks and memory growth during long SSE sessions;
- stale account data after sign-out or account switching;
- duplicate browser requests caused by effects or development Strict Mode;
- mobile layout and touch targets at the supported widths.

## Next.js, HTTP, and edge caching

Select cache policy by data class:

| Data | Shared cache? | Rule |
| --- | --- | --- |
| Static assets | Yes | Use hashed immutable files and compression. |
| Public Explore response | Yes, short | Key by normalized topic and page. Never include user state. |
| Public briefing content | Yes, after invalidation is defined | Key by stable slug. Purge or use a short TTL after unpublish. |
| Authenticated source match | No shared cache | It contains the current user's library state. |
| Private library, usage, billing | No shared cache | Keep cache account-scoped and short-lived. |
| Provider or payment webhooks | No | Process idempotently; never cache commands. |

Accepted first public cache:

- cache the Explore response for 30 to 60 seconds;
- key it by normalized topic, limit, offset, API contract, and deployment
  environment;
- record hit, miss, age, stale response, and origin error;
- start with TTL expiry;
- add explicit invalidation for list, unlist, block, or owner archive only if
  the short delay causes a product problem;
- prevent a cache stampede with request coalescing if traffic proves it is
  needed.

Never cache authorization decisions, bearer tokens, email addresses, user IDs,
or user-specific save state in a public key. Do not use `no-store` by habit or
cache by habit. State the freshness and invalidation rule for each route.

## FastAPI and application code

### Request design

- keep HTTP parsing in routers, business rules in application code, and provider
  I/O in services;
- use async I/O for database and network work;
- run independent calls together only when concurrency is bounded and failure
  behavior is clear;
- avoid sync libraries or CPU-heavy work on the event loop;
- return narrow response models rather than internal database rows;
- validate limits at the API boundary;
- use stable error codes so retries and user messages are deterministic;
- make commands idempotent when clients may retry them;
- apply an end-to-end deadline as well as provider-attempt timeouts.

### Connection reuse

Talven currently creates an owned Supabase HTTP client for each application
operation and closes it when the operation ends. This gives clear token and
transport ownership, but it reduces connection reuse between API requests.

Measure TLS/connection time and PostgREST latency before changing this boundary.
If it is material:

1. keep user authorization isolated;
2. reuse a bounded transport or server-only admin client through application
   lifespan;
3. do not mutate one shared client's authorization header per request;
4. close shared clients during shutdown; and
5. test account switching and concurrent users before release.

The direct Postgres pool used by API rate limiting is currently bounded from 1
to 10 connections. The worker also uses direct database connections for durable
notifications. Size all web, API, worker, migration, and provider-pool
connections together against the Supabase limit.

### Payload and serialization

- do not fetch transcript text or full summary Markdown for list cards;
- do not return internal provider, billing, or lifecycle fields;
- use compression for text responses at the deployment edge;
- keep JSON list items small and fetch full reader content on demand;
- record response bytes by route group;
- stream only when it improves time to useful content or memory use.

## Database query design

### Query checklist

Before adding or changing a query:

1. confirm its ownership and RLS boundary;
2. select only required columns;
3. bound the number of rows;
4. use stable ordering with a unique tie-breaker;
5. check filters, joins, and sort order against available indexes;
6. avoid one query per returned item;
7. decide whether an exact total count is required;
8. inspect the plan with representative row counts;
9. measure rows read versus rows returned;
10. add a test for empty, maximum-page, unauthorized, and concurrent cases.

An index should support a proven read, constraint, or maintenance task. Each
index adds storage, memory pressure, vacuum work, and write cost. Review unused,
overlapping, and duplicate indexes before adding more.

### Pagination and counts

Offset pagination is simple and correct for small pages. Its cost grows with a
large offset, and rows can shift between requests when new data arrives.

Use keyset pagination when large lists or high offsets become material. The
cursor should include the ordered timestamp and a unique ID. Keep offset
pagination where the list is small and the simpler contract is more valuable.

Exact counts can require extra database work. Keep them when the UI uses the
number. Use `has_more` from one extra row or an estimated count when a precise
total has no product value.

### RLS and security

RLS and API ownership checks are part of the query cost and the security
contract. Index columns used by ownership policies, foreign keys, and frequent
existence checks. Never move a private query to an anonymous browser client to
make it faster.

Use server-only views and SQL functions carefully:

- fix the function `search_path`;
- grant only the required role;
- keep the public result shape narrow;
- test RLS or `security_invoker` behavior explicitly;
- make security-definer commands validate caller-derived identifiers.

### Database health

Review these in Supabase and Grafana:

- database CPU, memory, I/O, and connection saturation;
- pool wait and timeout rate;
- slow and frequently executed queries;
- locks, deadlocks, long transactions, and idle transactions;
- table, index, and TOAST bytes;
- dead tuples, vacuum, analyze, and bloat;
- cache-hit ratio, while remembering that a high ratio does not prove a query
  is efficient;
- rows and byte growth by table.

Run `ANALYZE` through normal managed maintenance after large data changes. Do
not add manual vacuum jobs without evidence that managed maintenance is not
keeping up.

### Retention and partitioning

Apply retention to data whose product, support, accounting, and recovery value
has ended. Candidate high-volume data includes ordinary terminal `job_events`
and expired operational buckets. Never prune billing evidence, usage
settlements, unresolved webhooks, or active recovery data as a generic
performance action.

Partition a table only when it is large enough that measured query, vacuum,
retention, or index-management cost requires it. Time partitioning is most
suitable for large append-only event data. It adds migration, query, uniqueness,
retention, and operational complexity. It is not current launch work.

## Current Explore query

Explore uses four bounded PostgREST requests per page:

1. read one page of Listed publications;
2. read all related jobs in one batch;
3. read all related summaries in one batch;
4. read all related transcripts in one batch.

The job and summary requests run together. Request count does not grow with the
number of cards, so this is not an N+1 query. The API page limit is 100.

If measured latency or PostgREST volume becomes material, use one read model:

| Option | Good part | Trade-off |
| --- | --- | --- |
| Nested PostgREST select | Small code and schema change | Shape depends on detected foreign-key relationships. |
| Database view | Reusable projection | Grants and `security_invoker` behavior need tests. |
| SQL function/RPC | Exact stable server contract | Adds a versioned database function and migration. |

Preferred order:

1. add the short public Explore cache;
2. measure p95 latency, database time, response bytes, and request volume;
3. if needed, add one server-only SQL function as the read contract;
4. do not add all three read options.

Current scale limitations that need a product decision or a later change:

- the web page shows only the first 48 results;
- exact count runs for each Explore request;
- topic filtering uses one controlled topic value and an indexed exact match;
- public pages currently have no cross-request cache;
- authenticated saved-state checks use a separate bounded request and are not
  part of the public cache.

## Current private library query

Normal library reads paginate in the database. Filtered search reads bounded
batches of 200 rows and applies its multi-word match in Python. Reducing the
batch to 100 would reduce response size but increase requests. It would not fix
the scaling limit.

Move filtered search into Postgres when searches need several batches or become
a regular slow-query source.

Intended design:

- one server-only query or RPC joins the user's jobs to the required summary
  and transcript presentation fields;
- ownership, active/archive state, filters, ordering, and pagination run in the
  database;
- a normalized search document contains only approved searchable text;
- stable ordering uses a unique tie-breaker.

### `tsvector` and GIN in simple terms

A `tsvector` is a normalized list of searchable words from fields such as title,
author, topic, and approved briefing text. Postgres can apply stemming and
language rules, so a search is based on words rather than scanning every full
string.

A GIN index maps each word to the rows that contain it. Postgres can then find
matching rows without reading every briefing. This is useful for word search in
a growing library or Explore catalogue.

Full-text search does not preserve every partial-string behavior. For partial
titles, URL fragments, or typo-tolerant search, assess a `pg_trgm` GIN index.
Do not add both until the required search behavior and query plans justify them.

## Cache layers

Talven has several different cache types:

| Cache | Purpose | Main invalidation |
| --- | --- | --- |
| Browser app cache | Avoid repeat private reads | account generation, mutation, short TTL |
| Next.js/request deduplication | Avoid duplicate server reads in one render | request lifetime |
| Public response/CDN cache | Absorb repeated anonymous reads | short TTL or publication change |
| Transcript cache | Avoid repeat Groq work | provider/segment contract version |
| Summary cache | Avoid repeat OpenRouter work | prompt/model contract version |
| PDF cache | Avoid repeat rendering | renderer version and content change |

For every new cache, define:

- full key, including environment and contract version;
- private or shared scope;
- TTL and maximum size;
- invalidation and stale-data behavior;
- failure behavior when cache storage is unavailable;
- hit, miss, age, eviction, and error metrics;
- stampede protection if a miss is expensive.

Do not cache failed provider results as ready work. Do not let an old model or
prompt result look current after a contract change.

## Worker, queue, and concurrency

The current worker uses Postgres-backed jobs, durable events, leases, bounded
concurrency, and database notifications with reconciliation fallback. This is a
valid launch architecture.

Tune it in this order:

1. measure queue age, stage latency, provider limits, CPU, RAM, and connections;
2. remove unnecessary polling and database round trips;
3. tune bounded worker concurrency;
4. add worker replicas only when leases, provider limits, and connection budget
   are proven;
5. consider another broker only if Postgres queue behavior remains a measured
   limit after tuning.

Track:

- runnable depth and oldest runnable age;
- claim and notification-to-wake latency;
- active jobs versus concurrency;
- lease renewals, lease loss, requeues, and exhausted retries;
- stage p50/p95/p99;
- worker event-loop lag, CPU, RAM, and temporary disk;
- database connections per worker replica;
- provider concurrency and rate-limit headroom.

Use backpressure. Do not accept unlimited in-memory work when the queue or a
provider is slow.

## Audio, Groq, and OpenRouter

The cold-source path is expected to dominate time and variable cost. Record for
each stage:

- source duration and downloaded bytes;
- download and metadata latency;
- normalized audio size and bitrate;
- temporary upload and signed-download time;
- transcription latency, audio seconds, retries, and real-time factor;
- prompt input/output tokens, summary latency, retries, and model;
- end-to-end time and cost;
- cache contract and hit/miss reason.

Use chunking when the normalized file exceeds the provider limit or a benchmark
shows better recovery for long files. Chunking must keep timestamp offsets,
ordering, retry identity, and final transcript assembly correct. More chunks
also mean more requests and more failure points.

Provider changes require a representative benchmark of quality, timestamps,
latency, limits, retries, support, cost, and integration effort. A cheaper price
per hour alone is not enough.

## Storage and network

Talven uses temporary audio and cached PDF objects. For both:

- stream large transfers instead of loading full files into memory;
- set size, time, and content limits before expensive work;
- use random server-owned object keys;
- keep signed URLs short-lived;
- delete temporary audio on success, failure, and cancellation;
- sweep safe orphaned temporary objects;
- track ingress, egress, object count, bytes, age, and cleanup failure;
- avoid Railway persistent volumes unless a later design requires them.

Egress is data sent out of a provider. A database row read, Storage download,
API response, temporary-audio transfer, or PDF download can contribute to
egress when bytes cross that provider's boundary.

Move temporary objects to R2 only when measured Supabase/Railway egress,
Storage cost, or lifecycle behavior supports the migration. Free R2 Internet
egress does not remove Railway egress or integration cost.

## SSE and progress delivery

SSE is a long-lived connection, so measure it differently from normal API
requests:

- active streams and streams per user;
- open latency, lifetime, reconnects, and disconnect reason;
- replayed events and replay duration;
- event-to-browser delay;
- snapshot fallback and resume failure;
- server memory and connection use per stream;
- proxy buffering and idle timeout behavior in staging.

Keep persisted events bounded by a safe retention policy. Slow clients must not
create an unbounded memory queue. Test deploys, network changes, browser sleep,
and duplicate tabs.

## Auth, billing, email, and external commands

Performance changes must keep external commands correct:

- Polar webhooks and billing operations stay idempotent and recoverable;
- webhook acknowledgment time is separate from later processing time;
- Supabase Auth errors and rate limits have stable metrics;
- Resend send success is separate from delivery, bounce, or complaint;
- checkout and portal requests use bounded provider timeouts;
- retries do not create duplicate purchases, credits, refunds, or emails;
- secrets and external payloads do not enter metric labels or public logs.

Optimize correctness-sensitive writes only after proving the existing path is a
user-visible limit.

## Load and capacity tests

Use a production-like staging topology. Do not run a destructive load test
against production.

Test at least:

1. public Explore and briefing traffic with warm and cold public cache;
2. concurrent sign-ins and private library reads;
3. library search at representative row counts;
4. create requests for new, active, cached, and Explore-matched sources;
5. worker bursts with realistic source durations and provider stubs or approved
   test quotas;
6. SSE reconnect and replay during a deploy;
7. concurrent save, publish, unpublish, archive, checkout, and webhook retries;
8. database connection pressure with web, API, and worker together.

Increase load in steps. Stop on data-integrity failure, unexpected provider
spend, connection exhaustion, sustained errors, or resource danger. Record the
largest safe level and the first limiting resource.

## Monitoring and regression control

The Grafana runbook is authoritative for dashboards. Performance work should
also provide:

- release revision on web, API, and worker telemetry;
- route templates instead of raw paths with IDs;
- bounded metric labels;
- traces or correlation logs across API, database, worker stage, and provider;
- browser telemetry without source URLs, transcript text, email, or user IDs;
- alerts for sustained symptoms, not single noisy samples;
- collector freshness so missing telemetry cannot appear healthy.

Add automated regression gates only after a stable baseline exists. Useful
later gates include route bundle budgets, Lighthouse checks on stable public
pages, API microbenchmarks for pure code, and representative query-plan checks.
Do not make CI depend on noisy Internet provider latency.

## Priority roadmap

### Before public paid launch

- run the normal backend, frontend, API-contract, and database migration checks;
- test the critical user paths manually in staging;
- record a mobile and desktop frontend baseline;
- record API, queue, provider, connection, CPU, and RAM baselines;
- verify temporary-audio cleanup and SSE recovery;
- add the minimum production dashboards and alerts from the runbook;
- load-test the exact deployment at a safe representative level.

### First performance work after launch

1. Add the 30-to-60-second public Explore cache.
2. Measure Supabase client connection setup and PostgREST request latency.
3. Move private library search into Postgres when scans become material.
4. Add a single Explore read model only if four requests remain material after
   caching.
5. Tune worker concurrency from queue, provider, connection, CPU, and RAM data.
6. Apply a proven event-retention policy before event growth becomes expensive.

### Trigger table

| Signal | First action | Later structural action |
| --- | --- | --- |
| Explore API p95 above 250-300 ms due to reads | add/inspect short cache and query plans | one database read model |
| Low public cache hit rate | inspect key fragmentation and TTL | explicit invalidation or request coalescing |
| Library search needs several 200-row batches | measure representative query | `tsvector`/GIN or `pg_trgm` search RPC |
| High-offset list becomes slow | inspect plan and UX need | keyset pagination |
| Exact counts become expensive | confirm UI need | one-extra-row `has_more` or estimates |
| Pool wait or connections above 70% | find connection owners and leaks | tune pools/replicas or compute plan |
| Queue age grows with saturated workers | tune concurrency and provider backpressure | add replicas; broker review only if still needed |
| Database growth accelerates | inspect table/index/TOAST bytes and retention | disk expansion, proven TTL, then partitioning if required |
| Supabase or Railway egress forecast crosses runbook threshold | find byte path and cache/retry cause | benchmark R2 or alternate architecture |
| Frontend p75 misses a Core Web Vital | inspect route waterfall, bundle, render, and media | route redesign only after the cause is known |

## Review checklist

Before merging a performance change, confirm:

- the current bottleneck is measured;
- success and rollback values are written down;
- data visibility and account isolation are unchanged;
- lists, retries, concurrency, and memory remain bounded;
- query plans and indexes were checked where relevant;
- cache key, TTL, invalidation, and failure behavior are explicit;
- browser, API, worker, provider, and cost effects were considered;
- representative automated and staging checks passed;
- docs, dashboards, and alerts match the new behavior;
- the change adds less operational work than the problem it solves.
