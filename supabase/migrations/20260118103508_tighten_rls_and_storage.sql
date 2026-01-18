-- Tighten RLS policies and storage access.
--
-- Goals:
-- - Users should NOT be able to update jobs (worker-only).
-- - Summaries remain read-only for users (worker writes with secret key).
-- - Storage access is scoped to user-owned paths (user_id/summary_id.pdf).

-- Jobs: drop user update policy (worker uses secret key).
drop policy if exists "jobs_update_own" on public.jobs;

-- Storage: ensure RLS is enabled and restrict reads to user-owned paths.
-- The storage.objects table is owned by supabase_storage_admin in local dev.
-- Migrations run as supabase_admin, which cannot set that role in local.
-- We only apply these statements when the current role can assume ownership.
do $$
begin
  if pg_has_role(current_user, 'supabase_storage_admin', 'member') then
    execute 'set role supabase_storage_admin';
    execute 'alter table storage.objects enable row level security';
    execute 'drop policy if exists "storage_objects_select_own" on storage.objects';
    execute $policy$
      create policy "storage_objects_select_own"
      on storage.objects
      for select
      to authenticated
      using (
        -- If you change SUPABASE_BUCKET, update this policy too.
        bucket_id = 'fathom'
        and (storage.foldername(name))[1] = (select auth.uid()::text)
      )
    $policy$;
    execute 'reset role';
  else
    raise notice 'Skipping storage.objects policy; supabase_storage_admin not granted to %', current_user;
  end if;
end
$$;
