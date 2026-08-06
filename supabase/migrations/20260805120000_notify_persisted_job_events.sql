-- Wake API replicas after a durable job event commits. The notification is a
-- coalescible hint only; consumers always fetch tenant-scoped persisted rows.

create or replace function public.notify_job_event_available()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog
as $$
begin
  perform pg_catalog.pg_notify(
    'job_event_available',
    pg_catalog.json_build_object('job_id', new.job_id)::text
  );
  return new;
end;
$$;

drop trigger if exists job_event_available_trigger on public.job_events;
create trigger job_event_available_trigger
after insert on public.job_events
for each row
execute function public.notify_job_event_available();

revoke all on function public.notify_job_event_available()
  from public, anon, authenticated, service_role;

comment on function public.notify_job_event_available() is
  'Emits a job-scoped wake hint after a durable event commits.';
comment on trigger job_event_available_trigger on public.job_events is
  'Wakes API replicas so local SSE subscribers can fetch and fan out durable events.';
