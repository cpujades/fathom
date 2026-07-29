-- Restrict job and maintenance commands to trusted server code.
--
-- Authenticated clients retain RLS-scoped reads. All job mutations flow through
-- the API or worker, both of which use the service role after authenticating and
-- authorizing the request.

drop policy if exists "jobs_insert_own" on public.jobs;
drop policy if exists "jobs_update_own" on public.jobs;

revoke insert, update, delete on table public.jobs from anon, authenticated;
grant select on table public.jobs to authenticated;
grant select, insert, update, delete on table public.jobs to service_role;

alter function public.claim_next_job() set search_path = pg_catalog;
alter function public.requeue_stale_jobs(interval) set search_path = pg_catalog;

create or replace function public.prune_usage_ledger(days_to_keep integer default 365)
returns integer
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  deleted_count integer;
begin
  delete from public.usage_ledger
  where created_at < pg_catalog.now() - pg_catalog.make_interval(days => days_to_keep);

  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;

revoke all on function public.claim_next_job() from public, anon, authenticated;
revoke all on function public.requeue_stale_jobs(interval) from public, anon, authenticated;
revoke all on function public.prune_usage_ledger(integer) from public, anon, authenticated;

grant execute on function public.claim_next_job() to service_role;
grant execute on function public.requeue_stale_jobs(interval) to service_role;
grant execute on function public.prune_usage_ledger(integer) to service_role;

-- PostgreSQL grants EXECUTE on new functions to PUBLIC by default. Migrations
-- run under the same schema owner, so make future server commands opt-in.
alter default privileges in schema public
  revoke execute on functions from public;
