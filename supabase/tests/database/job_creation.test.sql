begin;

set local search_path = extensions, public, pg_catalog;

select plan(35);

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
  has_function_privilege(
    'service_role',
    'public.create_or_reuse_job(uuid,text,text,integer,uuid)',
    'execute'
  ),
  'service role can create jobs through the server command'
);

create temporary table first_resolution as
select public.create_or_reuse_job(
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

create temporary table joined_resolution as
select public.create_or_reuse_job(
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
  user_id,
  transcript_id,
  prompt_key,
  summary_model,
  summary_markdown
)
values (
  '60000000-0000-0000-0000-000000000001',
  '40000000-0000-0000-0000-000000000001',
  '50000000-0000-0000-0000-000000000001',
  'default',
  'test-model',
  '# Ready'
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
    public.create_or_reuse_job(
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
    public.create_or_reuse_job(
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
    public.create_or_reuse_job(
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
    select public.create_or_reuse_job(
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
    select public.create_or_reuse_job(
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
    select public.create_or_reuse_job(
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
  'cached session is created in its final state'
);
select is(
  (select result -> 'job' ->> 'stage' from cached_resolution),
  'cached',
  'cached session records its reuse stage atomically'
);
select is(
  (select result -> 'job' ->> 'summary_id' from cached_resolution),
  '60000000-0000-0000-0000-000000000001',
  'cached session attaches its summary atomically'
);
select ok(
  (public.claim_next_job(interval '2 minutes')).id is null,
  'worker cannot claim an atomically completed cached session'
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

select * from finish();

rollback;
