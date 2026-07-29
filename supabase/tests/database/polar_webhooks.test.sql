begin;

set local search_path = extensions, public, pg_catalog;

select plan(51);

select col_not_null(
  'public',
  'billing_webhook_events',
  'provider_event_at',
  'webhook events retain a provider ordering timestamp'
);
select has_column(
  'public',
  'billing_webhook_events',
  'resource_type',
  'webhook events identify the normalized resource type'
);
select has_column(
  'public',
  'billing_webhook_events',
  'resource_id',
  'webhook events identify the normalized resource'
);
select has_index(
  'public',
  'billing_webhook_events',
  'billing_webhook_events_resource_idx',
  'resource replay lookup is indexed'
);
select has_column(
  'public',
  'entitlements',
  'provider_event_at',
  'subscription snapshots retain their ordering fence'
);
select has_column(
  'public',
  'entitlements',
  'provider_event_id',
  'subscription snapshots retain their ordering tie-breaker'
);
select has_column(
  'public',
  'polar_customers',
  'provider_event_at',
  'customer snapshots retain their ordering fence'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.apply_polar_webhook_event(text,text,timestamptz,text,text,jsonb,integer)',
    'execute'
  ),
  'authenticated users cannot apply billing webhooks'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.apply_polar_webhook_event(text,text,timestamptz,text,text,jsonb,integer)',
    'execute'
  ),
  'service role can apply billing webhooks'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.get_billing_webhook_diagnostics(interval)',
    'execute'
  ),
  'authenticated users cannot inspect webhook diagnostics'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.get_billing_webhook_diagnostics(interval)',
    'execute'
  ),
  'service role can inspect webhook diagnostics'
);
select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.apply_polar_webhook_event(text,text,timestamptz,text,text,jsonb,integer)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'webhook command has an immutable search path'
);
select is(
  (
    select proconfig
    from pg_catalog.pg_proc
    where oid = 'public.get_billing_webhook_diagnostics(interval)'::regprocedure
  ),
  array['search_path=pg_catalog']::text[],
  'diagnostic command has an immutable search path'
);

insert into public.plans (
  id,
  name,
  plan_type,
  polar_product_id,
  plan_code,
  currency,
  amount_cents,
  billing_interval,
  version,
  quota_seconds,
  rollover_cap_seconds,
  pack_expiry_days
)
values
  (
    '92000000-0000-0000-0000-000000000001',
    'Replay Pack',
    'pack',
    'prod_pack_replay',
    'replay_pack',
    'usd',
    3000,
    null,
    1,
    600,
    0,
    30
  ),
  (
    '92000000-0000-0000-0000-000000000002',
    'Replay Subscription',
    'subscription',
    'prod_subscription_replay',
    'replay_subscription',
    'usd',
    1000,
    'month',
    1,
    1200,
    300,
    null
  );

insert into public.entitlements (
  user_id,
  debt_seconds,
  is_blocked
)
values (
  '91000000-0000-0000-0000-000000000001',
  100,
  false
);

create temporary table first_paid as
select public.apply_polar_webhook_event(
  'evt_order_paid_001',
  'order.paid',
  '2026-07-29T10:00:00+00:00',
  'order',
  'ord_replay_001',
  jsonb_build_object(
    'order_id', 'ord_replay_001',
    'user_id', '91000000-0000-0000-0000-000000000001',
    'product_id', 'prod_pack_replay',
    'customer_id', 'cus_replay_001',
    'email', 'not-retained@example.test',
    'currency', 'usd',
    'paid_amount_cents', 3000
  ),
  600
) as result;

select is(
  (select result ->> 'resolution_type' from first_paid),
  'processed',
  'first paid event applies successfully'
);

create temporary table duplicate_paid as
select public.apply_polar_webhook_event(
  'evt_order_paid_001',
  'order.paid',
  '2026-07-29T10:00:00+00:00',
  'order',
  'ord_replay_001',
  jsonb_build_object(
    'order_id', 'ord_replay_001',
    'user_id', '91000000-0000-0000-0000-000000000001',
    'product_id', 'prod_pack_replay',
    'customer_id', 'cus_replay_001',
    'email', 'not-retained@example.test',
    'currency', 'usd',
    'paid_amount_cents', 3000
  ),
  600
) as result;

select is(
  (select result ->> 'resolution_type' from duplicate_paid),
  'already_processed',
  'same provider event id is acknowledged without replay'
);
select is(
  (select count(*) from public.billing_webhook_events where event_id = 'evt_order_paid_001'),
  1::bigint,
  'one audit row exists for a replayed provider event'
);
select is(
  (select count(*) from public.billing_orders where polar_order_id = 'ord_replay_001'),
  1::bigint,
  'one billing order exists after duplicate delivery'
);
select is(
  (
    select count(*)
    from public.credit_lots
    where lot_type = 'pack_order'
      and source_key = 'ord_replay_001'
  ),
  1::bigint,
  'one credit lot exists after duplicate delivery'
);
select is(
  (
    select consumed_seconds
    from public.credit_lots
    where lot_type = 'pack_order'
      and source_key = 'ord_replay_001'
  ),
  100,
  'duplicate delivery cannot repeat debt paydown'
);
select is(
  (
    select pack_available_seconds
    from public.entitlements
    where user_id = '91000000-0000-0000-0000-000000000001'
  ),
  500,
  'entitlement snapshot reflects the one-time pack grant and debt paydown'
);
select ok(
  not (
    select payload ? 'email'
    from public.billing_webhook_events
    where event_id = 'evt_order_paid_001'
  ),
  'normalized event audit does not retain customer email'
);
select is(
  (
    select status
    from public.billing_webhook_events
    where event_id = 'evt_order_paid_001'
  ),
  'processed',
  'success and its effects commit together'
);

create temporary table failed_paid as
select public.apply_polar_webhook_event(
  'evt_order_paid_retry',
  'order.paid',
  '2026-07-29T10:10:00+00:00',
  'order',
  'ord_retry_001',
  jsonb_build_object(
    'order_id', 'ord_retry_001',
    'user_id', '91000000-0000-0000-0000-000000000002',
    'product_id', 'prod_added_after_failure',
    'currency', 'usd',
    'paid_amount_cents', 2000
  ),
  600
) as result;

select is(
  (select result ->> 'resolution_type' from failed_paid),
  'failed',
  'a failed effect reports a retryable failure'
);
select is(
  (
    select status
    from public.billing_webhook_events
    where event_id = 'evt_order_paid_retry'
  ),
  'failed',
  'failed event remains visible for replay'
);
select is(
  (select count(*) from public.billing_orders where polar_order_id = 'ord_retry_001'),
  0::bigint,
  'a failed event leaves no partial order'
);
select is(
  (
    select count(*)
    from public.credit_lots
    where source_key = 'ord_retry_001'
  ),
  0::bigint,
  'a failed event leaves no partial credit lot'
);

insert into public.plans (
  id,
  name,
  plan_type,
  polar_product_id,
  plan_code,
  currency,
  amount_cents,
  billing_interval,
  version,
  quota_seconds,
  rollover_cap_seconds,
  pack_expiry_days
)
values (
  '92000000-0000-0000-0000-000000000003',
  'Retry Pack',
  'pack',
  'prod_added_after_failure',
  'retry_pack',
  'usd',
  2000,
  null,
  1,
  400,
  0,
  30
);

create temporary table retried_paid as
select public.apply_polar_webhook_event(
  'evt_order_paid_retry',
  'order.paid',
  '2026-07-29T10:10:00+00:00',
  'order',
  'ord_retry_001',
  jsonb_build_object(
    'order_id', 'ord_retry_001',
    'user_id', '91000000-0000-0000-0000-000000000002',
    'product_id', 'prod_added_after_failure',
    'currency', 'usd',
    'paid_amount_cents', 2000
  ),
  600
) as result;

select is(
  (select result ->> 'resolution_type' from retried_paid),
  'processed',
  'same failed provider event can be safely retried'
);
select is(
  (
    select status
    from public.billing_webhook_events
    where event_id = 'evt_order_paid_retry'
  ),
  'processed',
  'successful retry converges the audit row'
);
select is(
  (select count(*) from public.billing_orders where polar_order_id = 'ord_retry_001'),
  1::bigint,
  'successful retry creates exactly one order'
);

create temporary table early_refund as
select public.apply_polar_webhook_event(
  'evt_refund_before_paid',
  'order.refunded',
  '2026-07-29T10:20:00+00:00',
  'order',
  'ord_refund_before_paid',
  jsonb_build_object(
    'order_id', 'ord_refund_before_paid',
    'provider_total_refunded', 3000,
    'refund_delta_cents', 0
  ),
  600
) as result;

select is(
  (select result ->> 'resolution_type' from early_refund),
  'deferred',
  'refund arriving before its order is safely deferred'
);
select is(
  (
    select status
    from public.billing_webhook_events
    where event_id = 'evt_refund_before_paid'
  ),
  'deferred',
  'deferred refund remains visible without partial effects'
);

create temporary table late_paid as
select public.apply_polar_webhook_event(
  'evt_paid_after_refund',
  'order.paid',
  '2026-07-29T10:15:00+00:00',
  'order',
  'ord_refund_before_paid',
  jsonb_build_object(
    'order_id', 'ord_refund_before_paid',
    'user_id', '91000000-0000-0000-0000-000000000003',
    'product_id', 'prod_pack_replay',
    'currency', 'usd',
    'paid_amount_cents', 3000
  ),
  600
) as result;

select is(
  (select result ->> 'resolution_type' from late_paid),
  'processed',
  'later paid delivery creates the missing order'
);
select is(
  (
    select status
    from public.billing_webhook_events
    where event_id = 'evt_refund_before_paid'
  ),
  'processed',
  'paid event consumes its deferred refund atomically'
);
select is(
  (
    select status
    from public.billing_orders
    where polar_order_id = 'ord_refund_before_paid'
  ),
  'refunded',
  'out-of-order paid and refund events converge to refunded'
);
select is(
  (
    select status
    from public.credit_lots
    where lot_type = 'pack_order'
      and source_key = 'ord_refund_before_paid'
  ),
  'revoked',
  'refund policy revokes the remaining pack exactly as before'
);

create temporary table subscription_active as
select public.apply_polar_webhook_event(
  'evt_subscription_active_new',
  'subscription.active',
  '2026-07-29T12:00:00+00:00',
  'subscription',
  'sub_replay_001',
  jsonb_build_object(
    'subscription_id', 'sub_replay_001',
    'user_id', '91000000-0000-0000-0000-000000000004',
    'product_id', 'prod_subscription_replay',
    'status', 'active',
    'period_start', '2026-07-01T00:00:00+00:00',
    'period_end', '2026-08-01T00:00:00+00:00'
  ),
  600
) as result;

select is(
  (select result ->> 'resolution_type' from subscription_active),
  'processed',
  'current subscription event applies'
);
select is(
  (
    select subscription_status
    from public.entitlements
    where user_id = '91000000-0000-0000-0000-000000000004'
  ),
  'active',
  'subscription snapshot becomes active'
);
select is(
  (
    select status
    from public.credit_lots
    where lot_type = 'subscription_cycle'
      and source_key = 'sub_replay_001:2026-07-01T00:00:00+00:00'
  ),
  'active',
  'active subscription owns one current cycle lot'
);

create temporary table stale_revoked as
select public.apply_polar_webhook_event(
  'evt_subscription_revoked_old',
  'subscription.revoked',
  '2026-07-29T11:00:00+00:00',
  'subscription',
  'sub_replay_001',
  jsonb_build_object(
    'subscription_id', 'sub_replay_001',
    'user_id', '91000000-0000-0000-0000-000000000004',
    'product_id', 'prod_subscription_replay',
    'status', 'revoked',
    'period_start', '2026-07-01T00:00:00+00:00',
    'period_end', '2026-08-01T00:00:00+00:00'
  ),
  600
) as result;

select is(
  (select result ->> 'outcome' from stale_revoked),
  'stale_ignored',
  'older subscription state is acknowledged as a no-op'
);
select is(
  (
    select subscription_status
    from public.entitlements
    where user_id = '91000000-0000-0000-0000-000000000004'
  ),
  'active',
  'older revoked event cannot regress a newer active snapshot'
);

create temporary table current_revoked as
select public.apply_polar_webhook_event(
  'evt_subscription_revoked_new',
  'subscription.revoked',
  '2026-07-29T13:00:00+00:00',
  'subscription',
  'sub_replay_001',
  jsonb_build_object(
    'subscription_id', 'sub_replay_001',
    'user_id', '91000000-0000-0000-0000-000000000004',
    'product_id', 'prod_subscription_replay',
    'status', 'revoked',
    'period_start', '2026-07-01T00:00:00+00:00',
    'period_end', '2026-08-01T00:00:00+00:00'
  ),
  600
) as result;

select is(
  (select result ->> 'outcome' from current_revoked),
  'applied',
  'newer revoked event applies'
);
select is(
  (
    select subscription_status
    from public.entitlements
    where user_id = '91000000-0000-0000-0000-000000000004'
  ),
  'revoked',
  'newer revoked event becomes provider truth'
);
select is(
  (
    select status
    from public.credit_lots
    where lot_type = 'subscription_cycle'
      and source_key = 'sub_replay_001:2026-07-01T00:00:00+00:00'
  ),
  'expired',
  'revoked subscription expires the current cycle lot'
);

create temporary table replayed_old_active as
select public.apply_polar_webhook_event(
  'evt_subscription_active_replayed_old',
  'subscription.active',
  '2026-07-29T12:30:00+00:00',
  'subscription',
  'sub_replay_001',
  jsonb_build_object(
    'subscription_id', 'sub_replay_001',
    'user_id', '91000000-0000-0000-0000-000000000004',
    'product_id', 'prod_subscription_replay',
    'status', 'active',
    'period_start', '2026-07-01T00:00:00+00:00',
    'period_end', '2026-08-01T00:00:00+00:00'
  ),
  600
) as result;

select is(
  (select result ->> 'outcome' from replayed_old_active),
  'stale_ignored',
  'replayed older active event is deterministic'
);
select is(
  (
    select subscription_status
    from public.entitlements
    where user_id = '91000000-0000-0000-0000-000000000004'
  ),
  'revoked',
  'out-of-order sequence converges to the newest subscription state'
);

select is(
  (
    public.apply_polar_webhook_event(
      'evt_diagnostic_failed',
      'order.paid',
      '2026-07-29T14:00:00+00:00',
      'order',
      'ord_diagnostic_failed',
      jsonb_build_object(
        'order_id', 'ord_diagnostic_failed',
        'user_id', '91000000-0000-0000-0000-000000000005',
        'product_id', 'missing_diagnostic_product',
        'currency', 'usd',
        'paid_amount_cents', 1
      ),
      600
    ) ->> 'resolution_type'
  ),
  'failed',
  'diagnostic fixture creates one visible failed event'
);
select is(
  (
    public.apply_polar_webhook_event(
      'evt_diagnostic_deferred',
      'order.refunded',
      '2026-07-29T14:05:00+00:00',
      'order',
      'ord_diagnostic_missing',
      jsonb_build_object(
        'order_id', 'ord_diagnostic_missing',
        'provider_total_refunded', 1,
        'refund_delta_cents', 0
      ),
      600
    ) ->> 'resolution_type'
  ),
  'deferred',
  'diagnostic fixture creates one visible deferred event'
);

create temporary table webhook_diagnostic as
select public.get_billing_webhook_diagnostics(interval '5 minutes') as result;

select is(
  (select (result ->> 'failed_count')::integer from webhook_diagnostic),
  1,
  'diagnostic reports failed events'
);
select is(
  (select (result ->> 'deferred_count')::integer from webhook_diagnostic),
  1,
  'diagnostic reports deferred events'
);
select is(
  (select (result ->> 'deferred_unknown_order_count')::integer from webhook_diagnostic),
  1,
  'diagnostic identifies deferred refunds missing their order'
);
select ok(
  (select result ->> 'oldest_unresolved_at' from webhook_diagnostic) is not null,
  'diagnostic exposes the age of unresolved work without provider payload data'
);

select * from finish();

rollback;
