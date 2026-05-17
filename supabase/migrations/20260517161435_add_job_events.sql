-- Persist sparse job milestones for local/admin debugging.
-- This is intentionally not a user-facing event stream; it helps operators
-- answer "what happened to this briefing session?" after the fact.

create table if not exists public.job_events (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references public.jobs (id) on delete cascade,
  event_type text not null,
  stage text,
  message text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists job_events_job_id_created_at_idx
  on public.job_events (job_id, created_at asc);

alter table public.job_events enable row level security;
