-- Serialize pack refunds with usage settlement and make billing recovery
-- single-owner, transactional, and replay-safe.

create table if not exists public.billing_maintenance_leases (
  lease_name text primary key,
  lease_token uuid not null,
  lease_expires_at timestamptz not null,
  updated_at timestamptz not null default pg_catalog.now(),
  constraint billing_maintenance_leases_name_not_empty
    check (pg_catalog.btrim(lease_name) <> '')
);

alter table public.billing_maintenance_leases enable row level security;

revoke all on table public.billing_maintenance_leases
from public, anon, authenticated, service_role;

create or replace function public.claim_billing_maintenance_lease(
  p_lease_name text,
  p_lease_token uuid,
  p_lease_for interval
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  acquired boolean := false;
begin
  if p_lease_name is null or pg_catalog.btrim(p_lease_name) = '' or p_lease_token is null then
    raise exception 'lease name and token are required' using errcode = '22023';
  end if;
  if p_lease_for is null
    or p_lease_for < interval '10 seconds'
    or p_lease_for > interval '10 minutes'
  then
    raise exception 'billing maintenance lease must be between 10 seconds and 10 minutes'
      using errcode = '22023';
  end if;

  insert into public.billing_maintenance_leases (
    lease_name,
    lease_token,
    lease_expires_at,
    updated_at
  )
  values (
    p_lease_name,
    p_lease_token,
    pg_catalog.now() + p_lease_for,
    pg_catalog.now()
  )
  on conflict (lease_name) do update
  set lease_token = excluded.lease_token,
      lease_expires_at = excluded.lease_expires_at,
      updated_at = excluded.updated_at
  where public.billing_maintenance_leases.lease_expires_at <= pg_catalog.now()
     or public.billing_maintenance_leases.lease_token = excluded.lease_token
  returning true into acquired;

  return coalesce(acquired, false);
end;
$$;

create or replace function public.renew_billing_maintenance_lease(
  p_lease_name text,
  p_lease_token uuid,
  p_lease_for interval
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  updated_count integer;
begin
  if p_lease_name is null or pg_catalog.btrim(p_lease_name) = '' or p_lease_token is null then
    raise exception 'lease name and token are required' using errcode = '22023';
  end if;
  if p_lease_for is null
    or p_lease_for < interval '10 seconds'
    or p_lease_for > interval '10 minutes'
  then
    raise exception 'billing maintenance lease must be between 10 seconds and 10 minutes'
      using errcode = '22023';
  end if;

  update public.billing_maintenance_leases
  set lease_expires_at = pg_catalog.now() + p_lease_for,
      updated_at = pg_catalog.now()
  where lease_name = p_lease_name
    and lease_token = p_lease_token
    and lease_expires_at > pg_catalog.now();

  get diagnostics updated_count = row_count;
  return updated_count = 1;
end;
$$;

create or replace function public.release_billing_maintenance_lease(
  p_lease_name text,
  p_lease_token uuid
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  deleted_count integer;
begin
  if p_lease_name is null or pg_catalog.btrim(p_lease_name) = '' or p_lease_token is null then
    raise exception 'lease name and token are required' using errcode = '22023';
  end if;

  delete from public.billing_maintenance_leases
  where lease_name = p_lease_name
    and lease_token = p_lease_token;

  get diagnostics deleted_count = row_count;
  return deleted_count = 1;
end;
$$;

-- Lock the billing order before its lot, matching settle_job_usage. Once this
-- transaction commits, settlement sees refund_pending and excludes the pack.
create or replace function public.begin_pack_refund(
  p_user_id uuid,
  p_order_id text,
  p_debt_cap_seconds integer
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  order_row public.billing_orders;
  lot_row public.credit_lots;
  remaining_seconds integer;
  refundable_amount_cents integer;
begin
  if p_user_id is null or p_order_id is null or pg_catalog.btrim(p_order_id) = '' then
    raise exception 'user id and order id are required' using errcode = '22023';
  end if;
  if p_debt_cap_seconds is null or p_debt_cap_seconds < 0 then
    raise exception 'debt cap seconds cannot be negative' using errcode = '22023';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('polar:order:' || p_order_id, 0)
  );

  select *
  into order_row
  from public.billing_orders
  where polar_order_id = p_order_id
    and user_id = p_user_id
  for update;

  if not found then
    return pg_catalog.jsonb_build_object('resolution_type', 'not_found');
  end if;
  if order_row.plan_type <> 'pack' then
    return pg_catalog.jsonb_build_object('resolution_type', 'not_pack');
  end if;
  if order_row.status = 'refund_pending' then
    return pg_catalog.jsonb_build_object('resolution_type', 'already_pending');
  end if;
  if order_row.status = 'refunded' then
    return pg_catalog.jsonb_build_object('resolution_type', 'already_refunded');
  end if;

  select *
  into lot_row
  from public.credit_lots
  where user_id = p_user_id
    and lot_type = 'pack_order'
    and source_key = p_order_id
  for update;

  if not found then
    return pg_catalog.jsonb_build_object('resolution_type', 'lot_not_found');
  end if;

  remaining_seconds := greatest(
    lot_row.granted_seconds - lot_row.consumed_seconds - lot_row.revoked_seconds,
    0
  );
  if lot_row.status <> 'active'
    or lot_row.granted_seconds <= 0
    or order_row.paid_amount_cents <= 0
  then
    return pg_catalog.jsonb_build_object('resolution_type', 'not_refundable');
  end if;
  if remaining_seconds <= 0 then
    return pg_catalog.jsonb_build_object('resolution_type', 'nothing_remaining');
  end if;

  refundable_amount_cents := (
    order_row.paid_amount_cents::bigint * remaining_seconds::bigint
    / lot_row.granted_seconds::bigint
  )::integer;
  if refundable_amount_cents <= 0 then
    return pg_catalog.jsonb_build_object('resolution_type', 'nothing_remaining');
  end if;

  update public.billing_orders
  set status = 'refund_pending',
      updated_at = pg_catalog.now()
  where id = order_row.id;

  perform public.refresh_billing_entitlement_snapshot(p_user_id, p_debt_cap_seconds);

  return pg_catalog.jsonb_build_object(
    'resolution_type', 'started',
    'order_id', order_row.id,
    'refundable_amount_cents', refundable_amount_cents,
    'remaining_seconds_before_refund', remaining_seconds
  );
end;
$$;

-- Reopening is used only after Polar definitively proves that no refund was
-- created. It shares the webhook resource lock and refreshes the snapshot in
-- the same transaction.
create or replace function public.reopen_pack_refund(
  p_user_id uuid,
  p_order_id text,
  p_debt_cap_seconds integer
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  order_row public.billing_orders;
begin
  if p_user_id is null or p_order_id is null or pg_catalog.btrim(p_order_id) = '' then
    raise exception 'user id and order id are required' using errcode = '22023';
  end if;
  if p_debt_cap_seconds is null or p_debt_cap_seconds < 0 then
    raise exception 'debt cap seconds cannot be negative' using errcode = '22023';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('polar:order:' || p_order_id, 0)
  );

  select *
  into order_row
  from public.billing_orders
  where polar_order_id = p_order_id
    and user_id = p_user_id
  for update;

  if not found then
    return pg_catalog.jsonb_build_object('resolution_type', 'not_found');
  end if;
  if order_row.plan_type <> 'pack' then
    return pg_catalog.jsonb_build_object('resolution_type', 'not_pack');
  end if;
  if order_row.status = 'refunded' then
    return pg_catalog.jsonb_build_object('resolution_type', 'already_refunded');
  end if;
  if order_row.status = 'paid' then
    return pg_catalog.jsonb_build_object('resolution_type', 'already_paid');
  end if;

  update public.billing_orders
  set status = 'paid',
      updated_at = pg_catalog.now()
  where id = order_row.id
    and status = 'refund_pending';

  perform public.refresh_billing_entitlement_snapshot(p_user_id, p_debt_cap_seconds);

  return pg_catalog.jsonb_build_object('resolution_type', 'reopened');
end;
$$;

-- A refunded pack and its remaining lot must change state in one transaction,
-- even if a future trusted caller updates the order outside the normal webhook
-- command.
create or replace function public.revoke_refunded_pack_lot()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog
as $$
begin
  if new.plan_type = 'pack'
    and new.status = 'refunded'
  then
    if tg_op = 'INSERT'
      or (tg_op = 'UPDATE' and old.status is distinct from new.status)
    then
      update public.credit_lots
      set revoked_seconds = revoked_seconds
          + greatest(granted_seconds - consumed_seconds - revoked_seconds, 0),
          status = 'revoked',
          updated_at = pg_catalog.now()
      where user_id = new.user_id
        and lot_type = 'pack_order'
        and source_key = new.polar_order_id
        and status = 'active';
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists revoke_refunded_pack_lot on public.billing_orders;
create trigger revoke_refunded_pack_lot
after insert or update of status on public.billing_orders
for each row
execute function public.revoke_refunded_pack_lot();

create or replace function public.reject_active_refunding_pack_lot()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog
as $$
begin
  if new.lot_type = 'pack_order'
    and new.status = 'active'
    and exists (
      select 1
      from public.billing_orders
      where user_id = new.user_id
        and polar_order_id = new.source_key
        and status in ('refund_pending', 'refunded')
    )
  then
    raise exception 'cannot activate a credit lot for a refunding or refunded pack order'
      using errcode = '23514';
  end if;
  return new;
end;
$$;

drop trigger if exists reject_active_refunding_pack_lot on public.credit_lots;
create trigger reject_active_refunding_pack_lot
before insert or update of status, source_key, user_id, lot_type on public.credit_lots
for each row
execute function public.reject_active_refunding_pack_lot();

-- Converge any legacy refunded order whose lot was left active.
update public.credit_lots as lots
set revoked_seconds = lots.revoked_seconds
    + greatest(lots.granted_seconds - lots.consumed_seconds - lots.revoked_seconds, 0),
    status = 'revoked',
    updated_at = pg_catalog.now()
where lots.lot_type = 'pack_order'
  and lots.status = 'active'
  and exists (
    select 1
    from public.billing_orders as orders
    where orders.user_id = lots.user_id
      and orders.polar_order_id = lots.source_key
      and orders.status = 'refunded'
  );

-- Keep entitlement snapshots defensive even if they encounter historical
-- active lots linked to refunded orders.
create or replace function public.refresh_billing_entitlement_snapshot(
  p_user_id uuid,
  p_debt_cap_seconds integer
)
returns void
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  snapshot_now timestamptz := pg_catalog.now();
  subscription_remaining integer := 0;
  pack_remaining integer := 0;
  next_pack_expiry timestamptz;
begin
  if p_user_id is null then
    raise exception 'user id is required' using errcode = '22023';
  end if;
  if p_debt_cap_seconds is null or p_debt_cap_seconds < 0 then
    raise exception 'debt cap seconds cannot be negative' using errcode = '22023';
  end if;

  insert into public.entitlements (user_id)
  values (p_user_id)
  on conflict (user_id) do nothing;

  update public.credit_lots
  set status = 'expired',
      updated_at = snapshot_now
  where user_id = p_user_id
    and status = 'active'
    and pack_expires_at is not null
    and pack_expires_at <= snapshot_now;

  select
    coalesce(
      sum(
        case
          when lots.lot_type = 'subscription_cycle'
            then greatest(lots.granted_seconds - lots.consumed_seconds - lots.revoked_seconds, 0)
          else 0
        end
      ),
      0
    )::integer,
    coalesce(
      sum(
        case
          when lots.lot_type = 'pack_order'
            and not exists (
              select 1
              from public.billing_orders as orders
              where orders.polar_order_id = lots.source_key
                and orders.status in ('refund_pending', 'refunded')
            )
            then greatest(lots.granted_seconds - lots.consumed_seconds - lots.revoked_seconds, 0)
          else 0
        end
      ),
      0
    )::integer,
    min(lots.pack_expires_at) filter (
      where lots.lot_type = 'pack_order'
        and greatest(lots.granted_seconds - lots.consumed_seconds - lots.revoked_seconds, 0) > 0
        and not exists (
          select 1
          from public.billing_orders as orders
          where orders.polar_order_id = lots.source_key
            and orders.status in ('refund_pending', 'refunded')
        )
    )
  into subscription_remaining, pack_remaining, next_pack_expiry
  from public.credit_lots as lots
  where lots.user_id = p_user_id
    and lots.status = 'active'
    and lots.lot_type in ('subscription_cycle', 'pack_order');

  update public.entitlements
  set subscription_available_seconds = subscription_remaining,
      pack_available_seconds = pack_remaining,
      pack_expires_at = next_pack_expiry,
      is_blocked = debt_seconds >= p_debt_cap_seconds,
      last_balance_sync_at = snapshot_now,
      updated_at = snapshot_now
  where user_id = p_user_id;
end;
$$;

-- Debt paydown is another credit consumer. Keep refunding packs unavailable
-- there as well, while retaining its existing entitlement-then-lot lock order.
create or replace function public.pay_down_billing_debt_from_lot(
  p_user_id uuid,
  p_lot_id uuid,
  p_debt_cap_seconds integer
)
returns integer
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  entitlement_row public.entitlements;
  lot_row public.credit_lots;
  lot_remaining integer;
  paydown integer;
  debt_after integer;
begin
  insert into public.entitlements (user_id)
  values (p_user_id)
  on conflict (user_id) do nothing;

  select *
  into entitlement_row
  from public.entitlements
  where user_id = p_user_id
  for update;

  select *
  into lot_row
  from public.credit_lots
  where id = p_lot_id
    and user_id = p_user_id
  for update;

  if not found
    or lot_row.status <> 'active'
    or (
      lot_row.lot_type = 'pack_order'
      and exists (
        select 1
        from public.billing_orders
        where user_id = p_user_id
          and polar_order_id = lot_row.source_key
          and status in ('refund_pending', 'refunded')
      )
    )
  then
    return greatest(coalesce(entitlement_row.debt_seconds, 0), 0);
  end if;

  lot_remaining := greatest(
    lot_row.granted_seconds - lot_row.consumed_seconds - lot_row.revoked_seconds,
    0
  );
  paydown := least(greatest(coalesce(entitlement_row.debt_seconds, 0), 0), lot_remaining);
  debt_after := greatest(coalesce(entitlement_row.debt_seconds, 0) - paydown, 0);

  if paydown > 0 then
    update public.credit_lots
    set consumed_seconds = consumed_seconds + paydown,
        updated_at = pg_catalog.now()
    where id = p_lot_id;

    update public.entitlements
    set debt_seconds = debt_after,
        is_blocked = debt_after >= p_debt_cap_seconds,
        last_balance_sync_at = pg_catalog.now(),
        updated_at = pg_catalog.now()
    where user_id = p_user_id;
  end if;

  return debt_after;
end;
$$;

revoke all on function public.claim_billing_maintenance_lease(text, uuid, interval)
from public, anon, authenticated;
revoke all on function public.renew_billing_maintenance_lease(text, uuid, interval)
from public, anon, authenticated;
revoke all on function public.release_billing_maintenance_lease(text, uuid)
from public, anon, authenticated;
revoke all on function public.begin_pack_refund(uuid, text, integer)
from public, anon, authenticated;
revoke all on function public.reopen_pack_refund(uuid, text, integer)
from public, anon, authenticated;
revoke all on function public.pay_down_billing_debt_from_lot(uuid, uuid, integer)
from public, anon, authenticated;
revoke all on function public.revoke_refunded_pack_lot()
from public, anon, authenticated, service_role;
revoke all on function public.reject_active_refunding_pack_lot()
from public, anon, authenticated, service_role;

grant execute on function public.claim_billing_maintenance_lease(text, uuid, interval)
to service_role;
grant execute on function public.renew_billing_maintenance_lease(text, uuid, interval)
to service_role;
grant execute on function public.release_billing_maintenance_lease(text, uuid)
to service_role;
grant execute on function public.begin_pack_refund(uuid, text, integer)
to service_role;
grant execute on function public.reopen_pack_refund(uuid, text, integer)
to service_role;
