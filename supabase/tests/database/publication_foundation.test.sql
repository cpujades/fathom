begin;

set local search_path = extensions, public, pg_catalog;

select plan(49);

insert into auth.users (id)
values
  ('d4000000-0000-0000-0000-000000000001'),
  ('d4000000-0000-0000-0000-000000000002'),
  ('d4000000-0000-0000-0000-000000000003'),
  ('d4000000-0000-0000-0000-000000000004'),
  ('d4000000-0000-0000-0000-000000000005');

select has_table(
  'public',
  'briefing_publications',
  'briefing publications table exists'
);
select is(
  (
    select pg_catalog.count(*)
    from pg_catalog.pg_class
    where oid = 'public.briefing_publications'::regclass
      and relrowsecurity
  ),
  1::bigint,
  'all publication tables enforce row-level security'
);

select ok(
  not pg_catalog.has_table_privilege('authenticated', 'public.briefing_publications', 'select'),
  'authenticated clients cannot read publication rows directly'
);
select ok(
  not pg_catalog.has_table_privilege('anon', 'public.briefing_publications', 'select')
    and not pg_catalog.has_table_privilege('anon', 'public.briefing_publications', 'insert')
    and not pg_catalog.has_table_privilege('anon', 'public.briefing_publications', 'update')
    and not pg_catalog.has_table_privilege('anon', 'public.briefing_publications', 'delete'),
  'anonymous clients have no direct publication access'
);
select ok(
  pg_catalog.has_table_privilege('service_role', 'public.briefing_publications', 'select')
    and pg_catalog.has_table_privilege('service_role', 'public.briefing_publications', 'insert')
    and pg_catalog.has_table_privilege('service_role', 'public.briefing_publications', 'update')
    and pg_catalog.has_table_privilege('service_role', 'public.briefing_publications', 'delete'),
  'the backend can manage publications'
);

select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.validate_briefing_publication()'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'publication validation has a fixed search path'
);
select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.unpublish_inactive_job_publication()'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'archive publication cleanup has a fixed search path'
);
select ok(
  not pg_catalog.has_function_privilege(
    'authenticated',
    'public.validate_briefing_publication()',
    'execute'
  ),
  'authenticated clients cannot call publication validation directly'
);
select ok(
  not pg_catalog.has_function_privilege(
    'authenticated',
    'public.unpublish_inactive_job_publication()',
    'execute'
  ),
  'authenticated clients cannot call archive publication cleanup directly'
);
select has_function(
  'public',
  'save_briefing_publication',
  array['uuid', 'text'],
  'saving a public briefing is an atomic database command'
);
select ok(
  not pg_catalog.has_function_privilege(
    'anon',
    'public.save_briefing_publication(uuid,text)',
    'execute'
  )
    and not pg_catalog.has_function_privilege(
      'authenticated',
      'public.save_briefing_publication(uuid,text)',
      'execute'
    ),
  'browser roles cannot save through the server command directly'
);
select ok(
  pg_catalog.has_function_privilege(
    'service_role',
    'public.save_briefing_publication(uuid,text)',
    'execute'
  ),
  'the authenticated API can save a public briefing'
);

select col_not_null(
  'public',
  'briefing_publications',
  'public_slug',
  'every publication has a public slug'
);
select col_not_null(
  'public',
  'briefing_publications',
  'visibility',
  'every publication has a visibility state'
);
select col_not_null(
  'public',
  'briefing_publications',
  'source_key',
  'every publication has a normalized source identity'
);
select has_index(
  'public',
  'briefing_publications',
  'briefing_publications_one_listed_source_idx',
  'Listed source matching has a bounded index'
);
select index_is_unique(
  'public',
  'briefing_publications',
  'briefing_publications_one_listed_source_idx',
  'only one clear Listed publication can represent a source'
);

insert into public.transcripts (
  id,
  url_hash,
  video_id,
  transcript_text,
  provider_model
)
values (
  'd1000000-0000-0000-0000-000000000001',
  'publication-foundation',
  'publication-foundation',
  'Publication foundation transcript.',
  'groq:test'
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
values
  (
    'd2000000-0000-0000-0000-000000000001',
    'd1000000-0000-0000-0000-000000000001',
    'publication-v1',
    'openrouter:test',
    '# Publication one',
    'ready',
    pg_catalog.now(),
    pg_catalog.now()
  ),
  (
    'd2000000-0000-0000-0000-000000000002',
    'd1000000-0000-0000-0000-000000000001',
    'publication-v2',
    'openrouter:test',
    '# Publication two',
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
  usage_settlement_required
)
values
  (
    'd3000000-0000-0000-0000-000000000001',
    'd4000000-0000-0000-0000-000000000001',
    'succeeded',
    'https://www.youtube.com/watch?v=publication-one',
    'youtube:publication-one',
    'd2000000-0000-0000-0000-000000000001',
    'completed',
    100,
    false
  ),
  (
    'd3000000-0000-0000-0000-000000000002',
    'd4000000-0000-0000-0000-000000000002',
    'succeeded',
    'https://www.youtube.com/watch?v=publication-two',
    'youtube:publication-two',
    'd2000000-0000-0000-0000-000000000001',
    'completed',
    100,
    false
  ),
  (
    'd3000000-0000-0000-0000-000000000003',
    'd4000000-0000-0000-0000-000000000003',
    'running',
    'https://www.youtube.com/watch?v=publication-running',
    'youtube:publication-running',
    'd2000000-0000-0000-0000-000000000001',
    'finalizing',
    98,
    false
  );

select lives_ok(
  $$
    insert into public.briefing_publications (
      id,
      owner_user_id,
      owner_job_id,
      summary_id,
      public_slug,
      visibility,
      published_at
    )
    values (
      'd5000000-0000-0000-0000-000000000001',
      'd4000000-0000-0000-0000-000000000001',
      'd3000000-0000-0000-0000-000000000001',
      'd2000000-0000-0000-0000-000000000001',
      'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      'unlisted',
      pg_catalog.now()
    )
  $$,
  'a completed owner can create an unlisted publication'
);
select is(
  (
    select public_slug
    from public.briefing_publications
    where id = 'd5000000-0000-0000-0000-000000000001'
  ),
  'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  'the publication keeps its stable slug'
);
select is(
  (
    select visibility
    from public.briefing_publications
    where id = 'd5000000-0000-0000-0000-000000000001'
  ),
  'unlisted',
  'the publication stores link-only visibility'
);
select is(
  (
    select source_key
    from public.briefing_publications
    where id = 'd5000000-0000-0000-0000-000000000001'
  ),
  'youtube:publication-one',
  'the publication copies its validated owner source identity'
);
select throws_ok(
  $$
    update public.briefing_publications
    set public_slug = '99999999999999999999999999999999'
    where id = 'd5000000-0000-0000-0000-000000000001'
  $$,
  '23514',
  'publication identity is immutable',
  'a public link cannot change after publication creation'
);

create temporary table saved_publication_resolution as
select public.save_briefing_publication(
  'd4000000-0000-0000-0000-000000000004',
  'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
) as result;

select is(
  (select result ->> 'resolution_type' from saved_publication_resolution),
  'new',
  'first save creates a library entry'
);
select is(
  (select result -> 'job' ->> 'status' from saved_publication_resolution),
  'succeeded',
  'a saved public briefing is immediately readable'
);
select ok(
  not (
    select (result -> 'job' ->> 'usage_settlement_required')::boolean
    from saved_publication_resolution
  ),
  'saving a public briefing does not require usage settlement'
);
select is(
  (select result -> 'job' ->> 'summary_id' from saved_publication_resolution),
  'd2000000-0000-0000-0000-000000000001',
  'the saved entry reuses the published summary'
);
select is(
  (
    select pg_catalog.count(*)
    from public.usage_settlements
    where job_id = (
      select (result -> 'job' ->> 'id')::uuid
      from saved_publication_resolution
    )
  ),
  0::bigint,
  'saving creates no usage settlement'
);

create temporary table repeated_save_resolution as
select public.save_briefing_publication(
  'd4000000-0000-0000-0000-000000000004',
  'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
) as result;

select is(
  (select result -> 'job' ->> 'id' from repeated_save_resolution),
  (select result -> 'job' ->> 'id' from saved_publication_resolution),
  'repeated save returns the existing library entry'
);
select is(
  (
    select pg_catalog.count(*)
    from public.jobs
    where user_id = 'd4000000-0000-0000-0000-000000000004'
      and source_key = 'youtube:publication-one'
      and status = 'succeeded'
  ),
  1::bigint,
  'repeated save does not duplicate the library entry'
);

select throws_ok(
  $$
    insert into public.briefing_publications (
      owner_user_id, owner_job_id, summary_id, public_slug
    )
    values (
      'd4000000-0000-0000-0000-000000000099',
      'd3000000-0000-0000-0000-000000000001',
      'd2000000-0000-0000-0000-000000000001',
      'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
    )
  $$,
  '23514',
  'publication owner must own the job',
  'a publication cannot claim another user job'
);
select throws_ok(
  $$
    insert into public.briefing_publications (
      owner_user_id, owner_job_id, summary_id, public_slug
    )
    values (
      'd4000000-0000-0000-0000-000000000002',
      'd3000000-0000-0000-0000-000000000002',
      'd2000000-0000-0000-0000-000000000002',
      'cccccccccccccccccccccccccccccccc'
    )
  $$,
  '23514',
  'publication summary must match the job summary',
  'a publication cannot replace the job summary'
);
select throws_ok(
  $$
    insert into public.briefing_publications (
      owner_user_id,
      owner_job_id,
      summary_id,
      public_slug,
      visibility,
      published_at
    )
    values (
      'd4000000-0000-0000-0000-000000000003',
      'd3000000-0000-0000-0000-000000000003',
      'd2000000-0000-0000-0000-000000000001',
      'dddddddddddddddddddddddddddddddd',
      'unlisted',
      pg_catalog.now()
    )
  $$,
  '23514',
  'new publication requires a completed job',
  'a running job cannot be published'
);
select throws_ok(
  $$
    insert into public.briefing_publications (
      owner_user_id, owner_job_id, summary_id, public_slug
    )
    values (
      'd4000000-0000-0000-0000-000000000003',
      'd3000000-0000-0000-0000-000000000003',
      'd2000000-0000-0000-0000-000000000001',
      'eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
    )
  $$,
  '23514',
  'new publication requires a completed job',
  'a running job cannot create a private publication shell'
);
select throws_ok(
  $$
    update public.briefing_publications
    set visibility = 'listed'
    where id = 'd5000000-0000-0000-0000-000000000001'
  $$,
  '23514',
  null,
  'Explore listing requires curated metadata'
);
select throws_ok(
  $$
    update public.briefing_publications
    set visibility = 'listed',
        topic = 'business'
    where id = 'd5000000-0000-0000-0000-000000000001'
  $$,
  '23514',
  null,
  'Explore listing requires a listing time'
);
select throws_ok(
  $$
    update public.briefing_publications
    set visibility = 'listed',
        topic = 'anything',
        listed_at = pg_catalog.now()
    where id = 'd5000000-0000-0000-0000-000000000001'
  $$,
  '23514',
  null,
  'Explore accepts only controlled topics'
);
select lives_ok(
  $$
    update public.briefing_publications
    set visibility = 'listed',
        topic = 'business',
        listed_at = pg_catalog.now()
    where id = 'd5000000-0000-0000-0000-000000000001'
  $$,
  'Talven can add a curated publication to Explore'
);
select is(
  (
    select visibility || ':' || topic
    from public.briefing_publications
    where id = 'd5000000-0000-0000-0000-000000000001'
  ),
  'listed:business',
  'Explore keeps the curated topic'
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
  usage_settlement_required
)
values (
  'd3000000-0000-0000-0000-000000000004',
  'd4000000-0000-0000-0000-000000000005',
  'succeeded',
  'https://www.youtube.com/watch?v=publication-one',
  'youtube:publication-one',
  'd2000000-0000-0000-0000-000000000001',
  'completed',
  100,
  false
);
insert into public.briefing_publications (
  id,
  owner_user_id,
  owner_job_id,
  summary_id,
  public_slug,
  visibility,
  published_at
)
values (
  'd5000000-0000-0000-0000-000000000004',
  'd4000000-0000-0000-0000-000000000005',
  'd3000000-0000-0000-0000-000000000004',
  'd2000000-0000-0000-0000-000000000001',
  '44444444444444444444444444444444',
  'unlisted',
  pg_catalog.now()
);
select throws_ok(
  $$
    update public.briefing_publications
    set visibility = 'listed',
        topic = 'business',
        listed_at = pg_catalog.now()
    where id = 'd5000000-0000-0000-0000-000000000004'
  $$,
  '23505',
  null,
  'one source cannot appear twice in Explore'
);
select lives_ok(
  $$
    update public.briefing_publications
    set visibility = 'unlisted',
        listed_at = null
    where id = 'd5000000-0000-0000-0000-000000000001'
  $$,
  'an Explore publication can return to link-only sharing'
);

select lives_ok(
  $$
    update public.briefing_publications
    set visibility = 'private',
        moderation_status = 'blocked',
        moderated_at = pg_catalog.now(),
        moderation_reason = 'Unsafe publication',
        unpublished_at = pg_catalog.now()
    where id = 'd5000000-0000-0000-0000-000000000001'
  $$,
  'Talven can record a complete takedown state'
);
select is(
  (
    select visibility || ':' || moderation_status
    from public.briefing_publications
    where id = 'd5000000-0000-0000-0000-000000000001'
  ),
  'private:blocked',
  'a takedown makes the publication private'
);
select throws_ok(
  $$
    update public.briefing_publications
    set visibility = 'unlisted',
        published_at = pg_catalog.now(),
        unpublished_at = null
    where id = 'd5000000-0000-0000-0000-000000000001'
  $$,
  '23514',
  null,
  'a blocked publication cannot return to public visibility'
);

select lives_ok(
  $$
    insert into public.briefing_publications (
      id,
      owner_user_id,
      owner_job_id,
      summary_id,
      public_slug,
      visibility,
      published_at
    )
    values (
      'd5000000-0000-0000-0000-000000000002',
      'd4000000-0000-0000-0000-000000000002',
      'd3000000-0000-0000-0000-000000000002',
      'd2000000-0000-0000-0000-000000000001',
      'ffffffffffffffffffffffffffffffff',
      'unlisted',
      pg_catalog.now()
    )
  $$,
  'a second owner can publish the same shared summary independently'
);
select lives_ok(
  $$
    update public.jobs
    set status = 'deleted',
        stage = 'deleted'
    where id = 'd3000000-0000-0000-0000-000000000002'
  $$,
  'archiving the owner job succeeds'
);
select is(
  (
    select visibility
    from public.briefing_publications
    where id = 'd5000000-0000-0000-0000-000000000002'
  ),
  'private',
  'archiving the owner job makes its publication private'
);
select ok(
  (
    select unpublished_at is not null
      and listed_at is null
    from public.briefing_publications
    where id = 'd5000000-0000-0000-0000-000000000002'
  ),
  'archive records unpublish time and clears Explore listing'
);
select lives_ok(
  $$
    update public.jobs
    set status = 'succeeded',
        stage = 'completed'
    where id = 'd3000000-0000-0000-0000-000000000002'
  $$,
  'restoring the owner job succeeds'
);
select is(
  (
    select visibility
    from public.briefing_publications
    where id = 'd5000000-0000-0000-0000-000000000002'
  ),
  'private',
  'restoring the owner job does not republish it'
);

select * from finish();

rollback;
