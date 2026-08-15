-- Add the server-mediated foundation for link sharing and curated Explore.
-- Browser roles keep no direct access to publication records or commands.

create table public.briefing_publications (
  id uuid primary key default gen_random_uuid(),
  owner_user_id uuid not null,
  owner_job_id uuid not null references public.jobs (id) on delete cascade,
  summary_id uuid not null references public.summaries (id) on delete cascade,
  source_key text not null,
  public_slug text not null default pg_catalog.replace(gen_random_uuid()::text, '-', ''),
  visibility text not null default 'private',
  topic text,
  listed_at timestamptz,
  moderation_status text not null default 'clear',
  moderated_at timestamptz,
  moderation_reason text,
  published_at timestamptz,
  unpublished_at timestamptz,
  created_at timestamptz not null default pg_catalog.now(),
  updated_at timestamptz not null default pg_catalog.now(),
  constraint briefing_publications_owner_job_key unique (owner_job_id),
  constraint briefing_publications_public_slug_key unique (public_slug),
  constraint briefing_publications_public_slug_check check (
    public_slug ~ '^[0-9a-f]{32}$'
  ),
  constraint briefing_publications_source_key_check check (
    source_key = pg_catalog.btrim(source_key)
    and pg_catalog.char_length(source_key) between 1 and 200
  ),
  constraint briefing_publications_visibility_check check (
    visibility in ('private', 'unlisted', 'listed')
  ),
  constraint briefing_publications_topic_check check (
    topic is null
    or topic in (
      'business',
      'culture',
      'finance',
      'health',
      'life',
      'productivity',
      'psychology',
      'science',
      'self-improvement',
      'society',
      'technology'
    )
  ),
  constraint briefing_publications_listing_state_check check (
    (visibility = 'listed' and topic is not null and listed_at is not null)
    or (visibility in ('private', 'unlisted') and listed_at is null)
  ),
  constraint briefing_publications_moderation_status_check check (
    moderation_status in ('clear', 'blocked')
  ),
  constraint briefing_publications_moderation_state_check check (
    (
      moderation_status = 'clear'
      and moderated_at is null
      and moderation_reason is null
    )
    or (
      moderation_status = 'blocked'
      and visibility = 'private'
      and listed_at is null
      and moderated_at is not null
      and moderation_reason = pg_catalog.btrim(moderation_reason)
      and pg_catalog.char_length(moderation_reason) between 1 and 1000
    )
  ),
  constraint briefing_publications_publication_window_check check (
    (
      visibility = 'private'
      and (
        (published_at is null and unpublished_at is null)
        or (
          published_at is not null
          and unpublished_at is not null
          and unpublished_at >= published_at
        )
      )
    )
    or (
      visibility in ('unlisted', 'listed')
      and published_at is not null
      and unpublished_at is null
    )
  )
);

create index briefing_publications_owner_created_at_idx
  on public.briefing_publications (owner_user_id, created_at desc);

create index briefing_publications_explore_idx
  on public.briefing_publications (topic, listed_at desc)
  where visibility = 'listed' and moderation_status = 'clear';

create unique index briefing_publications_one_listed_source_idx
  on public.briefing_publications (source_key)
  where visibility = 'listed' and moderation_status = 'clear';

create index jobs_user_source_library_idx
  on public.jobs (user_id, source_key, created_at desc)
  where status in ('queued', 'running', 'succeeded', 'deleted');

create trigger set_briefing_publications_updated_at
before update on public.briefing_publications
for each row
execute procedure public.set_updated_at();

create or replace function public.validate_briefing_publication()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog
as $$
declare
  job_owner_id uuid;
  job_status text;
  job_summary_id uuid;
  job_source_key text;
  summary_status text;
  summary_markdown text;
begin
  if tg_op = 'UPDATE' and (
    new.owner_user_id,
    new.owner_job_id,
    new.summary_id,
    new.source_key,
    new.public_slug
  ) is distinct from (
    old.owner_user_id,
    old.owner_job_id,
    old.summary_id,
    old.source_key,
    old.public_slug
  ) then
    raise exception 'publication identity is immutable'
      using errcode = '23514';
  end if;

  select
    jobs.user_id,
    jobs.status,
    jobs.summary_id,
    jobs.source_key,
    summaries.status,
    summaries.summary_markdown
  into
    job_owner_id,
    job_status,
    job_summary_id,
    job_source_key,
    summary_status,
    summary_markdown
  from public.jobs
  join public.summaries on summaries.id = jobs.summary_id
  where jobs.id = new.owner_job_id;

  if not found then
    raise exception 'publication requires a job with a summary'
      using errcode = '23514';
  end if;
  if job_owner_id is distinct from new.owner_user_id then
    raise exception 'publication owner must own the job'
      using errcode = '23514';
  end if;
  if job_summary_id is distinct from new.summary_id then
    raise exception 'publication summary must match the job summary'
      using errcode = '23514';
  end if;
  if tg_op = 'INSERT' then
    new.source_key := job_source_key;
  elsif new.source_key is distinct from job_source_key then
    raise exception 'publication source must match the job'
      using errcode = '23514';
  end if;
  if summary_status <> 'ready' or pg_catalog.btrim(summary_markdown) = '' then
    raise exception 'publication summary must be ready and non-empty'
      using errcode = '23514';
  end if;
  if tg_op = 'INSERT' and job_status <> 'succeeded' then
    raise exception 'new publication requires a completed job'
      using errcode = '23514';
  end if;
  if new.visibility <> 'private' and job_status <> 'succeeded' then
    raise exception 'public publication requires a completed job'
      using errcode = '23514';
  end if;

  return new;
end;
$$;

create trigger validate_briefing_publication
before insert or update on public.briefing_publications
for each row
execute procedure public.validate_briefing_publication();

create or replace function public.unpublish_inactive_job_publication()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog
as $$
begin
  if new.status = 'succeeded' then
    return new;
  end if;

  update public.briefing_publications
  set visibility = 'private',
      listed_at = null,
      unpublished_at = case
        when visibility <> 'private' then pg_catalog.now()
        else unpublished_at
      end
  where owner_job_id = new.id
    and visibility <> 'private';

  return new;
end;
$$;

create trigger unpublish_inactive_job_publication
after update of status on public.jobs
for each row
when (old.status is distinct from new.status)
execute procedure public.unpublish_inactive_job_publication();

create or replace function public.save_briefing_publication(
  p_user_id uuid,
  p_public_slug text
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  publication_row public.briefing_publications;
  owner_job_row public.jobs;
  summary_row public.summaries;
begin
  if p_user_id is null then
    raise exception 'user id is required' using errcode = '22023';
  end if;
  if p_public_slug is null or p_public_slug !~ '^[0-9a-f]{32}$' then
    raise exception 'valid public slug is required' using errcode = '22023';
  end if;

  select *
  into publication_row
  from public.briefing_publications
  where public_slug = p_public_slug
    and visibility in ('unlisted', 'listed')
    and moderation_status = 'clear'
  for share;

  if not found then
    raise exception 'publication not found' using errcode = 'P0002';
  end if;

  select *
  into owner_job_row
  from public.jobs
  where id = publication_row.owner_job_id
    and status = 'succeeded';

  select *
  into summary_row
  from public.summaries
  where id = publication_row.summary_id
    and status = 'ready'
    and pg_catalog.btrim(summary_markdown) <> '';

  if owner_job_row.id is null or summary_row.id is null then
    raise exception 'publication not found' using errcode = 'P0002';
  end if;

  return public.create_or_reuse_job(
    p_user_id,
    owner_job_row.url,
    owner_job_row.source_key,
    owner_job_row.duration_seconds,
    publication_row.summary_id
  );
end;
$$;

alter table public.briefing_publications enable row level security;

revoke all on table public.briefing_publications
from public, anon, authenticated;

grant select, insert, update, delete on table public.briefing_publications
to service_role;

revoke all on function public.validate_briefing_publication()
  from public, anon, authenticated, service_role;
revoke all on function public.unpublish_inactive_job_publication()
  from public, anon, authenticated, service_role;
revoke all on function public.save_briefing_publication(uuid, text)
  from public, anon, authenticated;
grant execute on function public.save_briefing_publication(uuid, text)
  to service_role;

comment on table public.briefing_publications is
  'Server-only public wrapper with immutable identity around one user-owned completed job and its shared ready summary. Listed rows are selected by Talven for Explore.';

comment on function public.save_briefing_publication(uuid, text) is
  'Atomically creates or restores a user library job from a public ready briefing without usage settlement.';
