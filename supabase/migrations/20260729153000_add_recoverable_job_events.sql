-- Make persisted job events the tenant-scoped source of truth for session
-- stream cursors. State-change events are written in the same transaction as
-- the job mutation, while richer application milestones remain additive.

alter table public.job_events
  add column if not exists sequence_id bigint;

create sequence if not exists public.job_events_sequence_id_seq;

alter sequence public.job_events_sequence_id_seq
  owned by public.job_events.sequence_id;

with ordered_events as (
  select
    id,
    pg_catalog.row_number() over (
      order by created_at asc, id asc
    ) as sequence_id
  from public.job_events
  where sequence_id is null
)
update public.job_events as events
set sequence_id = ordered_events.sequence_id
from ordered_events
where events.id = ordered_events.id;

select pg_catalog.setval(
  'public.job_events_sequence_id_seq',
  greatest(
    coalesce((select pg_catalog.max(sequence_id) from public.job_events), 0::bigint),
    1::bigint
  ),
  exists (select 1 from public.job_events)
);

alter table public.job_events
  alter column sequence_id set default pg_catalog.nextval('public.job_events_sequence_id_seq'),
  alter column sequence_id set not null;

create unique index if not exists job_events_sequence_id_idx
  on public.job_events (sequence_id);

drop index if exists public.job_events_job_id_created_at_idx;
create index if not exists job_events_job_id_sequence_idx
  on public.job_events (job_id, sequence_id);

revoke all on table public.job_events from anon, authenticated, service_role;
grant select on table public.job_events to authenticated;
grant select, insert on table public.job_events to service_role;
grant usage, select on sequence public.job_events_sequence_id_seq to service_role;

drop policy if exists "job_events_select_via_jobs" on public.job_events;
create policy "job_events_select_via_jobs"
on public.job_events
for select
to authenticated
using (
  exists (
    select 1
    from public.jobs
    where jobs.id = job_events.job_id
      and jobs.user_id = (select auth.uid())
  )
);

create or replace function public.record_job_state_event()
returns trigger
language plpgsql
security definer
set search_path = pg_catalog
as $$
begin
  insert into public.job_events (
    job_id,
    event_type,
    stage,
    message,
    metadata
  )
  values (
    new.id,
    case when tg_op = 'INSERT' then 'job_created' else 'job_state_changed' end,
    new.stage,
    new.status_message,
    pg_catalog.jsonb_build_object(
      'status', new.status,
      'progress', new.progress,
      'summary_id', new.summary_id,
      'error_code', new.error_code
    )
  );
  return new;
end;
$$;

revoke all on function public.record_job_state_event()
  from public, anon, authenticated, service_role;

drop trigger if exists job_state_event_insert_trigger on public.jobs;
create trigger job_state_event_insert_trigger
after insert on public.jobs
for each row
execute function public.record_job_state_event();

drop trigger if exists job_state_event_update_trigger on public.jobs;
create trigger job_state_event_update_trigger
after update of
  status,
  stage,
  progress,
  status_message,
  summary_id,
  error_code
on public.jobs
for each row
when (
  old.status is distinct from new.status
  or old.stage is distinct from new.stage
  or old.progress is distinct from new.progress
  or old.status_message is distinct from new.status_message
  or old.summary_id is distinct from new.summary_id
  or old.error_code is distinct from new.error_code
)
execute function public.record_job_state_event();

comment on column public.job_events.sequence_id is
  'Stable monotonic cursor used for tenant-scoped SSE replay.';
comment on function public.record_job_state_event() is
  'Persists a job state event transactionally; callable only as a trigger.';
