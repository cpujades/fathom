begin;

set local search_path = extensions, public, pg_catalog;

select plan(18);

select has_table(
  'public',
  'billing_sync_operations',
  'billing sync operations persist checkout and refund confirmation state'
);
select ok(
  (
    select relrowsecurity
    from pg_catalog.pg_class
    where oid = 'public.billing_sync_operations'::regclass
  ),
  'billing sync operations have RLS enabled'
);
select ok(
  not has_table_privilege('authenticated', 'public.billing_sync_operations', 'select'),
  'authenticated browsers cannot inspect billing operations directly'
);
select ok(
  not has_table_privilege('anon', 'public.billing_sync_operations', 'select'),
  'anonymous browsers cannot inspect billing operations'
);
select ok(
  has_table_privilege('service_role', 'public.billing_sync_operations', 'select')
    and has_table_privilege('service_role', 'public.billing_sync_operations', 'insert')
    and has_table_privilege('service_role', 'public.billing_sync_operations', 'update')
    and has_table_privilege('service_role', 'public.billing_sync_operations', 'delete'),
  'the authenticated API service can manage billing operations'
);
select has_index(
  'public',
  'billing_sync_operations',
  'billing_sync_operations_refund_order_idx',
  'refund webhooks can resolve pending operations by order efficiently'
);
select has_trigger(
  'public',
  'billing_sync_operations',
  'set_billing_sync_operations_updated_at',
  'billing operation updates receive an authoritative timestamp'
);

select has_function(
  'public',
  'resolve_billing_sync_operation',
  array['uuid', 'uuid', 'text', 'text', 'text', 'uuid', 'text'],
  'billing operation resolution is an atomic database command'
);
select ok(
  not has_function_privilege(
    'authenticated',
    'public.resolve_billing_sync_operation(uuid,uuid,text,text,text,uuid,text)',
    'execute'
  ),
  'authenticated browsers cannot resolve billing operations'
);
select ok(
  has_function_privilege(
    'service_role',
    'public.resolve_billing_sync_operation(uuid,uuid,text,text,text,uuid,text)',
    'execute'
  ),
  'the API service can resolve billing operations'
);

insert into auth.users (id)
values
  ('97000000-0000-0000-0000-000000000001'),
  ('97000000-0000-0000-0000-000000000002');

insert into public.billing_sync_operations (
  id,
  user_id,
  operation_type
)
values
  (
    '97000000-0000-0000-0000-000000000011',
    '97000000-0000-0000-0000-000000000001',
    'checkout'
  ),
  (
    '97000000-0000-0000-0000-000000000012',
    '97000000-0000-0000-0000-000000000001',
    'checkout'
  );

select is(
  public.resolve_billing_sync_operation(
    '97000000-0000-0000-0000-000000000011',
    '97000000-0000-0000-0000-000000000002',
    'checkout', 'succeeded', null, null, 'ord_correct'
  ),
  'correlation_mismatch',
  'the wrong owner cannot resolve an operation'
);
select is(
  public.resolve_billing_sync_operation(
    '97000000-0000-0000-0000-000000000011',
    '97000000-0000-0000-0000-000000000001',
    'refund', 'succeeded', null, null, 'ord_correct'
  ),
  'correlation_mismatch',
  'the wrong operation type cannot resolve an operation'
);
select is(
  public.resolve_billing_sync_operation(
    '97000000-0000-0000-0000-000000000011',
    '97000000-0000-0000-0000-000000000001',
    'checkout', 'succeeded', null,
    '97000000-0000-0000-0000-000000000099',
    'ord_correct'
  ),
  'correlation_mismatch',
  'the wrong plan cannot resolve an operation'
);
select is(
  public.resolve_billing_sync_operation(
    '97000000-0000-0000-0000-000000000011',
    '97000000-0000-0000-0000-000000000001',
    'checkout', 'succeeded', null, null, 'ord_correct'
  ),
  'resolved',
  'matching correlation resolves the pending operation'
);
select is(
  (
    select status || ':' || polar_order_id
    from public.billing_sync_operations
    where id = '97000000-0000-0000-0000-000000000011'
  ),
  'succeeded:ord_correct',
  'resolution persists the terminal status and provider order'
);
select is(
  public.resolve_billing_sync_operation(
    '97000000-0000-0000-0000-000000000011',
    '97000000-0000-0000-0000-000000000001',
    'checkout', 'succeeded', null, null, 'ord_correct'
  ),
  'already_resolved',
  'duplicate webhook resolution is idempotent'
);
select is(
  public.resolve_billing_sync_operation(
    '97000000-0000-0000-0000-000000000011',
    '97000000-0000-0000-0000-000000000001',
    'checkout', 'failed', 'late_failure', null, 'ord_correct'
  ),
  'terminal_mismatch',
  'a conflicting terminal result cannot overwrite success'
);
select is(
  (
    select status
    from public.billing_sync_operations
    where id = '97000000-0000-0000-0000-000000000012'
  ),
  'pending',
  'a nearby operation remains untouched'
);

select * from finish();

rollback;
