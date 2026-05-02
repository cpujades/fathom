create table if not exists public.api_rate_limit_buckets (
  subject text not null,
  scope text not null,
  window_start timestamptz not null,
  count integer not null default 0,
  updated_at timestamptz not null default now(),
  primary key (subject, scope, window_start),
  constraint api_rate_limit_buckets_count_nonnegative check (count >= 0)
);

create index if not exists api_rate_limit_buckets_window_start_idx
  on public.api_rate_limit_buckets (window_start);

alter table public.api_rate_limit_buckets enable row level security;
