-- Keep subscription recovery event-driven while retaining a bounded provider
-- audit for missed webhooks. The next-check time is durable across worker
-- replicas and restarts.

alter table public.entitlements
  add column if not exists next_subscription_reconcile_at timestamptz;

comment on column public.entitlements.next_subscription_reconcile_at is
  'Next time the worker may audit this non-terminal Polar subscription; null disables polling.';

create index if not exists entitlements_subscription_reconcile_due_idx
  on public.entitlements (next_subscription_reconcile_at, user_id)
  where polar_subscription_id is not null
    and next_subscription_reconcile_at is not null;

create or replace function public.schedule_subscription_reconciliation()
returns trigger
language plpgsql
set search_path = pg_catalog
as $$
begin
  if new.polar_subscription_id is null
    or coalesce(new.subscription_status, '') in ('revoked', 'ended', 'inactive')
  then
    new.next_subscription_reconcile_at = null;
  elsif tg_op = 'INSERT' then
    new.next_subscription_reconcile_at = pg_catalog.now() + interval '6 hours';
  elsif old.polar_subscription_id is distinct from new.polar_subscription_id
    or old.subscription_status is distinct from new.subscription_status
  then
    new.next_subscription_reconcile_at = pg_catalog.now() + interval '6 hours';
  end if;

  return new;
end;
$$;

drop trigger if exists schedule_subscription_reconciliation on public.entitlements;
create trigger schedule_subscription_reconciliation
before insert or update of polar_subscription_id, subscription_status
on public.entitlements
for each row
execute function public.schedule_subscription_reconciliation();

-- Existing non-terminal subscriptions get one delayed audit instead of a
-- simultaneous provider request as soon as this migration is deployed.
update public.entitlements
set next_subscription_reconcile_at = pg_catalog.now() + interval '6 hours'
where polar_subscription_id is not null
  and coalesce(subscription_status, '') not in ('revoked', 'ended', 'inactive')
  and next_subscription_reconcile_at is null;

update public.entitlements
set next_subscription_reconcile_at = null
where polar_subscription_id is null
  or coalesce(subscription_status, '') in ('revoked', 'ended', 'inactive');
