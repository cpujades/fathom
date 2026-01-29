-- Add progress metadata fields for job streaming updates.

alter table public.jobs
  add column if not exists stage text,
  add column if not exists progress integer,
  add column if not exists status_message text;

alter table public.jobs
  alter column stage set default 'queued',
  alter column progress set default 0,
  alter column status_message set default 'Queued';

update public.jobs
set stage = coalesce(stage, status),
    progress = coalesce(progress, case
      when status = 'queued' then 5
      when status = 'running' then 35
      when status = 'succeeded' then 100
      when status = 'failed' then 100
      else 0
    end),
    status_message = coalesce(status_message, case
      when status = 'queued' then 'Queued'
      when status = 'running' then 'Working'
      when status = 'succeeded' then 'Completed'
      when status = 'failed' then 'Failed'
      else 'Queued'
    end);

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
      stage = 'running',
      progress = 10,
      status_message = 'Starting summary job',
      claimed_at = now(),
      attempt_count = attempt_count + 1,
      run_after = null,
      updated_at = now()
  where id in (select id from candidate)
  returning * into job_row;

  return job_row;
end;
$$;
