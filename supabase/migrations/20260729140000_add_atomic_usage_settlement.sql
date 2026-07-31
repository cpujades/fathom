-- Settle post-processing usage exactly once while the caller owns the job.
--
-- Credit consumption, debt, entitlement snapshots, settlement audit data, and
-- usage ledger rows commit in one transaction. Existing jobs and jobs created
-- by a rolling old application instance are exempt because their settlement
-- state cannot be reconstructed safely. New application instances explicitly
-- mark newly created jobs as settlement-required.

alter table public.jobs
  add column if not exists usage_settlement_required boolean not null default false;

-- Keep the existing claim command safe for a rolling old worker: it may only
-- claim explicitly exempt jobs. New workers use the separate settled claim
-- command and can process both legacy and settlement-required jobs.
create or replace function public.claim_next_job(p_lease_for interval)
returns public.jobs
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  job_row public.jobs;
begin
  if p_lease_for is null
    or p_lease_for <= interval '0 seconds'
    or p_lease_for > interval '1 hour'
  then
    raise exception 'lease duration must be between 0 seconds and 1 hour'
      using errcode = '22023';
  end if;

  with candidate as (
    select id
    from public.jobs
    where status = 'queued'
      and not usage_settlement_required
      and (run_after is null or run_after <= pg_catalog.now())
    order by created_at asc
    for update skip locked
    limit 1
  )
  update public.jobs
  set status = 'running',
      stage = 'running',
      progress = 10,
      status_message = 'Starting summary job',
      claimed_at = pg_catalog.now(),
      heartbeat_at = pg_catalog.now(),
      lease_token = pg_catalog.gen_random_uuid(),
      lease_expires_at = pg_catalog.now() + p_lease_for,
      attempt_count = attempt_count + 1,
      run_after = null,
      updated_at = pg_catalog.now()
  where id in (select id from candidate)
  returning * into job_row;

  return job_row;
end;
$$;

create or replace function public.claim_next_settled_job(p_lease_for interval)
returns public.jobs
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  job_row public.jobs;
begin
  if p_lease_for is null
    or p_lease_for <= interval '0 seconds'
    or p_lease_for > interval '1 hour'
  then
    raise exception 'lease duration must be between 0 seconds and 1 hour'
      using errcode = '22023';
  end if;

  with candidate as (
    select id
    from public.jobs
    where status = 'queued'
      and (run_after is null or run_after <= pg_catalog.now())
    order by created_at asc
    for update skip locked
    limit 1
  )
  update public.jobs
  set status = 'running',
      stage = 'running',
      progress = 10,
      status_message = 'Starting summary job',
      claimed_at = pg_catalog.now(),
      heartbeat_at = pg_catalog.now(),
      lease_token = pg_catalog.gen_random_uuid(),
      lease_expires_at = pg_catalog.now() + p_lease_for,
      attempt_count = attempt_count + 1,
      run_after = null,
      updated_at = pg_catalog.now()
  where id in (select id from candidate)
  returning * into job_row;

  return job_row;
end;
$$;

create table if not exists public.usage_settlements (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null unique references public.jobs (id) on delete restrict,
  user_id uuid not null,
  lease_token uuid not null,
  duration_seconds integer not null,
  subscription_seconds integer not null default 0,
  pack_seconds integer not null default 0,
  debt_incurred_seconds integer not null default 0,
  entitlement_debt_after_seconds integer not null default 0,
  settled_at timestamptz not null default now(),
  constraint usage_settlements_duration_check check (duration_seconds >= 0),
  constraint usage_settlements_subscription_check check (subscription_seconds >= 0),
  constraint usage_settlements_pack_check check (pack_seconds >= 0),
  constraint usage_settlements_debt_check check (debt_incurred_seconds >= 0),
  constraint usage_settlements_debt_after_check check (entitlement_debt_after_seconds >= 0),
  constraint usage_settlements_balance_check check (
    subscription_seconds + pack_seconds + debt_incurred_seconds = duration_seconds
  )
);

alter table public.usage_ledger
  add column if not exists settlement_id uuid
    references public.usage_settlements (id) on delete restrict;

create unique index if not exists usage_ledger_one_source_per_settlement_idx
  on public.usage_ledger (settlement_id, source)
  where settlement_id is not null;

create index if not exists usage_settlements_user_settled_idx
  on public.usage_settlements (user_id, settled_at desc);

alter table public.usage_settlements enable row level security;

revoke all on table public.usage_settlements from anon, authenticated;
grant select, insert on table public.usage_settlements to service_role;

comment on table public.usage_settlements is
  'One immutable, lease-fenced usage settlement per job.';
comment on column public.jobs.usage_settlement_required is
  'True when terminal success requires a matching usage_settlements row.';
comment on column public.usage_ledger.settlement_id is
  'Links new ledger rows to their atomic job settlement; null identifies legacy rows.';

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

  if subscription_consumed > 0 then
    insert into public.usage_ledger (
      user_id,
      job_id,
      settlement_id,
      seconds_used,
      source,
      created_at
    )
    values (
      job_row.user_id,
      p_job_id,
      settlement_row.id,
      subscription_consumed,
      'subscription',
      settlement_now
    );
  end if;

  if pack_consumed > 0 then
    insert into public.usage_ledger (
      user_id,
      job_id,
      settlement_id,
      seconds_used,
      source,
      created_at
    )
    values (
      job_row.user_id,
      p_job_id,
      settlement_row.id,
      pack_consumed,
      'pack',
      settlement_now
    );
  end if;

  return pg_catalog.jsonb_build_object(
    'resolution_type', settlement_resolution,
    'settlement', pg_catalog.to_jsonb(settlement_row)
  );
end;
$$;

create or replace function public.complete_job_after_settlement(
  p_job_id uuid,
  p_summary_id uuid,
  p_lease_token uuid
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  updated_count integer;
begin
  update public.jobs
  set status = 'succeeded',
      stage = 'completed',
      progress = 100,
      status_message = 'Summary ready',
      summary_id = p_summary_id,
      error_code = null,
      error_message = null,
      last_error_at = null,
      run_after = null,
      claimed_at = null,
      heartbeat_at = null,
      lease_token = null,
      lease_expires_at = null,
      updated_at = pg_catalog.now()
  where id = p_job_id
    and status = 'running'
    and lease_token = p_lease_token
    and lease_expires_at > pg_catalog.now()
    and (
      not usage_settlement_required
      or exists (
        select 1
        from public.usage_settlements
        where job_id = p_job_id
      )
    )
    and exists (
      select 1
      from public.summaries
      where id = p_summary_id
        and status = 'ready'
        and pg_catalog.btrim(summary_markdown) <> ''
    );

  get diagnostics updated_count = row_count;
  return updated_count = 1;
end;
$$;

create or replace function public.requeue_unsettled_jobs()
returns integer
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  updated_count integer;
begin
  update public.jobs as jobs
  set status = 'queued',
      stage = 'finalizing',
      progress = 98,
      status_message = 'Finalizing your briefing; retrying shortly',
      error_code = 'usage_settlement_missing',
      error_message = 'Usage settlement was missing after completion.',
      last_error_at = pg_catalog.now(),
      run_after = pg_catalog.now(),
      claimed_at = null,
      heartbeat_at = null,
      lease_token = null,
      lease_expires_at = null,
      updated_at = pg_catalog.now()
  where jobs.status = 'succeeded'
    and jobs.usage_settlement_required
    and not exists (
      select 1
      from public.usage_settlements
      where usage_settlements.job_id = jobs.id
    )
    and not exists (
      select 1
      from public.jobs as active_jobs
      where active_jobs.id <> jobs.id
        and active_jobs.user_id = jobs.user_id
        and active_jobs.source_key = jobs.source_key
        and active_jobs.status in ('queued', 'running')
    );

  get diagnostics updated_count = row_count;
  return updated_count;
end;
$$;

-- Preserve the current stale-job recovery, but keep generated work visibly in
-- finalization so a crash after summary creation does not look like a restart.
create or replace function public.requeue_stale_jobs(stale_after interval)
returns integer
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  updated_count integer;
begin
  if stale_after is null or stale_after <= interval '0 seconds' then
    raise exception 'stale interval must be greater than 0 seconds'
      using errcode = '22023';
  end if;

  update public.jobs as jobs
  set status = 'queued',
      stage = case
        when exists (
          select 1
          from public.summaries
          where summaries.id = jobs.summary_id
            and summaries.status = 'ready'
            and pg_catalog.btrim(summaries.summary_markdown) <> ''
        ) then 'finalizing'
        else 'queued'
      end,
      progress = case
        when exists (
          select 1
          from public.summaries
          where summaries.id = jobs.summary_id
            and summaries.status = 'ready'
            and pg_catalog.btrim(summaries.summary_markdown) <> ''
        ) then 98
        else 5
      end,
      status_message = case
        when exists (
          select 1
          from public.summaries
          where summaries.id = jobs.summary_id
            and summaries.status = 'ready'
            and pg_catalog.btrim(summaries.summary_markdown) <> ''
        ) then 'Finalizing your briefing; retrying shortly'
        else 'Queued for retry'
      end,
      error_code = 'stale_job_requeued',
      error_message = 'Requeued after worker lease expired.',
      last_error_at = pg_catalog.now(),
      run_after = pg_catalog.now(),
      claimed_at = null,
      heartbeat_at = null,
      lease_token = null,
      lease_expires_at = null,
      updated_at = pg_catalog.now()
  where jobs.status = 'running'
    and (
      (jobs.lease_expires_at is not null and jobs.lease_expires_at <= pg_catalog.now())
      or (
        jobs.lease_expires_at is null
        and jobs.claimed_at is not null
        and jobs.claimed_at < pg_catalog.now() - stale_after
      )
    );

  get diagnostics updated_count = row_count;
  return updated_count;
end;
$$;

-- Preserve the existing five-argument command for rolling-deploy
-- compatibility. Old application instances may still create a cached job in
-- its historical terminal form, so those compatibility rows are explicitly
-- settlement-exempt. All jobs created through the new command explicitly
-- require settlement.
create or replace function public.create_or_reuse_job(
  p_user_id uuid,
  p_url text,
  p_source_key text,
  p_duration_seconds integer default null,
  p_summary_id uuid default null
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  job_row public.jobs;
begin
  if p_user_id is null then
    raise exception 'user id is required' using errcode = '22023';
  end if;
  if p_url is null or pg_catalog.btrim(p_url) = '' then
    raise exception 'url is required' using errcode = '22023';
  end if;
  if p_source_key is null
    or p_source_key <> pg_catalog.btrim(p_source_key)
    or pg_catalog.char_length(p_source_key) not between 1 and 200
  then
    raise exception 'source key must contain 1 to 200 non-padded characters'
      using errcode = '22023';
  end if;
  if p_source_key <> public.derive_job_source_key(p_url) then
    raise exception 'source key does not match the canonical url'
      using errcode = '22023';
  end if;
  if p_duration_seconds is not null and p_duration_seconds < 0 then
    raise exception 'duration seconds cannot be negative' using errcode = '22023';
  end if;
  if p_summary_id is not null
    and not exists (
      select 1
      from public.summaries
      where id = p_summary_id
        and status = 'ready'
        and pg_catalog.btrim(summary_markdown) <> ''
    )
  then
    raise exception 'cached summary must be ready and non-empty'
      using errcode = '22023';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(p_user_id::text || ':' || p_source_key, 0)
  );

  select *
  into job_row
  from public.jobs
  where user_id = p_user_id
    and source_key = p_source_key
    and status in ('queued', 'running')
  order by created_at desc
  limit 1;

  if found then
    return pg_catalog.jsonb_build_object(
      'resolution_type', 'joined_existing',
      'job', pg_catalog.to_jsonb(job_row)
    );
  end if;

  select jobs.*
  into job_row
  from public.jobs as jobs
  join public.summaries as summaries
    on summaries.id = jobs.summary_id
  where jobs.user_id = p_user_id
    and jobs.source_key = p_source_key
    and jobs.status in ('succeeded', 'deleted')
    and summaries.status = 'ready'
    and pg_catalog.btrim(summaries.summary_markdown) <> ''
  order by jobs.created_at desc
  limit 1;

  if found then
    if job_row.status = 'deleted' then
      update public.jobs
      set status = 'succeeded',
          stage = 'completed',
          progress = 100,
          status_message = 'Using an existing briefing',
          error_code = null,
          error_message = null
      where id = job_row.id
      returning * into job_row;
    end if;

    return pg_catalog.jsonb_build_object(
      'resolution_type', 'reused_ready',
      'job', pg_catalog.to_jsonb(job_row)
    );
  end if;

  insert into public.jobs (
    user_id,
    status,
    url,
    source_key,
    duration_seconds,
    summary_id,
    stage,
    progress,
    status_message,
    usage_settlement_required
  )
  values (
    p_user_id,
    case when p_summary_id is null then 'queued' else 'succeeded' end,
    p_url,
    p_source_key,
    p_duration_seconds,
    p_summary_id,
    case when p_summary_id is null then 'queued' else 'cached' end,
    case when p_summary_id is null then 5 else 100 end,
    case
      when p_summary_id is null then 'Queued — waiting for a worker'
      else 'Using an existing briefing'
    end,
    false
  )
  returning * into job_row;

  return pg_catalog.jsonb_build_object(
    'resolution_type', 'new',
    'job', pg_catalog.to_jsonb(job_row)
  );
end;
$$;

-- New application instances use a separate command so old API/worker
-- processes cannot produce a settlement-required job through code that does
-- not know how to settle it. The compatibility command and this upgrade
-- execute in one transaction under the same user/source advisory lock.
create or replace function public.create_or_reuse_settled_job(
  p_user_id uuid,
  p_url text,
  p_source_key text,
  p_duration_seconds integer,
  p_summary_id uuid,
  p_cached_lease_for interval default interval '2 minutes'
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  resolution jsonb;
  job_row public.jobs;
  cached_now timestamptz;
begin
  if p_summary_id is not null
    and (
      p_cached_lease_for is null
      or p_cached_lease_for <= interval '0 seconds'
      or p_cached_lease_for > interval '1 hour'
    )
  then
    raise exception 'cached lease duration must be between 0 seconds and 1 hour'
      using errcode = '22023';
  end if;

  resolution := public.create_or_reuse_job(
    p_user_id,
    p_url,
    p_source_key,
    p_duration_seconds,
    p_summary_id
  );

  if resolution ->> 'resolution_type' <> 'new' then
    return resolution;
  end if;

  if p_summary_id is null then
    update public.jobs
    set usage_settlement_required = true,
        updated_at = pg_catalog.now()
    where id = (resolution -> 'job' ->> 'id')::uuid
    returning * into job_row;
  else
    cached_now := pg_catalog.now();
    update public.jobs
    set status = 'running',
        stage = 'finalizing',
        progress = 98,
        status_message = 'Finalizing your briefing',
        usage_settlement_required = true,
        attempt_count = 1,
        claimed_at = cached_now,
        heartbeat_at = cached_now,
        lease_token = pg_catalog.gen_random_uuid(),
        lease_expires_at = cached_now + p_cached_lease_for,
        updated_at = cached_now
    where id = (resolution -> 'job' ->> 'id')::uuid
    returning * into job_row;
  end if;

  if not found then
    raise exception 'settlement-required job could not be prepared' using errcode = '55000';
  end if;

  return pg_catalog.jsonb_build_object(
    'resolution_type', 'new',
    'job', pg_catalog.to_jsonb(job_row)
  );
end;
$$;

revoke all on function public.settle_job_usage(uuid, uuid, integer)
  from public, anon, authenticated;
revoke all on function public.complete_job_after_settlement(uuid, uuid, uuid)
  from public, anon, authenticated;
revoke all on function public.requeue_unsettled_jobs()
  from public, anon, authenticated;
revoke all on function public.requeue_stale_jobs(interval)
  from public, anon, authenticated;
revoke all on function public.claim_next_job(interval)
  from public, anon, authenticated;
revoke all on function public.claim_next_settled_job(interval)
  from public, anon, authenticated;
revoke all on function public.create_or_reuse_job(uuid, text, text, integer, uuid)
  from public, anon, authenticated;
revoke all on function public.create_or_reuse_settled_job(uuid, text, text, integer, uuid, interval)
  from public, anon, authenticated;

grant execute on function public.settle_job_usage(uuid, uuid, integer)
  to service_role;
grant execute on function public.complete_job_after_settlement(uuid, uuid, uuid)
  to service_role;
grant execute on function public.requeue_unsettled_jobs()
  to service_role;
grant execute on function public.requeue_stale_jobs(interval)
  to service_role;
grant execute on function public.claim_next_job(interval)
  to service_role;
grant execute on function public.claim_next_settled_job(interval)
  to service_role;
grant execute on function public.create_or_reuse_job(uuid, text, text, integer, uuid)
  to service_role;
grant execute on function public.create_or_reuse_settled_job(uuid, text, text, integer, uuid, interval)
  to service_role;
