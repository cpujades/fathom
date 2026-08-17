-- Admit several billable jobs safely without moving credit before success.
-- Unsettled active durations act as a derived hold against the current balance.

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
  entitlement_row public.entitlements;
  cached_now timestamptz;
  active_job_count integer := 0;
  pending_seconds integer := 0;
  spendable_seconds integer := 0;
  available_seconds integer := 0;
  maximum_active_jobs constant integer := 3;
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
  if p_duration_seconds is null or p_duration_seconds = 0 then
    raise exception 'duration seconds must be positive' using errcode = '22023';
  end if;
  if p_duration_seconds < 0 then
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

  -- Serialize all billable admissions for this user. The source lock keeps the
  -- preflight aligned with same-source saves and compatibility reuse.
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('usage-admission:' || p_user_id::text, 0)
  );
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(p_user_id::text || ':' || p_source_key, 0)
  );

  if exists (
    select 1
    from public.jobs
    where user_id = p_user_id
      and source_key = p_source_key
      and status in ('queued', 'running')
  ) or exists (
    select 1
    from public.jobs as jobs
    join public.summaries as summaries
      on summaries.id = jobs.summary_id
    where jobs.user_id = p_user_id
      and jobs.source_key = p_source_key
      and jobs.status in ('succeeded', 'deleted')
      and summaries.status = 'ready'
      and pg_catalog.btrim(summaries.summary_markdown) <> ''
  ) then
    return public.create_or_reuse_job(
      p_user_id,
      p_url,
      p_source_key,
      p_duration_seconds,
      p_summary_id
    );
  end if;

  select *
  into entitlement_row
  from public.entitlements
  where user_id = p_user_id
  for update;

  if not found then
    raise exception 'billing entitlement is missing' using errcode = 'P0002';
  end if;

  select
    pg_catalog.count(*)::integer,
    coalesce(
      pg_catalog.sum(jobs.duration_seconds) filter (where settlements.job_id is null),
      0
    )::integer
  into active_job_count, pending_seconds
  from public.jobs as jobs
  left join public.usage_settlements as settlements
    on settlements.job_id = jobs.id
  where jobs.user_id = p_user_id
    and jobs.status in ('queued', 'running')
    and jobs.usage_settlement_required;

  spendable_seconds := greatest(
    entitlement_row.subscription_available_seconds
      + entitlement_row.pack_available_seconds,
    0
  );
  available_seconds := greatest(spendable_seconds - pending_seconds, 0);

  if entitlement_row.is_blocked then
    return pg_catalog.jsonb_build_object(
      'resolution_type', 'balance_blocked',
      'details', pg_catalog.jsonb_build_object(
        'debt_seconds', greatest(entitlement_row.debt_seconds, 0)
      )
    );
  end if;

  if active_job_count >= maximum_active_jobs then
    return pg_catalog.jsonb_build_object(
      'resolution_type', 'active_job_limit_reached',
      'details', pg_catalog.jsonb_build_object(
        'active_job_count', active_job_count,
        'maximum_active_jobs', maximum_active_jobs
      )
    );
  end if;

  if spendable_seconds <= 0 then
    return pg_catalog.jsonb_build_object(
      'resolution_type', 'no_video_time',
      'details', pg_catalog.jsonb_build_object('available_seconds', 0)
    );
  end if;

  if p_duration_seconds > available_seconds then
    if pending_seconds > 0 then
      return pg_catalog.jsonb_build_object(
        'resolution_type', 'video_time_committed',
        'details', pg_catalog.jsonb_build_object(
          'required_seconds', p_duration_seconds,
          'available_seconds', available_seconds,
          'pending_seconds', pending_seconds
        )
      );
    end if;

    return pg_catalog.jsonb_build_object(
      'resolution_type', 'insufficient_video_time',
      'details', pg_catalog.jsonb_build_object(
        'required_seconds', p_duration_seconds,
        'available_seconds', available_seconds
      )
    );
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
    raise exception 'settlement-required job could not be prepared'
      using errcode = '55000';
  end if;

  return pg_catalog.jsonb_build_object(
    'resolution_type', 'new',
    'job', pg_catalog.to_jsonb(job_row)
  );
end;
$$;

revoke all on function public.create_or_reuse_settled_job(
  uuid, text, text, integer, uuid, interval
) from public, anon, authenticated;
grant execute on function public.create_or_reuse_settled_job(
  uuid, text, text, integer, uuid, interval
) to service_role;

comment on function public.create_or_reuse_settled_job(
  uuid, text, text, integer, uuid, interval
) is
  'Creates billable jobs under an atomic three-job and pending-duration admission guard.';

-- Refund admission shares the user lock with job admission. Whichever command
-- commits first becomes authoritative: a new job blocks the refund, while a
-- started refund removes its pack credit before another job can be admitted.
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
    pg_catalog.hashtextextended('usage-admission:' || p_user_id::text, 0)
  );
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

  if exists (
    select 1
    from public.jobs
    where user_id = p_user_id
      and status in ('queued', 'running')
      and usage_settlement_required
  ) then
    return pg_catalog.jsonb_build_object(
      'resolution_type', 'active_jobs_in_progress'
    );
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

revoke all on function public.begin_pack_refund(uuid, text, integer)
from public, anon, authenticated;
grant execute on function public.begin_pack_refund(uuid, text, integer)
to service_role;

comment on function public.begin_pack_refund(uuid, text, integer) is
  'Starts a pack refund only when the user has no active billable briefings.';
