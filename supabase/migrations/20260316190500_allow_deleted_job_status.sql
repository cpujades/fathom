-- Allow soft-deleted briefing sessions to be archived in the jobs table.
-- The application already reads and restores jobs with status = 'deleted',
-- but the original constraint still rejected that value.

alter table public.jobs
  drop constraint if exists jobs_status_check;

alter table public.jobs
  add constraint jobs_status_check
  check (status in ('queued', 'running', 'succeeded', 'failed', 'deleted'));
