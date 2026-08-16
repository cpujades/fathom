begin;

set local search_path = extensions, public, pg_catalog;

select plan(59);

insert into auth.users (id)
values ('12000000-0000-0000-0000-000000000001');

select has_column(
  'public',
  'entitlements',
  'next_subscription_reconcile_at',
  'subscriptions persist their next provider audit time'
);
select has_index(
  'public',
  'entitlements',
  'entitlements_subscription_reconcile_due_idx',
  'due subscription audits have a bounded lookup index'
);
select has_trigger(
  'public',
  'entitlements',
  'schedule_subscription_reconciliation',
  'subscription state changes schedule or disable provider audits'
);

select has_table(
  'public',
  'billing_maintenance_leases',
  'distributed billing maintenance leases exist'
);
select ok(
  (
    select relrowsecurity
    from pg_catalog.pg_class
    where oid = 'public.billing_maintenance_leases'::regclass
  ),
  'billing maintenance leases have RLS enabled'
);
select ok(
  not has_table_privilege('authenticated', 'public.billing_maintenance_leases', 'select'),
  'authenticated users cannot inspect maintenance leases'
);
select ok(
  not has_table_privilege('service_role', 'public.billing_maintenance_leases', 'select'),
  'service role must use the lease commands instead of direct table access'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.begin_pack_refund(uuid,text,integer)',
    'execute'
  ),
  'authenticated users cannot begin refunds directly'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.begin_pack_refund(uuid,text,integer)',
    'execute'
  ),
  'service role can begin pack refunds'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.reopen_pack_refund(uuid,text,integer)',
    'execute'
  ),
  'authenticated users cannot reopen refunds directly'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.reopen_pack_refund(uuid,text,integer)',
    'execute'
  ),
  'service role can reopen pack refunds'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.claim_billing_maintenance_lease(text,uuid,interval)',
    'execute'
  ),
  'authenticated users cannot claim billing maintenance'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.claim_billing_maintenance_lease(text,uuid,interval)',
    'execute'
  ),
  'service role can claim billing maintenance'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.renew_billing_maintenance_lease(text,uuid,interval)',
    'execute'
  ),
  'authenticated users cannot renew billing maintenance'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.renew_billing_maintenance_lease(text,uuid,interval)',
    'execute'
  ),
  'service role can renew billing maintenance'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.release_billing_maintenance_lease(text,uuid)',
    'execute'
  ),
  'authenticated users cannot release billing maintenance'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.release_billing_maintenance_lease(text,uuid)',
    'execute'
  ),
  'service role can release billing maintenance'
);
select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.begin_pack_refund(uuid,text,integer)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'refund initiation has an immutable search path'
);
select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.reopen_pack_refund(uuid,text,integer)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'refund reopening has an immutable search path'
);
select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.claim_billing_maintenance_lease(text,uuid,interval)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'lease claiming has an immutable search path'
);
select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.renew_billing_maintenance_lease(text,uuid,interval)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'lease renewal has an immutable search path'
);
select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.release_billing_maintenance_lease(text,uuid)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'lease release has an immutable search path'
);
select has_trigger(
  'public',
  'billing_orders',
  'revoke_refunded_pack_lot',
  'refunded orders revoke their pack lots in the same transaction'
);
select has_trigger(
  'public',
  'credit_lots',
  'reject_active_refunding_pack_lot',
  'refunding pack lots cannot be reactivated'
);

select throws_ok(
  $$
    select public.claim_billing_maintenance_lease(
      'billing-recovery-test',
      '11000000-0000-0000-0000-000000000001',
      interval '1 second'
    )
  $$,
  '22023',
  'billing maintenance lease must be between 10 seconds and 10 minutes',
  'unreasonably short leases are rejected'
);
select ok(
  public.claim_billing_maintenance_lease(
    'billing-recovery-test',
    '11000000-0000-0000-0000-000000000001',
    interval '2 minutes'
  ),
  'first maintenance worker claims the lease'
);
select ok(
  not public.claim_billing_maintenance_lease(
    'billing-recovery-test',
    '11000000-0000-0000-0000-000000000002',
    interval '2 minutes'
  ),
  'second maintenance worker cannot claim an active lease'
);
select ok(
  not public.renew_billing_maintenance_lease(
    'billing-recovery-test',
    '11000000-0000-0000-0000-000000000002',
    interval '2 minutes'
  ),
  'non-owner cannot renew the lease'
);
select ok(
  public.renew_billing_maintenance_lease(
    'billing-recovery-test',
    '11000000-0000-0000-0000-000000000001',
    interval '2 minutes'
  ),
  'owner renews the lease'
);
select ok(
  not public.release_billing_maintenance_lease(
    'billing-recovery-test',
    '11000000-0000-0000-0000-000000000002'
  ),
  'non-owner cannot release the lease'
);
select ok(
  public.release_billing_maintenance_lease(
    'billing-recovery-test',
    '11000000-0000-0000-0000-000000000001'
  ),
  'owner releases the lease'
);
select ok(
  public.claim_billing_maintenance_lease(
    'billing-recovery-test',
    '11000000-0000-0000-0000-000000000002',
    interval '2 minutes'
  ),
  'another worker can claim after release'
);
select ok(
  public.release_billing_maintenance_lease(
    'billing-recovery-test',
    '11000000-0000-0000-0000-000000000002'
  ),
  'second owner releases its lease'
);
select is(
  (
    select pg_catalog.count(*)
    from public.billing_maintenance_leases
    where lease_name = 'billing-recovery-test'
  ),
  0::bigint,
  'released maintenance leases leave no owner row'
);

insert into public.entitlements (user_id)
values ('12000000-0000-0000-0000-000000000001');

update public.entitlements
set polar_subscription_id = 'sub_reconcile_schedule_001',
    subscription_status = 'active'
where user_id = '12000000-0000-0000-0000-000000000001';

select ok(
  (
    select next_subscription_reconcile_at
    from public.entitlements
    where user_id = '12000000-0000-0000-0000-000000000001'
  ) >= pg_catalog.now() + interval '5 hours 59 minutes',
  'active subscription changes schedule a delayed provider audit'
);

update public.entitlements
set subscription_status = 'revoked'
where user_id = '12000000-0000-0000-0000-000000000001';

select is(
  (
    select next_subscription_reconcile_at
    from public.entitlements
    where user_id = '12000000-0000-0000-0000-000000000001'
  ),
  null::timestamptz,
  'terminal subscriptions disable future provider polling'
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
  'ord_atomic_refund_001',
  '12000000-0000-0000-0000-000000000001',
  'pack',
  'usd',
  3000,
  'paid'
);

insert into public.credit_lots (
  id,
  user_id,
  lot_type,
  source_key,
  granted_seconds,
  consumed_seconds,
  expires_at,
  status
)
values (
  '13000000-0000-0000-0000-000000000001',
  '12000000-0000-0000-0000-000000000001',
  'pack_order',
  'ord_atomic_refund_001',
  600,
  200,
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
  stage,
  progress,
  usage_settlement_required
)
values (
  '14000000-0000-0000-0000-000000000001',
  '12000000-0000-0000-0000-000000000001',
  'queued',
  'https://www.youtube.com/watch?v=refund-active-job',
  'youtube:refund-active-job',
  100,
  'queued',
  0,
  true
);

create temporary table blocked_refund as
select public.begin_pack_refund(
  '12000000-0000-0000-0000-000000000001',
  'ord_atomic_refund_001',
  600
) as result;

select is(
  (select result ->> 'resolution_type' from blocked_refund),
  'active_jobs_in_progress',
  'an active billable briefing blocks a pack refund'
);
select is(
  (select status from public.billing_orders where polar_order_id = 'ord_atomic_refund_001'),
  'paid',
  'a blocked refund leaves the billing order paid'
);
select is(
  (
    select consumed_seconds
    from public.credit_lots
    where source_key = 'ord_atomic_refund_001'
  ),
  200,
  'a blocked refund does not change pack consumption'
);

delete from public.jobs
where id = '14000000-0000-0000-0000-000000000001';

create temporary table first_refund as
select public.begin_pack_refund(
  '12000000-0000-0000-0000-000000000001',
  'ord_atomic_refund_001',
  600
) as result;

select is(
  (select result ->> 'resolution_type' from first_refund),
  'started',
  'refund starts from the locked order and lot state'
);
select is(
  (select (result ->> 'refundable_amount_cents')::integer from first_refund),
  2000,
  'refund amount is recomputed proportionally from remaining credit'
);
select is(
  (select (result ->> 'remaining_seconds_before_refund')::integer from first_refund),
  400,
  'refund result reports the authoritative remaining seconds'
);
select is(
  (select status from public.billing_orders where polar_order_id = 'ord_atomic_refund_001'),
  'refund_pending',
  'order becomes refund-pending in the quote transaction'
);
select is(
  (
    select pack_available_seconds
    from public.entitlements
    where user_id = '12000000-0000-0000-0000-000000000001'
  ),
  0,
  'refund-pending credit is unavailable in the same transaction'
);
select is(
  (
    public.begin_pack_refund(
      '12000000-0000-0000-0000-000000000001',
      'ord_atomic_refund_001',
      600
    ) ->> 'resolution_type'
  ),
  'already_pending',
  'duplicate refund initiation cannot quote the lot again'
);

update public.entitlements
set debt_seconds = 100
where user_id = '12000000-0000-0000-0000-000000000001';

select is(
  public.pay_down_billing_debt_from_lot(
    '12000000-0000-0000-0000-000000000001',
    '13000000-0000-0000-0000-000000000001',
    600
  ),
  100,
  'refund-pending pack cannot pay down debt'
);
select is(
  (select consumed_seconds from public.credit_lots where source_key = 'ord_atomic_refund_001'),
  200,
  'refund-pending pack remains unconsumed by debt paydown'
);

update public.entitlements
set debt_seconds = 0
where user_id = '12000000-0000-0000-0000-000000000001';

select is(
  (
    public.reopen_pack_refund(
      '12000000-0000-0000-0000-000000000001',
      'ord_atomic_refund_001',
      600
    ) ->> 'resolution_type'
  ),
  'reopened',
  'definitively failed provider refund reopens atomically'
);
select is(
  (select status from public.billing_orders where polar_order_id = 'ord_atomic_refund_001'),
  'paid',
  'reopened order returns to paid'
);
select is(
  (
    select pack_available_seconds
    from public.entitlements
    where user_id = '12000000-0000-0000-0000-000000000001'
  ),
  400,
  'reopening restores only the actual remaining credit'
);

update public.billing_orders
set status = 'refunded',
    refunded_amount_cents = 2000
where polar_order_id = 'ord_atomic_refund_001';

select is(
  (select status from public.credit_lots where source_key = 'ord_atomic_refund_001'),
  'revoked',
  'refunded order revokes its pack lot atomically'
);
select is(
  (select consumed_seconds from public.credit_lots where source_key = 'ord_atomic_refund_001'),
  200,
  'refund revocation preserves already consumed credit'
);
select is(
  (select revoked_seconds from public.credit_lots where source_key = 'ord_atomic_refund_001'),
  400,
  'refund revocation removes exactly the remaining credit'
);
select lives_ok(
  $$
    select public.refresh_billing_entitlement_snapshot(
      '12000000-0000-0000-0000-000000000001',
      600
    )
  $$,
  'refunded entitlement snapshot refresh succeeds'
);
select is(
  (
    select pack_available_seconds
    from public.entitlements
    where user_id = '12000000-0000-0000-0000-000000000001'
  ),
  0,
  'refunded credit remains unavailable to entitlement snapshots'
);
select throws_ok(
  $$
    update public.credit_lots
    set status = 'active'
    where source_key = 'ord_atomic_refund_001'
  $$,
  '23514',
  'cannot activate a credit lot for a refunding or refunded pack order',
  'refunded pack lot cannot be reactivated'
);
select is(
  (select status from public.credit_lots where source_key = 'ord_atomic_refund_001'),
  'revoked',
  'failed reactivation leaves refunded pack credit revoked'
);

insert into public.credit_lots (
  id,
  user_id,
  lot_type,
  source_key,
  granted_seconds,
  expires_at,
  status
)
values (
  '13000000-0000-0000-0000-000000000002',
  '12000000-0000-0000-0000-000000000001',
  'pack_order',
  'ord_inserted_refunded_001',
  100,
  pg_catalog.now() + interval '30 days',
  'active'
);

insert into public.billing_orders (
  polar_order_id,
  user_id,
  plan_type,
  currency,
  paid_amount_cents,
  refunded_amount_cents,
  status
)
values (
  'ord_inserted_refunded_001',
  '12000000-0000-0000-0000-000000000001',
  'pack',
  'usd',
  1000,
  1000,
  'refunded'
);

select is(
  (select status from public.credit_lots where source_key = 'ord_inserted_refunded_001'),
  'revoked',
  'inserting an already-refunded order revokes a pre-existing pack lot'
);
select is(
  (select revoked_seconds from public.credit_lots where source_key = 'ord_inserted_refunded_001'),
  100,
  'insert-time refund revocation removes the full remaining lot'
);

select * from finish();

rollback;
