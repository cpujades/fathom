# Database, RLS, and persistence

Supabase Postgres is both the durable application state and the worker queue.
The Python code uses Supabase PostgREST for ordinary reads/writes and protected
Postgres RPCs for operations that must be atomic, fenced, or multi-row. There
is no ORM model layer to update separately from the migrations.

## The 16 application tables

These are the current public application tables. Supabase Auth and Storage
tables are platform-owned and are not included.

| Group | Tables | Responsibility |
| --- | --- | --- |
| User work | `jobs`, `job_events` | Private session/library state, queue progress, and replayable state changes |
| Reusable processing | `transcripts`, `transcript_segments`, `summaries` | Source metadata, immutable timestamp evidence, and versioned briefing output |
| Catalog and billing | `plans`, `polar_customers`, `billing_orders`, `billing_webhook_events`, `credit_lots`, `entitlements`, `usage_ledger`, `usage_settlements` | Product catalog, provider identity, commerce facts, webhook audit, credit lots, balance snapshot, usage history, and one charge per job |
| Coordination | `billing_maintenance_leases`, `briefing_stream_leases`, `api_rate_limit_buckets` | Short-lived distributed locks, stream caps, and shared request counters |

The key ownership decision is that most tables carry a `user_id` without a
foreign key to `auth.users`. This keeps local seed/backfill operations simple.
Ownership is enforced by API checks and RLS predicates; a UUID is never treated
as permission by itself.

## Foreign keys and deletion behavior

| Parent | Child | Constraint behavior |
| --- | --- | --- |
| `transcripts` | `transcript_segments` | `transcript_id`, cascade on transcript deletion |
| `transcripts` | `summaries` | `transcript_id`, cascade on transcript deletion |
| `summaries` | `jobs` | `summary_id`, set null if the summary is deleted |
| `jobs` | `job_events` | `job_id`, cascade with the job |
| `jobs` | `usage_settlements` | Unique `job_id`, restrict deletion |
| `jobs` | legacy `usage_ledger` rows | `job_id`, set null |
| `usage_settlements` | new `usage_ledger` rows | `settlement_id`, restrict deletion |
| `plans` | `entitlements`, `billing_orders`, `credit_lots` | `plan_id`, set null |

Relationships such as `user_id`, Polar order IDs, provider event IDs, and
`credit_lots.source_key` are intentionally logical rather than Auth foreign
keys. The application and SQL commands lock and validate them when changing
state.

## Browser RLS and server privileges

All 16 application tables have RLS enabled. The final client boundary grants
the authenticated role `SELECT` on only:

| Table | Final read rule |
| --- | --- |
| `jobs` | `jobs.user_id = auth.uid()` |
| `job_events` | The event’s job belongs to `auth.uid()` |
| `summaries` | The summary is `ready`, non-empty, and linked to that user’s `succeeded` or `deleted` job |

Authenticated clients have no direct insert, update, or delete privilege on
application tables, no direct Storage access, and no direct reads of
transcripts, plans, billing, usage, settlement, stream-lease, maintenance, or
rate-limit data. The API reads those records with a service client only after
authenticating the user and applying the corresponding ownership filter.

`FORCE ROW LEVEL SECURITY` is not enabled because trusted table owners and the
service role must run server operations. This makes secret-key handling a hard
security boundary: the service key must remain out of the browser and logs.

## Server RPCs: where invariants live

These are the important current command families. The exact signatures and
grants live in `supabase/migrations/`; the Python CRUD modules call them.

| Concern | Main RPCs | Invariant protected |
| --- | --- | --- |
| Queue and leases | `create_or_reuse_job`, `claim_next_job`, `renew_job_lease`, `update_job_with_valid_lease`, `requeue_stale_jobs`, `requeue_unsettled_jobs` | One user/source job resolution, atomic claim, lease fencing, and recoverability |
| Transcripts | `create_transcript_with_segments` | One provider-contract transcript and contiguous validated segments |
| Summaries | `prepare_summary`, `update_summary_draft`, `complete_summary_generation`, `fail_summary_generation` | One live producer, takeover after orphaning, ready-only cache reuse |
| Usage | `settle_job_usage`, `complete_job_after_settlement` | One settlement per job; subscription then pack then debt accounting |
| Polar billing | `apply_polar_webhook_event`, `begin_pack_refund`, `reopen_pack_refund`, `refresh_billing_entitlement_snapshot`, `schedule_subscription_reconciliation` | Idempotent ordered events, refund/settlement locking, and rebuildable balance snapshot |
| PDF | `prepare_summary_pdf`, `complete_summary_pdf`, `fail_summary_pdf` | One renderer per summary/cache version |
| SSE/maintenance | `claim/renew/release_briefing_stream_lease`, `claim/renew/release_billing_maintenance_lease` | Bounded active streams and one recovery owner across replicas |

Most RPCs are executable only by `service_role`. Triggers create state-change
events and `NOTIFY` queue wake-ups; callers do not write cursors or lease tokens
directly.

## Current Python CRUD modules

`apps/backend/fathom/crud/supabase/billing.py` is a stable import facade. The
implementation is split by database responsibility:

| Module | Main operations |
| --- | --- |
| `jobs.py` | Create/reuse, fetch active/reusable/page, claim/renew/requeue, progress/status changes, archive/restore |
| `transcripts.py` | Fetch by hash/video/id, create with segments, fetch ordered segments |
| `summaries.py` | Fetch by ID/keys, prepare/update/ready/failed lifecycle, PDF prepare/complete/fail |
| `job_events.py` | Record best-effort milestones, list all/after cursor, fetch latest sequence |
| `storage_objects.py` | Upload, signed URL, delete, retry cleanup, PDF helpers |
| `stream_leases.py` | Claim, renew, release active SSE lease |
| `billing_catalog.py` | Fetch active plans and plan identity |
| `billing_credits.py` | Fetch/upsert/consume/expire/summarize credit lots |
| `billing_entitlements.py` | Fetch/upsert balance snapshot and adjust debt |
| `billing_orders.py` | List user orders, refund-pending orders, reconciliation candidates |
| `billing_usage.py` | Fetch usage history and call atomic settlement |
| `billing_webhooks.py` | Upsert provider customer, reclaim stale events, apply webhook transaction |
| `billing_recovery.py` | Begin/reopen refunds, maintenance leases, webhook diagnostics |

Application code should call a use case, not a CRUD function, when the action
has user-facing policy. CRUD owns persistence shape and error translation; the
application layer owns decisions such as “a known source must fit the current
balance.”

## How to change the data model safely

1. Add an immutable migration; never edit an applied migration.
2. Decide whether the relationship is a real foreign key or an intentional
   provider/user logical link.
3. Add or change RLS, table grants, and RPC grants in the same migration.
4. Update the relevant CRUD module and Pydantic/transport model.
5. Add database tests for roles, cross-tenant access, constraints, and
   concurrency where the invariant is transactional.
6. Regenerate and check the API client if the change crosses the HTTP boundary.
7. Update the relevant owner guide and run the clean-database gate for the
   candidate migrations.

The [security page](./security-and-data-access.md) explains the trust boundary;
the [system lifecycle](./system-and-job-lifecycle.md) explains when each table
changes during a briefing.
