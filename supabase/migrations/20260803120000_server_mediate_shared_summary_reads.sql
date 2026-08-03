-- Keep transcripts and summaries globally reusable without exposing their
-- internal cache rows to authenticated browser clients.
--
-- A user's own settled job remains the authorization proof. FastAPI checks that
-- job with the user's token, then reads the shared summary with the server-only
-- service role and returns the narrow public response model.

revoke select on table public.summaries from authenticated;

drop policy if exists "summaries_select_via_settled_jobs"
  on public.summaries;

comment on table public.summaries is
  'Server-only global summary cache. User access is authorized through tenant-owned jobs and projected by FastAPI.';
