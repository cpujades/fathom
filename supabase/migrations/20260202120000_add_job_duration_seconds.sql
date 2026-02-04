-- Store media duration for usage enforcement.

alter table public.jobs
  add column if not exists duration_seconds integer;

create index if not exists jobs_duration_seconds_idx
  on public.jobs (duration_seconds);
