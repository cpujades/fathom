-- Converge Talven's browser-facing database boundary.
--
-- Authenticated clients may read only their own jobs, terminal settled
-- summaries, and persisted job events. Every mutation and all billing,
-- transcript, cache, and rate-limit data remain server-mediated.

alter table public.jobs enable row level security;
alter table public.summaries enable row level security;
alter table public.transcripts enable row level security;
alter table public.plans enable row level security;
alter table public.entitlements enable row level security;
alter table public.usage_ledger enable row level security;
alter table public.polar_customers enable row level security;
alter table public.billing_webhook_events enable row level security;
alter table public.billing_orders enable row level security;
alter table public.credit_lots enable row level security;
alter table public.api_rate_limit_buckets enable row level security;
alter table public.usage_settlements enable row level security;
alter table public.transcript_segments enable row level security;
alter table public.job_events enable row level security;

revoke all on table
  public.jobs,
  public.summaries,
  public.transcripts,
  public.plans,
  public.entitlements,
  public.usage_ledger,
  public.polar_customers,
  public.billing_webhook_events,
  public.billing_orders,
  public.credit_lots,
  public.api_rate_limit_buckets,
  public.usage_settlements,
  public.transcript_segments,
  public.job_events
from public, anon, authenticated;

grant select on table
  public.jobs,
  public.summaries,
  public.job_events
to authenticated;

grant select, insert, update, delete on table
  public.jobs,
  public.summaries,
  public.transcripts,
  public.plans,
  public.entitlements,
  public.usage_ledger,
  public.polar_customers,
  public.billing_webhook_events,
  public.billing_orders,
  public.credit_lots,
  public.api_rate_limit_buckets
to service_role;

grant select, insert on table
  public.usage_settlements,
  public.job_events
to service_role;

grant select on table public.transcript_segments
to service_role;

drop policy if exists "summaries_select_own" on public.summaries;
drop policy if exists "summaries_select_via_jobs" on public.summaries;
create policy "summaries_select_via_settled_jobs"
on public.summaries
for select
to authenticated
using (
  summaries.status = 'ready'
  and pg_catalog.btrim(summaries.summary_markdown) <> ''
  and exists (
    select 1
    from public.jobs
    where jobs.summary_id = summaries.id
      and jobs.user_id = (select auth.uid())
      and jobs.status in ('succeeded', 'deleted')
  )
);

-- Billing and plan reads are exposed through authenticated API routes, not
-- through PostgREST. Remove obsolete direct-client policies as well as ACLs.
drop policy if exists "plans_select_all" on public.plans;
drop policy if exists "entitlements_select_own" on public.entitlements;
drop policy if exists "usage_ledger_select_own" on public.usage_ledger;
drop policy if exists "polar_customers_select_own" on public.polar_customers;
drop policy if exists "billing_orders_select_own" on public.billing_orders;
drop policy if exists "credit_lots_select_own" on public.credit_lots;

revoke all on sequence public.job_events_sequence_id_seq
  from public, anon, authenticated;
grant usage, select on sequence public.job_events_sequence_id_seq
  to service_role;

-- Old rolling-deploy commands remain as private implementation details for
-- their settlement-aware wrappers, but cannot be called directly by the
-- service role.
revoke execute on function public.claim_next_job(interval)
  from service_role;
revoke execute on function public.create_or_reuse_job(uuid, text, text, integer, uuid)
  from service_role;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog
as $$
begin
  new.updated_at = pg_catalog.now();
  return new;
end;
$$;

create or replace function public.notify_job_created()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog
as $$
begin
  perform pg_catalog.pg_notify(
    'job_created',
    pg_catalog.json_build_object(
      'id', new.id,
      'created_at', new.created_at
    )::text
  );
  return new;
end;
$$;

revoke all on function public.set_updated_at()
  from public, anon, authenticated, service_role;
revoke all on function public.notify_job_created()
  from public, anon, authenticated, service_role;

-- ON CONFLICT DO UPDATE is intentional: an existing bucket must converge to
-- private instead of retaining a stale public flag.
insert into storage.buckets (id, name, public)
values
  ('fathom', 'fathom', false),
  ('fathom_groq', 'fathom_groq', false)
on conflict (id)
do update set public = excluded.public;
