# Data model reference

**Authority:** `supabase/migrations/*.sql` applied in filename order.

The application schema has 17 tables. `usage_settlements` owns immutable usage
history; there is no separate usage-ledger table.

Supabase Postgres stores durable application state and acts as the worker queue.
There is no separate ORM schema.

## Contents

- [Application tables](#application-tables)
- [Main relationships](#main-relationships)
- [Browser boundary](#browser-boundary)
- [Important command families](#important-command-families)
- [Publication invariants](#publication-invariants)
- [Settlement invariants](#settlement-invariants)
- [Pre-launch hardening reset](#pre-launch-hardening-reset)
- [CRUD map](#crud-map)
- [Safe schema inspection](#safe-schema-inspection)
- [Schema change checklist](#schema-change-checklist)

## Application tables

| Group | Table | Responsibility |
| --- | --- | --- |
| User work | `jobs` | User-owned session, library state, queue state, lease, duration, and result link |
| User work | `job_events` | Persisted progress and recovery events |
| Processing | `transcripts` | Permanent reusable source transcript identity and text |
| Processing | `transcript_segments` | Ordered timestamp evidence |
| Processing | `summaries` | Permanent global briefing and PDF cache state |
| Publication | `briefing_publications` | Private/Unlisted/Listed state, slug, topic, and moderation |
| Catalogue | `plans` | Versioned subscriptions and packs |
| Billing | `polar_customers` | Provider IDs only; email remains in Auth and Polar |
| Billing | `billing_orders` | Purchases and refunds |
| Billing | `billing_webhook_events` | Event idempotency, ordering, replay, and diagnostics |
| Billing | `billing_sync_operations` | User-scoped checkout/refund confirmation |
| Billing | `credit_lots` | Subscription, pack, and promotional grants and consumption |
| Billing | `entitlements` | Fast current balance, subscription, debt, and block snapshot |
| Billing | `usage_settlements` | One immutable usage charge and history entry per successful job |
| Coordination | `billing_maintenance_leases` | One billing-recovery owner across workers |
| Coordination | `briefing_stream_leases` | Bounded active event streams |
| Coordination | `api_rate_limit_buckets` | Shared hosted request counters |

Supabase Auth and Storage tables are platform-owned and are not included.

## Main relationships

| Parent | Child | Important behavior |
| --- | --- | --- |
| Supabase Auth user | `jobs`, `entitlements`, `credit_lots`, `polar_customers`, `briefing_stream_leases`, `billing_sync_operations` | User deletion cascades through user-owned operational data |
| Supabase Auth user | `billing_orders` | User deletion clears the optional user link; the commerce record remains for refund and provider audit |
| `transcripts` | `transcript_segments` | Segment deletion cascades with transcript |
| `transcripts` | `summaries` | Summary deletion cascades with transcript |
| `summaries` | `jobs` | Deleting summary clears the optional job link |
| `jobs` | `job_events` | Events delete with the job |
| `jobs` | `usage_settlements` | `job_id` is the settlement primary key; settlement deletes with its job |
| `jobs`, `summaries` | `briefing_publications` | Composite owner/job key proves ownership; publication also points to the ready summary |
| `plans` | `entitlements`, `billing_orders`, `credit_lots` | Financial history survives plan removal with optional plan link cleared |
| Auth user, `plans` | `billing_sync_operations` | User deletion removes operation; plan deletion clears optional plan link |

Provider IDs remain external identifiers because Polar is not part of this
database. User-owned root tables use foreign keys to `auth.users`. Shared
transcripts and summaries do not have a user owner. User access to shared cache
rows is granted through a user-owned job.

Transcripts and summaries have no TTL. The source content is not dynamic, so
the cache remains reusable until an explicit cache-version or deletion policy
replaces it.

## Browser boundary

All 17 application tables have RLS enabled.

The authenticated browser role has direct `SELECT` only on:

| Table | Rule |
| --- | --- |
| `jobs` | `user_id = auth.uid()` |
| `job_events` | Parent job belongs to `auth.uid()` |

It has no direct application-table mutation, billing read, transcript/summary
read, publication-table read, coordination-table access, or Storage-object
access.

Normal product requests use the API. The backend authenticates the user and
then uses the service client for the minimum required privileged operation.

Public briefing routes return an explicit response model. They never expose a
PostgREST publication row directly.

## Important command families

Exact signatures and grants remain in migrations.

| Concern | Main commands | Protected invariant |
| --- | --- | --- |
| Jobs | `create_or_reuse_settled_job`, `claim_next_settled_job`, `renew_job_lease`, `update_job_with_valid_lease`, requeue commands | User/source convergence, atomic pending-usage admission, claim, lease fencing, recovery |
| Queue delay | `next_queued_job_delay_seconds` | Event-driven delayed retry timing |
| Transcript | `create_transcript_with_segments` | Compatible transcript and contiguous validated segments |
| Summary | `prepare_summary`, update, complete, and fail commands | One producer, safe takeover, ready-only reuse |
| Usage | `settle_job_usage`, `complete_job_after_settlement` | One charge per job and atomic subscription/pack/debt update |
| Polar | `apply_polar_webhook_event`, refund, entitlement, and reconciliation commands | Ordered idempotent commerce and rebuildable balance |
| Publication | `save_briefing_publication` plus validation/unpublish triggers | Safe public projection and no-charge private save |
| PDF | prepare, complete, and fail PDF commands | One current renderer per summary/version |
| Streams | claim, renew, and release stream lease | Per-user and per-client stream caps |
| Maintenance | claim, renew, and release billing lease | One recovery owner |

Most commands are executable only by `service_role`.

## Publication invariants

A publication must:

- point to the owner's job;
- point to that job's ready, non-empty summary;
- preserve immutable owner, job, summary, source, and slug identity;
- be Private, Unlisted, or Listed;
- have a controlled topic and listing time when Listed;
- have clear moderation state to appear publicly; and
- be the only clear Listed publication for its normalized source.

Archiving or otherwise deactivating the owner job makes the publication Private.
Restoring the job does not republish it.

## Settlement invariants

Admission locks the user's billing boundary before queueing new billable work.
At most three billable jobs can be queued or running. Their combined unsettled
durations cannot exceed the current spendable entitlement. Same-source reuse
is resolved before this limit and does not create another job.

`usage_settlements.job_id` is its primary key. One job can have zero or one
settlement.

The settlement command locks and updates:

- eligible credit lots;
- debt;
- the entitlement snapshot;
- one settlement row; and
- the job's finalization state.

Subscription seconds, pack seconds, and new debt must add up to the settled
source duration. A retry returns the existing settlement.

The row is write-once during normal billing operation. It is not independent
of account deletion: deleting the parent Auth user cascades through the job and
its settlement. `billing_orders` remain with a null user link for commerce and
refund evidence.

Direct Auth user deletion is not an approved account-deletion workflow. A
future workflow must first resolve Polar subscriptions, refunds, retained
commerce evidence, shared cache rows, Storage objects, and provider data.

## Pre-launch hardening reset

`20260815130000_reset_and_harden_schema.sql` starts by truncating mutable
application tables. It is a one-time pre-user reset, not a reusable deployment
pattern.

**Owner decision:** Accepted. The reset intentionally removes all existing
application rows except retained catalogue and platform configuration so the
schema can establish the final foreign keys, deletion rules, and constraints
before external users exist.

The migration does not delete Auth users, Storage objects, or Polar customers.
Its comment mentions a guarded reset script, but that script is not present in
the repository. Confirm the target and perform provider cleanup separately
before applying it.

After external data exists, use forward schema and data migrations that
preserve required records. Do not add another broad truncate.

## CRUD map

| Module | Responsibility |
| --- | --- |
| `jobs.py` | Session create/reuse, list, claim, lease, retry, archive, and restore |
| `job_events.py` | Persist and page progress events |
| `transcripts.py` | Transcript identities and ordered segments |
| `summaries.py` | Summary producer lifecycle and PDF state |
| `publications.py` | Owner/public/Explore reads and save command |
| `storage_objects.py` | Private upload, signed URL, and cleanup |
| `stream_leases.py` | Active SSE lease |
| `billing_catalog.py` | Plan identity |
| `billing_credits.py` | Credit lots |
| `billing_entitlements.py` | Current balance snapshot |
| `billing_orders.py` | Orders, refunds, and candidates |
| `billing_operations.py` | Checkout/refund operation state |
| `billing_usage.py` | Settlement and usage history |
| `billing_webhooks.py` | Provider customer/event application |
| `billing_recovery.py` | Refund and maintenance recovery |

Application use cases should call CRUD. HTTP routers should call application
use cases.

## Safe schema inspection

Use a local or dedicated staging SQL editor:

    select table_name
    from information_schema.tables
    where table_schema = 'public'
      and table_type = 'BASE TABLE'
    order by table_name;

Inspect RLS:

    select schemaname, tablename, policyname, roles, cmd, qual, with_check
    from pg_policies
    where schemaname = 'public'
    order by tablename, policyname;

Inspect grants:

    select grantee, table_name, privilege_type
    from information_schema.role_table_grants
    where table_schema = 'public'
    order by table_name, grantee, privilege_type;

Do not use production as a learning sandbox.

See [Performance reference](./performance.md) for the query-driven indexes and
the current pagination decisions.

## Schema change checklist

1. Add a new forward migration.
2. Decide foreign keys, checks, deletion behavior, RLS, table grants, and RPC
   grants together.
3. Update the owning CRUD and application modules.
4. Add cross-tenant, role, constraint, and concurrency tests.
5. Run the complete migration history from a clean database.
6. Regenerate the API client if the HTTP contract changed.
7. Update this page when tables or command ownership changed.

## Next read

[Processing and providers](../03-processing-and-providers.md)
