-- Polar Billing V2
-- Consolidated migration for local-truth credit accounting with Polar as commerce provider.

-- ---------------------------------------------------------------------------
-- plans: Stripe -> Polar mapping + pricing metadata
-- ---------------------------------------------------------------------------
alter table public.plans
  add column if not exists polar_product_id text,
  add column if not exists plan_code text,
  add column if not exists currency text,
  add column if not exists amount_cents integer,
  add column if not exists billing_interval text,
  add column if not exists version integer;

update public.plans
set plan_code = lower(regexp_replace(name, '[^a-z0-9]+', '_', 'g'))
where plan_code is null;

update public.plans
set currency = 'usd'
where currency is null;

update public.plans
set amount_cents = 0
where amount_cents is null;

update public.plans
set version = 1
where version is null;

update public.plans
set billing_interval = case when plan_type = 'subscription' then 'month' else null end
where billing_interval is null;

alter table public.plans
  alter column plan_code set not null,
  alter column currency set not null,
  alter column amount_cents set not null,
  alter column version set not null;

alter table public.plans
  drop column if exists stripe_price_id;

alter table public.plans
  drop constraint if exists plans_amount_cents_check;
alter table public.plans
  add constraint plans_amount_cents_check check (amount_cents >= 0);

alter table public.plans
  drop constraint if exists plans_billing_interval_check;
alter table public.plans
  add constraint plans_billing_interval_check check (
    (plan_type = 'subscription' and billing_interval = 'month')
    or (plan_type = 'pack' and billing_interval is null)
  );

create unique index if not exists plans_polar_product_id_key
  on public.plans (polar_product_id)
  where polar_product_id is not null;

drop index if exists public.plans_plan_code_key;
create unique index if not exists plans_plan_code_version_key
  on public.plans (plan_code, version);

-- ---------------------------------------------------------------------------
-- customer mapping: Stripe -> Polar
-- ---------------------------------------------------------------------------
drop table if exists public.stripe_customers;

create table if not exists public.polar_customers (
  user_id uuid primary key,
  external_customer_id text not null unique,
  polar_customer_id text,
  email text,
  country text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists polar_customers_polar_customer_id_idx
  on public.polar_customers (polar_customer_id)
  where polar_customer_id is not null;

create index if not exists polar_customers_email_idx
  on public.polar_customers (email)
  where email is not null;

-- ---------------------------------------------------------------------------
-- Webhook idempotency/audit
-- ---------------------------------------------------------------------------
create table if not exists public.billing_webhook_events (
  event_id text primary key,
  provider text not null,
  event_type text not null,
  payload jsonb not null,
  status text not null default 'received',
  error text,
  received_at timestamptz not null default now(),
  processed_at timestamptz
);

create index if not exists billing_webhook_events_provider_idx
  on public.billing_webhook_events (provider, received_at desc);

-- ---------------------------------------------------------------------------
-- billing_orders: payment truth only (no credit accounting fields)
-- ---------------------------------------------------------------------------
create table if not exists public.billing_orders (
  id uuid primary key default gen_random_uuid(),
  polar_order_id text not null unique,
  user_id uuid not null,
  plan_id uuid references public.plans (id) on delete set null,
  plan_type text not null,
  polar_product_id text,
  polar_subscription_id text,
  currency text not null,
  paid_amount_cents integer not null,
  refunded_amount_cents integer not null default 0,
  status text not null default 'paid',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint billing_orders_plan_type_check check (plan_type in ('subscription', 'pack')),
  constraint billing_orders_paid_amount_check check (paid_amount_cents >= 0),
  constraint billing_orders_refunded_amount_check check (refunded_amount_cents >= 0),
  constraint billing_orders_status_check check (status in ('paid', 'refund_pending', 'refunded'))
);

-- Legacy compatibility in case this table was partially created in local/dev.
do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'billing_orders'
      and column_name = 'amount_cents'
  ) then
    execute 'alter table public.billing_orders rename column amount_cents to paid_amount_cents';
  end if;

  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'billing_orders'
      and column_name = 'refund_amount_cents'
  ) then
    execute 'alter table public.billing_orders rename column refund_amount_cents to refunded_amount_cents';
  end if;
end $$;

alter table public.billing_orders
  add column if not exists paid_amount_cents integer,
  add column if not exists refunded_amount_cents integer not null default 0;

update public.billing_orders
set paid_amount_cents = 0
where paid_amount_cents is null;

alter table public.billing_orders
  alter column paid_amount_cents set not null;

alter table public.billing_orders
  drop column if exists granted_seconds,
  drop column if exists consumed_seconds,
  drop column if exists revoked_seconds,
  drop column if exists pack_expires_at;

alter table public.billing_orders
  drop constraint if exists billing_orders_amount_cents_check,
  drop constraint if exists billing_orders_refund_amount_check,
  drop constraint if exists billing_orders_paid_amount_check,
  drop constraint if exists billing_orders_refunded_amount_check,
  drop constraint if exists billing_orders_status_check,
  drop constraint if exists billing_orders_consumed_seconds_check,
  drop constraint if exists billing_orders_revoked_seconds_check,
  drop constraint if exists billing_orders_granted_seconds_check,
  drop constraint if exists billing_orders_consumed_revoked_bound_check;

alter table public.billing_orders
  add constraint billing_orders_paid_amount_check check (paid_amount_cents >= 0),
  add constraint billing_orders_refunded_amount_check check (refunded_amount_cents >= 0),
  add constraint billing_orders_status_check check (status in ('paid', 'refund_pending', 'refunded'));

create index if not exists billing_orders_user_id_idx
  on public.billing_orders (user_id, created_at desc);

create index if not exists billing_orders_subscription_idx
  on public.billing_orders (polar_subscription_id)
  where polar_subscription_id is not null;

-- ---------------------------------------------------------------------------
-- credit_lots: authoritative credit accounting
-- ---------------------------------------------------------------------------
create table if not exists public.credit_lots (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  plan_id uuid references public.plans (id) on delete set null,
  lot_type text not null,
  source_key text not null,
  granted_seconds integer not null,
  consumed_seconds integer not null default 0,
  revoked_seconds integer not null default 0,
  pack_expires_at timestamptz,
  status text not null default 'active',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint credit_lots_lot_type_check check (lot_type in ('subscription_cycle', 'pack_order', 'adjustment')),
  constraint credit_lots_status_check check (status in ('active', 'expired', 'revoked')),
  constraint credit_lots_granted_check check (granted_seconds >= 0),
  constraint credit_lots_consumed_check check (consumed_seconds >= 0),
  constraint credit_lots_revoked_check check (revoked_seconds >= 0),
  constraint credit_lots_bound_check check (consumed_seconds + revoked_seconds <= granted_seconds),
  constraint credit_lots_source_key_key unique (lot_type, source_key)
);

create index if not exists credit_lots_user_active_idx
  on public.credit_lots (user_id, lot_type, status, pack_expires_at, created_at);

-- ---------------------------------------------------------------------------
-- entitlements: snapshot/cache model
-- ---------------------------------------------------------------------------
do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'entitlements'
      and column_name = 'monthly_quota_seconds'
  ) then
    execute 'alter table public.entitlements rename column monthly_quota_seconds to subscription_cycle_grant_seconds';
  end if;

  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'entitlements'
      and column_name = 'rollover_seconds'
  ) then
    execute 'alter table public.entitlements rename column rollover_seconds to subscription_rollover_seconds';
  end if;

  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'entitlements'
      and column_name = 'pack_seconds_available'
  ) then
    execute 'alter table public.entitlements rename column pack_seconds_available to pack_available_seconds';
  end if;
end $$;

alter table public.entitlements
  add column if not exists subscription_available_seconds integer not null default 0,
  add column if not exists debt_seconds integer not null default 0,
  add column if not exists is_blocked boolean not null default false,
  add column if not exists last_balance_sync_at timestamptz;

alter table public.entitlements
  drop column if exists auto_refill_enabled,
  drop column if exists auto_refill_plan_id;

alter table public.entitlements
  drop constraint if exists entitlements_quota_check,
  drop constraint if exists entitlements_rollover_check,
  drop constraint if exists entitlements_pack_seconds_check,
  drop constraint if exists entitlements_subscription_cycle_grant_check,
  drop constraint if exists entitlements_subscription_rollover_check,
  drop constraint if exists entitlements_pack_available_check,
  drop constraint if exists entitlements_subscription_available_check,
  drop constraint if exists entitlements_debt_check;

alter table public.entitlements
  add constraint entitlements_subscription_cycle_grant_check
    check (subscription_cycle_grant_seconds is null or subscription_cycle_grant_seconds >= 0),
  add constraint entitlements_subscription_rollover_check
    check (subscription_rollover_seconds is null or subscription_rollover_seconds >= 0),
  add constraint entitlements_pack_available_check
    check (pack_available_seconds is null or pack_available_seconds >= 0),
  add constraint entitlements_subscription_available_check
    check (subscription_available_seconds >= 0),
  add constraint entitlements_debt_check
    check (debt_seconds >= 0);

-- ---------------------------------------------------------------------------
-- usage_ledger: audit-only retention helper
-- ---------------------------------------------------------------------------
create index if not exists usage_ledger_created_at_idx on public.usage_ledger (created_at desc);

create or replace function public.prune_usage_ledger(days_to_keep integer default 365)
returns integer
language plpgsql
security definer
as $$
declare
  deleted_count integer;
begin
  delete from public.usage_ledger
  where created_at < now() - make_interval(days => days_to_keep);

  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;

-- ---------------------------------------------------------------------------
-- updated_at triggers
-- ---------------------------------------------------------------------------
drop trigger if exists set_polar_customers_updated_at on public.polar_customers;
create trigger set_polar_customers_updated_at
before update on public.polar_customers
for each row
execute procedure public.set_updated_at();

drop trigger if exists set_billing_orders_updated_at on public.billing_orders;
create trigger set_billing_orders_updated_at
before update on public.billing_orders
for each row
execute procedure public.set_updated_at();

drop trigger if exists set_credit_lots_updated_at on public.credit_lots;
create trigger set_credit_lots_updated_at
before update on public.credit_lots
for each row
execute procedure public.set_updated_at();

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
alter table public.polar_customers enable row level security;
alter table public.billing_webhook_events enable row level security;
alter table public.billing_orders enable row level security;
alter table public.credit_lots enable row level security;

drop policy if exists "polar_customers_select_own" on public.polar_customers;
create policy "polar_customers_select_own"
on public.polar_customers
for select
to authenticated
using (user_id = auth.uid());

drop policy if exists "billing_orders_select_own" on public.billing_orders;
create policy "billing_orders_select_own"
on public.billing_orders
for select
to authenticated
using (user_id = auth.uid());

drop policy if exists "credit_lots_select_own" on public.credit_lots;
create policy "credit_lots_select_own"
on public.credit_lots
for select
to authenticated
using (user_id = auth.uid());
