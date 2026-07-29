-- Make briefing-session creation idempotent per user and normalized source.
--
-- Historical rows are assigned the same source identity used by the
-- application: YouTube video IDs when available, otherwise a SHA-256 hash of
-- the stored canonical URL. The migration intentionally fails if historical
-- active duplicates exist so operators can inspect them instead of silently
-- discarding in-flight work.

alter table public.jobs
  add column if not exists source_key text;

create or replace function public.derive_job_source_key(p_url text)
returns text
language sql
immutable
strict
set search_path = pg_catalog
as $$
  select case
    when p_url ~* '^https?://(www\.|m\.|music\.)?youtube\.com/watch/?\?'
      and pg_catalog.substring(p_url, '(?i)[?&]v=([^&#]+)') is not null
      then 'youtube:' || pg_catalog.substring(p_url, '(?i)[?&]v=([^&#]+)')
    when pg_catalog.substring(
      p_url,
      '(?i)^https?://(?:www\.|m\.|music\.)?youtube\.com/(?:shorts|embed|live)/([^/?#]+)'
    ) is not null
      then 'youtube:' || pg_catalog.substring(
        p_url,
        '(?i)^https?://(?:www\.|m\.|music\.)?youtube\.com/(?:shorts|embed|live)/([^/?#]+)'
      )
    when pg_catalog.substring(
      p_url,
      '(?i)^https?://youtu\.be/([^/?#]+)'
    ) is not null
      then 'youtube:' || pg_catalog.substring(
        p_url,
        '(?i)^https?://youtu\.be/([^/?#]+)'
      )
    else 'url:' || pg_catalog.encode(extensions.digest(p_url, 'sha256'), 'hex')
  end
$$;

update public.jobs
set source_key = public.derive_job_source_key(url)
where source_key is null;

alter table public.jobs
  alter column source_key set not null;

alter table public.jobs
  drop constraint if exists jobs_source_key_check;

alter table public.jobs
  add constraint jobs_source_key_check
  check (
    source_key = pg_catalog.btrim(source_key)
    and pg_catalog.char_length(source_key) between 1 and 200
  );

do $$
begin
  if exists (
    select 1
    from public.jobs
    where status in ('queued', 'running')
    group by user_id, source_key
    having pg_catalog.count(*) > 1
  ) then
    raise exception 'Cannot enforce active job uniqueness: duplicate active user/source rows exist.'
      using errcode = '23505';
  end if;
end;
$$;

create unique index if not exists jobs_one_active_source_per_user_idx
  on public.jobs (user_id, source_key)
  where status in ('queued', 'running');

create or replace function public.create_or_reuse_job(
  p_user_id uuid,
  p_url text,
  p_source_key text,
  p_duration_seconds integer default null,
  p_summary_id uuid default null
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  job_row public.jobs;
begin
  if p_user_id is null then
    raise exception 'user id is required' using errcode = '22023';
  end if;
  if p_url is null or pg_catalog.btrim(p_url) = '' then
    raise exception 'url is required' using errcode = '22023';
  end if;
  if p_source_key is null
    or p_source_key <> pg_catalog.btrim(p_source_key)
    or pg_catalog.char_length(p_source_key) not between 1 and 200
  then
    raise exception 'source key must contain 1 to 200 non-padded characters'
      using errcode = '22023';
  end if;
  if p_source_key <> public.derive_job_source_key(p_url) then
    raise exception 'source key does not match the canonical url'
      using errcode = '22023';
  end if;
  if p_duration_seconds is not null and p_duration_seconds < 0 then
    raise exception 'duration seconds cannot be negative' using errcode = '22023';
  end if;

  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(p_user_id::text || ':' || p_source_key, 0)
  );

  select *
  into job_row
  from public.jobs
  where user_id = p_user_id
    and source_key = p_source_key
    and status in ('queued', 'running')
  order by created_at desc
  limit 1;

  if found then
    return pg_catalog.jsonb_build_object(
      'resolution_type', 'joined_existing',
      'job', pg_catalog.to_jsonb(job_row)
    );
  end if;

  select *
  into job_row
  from public.jobs
  where user_id = p_user_id
    and source_key = p_source_key
    and status in ('succeeded', 'deleted')
    and summary_id is not null
  order by created_at desc
  limit 1;

  if found then
    if job_row.status = 'deleted' then
      update public.jobs
      set status = 'succeeded',
          stage = 'completed',
          progress = 100,
          status_message = 'Using an existing briefing',
          error_code = null,
          error_message = null
      where id = job_row.id
      returning * into job_row;
    end if;

    return pg_catalog.jsonb_build_object(
      'resolution_type', 'reused_ready',
      'job', pg_catalog.to_jsonb(job_row)
    );
  end if;

  insert into public.jobs (
    user_id,
    status,
    url,
    source_key,
    duration_seconds,
    summary_id,
    stage,
    progress,
    status_message
  )
  values (
    p_user_id,
    case when p_summary_id is null then 'queued' else 'succeeded' end,
    p_url,
    p_source_key,
    p_duration_seconds,
    p_summary_id,
    case when p_summary_id is null then 'queued' else 'cached' end,
    case when p_summary_id is null then 5 else 100 end,
    case
      when p_summary_id is null then 'Queued — waiting for a worker'
      else 'Using an existing briefing'
    end
  )
  returning * into job_row;

  return pg_catalog.jsonb_build_object(
    'resolution_type', 'new',
    'job', pg_catalog.to_jsonb(job_row)
  );
end;
$$;

revoke all on function public.create_or_reuse_job(uuid, text, text, integer, uuid)
  from public, anon, authenticated;
revoke all on function public.derive_job_source_key(text)
  from public, anon, authenticated;
grant execute on function public.create_or_reuse_job(uuid, text, text, integer, uuid)
  to service_role;
grant execute on function public.derive_job_source_key(text)
  to service_role;
