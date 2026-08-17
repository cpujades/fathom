begin;

set local search_path = extensions, public, pg_catalog;

select plan(62);

insert into auth.users (id)
values
  ('40000000-0000-0000-0000-000000000001'),
  ('40000000-0000-0000-0000-000000000002'),
  ('40000000-0000-0000-0000-000000000003'),
  ('40000000-0000-0000-0000-000000000004'),
  ('40000000-0000-0000-0000-000000000005'),
  ('40000000-0000-0000-0000-000000000006');

insert into public.entitlements (
  user_id,
  subscription_available_seconds,
  pack_available_seconds,
  debt_seconds,
  is_blocked
)
select
  id,
  case
    when id = '40000000-0000-0000-0000-000000000005' then 600
    when id = '40000000-0000-0000-0000-000000000006' then 0
    else 10000
  end,
  0,
  0,
  false
from auth.users
where id between
  '40000000-0000-0000-0000-000000000001'
  and '40000000-0000-0000-0000-000000000006';

select col_not_null(
  'public',
  'jobs',
  'source_key',
  'every job has a normalized source identity'
);
select has_index(
  'public',
  'jobs',
  'jobs_one_active_source_per_user_idx',
  'active user/source uniqueness is enforced by an index'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.derive_job_source_key(text)',
    'execute'
  ),
  'authenticated users cannot invoke the source-key derivation helper'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.derive_job_source_key(text)',
    'execute'
  ),
  'service role can invoke the source-key derivation helper'
);

select is(
  public.derive_job_source_key(source_url),
  'youtube:AbC123xYz',
  description
)
from (
  values
    ('https://youtube.com/watch?v=AbC123xYz', 'watch URL is normalized'),
    ('https://www.youtube.com/watch?feature=share&v=AbC123xYz#t=12', 'watch query order is normalized'),
    ('https://m.youtube.com/watch?v=AbC123xYz', 'mobile host is normalized'),
    ('https://music.youtube.com/watch?v=AbC123xYz', 'music host is normalized'),
    ('https://youtu.be/AbC123xYz?t=12', 'short URL is normalized'),
    ('https://www.youtube.com/shorts/AbC123xYz?feature=share', 'shorts URL is normalized'),
    ('https://www.youtube.com/embed/AbC123xYz', 'embed URL is normalized'),
    ('https://www.youtube.com/live/AbC123xYz?si=token', 'live URL is normalized')
) as source_cases(source_url, description);

select ok(
  not has_function_privilege(
    'anon',
    'public.create_or_reuse_job(uuid,text,text,integer,uuid)',
    'execute'
  ),
  'anon cannot create jobs through the server command'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.create_or_reuse_job(uuid,text,text,integer,uuid)',
    'execute'
  ),
  'authenticated users cannot create jobs through the server command'
);
select ok(
  not has_function_privilege(
    'service_role',
    'public.create_or_reuse_job(uuid,text,text,integer,uuid)',
    'execute'
  ),
  'service role cannot call settlement-exempt compatibility creation directly'
);
select ok(
  not has_function_privilege(
    'anon',
    'public.create_or_reuse_settled_job(uuid,text,text,integer,uuid,interval)',
    'execute'
  ),
  'anon cannot create lease-owned cached jobs'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.create_or_reuse_settled_job(uuid,text,text,integer,uuid,interval)',
    'execute'
  ),
  'authenticated users cannot create lease-owned cached jobs'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.create_or_reuse_settled_job(uuid,text,text,integer,uuid,interval)',
    'execute'
  ),
  'service role can create lease-owned cached jobs'
);

create temporary table first_resolution as
select public.create_or_reuse_settled_job(
  '40000000-0000-0000-0000-000000000001',
  'https://www.youtube.com/watch?v=idempotent',
  'youtube:idempotent',
  1800,
  null
) as result;

select is(
  (select result ->> 'resolution_type' from first_resolution),
  'new',
  'first request creates a job'
);
select is(
  (select result -> 'job' ->> 'status' from first_resolution),
  'queued',
  'new job starts queued'
);
select is(
  (
    select result -> 'job' ->> 'source_key'
    from first_resolution
  ),
  'youtube:idempotent',
  'new job persists the normalized source key'
);
select ok(
  (
    select (result -> 'job' ->> 'usage_settlement_required')::boolean
    from first_resolution
  ),
  'new application job requires usage settlement'
);

create temporary table joined_resolution as
select public.create_or_reuse_settled_job(
  '40000000-0000-0000-0000-000000000001',
  'https://www.youtube.com/watch?v=idempotent',
  'youtube:idempotent',
  1800,
  null
) as result;

select is(
  (select result ->> 'resolution_type' from joined_resolution),
  'joined_existing',
  'repeated active request joins the existing job'
);
select is(
  (select result -> 'job' ->> 'id' from joined_resolution),
  (select result -> 'job' ->> 'id' from first_resolution),
  'joined request returns the original job'
);
select is(
  (
    select pg_catalog.count(*)
    from public.jobs
    where user_id = '40000000-0000-0000-0000-000000000001'
      and source_key = 'youtube:idempotent'
      and status in ('queued', 'running')
  ),
  1::bigint,
  'only one active job exists for a user and source'
);

insert into public.transcripts (
  id,
  url_hash,
  video_id,
  transcript_text,
  provider_model
)
values (
  '50000000-0000-0000-0000-000000000001',
  'idempotent-hash',
  'idempotent',
  'Transcript',
  'groq:whisper-large-v3-turbo'
);

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
  '60000000-0000-0000-0000-000000000001',
  '50000000-0000-0000-0000-000000000001',
  'default',
  'test-model',
  '# Ready',
  'ready',
  pg_catalog.now(),
  pg_catalog.now()
);

update public.jobs
set status = 'succeeded',
    stage = 'completed',
    summary_id = '60000000-0000-0000-0000-000000000001'
where id = (
  select (result -> 'job' ->> 'id')::uuid
  from first_resolution
);

select is(
  (
    public.create_or_reuse_settled_job(
      '40000000-0000-0000-0000-000000000001',
      'https://www.youtube.com/watch?v=idempotent',
      'youtube:idempotent',
      1800,
      null
    ) ->> 'resolution_type'
  ),
  'reused_ready',
  'completed job is reused'
);

update public.jobs
set status = 'deleted',
    stage = 'deleted'
where user_id = '40000000-0000-0000-0000-000000000001'
  and source_key = 'youtube:idempotent';

select is(
  (
    public.create_or_reuse_settled_job(
      '40000000-0000-0000-0000-000000000001',
      'https://www.youtube.com/watch?v=idempotent',
      'youtube:idempotent',
      1800,
      null
    ) ->> 'resolution_type'
  ),
  'reused_ready',
  'archived reusable job is restored'
);
select is(
  (
    select status
    from public.jobs
    where user_id = '40000000-0000-0000-0000-000000000001'
      and source_key = 'youtube:idempotent'
  ),
  'succeeded',
  'restored reusable job is visible as succeeded'
);

select is(
  (
    public.create_or_reuse_settled_job(
      '40000000-0000-0000-0000-000000000002',
      'https://www.youtube.com/watch?v=idempotent',
      'youtube:idempotent',
      1800,
      null
    ) ->> 'resolution_type'
  ),
  'new',
  'another user receives an independent job'
);

select throws_ok(
  $$
    insert into public.jobs (user_id, status, url, source_key)
    values (
      '40000000-0000-0000-0000-000000000002',
      'queued',
      'https://www.youtube.com/watch?v=idempotent',
      'youtube:idempotent'
    )
  $$,
  '23505',
  null,
  'partial unique index rejects a second active job'
);
select throws_ok(
  $$
    select public.create_or_reuse_settled_job(
      '40000000-0000-0000-0000-000000000003',
      'https://www.youtube.com/watch?v=invalid',
      '',
      1800,
      null
    )
  $$,
  '22023',
  'source key must contain 1 to 200 non-padded characters',
  'empty source key is rejected'
);
select throws_ok(
  $$
    select public.create_or_reuse_settled_job(
      '40000000-0000-0000-0000-000000000003',
      'https://www.youtube.com/watch?v=invalid',
      'youtube:invalid',
      -1,
      null
    )
  $$,
  '22023',
  'duration seconds cannot be negative',
  'negative duration is rejected'
);
select throws_ok(
  $$
    select public.create_or_reuse_settled_job(
      '40000000-0000-0000-0000-000000000003',
      'https://www.youtube.com/watch?v=canonical',
      'youtube:different',
      1800,
      null
    )
  $$,
  '22023',
  'source key does not match the canonical url',
  'source key must match the canonical URL'
);

create temporary table first_pending_job as
select public.create_or_reuse_settled_job(
  '40000000-0000-0000-0000-000000000005',
  'https://www.youtube.com/watch?v=pending-a',
  'youtube:pending-a',
  200,
  null
) as result;

select is(
  (select result ->> 'resolution_type' from first_pending_job),
  'new',
  'the first pending job fits the spendable balance'
);
select is(
  public.create_or_reuse_settled_job(
    '40000000-0000-0000-0000-000000000005',
    'https://www.youtube.com/watch?v=pending-b',
    'youtube:pending-b',
    250,
    null
  ) ->> 'resolution_type',
  'new',
  'a second pending job can run within the same balance'
);

create temporary table committed_time_rejection as
select public.create_or_reuse_settled_job(
  '40000000-0000-0000-0000-000000000005',
  'https://www.youtube.com/watch?v=pending-too-large',
  'youtube:pending-too-large',
  200,
  null
) as result;

select is(
  (select result ->> 'resolution_type' from committed_time_rejection),
  'video_time_committed',
  'pending durations protect the uncommitted balance'
);
select is(
  (select (result -> 'details' ->> 'available_seconds')::integer from committed_time_rejection),
  150,
  'the rejection returns the time still available'
);
select is(
  (select (result -> 'details' ->> 'pending_seconds')::integer from committed_time_rejection),
  450,
  'the rejection returns the time committed to active jobs'
);
select is(
  (
    select pg_catalog.count(*)
    from public.jobs
    where user_id = '40000000-0000-0000-0000-000000000005'
      and status in ('queued', 'running')
  ),
  2::bigint,
  'a rejected admission creates no job'
);

update public.jobs
set status = 'failed',
    stage = 'failed'
where id = (select (result -> 'job' ->> 'id')::uuid from first_pending_job);

select is(
  public.create_or_reuse_settled_job(
    '40000000-0000-0000-0000-000000000005',
    'https://www.youtube.com/watch?v=pending-c',
    'youtube:pending-c',
    200,
    null
  ) ->> 'resolution_type',
  'new',
  'a failed job releases its pending duration'
);
select is(
  public.create_or_reuse_settled_job(
    '40000000-0000-0000-0000-000000000005',
    'https://www.youtube.com/watch?v=pending-d',
    'youtube:pending-d',
    100,
    null
  ) ->> 'resolution_type',
  'new',
  'three jobs can run when their combined duration fits'
);

create temporary table active_limit_rejection as
select public.create_or_reuse_settled_job(
  '40000000-0000-0000-0000-000000000005',
  'https://www.youtube.com/watch?v=pending-fourth',
  'youtube:pending-fourth',
  10,
  null
) as result;

select is(
  (select result ->> 'resolution_type' from active_limit_rejection),
  'active_job_limit_reached',
  'a fourth billable job in progress is rejected'
);
select is(
  (select (result -> 'details' ->> 'maximum_active_jobs')::integer from active_limit_rejection),
  3,
  'the active-job rejection returns the account limit'
);
select is(
  (
    select pg_catalog.count(*)
    from public.jobs
    where user_id = '40000000-0000-0000-0000-000000000005'
      and status in ('queued', 'running')
  ),
  3::bigint,
  'the fourth-job rejection creates no job'
);
select is(
  public.create_or_reuse_settled_job(
    '40000000-0000-0000-0000-000000000005',
    'https://www.youtube.com/watch?v=pending-d',
    'youtube:pending-d',
    100,
    null
  ) ->> 'resolution_type',
  'joined_existing',
  'same-source reuse bypasses the new-job limit'
);

select is(
  public.create_or_reuse_settled_job(
    '40000000-0000-0000-0000-000000000006',
    'https://www.youtube.com/watch?v=no-time',
    'youtube:no-time',
    60,
    null
  ) ->> 'resolution_type',
  'no_video_time',
  'the database rejects admission with no spendable time'
);

update public.entitlements
set subscription_available_seconds = 600,
    debt_seconds = 600,
    is_blocked = true
where user_id = '40000000-0000-0000-0000-000000000006';

select is(
  public.create_or_reuse_settled_job(
    '40000000-0000-0000-0000-000000000006',
    'https://www.youtube.com/watch?v=blocked',
    'youtube:blocked',
    60,
    null
  ) ->> 'resolution_type',
  'balance_blocked',
  'the database keeps the debt block authoritative'
);

insert into public.summaries (
  id,
  transcript_id,
  prompt_key,
  summary_model,
  summary_markdown,
  status,
  status_updated_at,
  failed_at
)
values (
  '60000000-0000-0000-0000-000000000002',
  '50000000-0000-0000-0000-000000000001',
  'failed-test',
  'test-model',
  '',
  'failed',
  pg_catalog.now(),
  pg_catalog.now()
);

select throws_ok(
  $$
    select public.create_or_reuse_settled_job(
      '40000000-0000-0000-0000-000000000003',
      'https://www.youtube.com/watch?v=failed-cache',
      'youtube:failed-cache',
      1800,
      '60000000-0000-0000-0000-000000000002'
    )
  $$,
  '22023',
  'cached summary must be ready and non-empty',
  'failed empty summary can never create a cached session'
);

update public.jobs
set status = 'failed',
    stage = 'failed'
where status in ('queued', 'running');

create temporary table cached_resolution as
select public.create_or_reuse_job(
  '40000000-0000-0000-0000-000000000003',
  'https://www.youtube.com/watch?v=cached',
  'youtube:cached',
  1800,
  '60000000-0000-0000-0000-000000000001'
) as result;

select is(
  (select result ->> 'resolution_type' from cached_resolution),
  'new',
  'first cached request creates a session'
);
select is(
  (select result -> 'job' ->> 'status' from cached_resolution),
  'succeeded',
  'compatibility command preserves historical cached terminal behavior'
);
select is(
  (select result -> 'job' ->> 'stage' from cached_resolution),
  'cached',
  'compatibility command preserves the cached stage'
);
select is(
  (select result -> 'job' ->> 'summary_id' from cached_resolution),
  '60000000-0000-0000-0000-000000000001',
  'cached session attaches its summary atomically'
);
select ok(
  (public.claim_next_job(interval '2 minutes')).id is null,
  'worker cannot claim a compatibility cached session'
);
select ok(
  not (
    select (result -> 'job' ->> 'usage_settlement_required')::boolean
    from cached_resolution
  ),
  'rolling-deploy compatibility rows are exempt from unsafe recharging'
);

create temporary table leased_cached_resolution as
select public.create_or_reuse_settled_job(
  '40000000-0000-0000-0000-000000000004',
  'https://www.youtube.com/watch?v=cached-leased',
  'youtube:cached-leased',
  1800,
  '60000000-0000-0000-0000-000000000001',
  interval '2 minutes'
) as result;

select is(
  (select result ->> 'resolution_type' from leased_cached_resolution),
  'new',
  'new cached command creates an independent session'
);
select is(
  (select result -> 'job' ->> 'status' from leased_cached_resolution),
  'running',
  'new cached session remains running through settlement'
);
select is(
  (select result -> 'job' ->> 'stage' from leased_cached_resolution),
  'finalizing',
  'new cached session visibly finalizes'
);
select ok(
  (
    select (result -> 'job' ->> 'usage_settlement_required')::boolean
    from leased_cached_resolution
  ),
  'new cached session requires settlement'
);
select ok(
  (
    select result -> 'job' ->> 'lease_token' is not null
    from leased_cached_resolution
  ),
  'new cached session receives a lease token'
);
select ok(
  (public.claim_next_settled_job(interval '2 minutes')).id is null,
  'worker cannot steal a request-owned cached lease'
);

select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.create_or_reuse_job(uuid,text,text,integer,uuid)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'server command has an immutable search path'
);
select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.create_or_reuse_settled_job(uuid,text,text,integer,uuid,interval)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'cached server command has an immutable search path'
);

select * from finish();

rollback;
