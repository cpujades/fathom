begin;

set local search_path = extensions, public, pg_catalog;

select plan(31);

select has_column('public', 'summaries', 'pdf_cache_version', 'PDF cache version is persisted');
select has_column('public', 'summaries', 'pdf_generation_token', 'PDF generation token is persisted');
select has_column(
  'public',
  'summaries',
  'pdf_generation_cache_version',
  'claimed PDF cache version is persisted'
);
select has_column(
  'public',
  'summaries',
  'pdf_generation_expires_at',
  'PDF generation expiry is persisted'
);
select has_check('public', 'summaries', 'PDF cache and claim consistency is database-enforced');

select ok(
  not has_function_privilege('anon', 'public.prepare_summary_pdf(uuid,integer,uuid)', 'execute'),
  'anon cannot claim PDF generation'
);
select ok(
  not has_function_privilege('authenticated', 'public.prepare_summary_pdf(uuid,integer,uuid)', 'execute'),
  'authenticated users cannot claim PDF generation'
);
select ok(
  has_function_privilege('service_role', 'public.prepare_summary_pdf(uuid,integer,uuid)', 'execute'),
  'service role can claim PDF generation'
);
select ok(
  not has_function_privilege('authenticated', 'public.complete_summary_pdf(uuid,integer,uuid,text)', 'execute'),
  'authenticated users cannot publish cached PDFs'
);
select ok(
  has_function_privilege('service_role', 'public.complete_summary_pdf(uuid,integer,uuid,text)', 'execute'),
  'service role can publish cached PDFs'
);
select ok(
  not has_function_privilege('authenticated', 'public.fail_summary_pdf(uuid,uuid)', 'execute'),
  'authenticated users cannot release PDF claims'
);
select ok(
  has_function_privilege('service_role', 'public.fail_summary_pdf(uuid,uuid)', 'execute'),
  'service role can release PDF claims'
);

select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.prepare_summary_pdf(uuid,integer,uuid)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'PDF prepare command has an immutable search path'
);
select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.complete_summary_pdf(uuid,integer,uuid,text)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'PDF completion command has an immutable search path'
);
select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.fail_summary_pdf(uuid,uuid)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'PDF failure command has an immutable search path'
);

insert into public.transcripts (
  id,
  url_hash,
  video_id,
  transcript_text,
  provider_model
)
values (
  '81000000-0000-0000-0000-000000000001',
  'pdf-generation-proof',
  'pdf-generation-proof',
  'Transcript',
  'groq:whisper-large-v3-turbo'
);

insert into public.summaries (
  id,
  transcript_id,
  prompt_key,
  summary_model,
  summary_markdown,
  pdf_object_key,
  status,
  status_updated_at,
  ready_at
)
values (
  '82000000-0000-0000-0000-000000000001',
  '81000000-0000-0000-0000-000000000001',
  'default',
  'test-model',
  '# Ready',
  '83000000-0000-0000-0000-000000000001/video/legacy.pdf',
  'ready',
  pg_catalog.now(),
  pg_catalog.now()
);

select throws_ok(
  $$
    update public.summaries
    set pdf_generation_token = '84000000-0000-0000-0000-000000000001',
        pdf_generation_expires_at = pg_catalog.now() + interval '5 minutes'
    where id = '82000000-0000-0000-0000-000000000001'
  $$,
  '23514',
  null,
  'database rejects an incomplete PDF generation claim'
);

create temporary table first_pdf_claim as
select public.prepare_summary_pdf(
  '82000000-0000-0000-0000-000000000001',
  2,
  '84000000-0000-0000-0000-000000000001'
) as result;

select is(
  (select result ->> 'resolution_type' from first_pdf_claim),
  'acquired',
  'stale PDF cache is claimed for regeneration'
);
select ok(
  (
    select pdf_generation_token = '84000000-0000-0000-0000-000000000001'
      and pdf_generation_cache_version = 2
      and pdf_generation_expires_at > pg_catalog.now()
    from public.summaries
    where id = '82000000-0000-0000-0000-000000000001'
  ),
  'PDF claim records a live fencing token'
);
select is(
  (
    public.prepare_summary_pdf(
      '82000000-0000-0000-0000-000000000001',
      2,
      '84000000-0000-0000-0000-000000000002'
    ) ->> 'resolution_type'
  ),
  'in_progress',
  'a concurrent renderer observes the live claim'
);
select ok(
  not public.complete_summary_pdf(
    '82000000-0000-0000-0000-000000000001',
    3,
    '84000000-0000-0000-0000-000000000001',
    'wrong-version.pdf'
  ),
  'a producer cannot publish a different cache version than it claimed'
);
select ok(
  not public.complete_summary_pdf(
    '82000000-0000-0000-0000-000000000001',
    2,
    '84000000-0000-0000-0000-000000000002',
    'wrong-owner.pdf'
  ),
  'a non-owner cannot publish a PDF'
);
select ok(
  public.complete_summary_pdf(
    '82000000-0000-0000-0000-000000000001',
    2,
    '84000000-0000-0000-0000-000000000001',
    '83000000-0000-0000-0000-000000000001/video/v2/briefing.pdf'
  ),
  'the current owner can atomically publish a PDF'
);
select ok(
  (
    select pdf_cache_version = 2
      and pdf_object_key = '83000000-0000-0000-0000-000000000001/video/v2/briefing.pdf'
      and pdf_generation_token is null
      and pdf_generation_cache_version is null
      and pdf_generation_expires_at is null
    from public.summaries
    where id = '82000000-0000-0000-0000-000000000001'
  ),
  'completion stores the cache version and clears the claim'
);
select is(
  (
    public.prepare_summary_pdf(
      '82000000-0000-0000-0000-000000000001',
      2,
      '84000000-0000-0000-0000-000000000002'
    ) ->> 'resolution_type'
  ),
  'ready',
  'the current cache is reused without a new render'
);

update public.summaries
set pdf_cache_version = 1
where id = '82000000-0000-0000-0000-000000000001';

select is(
  (
    public.prepare_summary_pdf(
      '82000000-0000-0000-0000-000000000001',
      2,
      '84000000-0000-0000-0000-000000000002'
    ) ->> 'resolution_type'
  ),
  'acquired',
  'an older cache version is regenerated'
);

update public.summaries
set pdf_generation_expires_at = pg_catalog.now() - interval '1 second'
where id = '82000000-0000-0000-0000-000000000001';

select is(
  (
    public.prepare_summary_pdf(
      '82000000-0000-0000-0000-000000000001',
      2,
      '84000000-0000-0000-0000-000000000003'
    ) ->> 'resolution_type'
  ),
  'acquired',
  'an expired PDF claim can be taken over'
);
select ok(
  (
    select pdf_generation_token = '84000000-0000-0000-0000-000000000003'
      and pdf_generation_cache_version = 2
      and pdf_generation_expires_at > pg_catalog.now()
    from public.summaries
    where id = '82000000-0000-0000-0000-000000000001'
  ),
  'takeover installs a new fencing token'
);
select ok(
  not public.fail_summary_pdf(
    '82000000-0000-0000-0000-000000000001',
    '84000000-0000-0000-0000-000000000002'
  ),
  'the stale owner cannot release the replacement claim'
);
select ok(
  public.fail_summary_pdf(
    '82000000-0000-0000-0000-000000000001',
    '84000000-0000-0000-0000-000000000003'
  ),
  'the current owner can release its claim after failure'
);
select ok(
  (
    select pdf_generation_token is null
      and pdf_generation_cache_version is null
      and pdf_generation_expires_at is null
    from public.summaries
    where id = '82000000-0000-0000-0000-000000000001'
  ),
  'failure release clears the active claim'
);

update public.summaries
set summary_markdown = '# Updated briefing'
where id = '82000000-0000-0000-0000-000000000001';

select ok(
  (
    select pdf_object_key is null
      and pdf_cache_version is null
    from public.summaries
    where id = '82000000-0000-0000-0000-000000000001'
  ),
  'changing briefing content invalidates every older cached PDF'
);

select * from finish();

rollback;
