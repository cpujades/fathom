-- Add user ownership + RLS policies for private access.
--
-- Why:
-- - The API must be private; UUIDs are not access control.
-- - Server-side "secret" keys bypass RLS, so user-facing reads/writes must use a user's JWT.
-- - We keep transcripts as an internal cache; end users should not be able to read them.

-- Ownership columns (no FK to auth.users to keep local seeding/simple backfills).
alter table public.jobs
  add column if not exists user_id uuid;

alter table public.summaries
  add column if not exists user_id uuid;

-- Backfill any existing rows (e.g. local seed) so we can make the columns NOT NULL.
update public.jobs set user_id = gen_random_uuid() where user_id is null;
update public.summaries set user_id = gen_random_uuid() where user_id is null;

alter table public.jobs alter column user_id set not null;
alter table public.summaries alter column user_id set not null;

create index if not exists jobs_user_id_idx on public.jobs (user_id);
create index if not exists summaries_user_id_idx on public.summaries (user_id);

-- RLS: jobs are user-owned.
drop policy if exists "jobs_select_own" on public.jobs;
create policy "jobs_select_own"
on public.jobs
for select
to authenticated
using (user_id = auth.uid());

drop policy if exists "jobs_insert_own" on public.jobs;
create policy "jobs_insert_own"
on public.jobs
for insert
to authenticated
with check (user_id = auth.uid());

drop policy if exists "jobs_update_own" on public.jobs;
create policy "jobs_update_own"
on public.jobs
for update
to authenticated
using (user_id = auth.uid())
with check (user_id = auth.uid());

-- RLS: summaries are user-owned.
drop policy if exists "summaries_select_own" on public.summaries;
create policy "summaries_select_own"
on public.summaries
for select
to authenticated
using (user_id = auth.uid());

-- No policies for transcripts yet (internal cache). Authenticated users should not be able to read them.
