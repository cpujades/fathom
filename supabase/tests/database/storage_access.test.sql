begin;

set local search_path = extensions, public, pg_catalog;

select plan(10);

select is(
  (
    select count(*)
    from storage.buckets
    where id in ('fathom', 'fathom_groq')
      and public
  ),
  0::bigint,
  'application storage buckets are private'
);

select is(
  (
    select count(*)
    from pg_catalog.pg_policies
    where schemaname = 'storage'
      and tablename = 'objects'
      and 'authenticated' = any(roles)
      and (
        qual ilike '%fathom%'
        or with_check ilike '%fathom%'
        or policyname = 'storage_objects_select_own'
      )
  ),
  0::bigint,
  'authenticated clients have no Talven storage object policy'
);

select ok(
  (
    select relrowsecurity
    from pg_catalog.pg_class
    where oid = 'storage.objects'::regclass
  ),
  'storage objects enforce row-level security'
);

select ok(
  (
    select rolbypassrls
    from pg_catalog.pg_roles
    where rolname = 'service_role'
  ),
  'service role can perform server-mediated storage operations'
);

insert into storage.objects (id, bucket_id, name, owner, metadata)
values
  (
    'b1000000-0000-0000-0000-000000000001',
    'fathom',
    'a2000000-0000-0000-0000-000000000001/proof/briefing.pdf',
    'a2000000-0000-0000-0000-000000000001',
    '{}'::jsonb
  ),
  (
    'b1000000-0000-0000-0000-000000000002',
    'fathom_groq',
    'a2000000-0000-0000-0000-000000000001/proof/audio.mp3',
    'a2000000-0000-0000-0000-000000000001',
    '{}'::jsonb
  );

set local role authenticated;
select pg_catalog.set_config(
  'request.jwt.claim.sub',
  'a2000000-0000-0000-0000-000000000001',
  true
);

select is(
  (select count(*) from storage.objects where bucket_id = 'fathom'),
  0::bigint,
  'authenticated clients cannot list PDF objects'
);
select is(
  (select count(*) from storage.objects where bucket_id = 'fathom_groq'),
  0::bigint,
  'authenticated clients cannot list temporary audio objects'
);

select throws_ok(
  $$
    insert into storage.objects (id, bucket_id, name, owner, metadata)
    values (
      'b1000000-0000-0000-0000-000000000003',
      'fathom',
      'a2000000-0000-0000-0000-000000000001/proof/attack.pdf',
      'a2000000-0000-0000-0000-000000000001',
      '{}'::jsonb
    )
  $$,
  '42501',
  null,
  'authenticated clients cannot upload directly to Talven storage'
);
select lives_ok(
  $$
    update storage.objects
    set name = 'a2000000-0000-0000-0000-000000000001/proof/changed.pdf'
    where id = 'b1000000-0000-0000-0000-000000000001'
  $$,
  'an authenticated update is safely filtered by storage RLS'
);
select lives_ok(
  $$
    delete from storage.objects
    where id = 'b1000000-0000-0000-0000-000000000001'
  $$,
  'an authenticated delete is safely filtered by storage RLS'
);

reset role;
select is(
  (
    select count(*)
    from storage.objects
    where id in (
      'b1000000-0000-0000-0000-000000000001',
      'b1000000-0000-0000-0000-000000000002'
    )
  ),
  2::bigint,
  'denied browser operations leave server-owned objects unchanged'
);

select * from finish();

rollback;
