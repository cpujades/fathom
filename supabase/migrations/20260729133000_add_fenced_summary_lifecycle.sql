-- Give summaries an explicit, fenced generation lifecycle.
--
-- Ownership rule: a pending summary has a live producer only while its
-- generation_job_id points to a running job whose current lease_token equals
-- generation_token and whose lease has not expired. Failed summaries and
-- pending summaries without that live owner may be atomically taken over.
--
-- Legacy rule: a non-empty row becomes ready only when a succeeded or archived
-- job proves completion. Empty rows and interrupted/orphaned non-empty drafts
-- become failed and are never eligible for cache reuse.

alter table public.summaries
  add column if not exists status text,
  add column if not exists status_updated_at timestamptz,
  add column if not exists ready_at timestamptz,
  add column if not exists failed_at timestamptz,
  add column if not exists generation_job_id uuid,
  add column if not exists generation_token uuid;

update public.summaries as summary
set status = case
      when pg_catalog.btrim(summary.summary_markdown) <> ''
        and exists (
          select 1
          from public.jobs
          where jobs.summary_id = summary.id
            and jobs.status in ('succeeded', 'deleted')
        )
      then 'ready'
      else 'failed'
    end,
    status_updated_at = created_at,
    ready_at = case
      when pg_catalog.btrim(summary.summary_markdown) <> ''
        and exists (
          select 1
          from public.jobs
          where jobs.summary_id = summary.id
            and jobs.status in ('succeeded', 'deleted')
        )
      then created_at
      else null
    end,
    failed_at = case
      when pg_catalog.btrim(summary.summary_markdown) <> ''
        and exists (
          select 1
          from public.jobs
          where jobs.summary_id = summary.id
            and jobs.status in ('succeeded', 'deleted')
        )
      then null
      else created_at
    end,
    generation_job_id = null,
    generation_token = null
where status is null;

alter table public.summaries
  alter column status set not null,
  alter column status_updated_at set not null;

alter table public.summaries
  drop constraint if exists summaries_status_check,
  drop constraint if exists summaries_lifecycle_check;

alter table public.summaries
  add constraint summaries_status_check
    check (status in ('pending', 'ready', 'failed')),
  add constraint summaries_lifecycle_check
    check (
      (
        status = 'pending'
        and ready_at is null
        and failed_at is null
        and generation_job_id is not null
        and generation_token is not null
      )
      or (
        status = 'ready'
        and ready_at is not null
        and failed_at is null
        and generation_token is null
        and pg_catalog.btrim(summary_markdown) <> ''
      )
      or (
        status = 'failed'
        and ready_at is null
        and failed_at is not null
        and generation_token is null
      )
    );

create index if not exists summaries_status_idx
  on public.summaries (status);

comment on column public.summaries.status is
  'pending while one live job owns generation; ready is cacheable; failed is never cacheable';
comment on column public.summaries.generation_job_id is
  'job that most recently owned this summary generation';
comment on column public.summaries.generation_token is
  'must match the live owning job lease token for producer mutations';

create or replace function public.prepare_summary(
  p_summary_id uuid,
  p_user_id uuid,
  p_job_id uuid,
  p_generation_token uuid,
  p_transcript_id uuid,
  p_prompt_key text,
  p_summary_model text
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  summary_row public.summaries;
begin
  if p_summary_id is null
    or p_user_id is null
    or p_job_id is null
    or p_generation_token is null
    or p_transcript_id is null
  then
    raise exception 'summary, user, job, generation token, and transcript ids are required'
      using errcode = '22023';
  end if;
  if p_prompt_key is null or pg_catalog.btrim(p_prompt_key) = '' then
    raise exception 'prompt key is required' using errcode = '22023';
  end if;
  if p_summary_model is null or pg_catalog.btrim(p_summary_model) = '' then
    raise exception 'summary model is required' using errcode = '22023';
  end if;
  perform pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended(
      p_transcript_id::text || ':' || p_prompt_key || ':' || p_summary_model,
      0
    )
  );

  -- Recheck ownership after waiting for the summary-key lock. A producer whose
  -- lease expired while blocked must not create or take over summary work.
  if not exists (
    select 1
    from public.jobs
    where id = p_job_id
      and user_id = p_user_id
      and status = 'running'
      and lease_token = p_generation_token
      and lease_expires_at > pg_catalog.now()
  ) then
    raise exception 'summary producer must hold the current live job lease'
      using errcode = '55000';
  end if;

  select *
  into summary_row
  from public.summaries
  where transcript_id = p_transcript_id
    and prompt_key = p_prompt_key
    and summary_model = p_summary_model
  limit 1
  for update;

  if not found then
    insert into public.summaries (
      id,
      user_id,
      transcript_id,
      prompt_key,
      summary_model,
      summary_markdown,
      pdf_object_key,
      status,
      status_updated_at,
      ready_at,
      failed_at,
      generation_job_id,
      generation_token
    )
    values (
      p_summary_id,
      p_user_id,
      p_transcript_id,
      p_prompt_key,
      p_summary_model,
      '',
      null,
      'pending',
      pg_catalog.now(),
      null,
      null,
      p_job_id,
      p_generation_token
    )
    returning * into summary_row;

    return pg_catalog.jsonb_build_object(
      'resolution_type', 'created',
      'summary', pg_catalog.to_jsonb(summary_row)
    );
  end if;

  if summary_row.status = 'ready' then
    return pg_catalog.jsonb_build_object(
      'resolution_type', 'ready',
      'summary', pg_catalog.to_jsonb(summary_row)
    );
  end if;

  if summary_row.status = 'pending'
    and exists (
      select 1
      from public.jobs
      where id = summary_row.generation_job_id
        and status = 'running'
        and lease_token = summary_row.generation_token
        and lease_expires_at > pg_catalog.now()
    )
  then
    return pg_catalog.jsonb_build_object(
      'resolution_type', 'in_progress',
      'summary', pg_catalog.to_jsonb(summary_row)
    );
  end if;

  update public.summaries as summary
  set user_id = p_user_id,
      summary_markdown = '',
      pdf_object_key = null,
      status = 'pending',
      status_updated_at = pg_catalog.now(),
      ready_at = null,
      failed_at = null,
      generation_job_id = p_job_id,
      generation_token = p_generation_token
  where id = summary_row.id
  returning * into summary_row;

  return pg_catalog.jsonb_build_object(
    'resolution_type', 'taken_over',
    'summary', pg_catalog.to_jsonb(summary_row)
  );
end;
$$;

create or replace function public.update_summary_draft(
  p_summary_id uuid,
  p_generation_token uuid,
  p_summary_markdown text
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  updated_count integer;
begin
  update public.summaries as summary
  set summary_markdown = p_summary_markdown,
      status_updated_at = pg_catalog.now()
  where id = p_summary_id
    and status = 'pending'
    and generation_token = p_generation_token
    and exists (
      select 1
      from public.jobs
      where jobs.id = summary.generation_job_id
        and jobs.status = 'running'
        and jobs.lease_token = p_generation_token
        and jobs.lease_expires_at > pg_catalog.now()
    );

  get diagnostics updated_count = row_count;
  return updated_count = 1;
end;
$$;

create or replace function public.complete_summary_generation(
  p_summary_id uuid,
  p_generation_token uuid,
  p_summary_markdown text
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  updated_count integer;
begin
  if p_summary_markdown is null or pg_catalog.btrim(p_summary_markdown) = '' then
    raise exception 'ready summary markdown cannot be empty'
      using errcode = '22023';
  end if;

  update public.summaries as summary
  set summary_markdown = p_summary_markdown,
      status = 'ready',
      status_updated_at = pg_catalog.now(),
      ready_at = pg_catalog.now(),
      failed_at = null,
      generation_token = null
  where id = p_summary_id
    and status = 'pending'
    and generation_token = p_generation_token
    and exists (
      select 1
      from public.jobs
      where jobs.id = summary.generation_job_id
        and jobs.status = 'running'
        and jobs.lease_token = p_generation_token
        and jobs.lease_expires_at > pg_catalog.now()
    );

  get diagnostics updated_count = row_count;
  return updated_count = 1;
end;
$$;

create or replace function public.fail_summary_generation(
  p_summary_id uuid,
  p_generation_token uuid
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  updated_count integer;
begin
  update public.summaries as summary
  set status = 'failed',
      status_updated_at = pg_catalog.now(),
      ready_at = null,
      failed_at = pg_catalog.now(),
      generation_token = null
  where id = p_summary_id
    and status = 'pending'
    and generation_token = p_generation_token
    and exists (
      select 1
      from public.jobs
      where jobs.id = summary.generation_job_id
        and jobs.status = 'running'
        and jobs.lease_token = p_generation_token
        and jobs.lease_expires_at > pg_catalog.now()
    );

  get diagnostics updated_count = row_count;
  return updated_count = 1;
end;
$$;

revoke all on function public.prepare_summary(uuid, uuid, uuid, uuid, uuid, text, text)
  from public, anon, authenticated;
revoke all on function public.update_summary_draft(uuid, uuid, text)
  from public, anon, authenticated;
revoke all on function public.complete_summary_generation(uuid, uuid, text)
  from public, anon, authenticated;
revoke all on function public.fail_summary_generation(uuid, uuid)
  from public, anon, authenticated;

grant execute on function public.prepare_summary(uuid, uuid, uuid, uuid, uuid, text, text)
  to service_role;
grant execute on function public.update_summary_draft(uuid, uuid, text)
  to service_role;
grant execute on function public.complete_summary_generation(uuid, uuid, text)
  to service_role;
grant execute on function public.fail_summary_generation(uuid, uuid)
  to service_role;

-- A succeeded/deleted job is reusable only when its summary is explicitly
-- ready. This replaces the Slice 2b command without changing its API.
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
  if p_summary_id is not null
    and not exists (
      select 1
      from public.summaries
      where id = p_summary_id
        and status = 'ready'
        and pg_catalog.btrim(summary_markdown) <> ''
    )
  then
    raise exception 'cached summary must be ready and non-empty'
      using errcode = '22023';
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

  select jobs.*
  into job_row
  from public.jobs as jobs
  join public.summaries as summaries
    on summaries.id = jobs.summary_id
  where jobs.user_id = p_user_id
    and jobs.source_key = p_source_key
    and jobs.status in ('succeeded', 'deleted')
    and summaries.status = 'ready'
    and pg_catalog.btrim(summaries.summary_markdown) <> ''
  order by jobs.created_at desc
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
grant execute on function public.create_or_reuse_job(uuid, text, text, integer, uuid)
  to service_role;

-- Do not expose a legacy empty result as a successful briefing. Archived jobs
-- remain archived, but neither the API nor the server command may reuse them.
update public.jobs as jobs
set status = 'failed',
    stage = 'failed',
    progress = 100,
    status_message = 'Summary failed',
    error_code = 'legacy_empty_summary',
    error_message = 'Legacy summary content was empty.',
    last_error_at = pg_catalog.now()
from public.summaries as summaries
where jobs.summary_id = summaries.id
  and summaries.status = 'failed'
  and jobs.status = 'succeeded';
