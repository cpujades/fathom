-- Initial schema for Fathom.
--
-- Tables:
-- - jobs
-- - transcripts
-- - summaries

create extension if not exists "pgcrypto";

-- Keep this small and local to this migration.
create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = pg_catalog, public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.transcripts (
  id uuid primary key default gen_random_uuid(),
  url_hash text not null,
  video_id text,
  transcript_text text not null,
  provider_model text,
  created_at timestamptz not null default now(),
  ttl_expires_at timestamptz
);

create unique index if not exists transcripts_url_hash_provider_model_key
  on public.transcripts (url_hash, provider_model);

create index if not exists transcripts_video_id_idx
  on public.transcripts (video_id);

create index if not exists transcripts_ttl_expires_at_idx
  on public.transcripts (ttl_expires_at);

create table if not exists public.summaries (
  id uuid primary key default gen_random_uuid(),
  transcript_id uuid not null references public.transcripts (id) on delete cascade,
  prompt_key text not null,
  summary_model text,
  summary_markdown text not null,
  pdf_object_key text,
  created_at timestamptz not null default now(),
  ttl_expires_at timestamptz
);

create unique index if not exists summaries_transcript_id_prompt_key_key
  on public.summaries (transcript_id, prompt_key, summary_model);

create index if not exists summaries_ttl_expires_at_idx
  on public.summaries (ttl_expires_at);

create table if not exists public.jobs (
  id uuid primary key default gen_random_uuid(),
  status text not null default 'queued',
  url text not null,
  summary_id uuid references public.summaries (id) on delete set null,
  error_code text,
  error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint jobs_status_check check (status in ('queued', 'running', 'succeeded', 'failed'))
);

create index if not exists jobs_summary_id_idx
  on public.jobs (summary_id);

create index if not exists jobs_status_created_at_idx
  on public.jobs (status, created_at desc);

drop trigger if exists set_jobs_updated_at on public.jobs;
create trigger set_jobs_updated_at
before update on public.jobs
for each row
execute procedure public.set_updated_at();

-- Security: we enable RLS but do not add policies yet.
-- Reason: without an ownership column (e.g. user_id), any permissive policy would leak data.
-- Service role (server-side) bypasses RLS; clients will be blocked until you add explicit policies.
alter table public.jobs enable row level security;
alter table public.transcripts enable row level security;
alter table public.summaries enable row level security;
