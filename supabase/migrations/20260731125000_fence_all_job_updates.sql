-- Keep every worker-owned job mutation behind a live database-time lease check.
-- The JSON payload is intentionally restricted to the fields the worker owns.

create or replace function public.update_job_with_valid_lease(
  p_job_id uuid,
  p_lease_token uuid,
  p_payload jsonb
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog, public
as $$
declare
  updated_count integer;
begin
  if p_job_id is null
     or p_lease_token is null
     or p_payload is null
     or pg_catalog.jsonb_typeof(p_payload) <> 'object'
     or p_payload = '{}'::jsonb then
    raise exception 'invalid leased job update' using errcode = '22023';
  end if;

  if exists (
    select 1
    from pg_catalog.jsonb_object_keys(p_payload) as requested(key)
    where requested.key not in (
      'status', 'stage', 'progress', 'status_message', 'summary_id',
      'error_code', 'error_message', 'last_error_at', 'run_after',
      'claimed_at', 'heartbeat_at', 'lease_token', 'lease_expires_at'
    )
  ) then
    raise exception 'leased job update contains an unsupported field' using errcode = '22023';
  end if;

  if p_payload ? 'status'
     and p_payload->>'status' not in ('queued', 'failed') then
    raise exception 'invalid leased job status transition' using errcode = '22023';
  end if;
  if p_payload ? 'progress'
     and (p_payload->>'progress')::integer not between 0 and 100 then
    raise exception 'invalid leased job progress' using errcode = '22023';
  end if;
  if (p_payload ? 'claimed_at' and p_payload->'claimed_at' <> 'null'::jsonb)
     or (p_payload ? 'heartbeat_at' and p_payload->'heartbeat_at' <> 'null'::jsonb)
     or (p_payload ? 'lease_token' and p_payload->'lease_token' <> 'null'::jsonb)
     or (p_payload ? 'lease_expires_at' and p_payload->'lease_expires_at' <> 'null'::jsonb) then
    raise exception 'lease fields may only be cleared' using errcode = '22023';
  end if;

  update public.jobs
  set status = case when p_payload ? 'status' then p_payload->>'status' else status end,
      stage = case when p_payload ? 'stage' then p_payload->>'stage' else stage end,
      progress = case when p_payload ? 'progress' then (p_payload->>'progress')::integer else progress end,
      status_message = case when p_payload ? 'status_message' then p_payload->>'status_message' else status_message end,
      summary_id = case when p_payload ? 'summary_id' then (p_payload->>'summary_id')::uuid else summary_id end,
      error_code = case when p_payload ? 'error_code' then p_payload->>'error_code' else error_code end,
      error_message = case when p_payload ? 'error_message' then p_payload->>'error_message' else error_message end,
      last_error_at = case
        when p_payload ? 'last_error_at' then (p_payload->>'last_error_at')::timestamptz
        else last_error_at
      end,
      run_after = case
        when p_payload ? 'run_after' and p_payload->'run_after' = 'null'::jsonb then null
        when p_payload ? 'run_after' then (p_payload->>'run_after')::timestamptz
        else run_after
      end,
      claimed_at = case when p_payload ? 'claimed_at' then null else claimed_at end,
      heartbeat_at = case when p_payload ? 'heartbeat_at' then null else heartbeat_at end,
      lease_token = case when p_payload ? 'lease_token' then null else lease_token end,
      lease_expires_at = case when p_payload ? 'lease_expires_at' then null else lease_expires_at end,
      updated_at = pg_catalog.now()
  where id = p_job_id
    and status = 'running'
    and lease_token = p_lease_token
    and lease_expires_at > pg_catalog.now();

  get diagnostics updated_count = row_count;
  return updated_count = 1;
end;
$$;

revoke all on function public.update_job_with_valid_lease(uuid, uuid, jsonb)
  from public, anon, authenticated;
grant execute on function public.update_job_with_valid_lease(uuid, uuid, jsonb)
  to service_role;
