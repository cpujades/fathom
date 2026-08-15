-- Keep one immutable usage record per completed job. The settlement already
-- contains the total charge and its subscription, pack, and debt breakdown.

create or replace function public.settle_job_usage(
  p_job_id uuid,
  p_lease_token uuid,
  p_debt_cap_seconds integer
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  job_row public.jobs;
  settlement_row public.usage_settlements;
  lot_row public.credit_lots;
  settlement_resolution text := 'settled';
  effective_duration integer;
  remaining_seconds integer;
  lot_remaining integer;
  lot_consumption integer;
  subscription_consumed integer := 0;
  pack_consumed integer := 0;
  debt_incurred integer := 0;
  current_debt integer;
  debt_after integer;
  subscription_available integer := 0;
  pack_available integer := 0;
  next_pack_expiry timestamptz;
  settlement_now timestamptz := pg_catalog.now();
begin
  if p_job_id is null or p_lease_token is null then
    raise exception 'job id and lease token are required' using errcode = '22023';
  end if;
  if p_debt_cap_seconds is null or p_debt_cap_seconds < 0 then
    raise exception 'debt cap seconds cannot be negative' using errcode = '22023';
  end if;

  select *
  into job_row
  from public.jobs
  where id = p_job_id
  for update;

  if not found then
    raise exception 'job not found' using errcode = 'P0002';
  end if;
  if job_row.status <> 'running'
    or job_row.lease_token is distinct from p_lease_token
    or job_row.lease_expires_at is null
    or job_row.lease_expires_at <= settlement_now
  then
    raise exception 'job lease is not current' using errcode = '55000';
  end if;

  select *
  into settlement_row
  from public.usage_settlements
  where job_id = p_job_id;

  if found then
    settlement_resolution := 'already_settled';
    return pg_catalog.jsonb_build_object(
      'resolution_type', settlement_resolution,
      'settlement', pg_catalog.to_jsonb(settlement_row)
    );
  end if;

  effective_duration := greatest(
    coalesce(job_row.duration_seconds, 0),
    0
  );
  remaining_seconds := effective_duration;

  if effective_duration > 0 then
    -- Match the existing policy: expire unusable lots, then consume
    -- subscription credit before pack credit. Refund-pending packs remain
    -- excluded from both consumption and the entitlement snapshot.
    perform 1
    from public.billing_orders
    where user_id = job_row.user_id
    order by id
    for update;

    update public.credit_lots
    set status = 'expired',
        updated_at = settlement_now
    where user_id = job_row.user_id
      and status = 'active'
      and pack_expires_at is not null
      and pack_expires_at <= settlement_now;

    for lot_row in
      select lots.*
      from public.credit_lots as lots
      where lots.user_id = job_row.user_id
        and lots.status = 'active'
        and lots.lot_type in ('subscription_cycle', 'pack_order')
        and (lots.pack_expires_at is null or lots.pack_expires_at > settlement_now)
        and (
          lots.lot_type <> 'pack_order'
          or not exists (
            select 1
            from public.billing_orders as orders
            where orders.user_id = job_row.user_id
              and orders.status = 'refund_pending'
              and orders.polar_order_id = lots.source_key
          )
        )
      order by
        case when lots.lot_type = 'subscription_cycle' then 0 else 1 end,
        lots.pack_expires_at asc nulls last,
        lots.created_at asc,
        lots.id asc
      for update
    loop
      exit when remaining_seconds <= 0;

      lot_remaining := greatest(
        lot_row.granted_seconds - lot_row.consumed_seconds - lot_row.revoked_seconds,
        0
      );
      if lot_remaining <= 0 then
        continue;
      end if;

      lot_consumption := least(lot_remaining, remaining_seconds);
      update public.credit_lots
      set consumed_seconds = consumed_seconds + lot_consumption,
          updated_at = settlement_now
      where id = lot_row.id;

      if lot_row.lot_type = 'subscription_cycle' then
        subscription_consumed := subscription_consumed + lot_consumption;
      else
        pack_consumed := pack_consumed + lot_consumption;
      end if;
      remaining_seconds := remaining_seconds - lot_consumption;
    end loop;

    select debt_seconds
    into current_debt
    from public.entitlements
    where user_id = job_row.user_id
    for update;

    if not found then
      raise exception 'billing entitlement is missing' using errcode = 'P0002';
    end if;

    debt_incurred := greatest(remaining_seconds, 0);
    debt_after := greatest(current_debt + debt_incurred, 0);

    select
      coalesce(
        pg_catalog.sum(
          greatest(lots.granted_seconds - lots.consumed_seconds - lots.revoked_seconds, 0)
        ) filter (where lots.lot_type = 'subscription_cycle'),
        0
      )::integer,
      coalesce(
        pg_catalog.sum(
          greatest(lots.granted_seconds - lots.consumed_seconds - lots.revoked_seconds, 0)
        ) filter (where lots.lot_type = 'pack_order'),
        0
      )::integer,
      pg_catalog.min(lots.pack_expires_at) filter (
        where lots.lot_type = 'pack_order'
          and lots.granted_seconds - lots.consumed_seconds - lots.revoked_seconds > 0
      )
    into subscription_available, pack_available, next_pack_expiry
    from public.credit_lots as lots
    where lots.user_id = job_row.user_id
      and lots.status = 'active'
      and lots.lot_type in ('subscription_cycle', 'pack_order')
      and (lots.pack_expires_at is null or lots.pack_expires_at > settlement_now)
      and (
        lots.lot_type <> 'pack_order'
        or not exists (
          select 1
          from public.billing_orders as orders
          where orders.user_id = job_row.user_id
            and orders.status = 'refund_pending'
            and orders.polar_order_id = lots.source_key
        )
      );

    update public.entitlements
    set subscription_available_seconds = subscription_available,
        pack_available_seconds = pack_available,
        pack_expires_at = next_pack_expiry,
        debt_seconds = debt_after,
        is_blocked = debt_after >= p_debt_cap_seconds,
        last_balance_sync_at = settlement_now,
        updated_at = settlement_now
    where user_id = job_row.user_id;
  else
    debt_after := coalesce(
      (
        select debt_seconds
        from public.entitlements
        where user_id = job_row.user_id
      ),
      0
    );
  end if;

  insert into public.usage_settlements (
    job_id,
    user_id,
    lease_token,
    duration_seconds,
    subscription_seconds,
    pack_seconds,
    debt_incurred_seconds,
    entitlement_debt_after_seconds,
    settled_at
  )
  values (
    p_job_id,
    job_row.user_id,
    p_lease_token,
    effective_duration,
    subscription_consumed,
    pack_consumed,
    debt_incurred,
    debt_after,
    settlement_now
  )
  returning * into settlement_row;

  return pg_catalog.jsonb_build_object(
    'resolution_type', settlement_resolution,
    'settlement', pg_catalog.to_jsonb(settlement_row)
  );
end;
$$;

drop function public.prune_usage_ledger(integer);
drop table public.usage_ledger;

comment on table public.usage_settlements is
  'One immutable usage charge and history record per completed job.';
