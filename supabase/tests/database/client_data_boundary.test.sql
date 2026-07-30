begin;

set local search_path = extensions, public, pg_catalog;

select plan(25);

select is(
  (
    select pg_catalog.count(*)
    from pg_catalog.pg_class
    join pg_catalog.pg_namespace
      on pg_namespace.oid = pg_class.relnamespace
    where pg_namespace.nspname = 'public'
      and pg_class.relname in (
        'jobs',
        'summaries',
        'transcripts',
        'plans',
        'entitlements',
        'usage_ledger',
        'polar_customers',
        'billing_webhook_events',
        'billing_orders',
        'credit_lots',
        'api_rate_limit_buckets',
        'usage_settlements',
        'transcript_segments',
        'job_events'
      )
      and pg_class.relrowsecurity
  ),
  14::bigint,
  'every application table has row-level security enabled'
);

select is(
  (
    select pg_catalog.count(*)
    from (
      values
        ('jobs'),
        ('summaries'),
        ('transcripts'),
        ('plans'),
        ('entitlements'),
        ('usage_ledger'),
        ('polar_customers'),
        ('billing_webhook_events'),
        ('billing_orders'),
        ('credit_lots'),
        ('api_rate_limit_buckets'),
        ('usage_settlements'),
        ('transcript_segments'),
        ('job_events')
    ) as application_tables(table_name)
    where pg_catalog.has_table_privilege(
      'authenticated',
      'public.' || table_name,
      'select'
    )
  ),
  3::bigint,
  'authenticated clients can select only jobs, summaries, and job events'
);

select ok(
  pg_catalog.has_table_privilege('authenticated', 'public.jobs', 'select'),
  'authenticated clients can read their RLS-scoped jobs'
);
select ok(
  pg_catalog.has_table_privilege('authenticated', 'public.summaries', 'select'),
  'authenticated clients can read settled RLS-scoped summaries'
);
select ok(
  pg_catalog.has_table_privilege('authenticated', 'public.job_events', 'select'),
  'authenticated clients can read their RLS-scoped job events'
);
select ok(
  not pg_catalog.has_table_privilege('authenticated', 'public.transcripts', 'select'),
  'authenticated clients cannot read the transcript cache directly'
);
select ok(
  not pg_catalog.has_table_privilege('authenticated', 'public.entitlements', 'select'),
  'authenticated clients cannot read billing state directly'
);

select is(
  (
    select pg_catalog.count(*)
    from (
      values
        ('jobs'),
        ('summaries'),
        ('transcripts'),
        ('plans'),
        ('entitlements'),
        ('usage_ledger'),
        ('polar_customers'),
        ('billing_webhook_events'),
        ('billing_orders'),
        ('credit_lots'),
        ('api_rate_limit_buckets'),
        ('usage_settlements'),
        ('transcript_segments'),
        ('job_events')
    ) as application_tables(table_name)
    where pg_catalog.has_table_privilege('authenticated', 'public.' || table_name, 'insert')
      or pg_catalog.has_table_privilege('authenticated', 'public.' || table_name, 'update')
      or pg_catalog.has_table_privilege('authenticated', 'public.' || table_name, 'delete')
  ),
  0::bigint,
  'authenticated clients cannot mutate application tables'
);

select is(
  (
    select pg_catalog.count(*)
    from (
      values
        ('jobs'),
        ('summaries'),
        ('transcripts'),
        ('plans'),
        ('entitlements'),
        ('usage_ledger'),
        ('polar_customers'),
        ('billing_webhook_events'),
        ('billing_orders'),
        ('credit_lots'),
        ('api_rate_limit_buckets'),
        ('usage_settlements'),
        ('transcript_segments'),
        ('job_events')
    ) as application_tables(table_name)
    where pg_catalog.has_table_privilege('anon', 'public.' || table_name, 'select')
      or pg_catalog.has_table_privilege('anon', 'public.' || table_name, 'insert')
      or pg_catalog.has_table_privilege('anon', 'public.' || table_name, 'update')
      or pg_catalog.has_table_privilege('anon', 'public.' || table_name, 'delete')
  ),
  0::bigint,
  'anonymous clients have no application-table privileges'
);

select is(
  (
    select pg_catalog.array_agg(
      pg_catalog.format('%s.%s', tablename, policyname)
      order by tablename, policyname
    )
    from pg_catalog.pg_policies
    where schemaname = 'public'
      and roles @> array['authenticated'::name]
  ),
  array[
    'job_events.job_events_select_via_jobs',
    'jobs.jobs_select_own',
    'summaries.summaries_select_via_settled_jobs'
  ]::text[],
  'the browser has only the three intended tenant-scoped read policies'
);

select ok(
  not pg_catalog.has_sequence_privilege(
    'authenticated',
    'public.job_events_sequence_id_seq',
    'usage'
  ),
  'authenticated clients cannot allocate event sequence IDs'
);
select ok(
  not pg_catalog.has_sequence_privilege(
    'anon',
    'public.job_events_sequence_id_seq',
    'usage'
  ),
  'anonymous clients cannot allocate event sequence IDs'
);
select ok(
  pg_catalog.has_sequence_privilege(
    'service_role',
    'public.job_events_sequence_id_seq',
    'usage'
  ),
  'the backend can allocate event sequence IDs'
);

select ok(
  not pg_catalog.has_function_privilege(
    'service_role',
    'public.claim_next_job(interval)',
    'execute'
  ),
  'the backend cannot call the settlement-exempt compatibility claim directly'
);
select ok(
  not pg_catalog.has_function_privilege(
    'service_role',
    'public.create_or_reuse_job(uuid,text,text,integer,uuid)',
    'execute'
  ),
  'the backend cannot call settlement-exempt compatibility creation directly'
);
select ok(
  pg_catalog.has_function_privilege(
    'service_role',
    'public.claim_next_settled_job(interval)',
    'execute'
  ),
  'the backend can claim settlement-aware jobs'
);
select ok(
  pg_catalog.has_function_privilege(
    'service_role',
    'public.create_or_reuse_settled_job(uuid,text,text,integer,uuid,interval)',
    'execute'
  ),
  'the backend can use settlement-aware session creation'
);

select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.set_updated_at()'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'the update trigger has a fixed search path'
);
select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.notify_job_created()'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'the notification trigger has a fixed search path'
);
select ok(
  not pg_catalog.has_function_privilege(
    'authenticated',
    'public.notify_job_created()',
    'execute'
  ),
  'authenticated clients cannot invoke the notification trigger function'
);

insert into public.transcripts (
  id,
  url_hash,
  video_id,
  transcript_text,
  provider_model
)
values (
  'c1000000-0000-0000-0000-000000000001',
  'client-boundary-transcript',
  'client-boundary',
  'Private transcript.',
  'groq:test'
);

insert into public.summaries (
  id,
  transcript_id,
  prompt_key,
  summary_model,
  summary_markdown,
  user_id,
  status,
  status_updated_at,
  ready_at
)
values (
  'c2000000-0000-0000-0000-000000000001',
  'c1000000-0000-0000-0000-000000000001',
  'briefing-v5-evidence',
  'openrouter:test',
  '# Settled briefing',
  'c3000000-0000-0000-0000-000000000001',
  'ready',
  pg_catalog.now(),
  pg_catalog.now()
);

insert into public.jobs (
  id,
  user_id,
  status,
  url,
  source_key,
  summary_id,
  stage,
  progress,
  status_message
)
values (
  'c4000000-0000-0000-0000-000000000001',
  'c3000000-0000-0000-0000-000000000001',
  'running',
  'https://www.youtube.com/watch?v=client-boundary',
  'youtube:client-boundary',
  'c2000000-0000-0000-0000-000000000001',
  'finalizing',
  98,
  'Finalizing your briefing'
);

set local role authenticated;
select pg_catalog.set_config(
  'request.jwt.claim.sub',
  'c3000000-0000-0000-0000-000000000001',
  true
);

select is(
  (
    select pg_catalog.count(*)
    from public.summaries
    where id = 'c2000000-0000-0000-0000-000000000001'
  ),
  0::bigint,
  'a ready draft remains hidden while its job is still finalizing'
);

reset role;
update public.jobs
set status = 'succeeded',
    stage = 'completed',
    progress = 100,
    status_message = 'Summary ready'
where id = 'c4000000-0000-0000-0000-000000000001';

set local role authenticated;
select pg_catalog.set_config(
  'request.jwt.claim.sub',
  'c3000000-0000-0000-0000-000000000001',
  true
);
select is(
  (
    select pg_catalog.count(*)
    from public.summaries
    where id = 'c2000000-0000-0000-0000-000000000001'
  ),
  1::bigint,
  'the owner can read a ready summary after terminal settlement'
);

select pg_catalog.set_config(
  'request.jwt.claim.sub',
  'c3000000-0000-0000-0000-000000000002',
  true
);
select is(
  (
    select pg_catalog.count(*)
    from public.summaries
    where id = 'c2000000-0000-0000-0000-000000000001'
  ),
  0::bigint,
  'another tenant cannot read the settled summary'
);

reset role;
update public.summaries
set status = 'failed',
    summary_markdown = '',
    status_updated_at = pg_catalog.now(),
    ready_at = null,
    failed_at = pg_catalog.now()
where id = 'c2000000-0000-0000-0000-000000000001';

set local role authenticated;
select pg_catalog.set_config(
  'request.jwt.claim.sub',
  'c3000000-0000-0000-0000-000000000001',
  true
);
select is(
  (
    select pg_catalog.count(*)
    from public.summaries
    where id = 'c2000000-0000-0000-0000-000000000001'
  ),
  0::bigint,
  'a failed or empty summary is never browser-readable'
);

reset role;
update public.summaries
set status = 'ready',
    summary_markdown = '# Settled briefing',
    status_updated_at = pg_catalog.now(),
    ready_at = pg_catalog.now(),
    failed_at = null
where id = 'c2000000-0000-0000-0000-000000000001';
update public.jobs
set status = 'deleted'
where id = 'c4000000-0000-0000-0000-000000000001';

set local role authenticated;
select pg_catalog.set_config(
  'request.jwt.claim.sub',
  'c3000000-0000-0000-0000-000000000001',
  true
);
select is(
  (
    select pg_catalog.count(*)
    from public.summaries
    where id = 'c2000000-0000-0000-0000-000000000001'
  ),
  1::bigint,
  'archiving preserves the owner read path without regenerating the summary'
);

select * from finish();

rollback;
