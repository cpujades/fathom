-- Correlate one browser checkout or refund request with the webhook-backed
-- billing change that completes it. Operation identifiers are opaque and
-- always resolved through the authenticated API; clients never read this
-- table directly.

create table if not exists public.billing_sync_operations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  operation_type text not null,
  status text not null default 'pending',
  plan_id uuid references public.plans(id) on delete set null,
  polar_order_id text,
  failure_code text,
  expires_at timestamptz not null default (pg_catalog.now() + interval '24 hours'),
  created_at timestamptz not null default pg_catalog.now(),
  updated_at timestamptz not null default pg_catalog.now(),
  constraint billing_sync_operations_type_check
    check (operation_type in ('checkout', 'refund')),
  constraint billing_sync_operations_status_check
    check (status in ('pending', 'succeeded', 'failed')),
  constraint billing_sync_operations_failure_code_check
    check (failure_code is null or pg_catalog.length(failure_code) between 1 and 64),
  constraint billing_sync_operations_expiry_check
    check (expires_at > created_at)
);

create index if not exists billing_sync_operations_user_id_idx
  on public.billing_sync_operations (user_id, created_at desc);

create index if not exists billing_sync_operations_refund_order_idx
  on public.billing_sync_operations (polar_order_id, created_at desc)
  where operation_type = 'refund';

alter table public.billing_sync_operations enable row level security;

revoke all on table public.billing_sync_operations
  from public, anon, authenticated;
grant select, insert, update, delete on table public.billing_sync_operations
  to service_role;

drop trigger if exists set_billing_sync_operations_updated_at
  on public.billing_sync_operations;
create trigger set_billing_sync_operations_updated_at
before update on public.billing_sync_operations
for each row execute function public.set_updated_at();

-- Resolve one exact browser operation only when all webhook correlation fields
-- agree. The authoritative billing transaction is intentionally separate, so
-- a stale or forged operation id can never redirect another user's browser.
create or replace function public.resolve_billing_sync_operation(
  p_operation_id uuid,
  p_user_id uuid,
  p_operation_type text,
  p_status text,
  p_failure_code text default null,
  p_plan_id uuid default null,
  p_polar_order_id text default null
)
returns text
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  operation public.billing_sync_operations%rowtype;
begin
  if p_operation_type not in ('checkout', 'refund')
     or p_status not in ('succeeded', 'failed') then
    return 'invalid_transition';
  end if;

  select *
  into operation
  from public.billing_sync_operations
  where id = p_operation_id
  for update;

  if not found then
    return 'not_found';
  end if;

  if operation.user_id <> p_user_id
     or operation.operation_type <> p_operation_type
     or (p_plan_id is not null and operation.plan_id is distinct from p_plan_id)
     or (
       p_polar_order_id is not null
       and operation.polar_order_id is not null
       and operation.polar_order_id <> p_polar_order_id
     ) then
    return 'correlation_mismatch';
  end if;

  if operation.status = p_status
     and operation.failure_code is not distinct from p_failure_code then
    return 'already_resolved';
  end if;

  if operation.status <> 'pending' then
    return 'terminal_mismatch';
  end if;

  update public.billing_sync_operations
  set status = p_status,
      failure_code = p_failure_code,
      polar_order_id = coalesce(p_polar_order_id, polar_order_id)
  where id = p_operation_id;

  return 'resolved';
end;
$$;

revoke all on function public.resolve_billing_sync_operation(uuid, uuid, text, text, text, uuid, text)
  from public, anon, authenticated;
grant execute on function public.resolve_billing_sync_operation(uuid, uuid, text, text, text, uuid, text)
  to service_role;
