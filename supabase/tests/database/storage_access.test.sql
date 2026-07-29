begin;

set local search_path = extensions, public, pg_catalog;

select plan(6);

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

select * from finish();

rollback;
