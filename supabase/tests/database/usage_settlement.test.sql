begin;

set local search_path = extensions, public, pg_catalog;

select plan(57);

select col_not_null(
  'public',
  'jobs',
  'usage_settlement_required',
  'jobs explicitly record whether settlement is required'
);
select has_table(
  'public',
  'usage_settlements',
  'immutable job settlement records exist'
);
select has_column(
  'public',
  'usage_ledger',
  'settlement_id',
  'new ledger rows link to their settlement'
);
select has_index(
  'public',
  'usage_settlements',
  'usage_settlements_job_id_key',
  'one settlement per job is enforced'
);
select has_index(
  'public',
  'usage_ledger',
  'usage_ledger_one_source_per_settlement_idx',
  'one ledger row per settlement source is enforced'
);
select ok(
  not has_table_privilege('authenticated', 'public.usage_settlements', 'select'),
  'authenticated users cannot inspect settlement internals'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.settle_job_usage(uuid,uuid,integer)',
    'execute'
  ),
  'authenticated users cannot settle usage'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.settle_job_usage(uuid,uuid,integer)',
    'execute'
  ),
  'service role can settle usage'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.complete_job_after_settlement(uuid,uuid,uuid)',
    'execute'
  ),
  'authenticated users cannot complete settled jobs'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.complete_job_after_settlement(uuid,uuid,uuid)',
    'execute'
  ),
  'service role can complete settled jobs'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.requeue_unsettled_jobs()',
    'execute'
  ),
  'authenticated users cannot reconcile unsettled jobs'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.requeue_unsettled_jobs()',
    'execute'
  ),
  'service role can reconcile unsettled jobs'
);
select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.settle_job_usage(uuid,uuid,integer)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'settlement command has an immutable search path'
);
select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.complete_job_after_settlement(uuid,uuid,uuid)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'terminal command has an immutable search path'
);
select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.requeue_unsettled_jobs()'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'reconciliation command has an immutable search path'
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
  'usage-settlement-transcript',
  'settlement-main',
  'Transcript',
  'test-provider'
);

insert into public.summaries (
  id,
  user_id,
  transcript_id,
  prompt_key,
  summary_model,
  summary_markdown,
  status,
  status_updated_at,
  ready_at
)
values (
  '82000000-0000-0000-0000-000000000001',
  '83000000-0000-0000-0000-000000000001',
  '81000000-0000-0000-0000-000000000001',
  'usage-settlement',
  'test-model',
  '# Ready',
  'ready',
  pg_catalog.now(),
  pg_catalog.now()
);

insert into public.entitlements (
  user_id,
  subscription_available_seconds,
  pack_available_seconds,
  debt_seconds,
  is_blocked
)
values (
  '83000000-0000-0000-0000-000000000001',
  100,
  180,
  0,
  false
);

insert into public.credit_lots (
  id,
  user_id,
  lot_type,
  source_key,
  granted_seconds,
  pack_expires_at,
  status
)
values
  (
    '84000000-0000-0000-0000-000000000001',
    '83000000-0000-0000-0000-000000000001',
    'subscription_cycle',
    'subscription:test',
    100,
    pg_catalog.now() + interval '30 days',
    'active'
  ),
  (
    '84000000-0000-0000-0000-000000000002',
    '83000000-0000-0000-0000-000000000001',
    'pack_order',
    'pack:available',
    80,
    pg_catalog.now() + interval '60 days',
    'active'
  ),
  (
    '84000000-0000-0000-0000-000000000003',
    '83000000-0000-0000-0000-000000000001',
    'pack_order',
    'pack:refund-pending',
    100,
    pg_catalog.now() + interval '60 days',
    'active'
  );

insert into public.billing_orders (
  polar_order_id,
  user_id,
  plan_type,
  currency,
  paid_amount_cents,
  status
)
values (
  'pack:refund-pending',
  '83000000-0000-0000-0000-000000000001',
  'pack',
  'usd',
  1000,
  'refund_pending'
);

insert into public.jobs (
  id,
  user_id,
  status,
  url,
  source_key,
  duration_seconds,
  summary_id,
  stage,
  progress,
  claimed_at,
  heartbeat_at,
  lease_token,
  lease_expires_at,
  usage_settlement_required
)
values (
  '85000000-0000-0000-0000-000000000001',
  '83000000-0000-0000-0000-000000000001',
  'running',
  'https://www.youtube.com/watch?v=settlement-main',
  'youtube:settlement-main',
  300,
  '82000000-0000-0000-0000-000000000001',
  'finalizing',
  98,
  pg_catalog.now(),
  pg_catalog.now(),
  '86000000-0000-0000-0000-000000000001',
  pg_catalog.now() + interval '2 minutes',
  true
);

create temporary table first_settlement as
select public.settle_job_usage(
  '85000000-0000-0000-0000-000000000001',
  '86000000-0000-0000-0000-000000000001',
  100
) as result;

select is(
  (select result ->> 'resolution_type' from first_settlement),
  'settled',
  'first usage finalization creates the settlement'
);
select is(
  (select (result -> 'settlement' ->> 'subscription_seconds')::integer from first_settlement),
  100,
  'subscription credit is consumed first'
);
select is(
  (select (result -> 'settlement' ->> 'pack_seconds')::integer from first_settlement),
  80,
  'available pack credit is consumed second'
);
select is(
  (select (result -> 'settlement' ->> 'debt_incurred_seconds')::integer from first_settlement),
  120,
  'uncovered duration becomes debt under the existing policy'
);
select ok(
  (
    select
      (result -> 'settlement' ->> 'subscription_seconds')::integer
      + (result -> 'settlement' ->> 'pack_seconds')::integer
      + (result -> 'settlement' ->> 'debt_incurred_seconds')::integer
      = (result -> 'settlement' ->> 'duration_seconds')::integer
    from first_settlement
  ),
  'settlement components exactly balance to job duration'
);
select is(
  (
    select pg_catalog.count(*)
    from public.usage_settlements
    where job_id = '85000000-0000-0000-0000-000000000001'
  ),
  1::bigint,
  'exactly one job settlement exists'
);
select is(
  (
    select pg_catalog.count(*)
    from public.usage_ledger
    where job_id = '85000000-0000-0000-0000-000000000001'
  ),
  2::bigint,
  'one aggregate ledger row exists for each consumed source'
);
select is(
  (
    select pg_catalog.sum(seconds_used)::integer
    from public.usage_ledger
    where job_id = '85000000-0000-0000-0000-000000000001'
  ),
  180,
  'ledger total matches actual credit consumption'
);
select is(
  (
    select consumed_seconds
    from public.credit_lots
    where id = '84000000-0000-0000-0000-000000000001'
  ),
  100,
  'subscription lot mutation commits with settlement'
);
select is(
  (
    select consumed_seconds
    from public.credit_lots
    where id = '84000000-0000-0000-0000-000000000002'
  ),
  80,
  'pack lot mutation commits with settlement'
);
select is(
  (
    select consumed_seconds
    from public.credit_lots
    where id = '84000000-0000-0000-0000-000000000003'
  ),
  0,
  'refund-pending pack remains excluded'
);
select is(
  (
    select debt_seconds
    from public.entitlements
    where user_id = '83000000-0000-0000-0000-000000000001'
  ),
  120,
  'entitlement debt updates in the same transaction'
);
select ok(
  (
    select is_blocked
    from public.entitlements
    where user_id = '83000000-0000-0000-0000-000000000001'
  ),
  'existing debt-cap blocking policy is preserved'
);
select is(
  (
    select status
    from public.jobs
    where id = '85000000-0000-0000-0000-000000000001'
  ),
  'running',
  'settlement commit does not pretend terminal success already happened'
);

create temporary table repeated_settlement as
select public.settle_job_usage(
  '85000000-0000-0000-0000-000000000001',
  '86000000-0000-0000-0000-000000000001',
  100
) as result;

select is(
  (select result ->> 'resolution_type' from repeated_settlement),
  'already_settled',
  'duplicate settlement reuses the immutable result'
);
select is(
  (
    select pg_catalog.count(*)
    from public.usage_settlements
    where job_id = '85000000-0000-0000-0000-000000000001'
  ),
  1::bigint,
  'duplicate settlement cannot create another record'
);
select is(
  (
    select pg_catalog.count(*)
    from public.usage_ledger
    where job_id = '85000000-0000-0000-0000-000000000001'
  ),
  2::bigint,
  'duplicate settlement cannot duplicate ledger rows'
);
select ok(
  public.complete_job_after_settlement(
    '85000000-0000-0000-0000-000000000001',
    '82000000-0000-0000-0000-000000000001',
    '86000000-0000-0000-0000-000000000001'
  ),
  'settled job can transition to terminal success'
);
select is(
  (
    select status
    from public.jobs
    where id = '85000000-0000-0000-0000-000000000001'
  ),
  'succeeded',
  'terminal transition succeeds only after settlement'
);

insert into public.jobs (
  id,
  user_id,
  status,
  url,
  source_key,
  duration_seconds,
  summary_id,
  stage,
  progress,
  claimed_at,
  heartbeat_at,
  lease_token,
  lease_expires_at,
  usage_settlement_required
)
values (
  '85000000-0000-0000-0000-000000000002',
  '83000000-0000-0000-0000-000000000001',
  'running',
  'https://www.youtube.com/watch?v=settlement-missing',
  'youtube:settlement-missing',
  30,
  '82000000-0000-0000-0000-000000000001',
  'finalizing',
  98,
  pg_catalog.now(),
  pg_catalog.now(),
  '86000000-0000-0000-0000-000000000002',
  pg_catalog.now() + interval '2 minutes',
  true
);

select ok(
  not public.complete_job_after_settlement(
    '85000000-0000-0000-0000-000000000002',
    '82000000-0000-0000-0000-000000000001',
    '86000000-0000-0000-0000-000000000002'
  ),
  'terminal success is rejected without a settlement'
);
select is(
  (
    select status
    from public.jobs
    where id = '85000000-0000-0000-0000-000000000002'
  ),
  'running',
  'missing-settlement rejection leaves the owned attempt intact'
);
select throws_ok(
  $$
    select public.settle_job_usage(
      '85000000-0000-0000-0000-000000000002',
      '86000000-0000-0000-0000-000000000099',
      100
    )
  $$,
  '55000',
  'job lease is not current',
  'wrong lease token cannot settle usage'
);

update public.jobs
set lease_expires_at = pg_catalog.now() - interval '1 second'
where id = '85000000-0000-0000-0000-000000000002';

select throws_ok(
  $$
    select public.settle_job_usage(
      '85000000-0000-0000-0000-000000000002',
      '86000000-0000-0000-0000-000000000002',
      100
    )
  $$,
  '55000',
  'job lease is not current',
  'expired lease cannot settle usage'
);

insert into public.jobs (
  id,
  user_id,
  status,
  url,
  source_key,
  duration_seconds,
  summary_id,
  stage,
  progress,
  claimed_at,
  heartbeat_at,
  lease_token,
  lease_expires_at,
  usage_settlement_required
)
values (
  '85000000-0000-0000-0000-000000000003',
  '83000000-0000-0000-0000-000000000001',
  'running',
  'https://www.youtube.com/watch?v=settlement-crash',
  'youtube:settlement-crash',
  0,
  '82000000-0000-0000-0000-000000000001',
  'finalizing',
  98,
  pg_catalog.now(),
  pg_catalog.now(),
  '86000000-0000-0000-0000-000000000003',
  pg_catalog.now() + interval '2 minutes',
  true
);

select is(
  (
    public.settle_job_usage(
      '85000000-0000-0000-0000-000000000003',
      '86000000-0000-0000-0000-000000000003',
      100
    ) ->> 'resolution_type'
  ),
  'settled',
  'crash-boundary fixture settles before terminal success'
);

update public.jobs
set lease_expires_at = pg_catalog.now() - interval '1 second'
where id = '85000000-0000-0000-0000-000000000003';

select is(
  public.requeue_stale_jobs(interval '5 minutes'),
  2,
  'stale recovery requeues expired settled and unsettled attempts'
);
select is(
  (
    select stage
    from public.jobs
    where id = '85000000-0000-0000-0000-000000000003'
  ),
  'finalizing',
  'crash after summary creation remains visibly finalizing'
);

update public.jobs
set run_after = pg_catalog.now() + interval '1 hour'
where id = '85000000-0000-0000-0000-000000000002';

create temporary table reclaimed_settled_job as
select *
from public.claim_next_settled_job(interval '2 minutes');

select is(
  (select id from reclaimed_settled_job),
  '85000000-0000-0000-0000-000000000003'::uuid,
  'settled crash-boundary job receives a fresh lease'
);
select is(
  (
    public.settle_job_usage(
      '85000000-0000-0000-0000-000000000003',
      (select lease_token from reclaimed_settled_job),
      100
    ) ->> 'resolution_type'
  ),
  'already_settled',
  'fresh attempt reuses the pre-crash settlement'
);
select ok(
  public.complete_job_after_settlement(
    '85000000-0000-0000-0000-000000000003',
    '82000000-0000-0000-0000-000000000001',
    (select lease_token from reclaimed_settled_job)
  ),
  'fresh attempt completes without another charge'
);

insert into public.credit_lots (
  id,
  user_id,
  lot_type,
  source_key,
  granted_seconds,
  pack_expires_at,
  status
)
values (
  '84000000-0000-0000-0000-000000000004',
  '83000000-0000-0000-0000-000000000002',
  'subscription_cycle',
  'subscription:rollback',
  30,
  pg_catalog.now() + interval '30 days',
  'active'
);

insert into public.jobs (
  id,
  user_id,
  status,
  url,
  source_key,
  duration_seconds,
  summary_id,
  stage,
  progress,
  claimed_at,
  heartbeat_at,
  lease_token,
  lease_expires_at,
  usage_settlement_required
)
values (
  '85000000-0000-0000-0000-000000000006',
  '83000000-0000-0000-0000-000000000002',
  'running',
  'https://www.youtube.com/watch?v=settlement-rollback',
  'youtube:settlement-rollback',
  30,
  '82000000-0000-0000-0000-000000000001',
  'finalizing',
  98,
  pg_catalog.now(),
  pg_catalog.now(),
  '86000000-0000-0000-0000-000000000006',
  pg_catalog.now() + interval '2 minutes',
  true
);

select throws_ok(
  $$
    select public.settle_job_usage(
      '85000000-0000-0000-0000-000000000006',
      '86000000-0000-0000-0000-000000000006',
      100
    )
  $$,
  'P0002',
  'billing entitlement is missing',
  'failed settlement aborts when required billing state is missing'
);
select is(
  (
    select consumed_seconds
    from public.credit_lots
    where id = '84000000-0000-0000-0000-000000000004'
  ),
  0,
  'failed settlement rolls back prior lot consumption'
);
select is(
  (
    select pg_catalog.count(*)
    from public.usage_settlements
    where job_id = '85000000-0000-0000-0000-000000000006'
  ),
  0::bigint,
  'failed settlement leaves no idempotency record'
);
select is(
  (
    select pg_catalog.count(*)
    from public.usage_ledger
    where job_id = '85000000-0000-0000-0000-000000000006'
  ),
  0::bigint,
  'failed settlement leaves no ledger residue'
);

insert into public.jobs (
  id,
  user_id,
  status,
  url,
  source_key,
  duration_seconds,
  summary_id,
  stage,
  progress,
  usage_settlement_required
)
values
  (
    '85000000-0000-0000-0000-000000000004',
    '83000000-0000-0000-0000-000000000001',
    'succeeded',
    'https://www.youtube.com/watch?v=settlement-reconcile',
    'youtube:settlement-reconcile',
    30,
    '82000000-0000-0000-0000-000000000001',
    'completed',
    100,
    true
  ),
  (
    '85000000-0000-0000-0000-000000000005',
    '83000000-0000-0000-0000-000000000001',
    'succeeded',
    'https://www.youtube.com/watch?v=settlement-legacy',
    'youtube:settlement-legacy',
    30,
    '82000000-0000-0000-0000-000000000001',
    'completed',
    100,
    false
  );

select is(
  public.requeue_unsettled_jobs(),
  1,
  'reconciliation finds only settlement-required terminal gaps'
);
select is(
  (
    select status
    from public.jobs
    where id = '85000000-0000-0000-0000-000000000004'
  ),
  'queued',
  'unsettled terminal job becomes retryable'
);
select is(
  (
    select stage
    from public.jobs
    where id = '85000000-0000-0000-0000-000000000004'
  ),
  'finalizing',
  'reconciled job exposes a finalization state'
);
select is(
  (
    select status
    from public.jobs
    where id = '85000000-0000-0000-0000-000000000005'
  ),
  'succeeded',
  'legacy terminal jobs remain exempt from unsafe recharging'
);
select ok(
  (
    select usage_settlement_required
    from public.jobs
    where id = '85000000-0000-0000-0000-000000000004'
  ),
  'new jobs require settlement by default'
);
select ok(
  not (
    select usage_settlement_required
    from public.jobs
    where id = '85000000-0000-0000-0000-000000000005'
  ),
  'legacy exemption is explicit'
);
select throws_ok(
  $$
    insert into public.usage_settlements (
      job_id,
      user_id,
      lease_token,
      duration_seconds,
      subscription_seconds,
      pack_seconds,
      debt_incurred_seconds,
      entitlement_debt_after_seconds
    )
    values (
      '85000000-0000-0000-0000-000000000005',
      '83000000-0000-0000-0000-000000000001',
      '86000000-0000-0000-0000-000000000005',
      10,
      3,
      3,
      3,
      0
    )
  $$,
  '23514',
  null,
  'settlement balance constraint rejects incomplete accounting'
);
select throws_ok(
  $$
    insert into public.usage_ledger (
      user_id,
      job_id,
      settlement_id,
      seconds_used,
      source
    )
    select
      user_id,
      job_id,
      id,
      1,
      'subscription'
    from public.usage_settlements
    where job_id = '85000000-0000-0000-0000-000000000001'
  $$,
  '23505',
  null,
  'ledger uniqueness rejects a duplicate settlement source'
);
select ok(
  (
    select not usage_settlement_required
    from public.jobs
    where user_id = '00000000-0000-0000-0000-000000000001'
      and status = 'succeeded'
  ),
  'seeded historical terminal job is explicitly settlement-exempt'
);

select * from finish();

rollback;
