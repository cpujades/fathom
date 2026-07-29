begin;

set local search_path = extensions, public, pg_catalog;

select plan(20);

select ok(
  not has_function_privilege('anon', 'public.claim_next_job(interval)', 'execute'),
  'anon cannot claim jobs'
);
select ok(
  not has_function_privilege('authenticated', 'public.claim_next_job(interval)', 'execute'),
  'authenticated users cannot claim jobs'
);
select ok(
  has_function_privilege('service_role', 'public.claim_next_job(interval)', 'execute'),
  'service role can claim jobs'
);

select ok(
  not has_function_privilege('anon', 'public.requeue_stale_jobs(interval)', 'execute'),
  'anon cannot requeue jobs'
);
select ok(
  not has_function_privilege('authenticated', 'public.requeue_stale_jobs(interval)', 'execute'),
  'authenticated users cannot requeue jobs'
);
select ok(
  has_function_privilege('service_role', 'public.requeue_stale_jobs(interval)', 'execute'),
  'service role can requeue jobs'
);

select ok(
  not has_function_privilege('anon', 'public.prune_usage_ledger(integer)', 'execute'),
  'anon cannot prune usage records'
);
select ok(
  not has_function_privilege('authenticated', 'public.prune_usage_ledger(integer)', 'execute'),
  'authenticated users cannot prune usage records'
);
select ok(
  has_function_privilege('service_role', 'public.prune_usage_ledger(integer)', 'execute'),
  'service role can prune usage records'
);

select ok(
  has_table_privilege('authenticated', 'public.jobs', 'select'),
  'authenticated users retain RLS-scoped job reads'
);
select ok(
  not has_table_privilege('authenticated', 'public.jobs', 'insert'),
  'authenticated users cannot insert jobs directly'
);
select ok(
  not has_table_privilege('authenticated', 'public.jobs', 'update'),
  'authenticated users cannot update jobs directly'
);
select ok(
  not has_table_privilege('authenticated', 'public.jobs', 'delete'),
  'authenticated users cannot delete jobs directly'
);
select ok(
  not has_table_privilege('anon', 'public.jobs', 'insert'),
  'anon cannot insert jobs directly'
);
select ok(
  not has_table_privilege('anon', 'public.jobs', 'update'),
  'anon cannot update jobs directly'
);
select ok(
  not has_table_privilege('anon', 'public.jobs', 'delete'),
  'anon cannot delete jobs directly'
);

select is(
  (
    select count(*)
    from pg_catalog.pg_policies
    where schemaname = 'public'
      and tablename = 'jobs'
      and policyname in ('jobs_insert_own', 'jobs_update_own')
  ),
  0::bigint,
  'browser job mutation policies are absent'
);

select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.claim_next_job(interval)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'claim function has an immutable search path'
);

select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.requeue_stale_jobs(interval)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'requeue function has an immutable search path'
);

select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.prune_usage_ledger(integer)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'maintenance function has an immutable search path'
);

select * from finish();

rollback;
