-- Fence worker attempts with renewable leases.
--
-- A worker may mutate a running job only while it holds the current lease
-- token. Legacy running rows without a lease remain recoverable through the
-- stale claimed_at fallback in requeue_stale_jobs.

alter table public.jobs
  add column if not exists lease_token uuid,
  add column if not exists lease_expires_at timestamptz,
  add column if not exists heartbeat_at timestamptz;

create index if not exists jobs_expired_lease_idx
  on public.jobs (lease_expires_at)
  where status = 'running';

drop function if exists public.claim_next_job();

create function public.claim_next_job(p_lease_for interval)
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

create or replace function public.renew_job_lease(
  p_job_id uuid,
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
  if p_lease_for is null
    or p_lease_for <= interval '0 seconds'
    or p_lease_for > interval '1 hour'
  then
    raise exception 'lease duration must be between 0 seconds and 1 hour'
      using errcode = '22023';
  end if;

  update public.jobs
  set heartbeat_at = pg_catalog.now(),
      lease_expires_at = pg_catalog.now() + p_lease_for,
      updated_at = pg_catalog.now()
  where id = p_job_id
    and status = 'running'
    and lease_token = p_lease_token
    and lease_expires_at > pg_catalog.now();

  get diagnostics updated_count = row_count;
  return updated_count = 1;
end;
$$;

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

  update public.jobs
  set status = 'queued',
      stage = 'queued',
      progress = 5,
      status_message = 'Queued for retry',
      error_code = 'stale_job_requeued',
      error_message = 'Requeued after worker lease expired.',
      last_error_at = pg_catalog.now(),
      run_after = pg_catalog.now(),
      claimed_at = null,
      heartbeat_at = null,
      lease_token = null,
      lease_expires_at = null,
      updated_at = pg_catalog.now()
  where status = 'running'
    and (
      (lease_expires_at is not null and lease_expires_at <= pg_catalog.now())
      or (
        lease_expires_at is null
        and claimed_at is not null
        and claimed_at < pg_catalog.now() - stale_after
      )
    );

  get diagnostics updated_count = row_count;
  return updated_count;
end;
$$;

revoke all on function public.claim_next_job(interval) from public, anon, authenticated;
revoke all on function public.renew_job_lease(uuid, uuid, interval) from public, anon, authenticated;
revoke all on function public.requeue_stale_jobs(interval) from public, anon, authenticated;

grant execute on function public.claim_next_job(interval) to service_role;
grant execute on function public.renew_job_lease(uuid, uuid, interval) to service_role;
grant execute on function public.requeue_stale_jobs(interval) to service_role;
