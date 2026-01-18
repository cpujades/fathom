-- Tighten RLS policies and storage access.
--
-- Goals:
-- - Users should NOT be able to update jobs (worker-only).
-- - Summaries remain read-only for users (worker writes with secret key).
-- - Storage access is scoped to user-owned paths (user_id/summary_id.pdf).

-- Jobs: drop user update policy (worker uses secret key).
drop policy if exists "jobs_update_own" on public.jobs;

-- Storage: ensure RLS is enabled and restrict reads to user-owned paths.
alter table storage.objects enable row level security;

drop policy if exists "storage_objects_select_own" on storage.objects;
create policy "storage_objects_select_own"
on storage.objects
for select
to authenticated
using (
  -- If you change SUPABASE_BUCKET, update this policy too.
  bucket_id = 'fathom'
  and (storage.foldername(name))[1] = (select auth.uid()::text)
);
