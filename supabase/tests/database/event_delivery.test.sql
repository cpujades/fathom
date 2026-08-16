begin;

set local search_path = extensions, public, pg_catalog;

select plan(25);

insert into auth.users (id)
values
  ('a2000000-0000-0000-0000-000000000001'),
  ('a2000000-0000-0000-0000-000000000002');

select col_not_null(
  'public',
  'job_events',
  'sequence_id',
  'every persisted event has a stable replay cursor'
);
select has_index(
  'public',
  'job_events',
  'job_events_sequence_id_idx',
  'event cursors have a unique index'
);
select index_is_unique(
  'public',
  'job_events',
  'job_events_sequence_id_idx',
  'event cursors cannot be reused'
);
select has_index(
  'public',
  'job_events',
  'job_events_job_id_sequence_idx',
  'tenant job replay is ordered efficiently'
);
select ok(
  has_table_privilege('authenticated', 'public.job_events', 'select'),
  'authenticated users can read RLS-scoped job events'
);
select ok(
  not has_table_privilege('authenticated', 'public.job_events', 'insert'),
  'authenticated users cannot create job events'
);
select ok(
  not has_table_privilege('anon', 'public.job_events', 'select'),
  'anonymous users cannot read job events'
);
select ok(
  has_table_privilege('service_role', 'public.job_events', 'insert'),
  'service code can append job events'
);
select ok(
  not has_table_privilege('service_role', 'public.job_events', 'update'),
  'service code cannot rewrite persisted events'
);
select policies_are(
  'public',
  'job_events',
  array['job_events_select_via_jobs'],
  'job events expose only their ownership policy'
);
select trigger_is(
  'public',
  'jobs',
  'job_state_event_insert_trigger',
  'public',
  'record_job_state_event',
  'job creation persists an event transactionally'
);
select trigger_is(
  'public',
  'jobs',
  'job_state_event_update_trigger',
  'public',
  'record_job_state_event',
  'job state changes persist events transactionally'
);
select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.record_job_state_event()'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'event trigger function has an immutable search path'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.record_job_state_event()',
    'execute'
  ),
  'authenticated users cannot invoke the trigger function'
);
select trigger_is(
  'public',
  'job_events',
  'job_event_available_trigger',
  'public',
  'notify_job_event_available',
  'persisted events publish a replica wake hint'
);
select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.notify_job_event_available()'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'event notification function has an immutable search path'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.notify_job_event_available()',
    'execute'
  ),
  'authenticated users cannot invoke the event notification function'
);
select ok(
  not has_function_privilege(
    'service_role',
    'public.notify_job_event_available()',
    'execute'
  ),
  'service code cannot publish event notifications directly'
);

insert into public.jobs (
  id,
  user_id,
  status,
  url,
  source_key,
  stage,
  progress,
  status_message
)
values
  (
    'a1000000-0000-0000-0000-000000000001',
    'a2000000-0000-0000-0000-000000000001',
    'queued',
    'https://www.youtube.com/watch?v=event-owner-a',
    'youtube:event-owner-a',
    'queued',
    5,
    'Queued'
  ),
  (
    'a1000000-0000-0000-0000-000000000002',
    'a2000000-0000-0000-0000-000000000002',
    'queued',
    'https://www.youtube.com/watch?v=event-owner-b',
    'youtube:event-owner-b',
    'queued',
    5,
    'Queued'
  );

select is(
  (select count(*) from public.job_events where job_id::text like 'a1000000-%'),
  2::bigint,
  'job inserts create one event each'
);

update public.jobs
set stage = 'transcribing',
    progress = 30,
    status_message = 'Transcribing'
where id = 'a1000000-0000-0000-0000-000000000001';

select is(
  (
    select count(*)
    from public.job_events
    where job_id = 'a1000000-0000-0000-0000-000000000001'
  ),
  2::bigint,
  'a relevant update appends one event'
);
select is(
  (
    select count(distinct sequence_id)
    from public.job_events
    where job_id::text like 'a1000000-%'
  ),
  3::bigint,
  'event cursors remain unique'
);
select ok(
  (
    select pg_catalog.max(sequence_id) > pg_catalog.min(sequence_id)
    from public.job_events
    where job_id = 'a1000000-0000-0000-0000-000000000001'
  ),
  'later state has a greater cursor'
);

set local role authenticated;
select pg_catalog.set_config(
  'request.jwt.claim.sub',
  'a2000000-0000-0000-0000-000000000001',
  true
);

select is(
  (select count(*) from public.job_events),
  2::bigint,
  'owner sees all events for their own job'
);
select is(
  (
    select count(*)
    from public.job_events
    where job_id = 'a1000000-0000-0000-0000-000000000002'
  ),
  0::bigint,
  'owner cannot replay another tenant job'
);

reset role;
set local role authenticated;
select pg_catalog.set_config(
  'request.jwt.claim.sub',
  'a2000000-0000-0000-0000-000000000002',
  true
);

select is(
  (select count(*) from public.job_events),
  1::bigint,
  'second owner sees only their own event'
);

select * from finish();

rollback;
