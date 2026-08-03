-- Wake workers for every newly queued job and expose the next durable retry
-- deadline without requiring interval-based queue polling.

create or replace function public.notify_job_available()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog
as $$
begin
  if new.status <> 'queued' then
    return new;
  end if;

  if tg_op = 'UPDATE' then
    if old.status is not distinct from new.status
       and old.run_after is not distinct from new.run_after then
      return new;
    end if;
  end if;

  -- The notification is only a coalescible hint. Keep job identifiers and
  -- timing metadata in the durable table instead of the transient payload.
  perform pg_catalog.pg_notify('job_available', '{}'::text);
  return new;
end;
$$;

drop trigger if exists job_insert_trigger on public.jobs;
drop trigger if exists job_available_trigger on public.jobs;
create trigger job_available_trigger
after insert or update of status, run_after on public.jobs
for each row
execute function public.notify_job_available();

drop function if exists public.notify_job_created();

revoke all on function public.notify_job_available()
  from public, anon, authenticated, service_role;

comment on function public.notify_job_available() is
  'Emits a transaction-safe wake hint whenever a job enters or reschedules the queued state.';
comment on trigger job_available_trigger on public.jobs is
  'Wakes workers for new jobs and durable delayed retries.';

create or replace function public.next_queued_job_delay_seconds()
returns double precision
language sql
stable
security definer
set search_path = pg_catalog
as $$
  with next_job as (
    select pg_catalog.min(jobs.run_after) as run_after
    from public.jobs
    where jobs.status = 'queued'
      and jobs.run_after is not null
  )
  select case
    when next_job.run_after is null then null
    when next_job.run_after <= pg_catalog.now() then 0::double precision
    else pg_catalog.date_part('epoch', next_job.run_after - pg_catalog.now())::double precision
  end
  from next_job;
$$;

revoke all on function public.next_queued_job_delay_seconds()
  from public, anon, authenticated;
grant execute on function public.next_queued_job_delay_seconds()
  to service_role;

comment on function public.next_queued_job_delay_seconds() is
  'Returns the database-clock delay until the next queued retry is runnable.';
