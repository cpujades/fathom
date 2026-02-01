-- Billing tables: plans, entitlements, usage ledger, stripe customer mapping.

create table if not exists public.plans (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  plan_type text not null,
  stripe_price_id text unique,
  quota_seconds integer,
  rollover_cap_seconds integer,
  pack_expiry_days integer,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  constraint plans_plan_type_check check (plan_type in ('subscription', 'pack')),
  constraint plans_quota_seconds_check check (quota_seconds is null or quota_seconds >= 0),
  constraint plans_rollover_cap_seconds_check check (rollover_cap_seconds is null or rollover_cap_seconds >= 0),
  constraint plans_pack_expiry_days_check check (pack_expiry_days is null or pack_expiry_days >= 0)
);

create index if not exists plans_plan_type_idx on public.plans (plan_type);

create table if not exists public.entitlements (
  user_id uuid primary key,
  subscription_plan_id uuid references public.plans (id) on delete set null,
  subscription_status text,
  period_start timestamptz,
  period_end timestamptz,
  monthly_quota_seconds integer,
  rollover_seconds integer,
  pack_seconds_available integer,
  pack_expires_at timestamptz,
  auto_refill_enabled boolean not null default false,
  auto_refill_plan_id uuid references public.plans (id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint entitlements_quota_check check (monthly_quota_seconds is null or monthly_quota_seconds >= 0),
  constraint entitlements_rollover_check check (rollover_seconds is null or rollover_seconds >= 0),
  constraint entitlements_pack_seconds_check check (pack_seconds_available is null or pack_seconds_available >= 0)
);

drop trigger if exists set_entitlements_updated_at on public.entitlements;
create trigger set_entitlements_updated_at
before update on public.entitlements
for each row
execute procedure public.set_updated_at();

create table if not exists public.usage_ledger (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null,
  job_id uuid references public.jobs (id) on delete set null,
  seconds_used integer not null,
  source text not null,
  created_at timestamptz not null default now(),
  constraint usage_ledger_seconds_check check (seconds_used >= 0),
  constraint usage_ledger_source_check check (source in ('subscription', 'pack'))
);

create index if not exists usage_ledger_user_id_idx on public.usage_ledger (user_id);
create index if not exists usage_ledger_job_id_idx on public.usage_ledger (job_id);

create table if not exists public.stripe_customers (
  user_id uuid primary key,
  stripe_customer_id text not null unique,
  created_at timestamptz not null default now()
);

-- RLS policies
alter table public.plans enable row level security;
alter table public.entitlements enable row level security;
alter table public.usage_ledger enable row level security;
alter table public.stripe_customers enable row level security;

drop policy if exists "plans_select_all" on public.plans;
create policy "plans_select_all"
on public.plans
for select
to authenticated
using (true);

drop policy if exists "entitlements_select_own" on public.entitlements;
create policy "entitlements_select_own"
on public.entitlements
for select
to authenticated
using (user_id = auth.uid());

drop policy if exists "usage_ledger_select_own" on public.usage_ledger;
create policy "usage_ledger_select_own"
on public.usage_ledger
for select
to authenticated
using (user_id = auth.uid());
