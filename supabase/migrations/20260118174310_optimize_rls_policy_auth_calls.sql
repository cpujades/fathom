-- Optimize RLS policy performance by caching auth.uid() per statement.
-- This avoids per-row evaluation of auth.uid() in policy predicates.

-- Jobs policies.
drop policy if exists "jobs_select_own" on public.jobs;
create policy "jobs_select_own"
on public.jobs
for select
to authenticated
using (user_id = (select auth.uid()));

drop policy if exists "jobs_insert_own" on public.jobs;
create policy "jobs_insert_own"
on public.jobs
for insert
to authenticated
with check (user_id = (select auth.uid()));

drop policy if exists "jobs_update_own" on public.jobs;
create policy "jobs_update_own"
on public.jobs
for update
to authenticated
using (user_id = (select auth.uid()))
with check (user_id = (select auth.uid()));

-- Summaries policies.
drop policy if exists "summaries_select_own" on public.summaries;
create policy "summaries_select_own"
on public.summaries
for select
to authenticated
using (user_id = (select auth.uid()));
