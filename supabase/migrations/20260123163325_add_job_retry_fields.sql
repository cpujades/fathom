-- Add job retry/backoff fields and claim function.

alter table public.jobs
  add column if not exists attempt_count integer not null default 0,
  add column if not exists last_error_at timestamptz,
  add column if not exists run_after timestamptz,
  add column if not exists claimed_at timestamptz;

-- Ensure users cannot update jobs (worker-only).
drop policy if exists "jobs_update_own" on public.jobs;

-- Claim the next runnable job atomically.
create or replace function public.claim_next_job()
returns public.jobs
language plpgsql
security definer
set search_path = public
as $$
declare
  job_row public.jobs;
begin
  with candidate as (
    select id
    from public.jobs
    where status = 'queued'
      and (run_after is null or run_after <= now())
    order by created_at asc
    for update skip locked
    limit 1
  )
  update public.jobs
  set status = 'running',
      claimed_at = now(),
      attempt_count = attempt_count + 1,
      run_after = null,
      updated_at = now()
  where id in (select id from candidate)
  returning * into job_row;

  return job_row;
end;
$$;

-- Requeue stale running jobs (e.g., worker crashed mid-job).
create or replace function public.requeue_stale_jobs(stale_after interval)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  updated_count integer;
begin
  update public.jobs
  set status = 'queued',
      error_code = 'stale_job_requeued',
      error_message = 'Requeued after worker timeout.',
      last_error_at = now(),
      run_after = now()
  where status = 'running'
    and claimed_at is not null
    and claimed_at < now() - stale_after;

  get diagnostics updated_count = row_count;
  return updated_count;
end;
$$;
