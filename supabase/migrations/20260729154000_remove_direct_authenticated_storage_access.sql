-- Talven's storage access is server-mediated:
-- - the worker uploads temporary audio and signs it for Groq;
-- - the API uploads PDFs and returns short-lived signed URLs after checking
--   summary ownership through RLS.
-- Browser clients do not need direct storage.objects access.

do $$
begin
  if pg_catalog.pg_has_role(
    current_user,
    'supabase_storage_admin',
    'member'
  ) then
    execute 'set local role supabase_storage_admin';
    execute 'drop policy if exists "storage_objects_select_own" on storage.objects';
    execute 'reset role';
  elsif exists (
    select 1
    from pg_catalog.pg_policies
    where schemaname = 'storage'
      and tablename = 'objects'
      and policyname = 'storage_objects_select_own'
  ) then
    raise exception using
      message = 'Cannot remove obsolete authenticated storage policy',
      hint = 'Run this migration with a role that can assume supabase_storage_admin.';
  end if;
end
$$;
