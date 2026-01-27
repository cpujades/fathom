-- Allow reading summaries only when the user owns a job that points to them.
-- This enables secure global caching while preventing UUID guessing.

drop policy if exists "summaries_select_own" on public.summaries;
drop policy if exists "summaries_select_via_jobs" on public.summaries;

create policy "summaries_select_via_jobs"
on public.summaries
for select
to authenticated
using (
  exists (
    select 1
    from public.jobs
    where jobs.summary_id = summaries.id
      and jobs.user_id = (select auth.uid())
  )
);

-- Defensive indexes for the policy predicate.
create index if not exists jobs_user_id_idx on public.jobs (user_id);
create index if not exists jobs_summary_id_idx on public.jobs (summary_id);
