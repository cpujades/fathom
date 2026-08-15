begin;

set local search_path = extensions, public, pg_catalog;

select plan(47);

insert into auth.users (id)
values
  ('72000000-0000-0000-0000-000000000001'),
  ('72000000-0000-0000-0000-000000000002'),
  ('72000000-0000-0000-0000-000000000003');

select is(
  case
    when pg_catalog.btrim(markdown) <> '' and has_completed_job then 'ready'
    else 'failed'
  end,
  expected_status,
  description
)
from (
  values
    ('# Legacy briefing', true, 'ready', 'completed legacy non-empty summary backfills ready'),
    ('# Interrupted draft', false, 'failed', 'interrupted legacy non-empty draft backfills failed'),
    ('   ', true, 'failed', 'legacy empty summary backfills failed')
) as legacy_cases(markdown, has_completed_job, expected_status, description);

select col_not_null(
  'public',
  'summaries',
  'status',
  'summary lifecycle status is required'
);
select col_not_null(
  'public',
  'summaries',
  'status_updated_at',
  'summary lifecycle timestamp is required'
);
select has_check(
  'public',
  'summaries',
  'summary lifecycle consistency is database-enforced'
);

select ok(
  not has_function_privilege(
    'anon',
    'public.prepare_summary(uuid,uuid,uuid,uuid,uuid,text,text)',
    'execute'
  ),
  'anon cannot prepare summary generation'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.prepare_summary(uuid,uuid,uuid,uuid,uuid,text,text)',
    'execute'
  ),
  'authenticated users cannot prepare summary generation'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.prepare_summary(uuid,uuid,uuid,uuid,uuid,text,text)',
    'execute'
  ),
  'service role can prepare summary generation'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.update_summary_draft(uuid,uuid,text)',
    'execute'
  ),
  'authenticated users cannot mutate summary drafts'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.update_summary_draft(uuid,uuid,text)',
    'execute'
  ),
  'service role can mutate summary drafts'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.complete_summary_generation(uuid,uuid,text)',
    'execute'
  ),
  'authenticated users cannot complete summary generation'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.complete_summary_generation(uuid,uuid,text)',
    'execute'
  ),
  'service role can complete summary generation'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.fail_summary_generation(uuid,uuid)',
    'execute'
  ),
  'authenticated users cannot fail summary generation'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.fail_summary_generation(uuid,uuid)',
    'execute'
  ),
  'service role can fail summary generation'
);

select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.prepare_summary(uuid,uuid,uuid,uuid,uuid,text,text)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'prepare command has an immutable search path'
);
select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.update_summary_draft(uuid,uuid,text)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'draft command has an immutable search path'
);
select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.complete_summary_generation(uuid,uuid,text)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'complete command has an immutable search path'
);
select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.fail_summary_generation(uuid,uuid)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'failure command has an immutable search path'
);

insert into public.transcripts (
  id,
  url_hash,
  video_id,
  transcript_text,
  provider_model
)
values
  (
    '70000000-0000-0000-0000-000000000001',
    'summary-lifecycle-one',
    'summary-lifecycle-one',
    'Transcript one',
    'groq:whisper-large-v3-turbo'
  ),
  (
    '70000000-0000-0000-0000-000000000002',
    'summary-lifecycle-two',
    'summary-lifecycle-two',
    'Transcript two',
    'groq:whisper-large-v3-turbo'
  ),
  (
    '70000000-0000-0000-0000-000000000003',
    'summary-lifecycle-three',
    'summary-lifecycle-three',
    'Transcript three',
    'groq:whisper-large-v3-turbo'
  );

insert into public.jobs (
  id,
  user_id,
  status,
  url,
  source_key,
  stage,
  lease_token,
  lease_expires_at,
  heartbeat_at,
  claimed_at
)
values
  (
    '71000000-0000-0000-0000-000000000001',
    '72000000-0000-0000-0000-000000000001',
    'running',
    'https://www.youtube.com/watch?v=summary-owner-one',
    'youtube:summary-owner-one',
    'summarizing',
    '73000000-0000-0000-0000-000000000001',
    pg_catalog.now() + interval '5 minutes',
    pg_catalog.now(),
    pg_catalog.now()
  ),
  (
    '71000000-0000-0000-0000-000000000002',
    '72000000-0000-0000-0000-000000000002',
    'running',
    'https://www.youtube.com/watch?v=summary-owner-two',
    'youtube:summary-owner-two',
    'summarizing',
    '73000000-0000-0000-0000-000000000002',
    pg_catalog.now() + interval '5 minutes',
    pg_catalog.now(),
    pg_catalog.now()
  ),
  (
    '71000000-0000-0000-0000-000000000003',
    '72000000-0000-0000-0000-000000000003',
    'running',
    'https://www.youtube.com/watch?v=summary-owner-three',
    'youtube:summary-owner-three',
    'summarizing',
    '73000000-0000-0000-0000-000000000003',
    pg_catalog.now() + interval '5 minutes',
    pg_catalog.now(),
    pg_catalog.now()
  );

create temporary table first_preparation as
select public.prepare_summary(
  '74000000-0000-0000-0000-000000000001',
  '72000000-0000-0000-0000-000000000001',
  '71000000-0000-0000-0000-000000000001',
  '73000000-0000-0000-0000-000000000001',
  '70000000-0000-0000-0000-000000000001',
  'default',
  'test-model'
) as result;

select is(
  (select result ->> 'resolution_type' from first_preparation),
  'created',
  'first producer creates a pending summary'
);
select is(
  (select result -> 'summary' ->> 'status' from first_preparation),
  'pending',
  'new summary is explicitly pending'
);
select ok(
  (
    select generation_job_id = '71000000-0000-0000-0000-000000000001'
      and generation_token = '73000000-0000-0000-0000-000000000001'
    from public.summaries
    where id = '74000000-0000-0000-0000-000000000001'
  ),
  'pending summary records its owning job and lease token'
);

create temporary table concurrent_preparation as
select public.prepare_summary(
  '74000000-0000-0000-0000-000000000002',
  '72000000-0000-0000-0000-000000000002',
  '71000000-0000-0000-0000-000000000002',
  '73000000-0000-0000-0000-000000000002',
  '70000000-0000-0000-0000-000000000001',
  'default',
  'test-model'
) as result;

select is(
  (select result ->> 'resolution_type' from concurrent_preparation),
  'in_progress',
  'concurrent producer identifies the live owner'
);
select is(
  (select result -> 'summary' ->> 'id' from concurrent_preparation),
  '74000000-0000-0000-0000-000000000001',
  'concurrent producer receives the owned summary id'
);
select ok(
  not public.update_summary_draft(
    '74000000-0000-0000-0000-000000000001',
    '73000000-0000-0000-0000-000000000002',
    '# Wrong owner'
  ),
  'wrong generation token cannot update a draft'
);
select ok(
  public.update_summary_draft(
    '74000000-0000-0000-0000-000000000001',
    '73000000-0000-0000-0000-000000000001',
    '# Draft'
  ),
  'current generation token can update a draft'
);
select is(
  (
    select summary_markdown
    from public.summaries
    where id = '74000000-0000-0000-0000-000000000001'
  ),
  '# Draft',
  'owned draft mutation is persisted'
);
select ok(
  not public.complete_summary_generation(
    '74000000-0000-0000-0000-000000000001',
    '73000000-0000-0000-0000-000000000002',
    '# Wrong owner'
  ),
  'wrong generation token cannot complete a summary'
);
select ok(
  public.complete_summary_generation(
    '74000000-0000-0000-0000-000000000001',
    '73000000-0000-0000-0000-000000000001',
    '# Ready'
  ),
  'current generation token can complete a summary'
);
select ok(
  (
    select status = 'ready'
      and summary_markdown = '# Ready'
      and ready_at is not null
      and failed_at is null
      and generation_token is null
    from public.summaries
    where id = '74000000-0000-0000-0000-000000000001'
  ),
  'completion atomically establishes the ready invariant'
);
select is(
  (
    public.prepare_summary(
      '74000000-0000-0000-0000-000000000002',
      '72000000-0000-0000-0000-000000000002',
      '71000000-0000-0000-0000-000000000002',
      '73000000-0000-0000-0000-000000000002',
      '70000000-0000-0000-0000-000000000001',
      'default',
      'test-model'
    ) ->> 'resolution_type'
  ),
  'ready',
  'later producer receives the ready cache'
);
select throws_ok(
  $$
    select public.complete_summary_generation(
      '74000000-0000-0000-0000-000000000001',
      '73000000-0000-0000-0000-000000000001',
      '   '
    )
  $$,
  '22023',
  'ready summary markdown cannot be empty',
  'empty markdown can never be completed as ready'
);

create temporary table abandoned_preparation as
select public.prepare_summary(
  '74000000-0000-0000-0000-000000000003',
  '72000000-0000-0000-0000-000000000001',
  '71000000-0000-0000-0000-000000000001',
  '73000000-0000-0000-0000-000000000001',
  '70000000-0000-0000-0000-000000000002',
  'default',
  'test-model'
) as result;

select is(
  (select result ->> 'resolution_type' from abandoned_preparation),
  'created',
  'producer creates a second pending summary'
);
select ok(
  public.update_summary_draft(
    '74000000-0000-0000-0000-000000000003',
    '73000000-0000-0000-0000-000000000001',
    '# Abandoned draft'
  ),
  'abandoned producer persists a partial draft'
);

update public.jobs
set lease_expires_at = pg_catalog.now() - interval '1 second'
where id = '71000000-0000-0000-0000-000000000001';

select ok(
  not public.update_summary_draft(
    '74000000-0000-0000-0000-000000000003',
    '73000000-0000-0000-0000-000000000001',
    '# Expired writer'
  ),
  'matching token cannot write after its owning job lease expires'
);

create temporary table takeover_preparation as
select public.prepare_summary(
  '74000000-0000-0000-0000-000000000004',
  '72000000-0000-0000-0000-000000000002',
  '71000000-0000-0000-0000-000000000002',
  '73000000-0000-0000-0000-000000000002',
  '70000000-0000-0000-0000-000000000002',
  'default',
  'test-model'
) as result;

select is(
  (select result ->> 'resolution_type' from takeover_preparation),
  'taken_over',
  'expired producer ownership can be taken over'
);
select is(
  (select result -> 'summary' ->> 'id' from takeover_preparation),
  '74000000-0000-0000-0000-000000000003',
  'takeover retains the stable summary id'
);
select ok(
  (
    select generation_job_id = '71000000-0000-0000-0000-000000000002'
      and generation_token = '73000000-0000-0000-0000-000000000002'
      and summary_markdown = ''
    from public.summaries
    where id = '74000000-0000-0000-0000-000000000003'
  ),
  'takeover changes ownership and clears abandoned output'
);
select ok(
  not public.update_summary_draft(
    '74000000-0000-0000-0000-000000000003',
    '73000000-0000-0000-0000-000000000001',
    '# Stale writer'
  ),
  'stale producer cannot mutate after takeover'
);
select ok(
  public.update_summary_draft(
    '74000000-0000-0000-0000-000000000003',
    '73000000-0000-0000-0000-000000000002',
    '# Current draft'
  ),
  'takeover producer can mutate with its token'
);
select ok(
  public.fail_summary_generation(
    '74000000-0000-0000-0000-000000000003',
    '73000000-0000-0000-0000-000000000002'
  ),
  'current producer can mark generation failed'
);
select ok(
  (
    select status = 'failed'
      and ready_at is null
      and failed_at is not null
      and generation_token is null
    from public.summaries
    where id = '74000000-0000-0000-0000-000000000003'
  ),
  'failure atomically establishes the failed invariant'
);
select is(
  (
    public.prepare_summary(
      '74000000-0000-0000-0000-000000000005',
      '72000000-0000-0000-0000-000000000003',
      '71000000-0000-0000-0000-000000000003',
      '73000000-0000-0000-0000-000000000003',
      '70000000-0000-0000-0000-000000000002',
      'default',
      'test-model'
    ) ->> 'resolution_type'
  ),
  'taken_over',
  'failed generation can be retried by a new producer'
);
select ok(
  (
    select generation_job_id = '71000000-0000-0000-0000-000000000003'
      and generation_token = '73000000-0000-0000-0000-000000000003'
      and status = 'pending'
    from public.summaries
    where id = '74000000-0000-0000-0000-000000000003'
  ),
  'failed takeover records the new producer'
);
select ok(
  not public.fail_summary_generation(
    '74000000-0000-0000-0000-000000000003',
    '73000000-0000-0000-0000-000000000002'
  ),
  'stale producer cannot fail a taken-over generation'
);
select throws_ok(
  $$
    select public.prepare_summary(
      '74000000-0000-0000-0000-000000000006',
      '72000000-0000-0000-0000-000000000001',
      '71000000-0000-0000-0000-000000000001',
      '73000000-0000-0000-0000-000000000001',
      '70000000-0000-0000-0000-000000000003',
      'default',
      'test-model'
    )
  $$,
  '55000',
  'summary producer must hold the current live job lease',
  'expired job lease cannot prepare summary generation'
);
select throws_ok(
  $$
    insert into public.summaries (
      id,
      transcript_id,
      prompt_key,
      summary_model,
      summary_markdown,
      status,
      status_updated_at,
      ready_at
    )
    values (
      '74000000-0000-0000-0000-000000000007',
      '70000000-0000-0000-0000-000000000003',
      'default',
      'test-model',
      '',
      'ready',
      pg_catalog.now(),
      pg_catalog.now()
    )
  $$,
  '23514',
  null,
  'database rejects an empty ready summary'
);

select * from finish();

rollback;
