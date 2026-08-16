begin;

set local search_path = extensions, public, pg_catalog;

select plan(20);

select ok(
  pg_catalog.to_regclass('public.usage_ledger') is null,
  'the duplicate usage ledger table is absent'
);
select ok(
  not exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'summaries' and column_name = 'user_id'
  ),
  'the global summary cache has no user owner'
);
select ok(
  not exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'summaries' and column_name = 'ttl_expires_at'
  ),
  'summaries have no TTL'
);
select ok(
  not exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'transcripts' and column_name = 'ttl_expires_at'
  ),
  'transcripts have no TTL'
);
select ok(
  not exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'polar_customers' and column_name = 'email'
  ),
  'Polar customer mappings do not copy email'
);
select ok(
  not exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'polar_customers' and column_name = 'country'
  ),
  'Polar customer mappings do not copy country'
);
select has_column('public', 'credit_lots', 'expires_at', 'credit lots have one clear expiry field');
select ok(
  not exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'credit_lots' and column_name = 'pack_expires_at'
  ),
  'the old credit-lot expiry name is absent'
);
select col_is_pk('public', 'usage_settlements', 'job_id', 'one job has at most one usage settlement');

select is(
  (select confdeltype::text from pg_catalog.pg_constraint where conname = 'jobs_user_id_fkey'),
  'c',
  'Auth user deletion cascades to jobs'
);
select is(
  (select confdeltype::text from pg_catalog.pg_constraint where conname = 'entitlements_user_id_fkey'),
  'c',
  'Auth user deletion cascades to entitlements'
);
select is(
  (select confdeltype::text from pg_catalog.pg_constraint where conname = 'credit_lots_user_id_fkey'),
  'c',
  'Auth user deletion cascades to credit lots'
);
select is(
  (select confdeltype::text from pg_catalog.pg_constraint where conname = 'polar_customers_user_id_fkey'),
  'c',
  'Auth user deletion cascades to Polar mappings'
);
select is(
  (select confdeltype::text from pg_catalog.pg_constraint where conname = 'briefing_stream_leases_user_id_fkey'),
  'c',
  'Auth user deletion cascades to stream leases'
);
select is(
  (select confdeltype::text from pg_catalog.pg_constraint where conname = 'billing_orders_user_id_fkey'),
  'n',
  'Auth user deletion keeps commerce records and clears their user link'
);

select is(
  (
    select pg_catalog.pg_get_constraintdef(oid)
    from pg_catalog.pg_constraint
    where conname = 'usage_settlements_job_owner_fkey'
  ),
  'FOREIGN KEY (job_id, user_id) REFERENCES jobs(id, user_id) ON DELETE CASCADE',
  'a settlement must belong to its job owner'
);
select is(
  (
    select pg_catalog.pg_get_constraintdef(oid)
    from pg_catalog.pg_constraint
    where conname = 'briefing_publications_owner_job_fkey'
  ),
  'FOREIGN KEY (owner_job_id, owner_user_id) REFERENCES jobs(id, user_id) ON DELETE CASCADE',
  'a publication owner must own its source job'
);

select has_index(
  'public',
  'jobs',
  'jobs_briefing_library_idx',
  'briefing library pagination has a user and stable-order index'
);
select has_index(
  'public',
  'usage_settlements',
  'usage_settlements_user_settled_idx',
  'usage history pagination has a user and stable-order index'
);
select ok(
  exists (
    select 1
    from pg_catalog.pg_constraint
    where conname = 'plans_shape_check'
      and conrelid = 'public.plans'::pg_catalog.regclass
  ),
  'the retained plan catalogue has a complete shape constraint'
);

select * from finish();

rollback;
