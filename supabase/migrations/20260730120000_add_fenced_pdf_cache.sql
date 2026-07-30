-- Version cached PDFs and fence one renderer per ready summary.
--
-- A PDF generation claim is live for five minutes. Another API process may
-- take over only after that claim expires. Completion and failure are fenced
-- by the generation token, so an older renderer cannot publish over a newer
-- claim. Existing unversioned PDFs remain private but are treated as stale.

alter table public.summaries
  add column if not exists pdf_cache_version integer,
  add column if not exists pdf_generation_token uuid,
  add column if not exists pdf_generation_cache_version integer,
  add column if not exists pdf_generation_expires_at timestamptz;

alter table public.summaries
  drop constraint if exists summaries_pdf_cache_check,
  add constraint summaries_pdf_cache_check
    check (
      (
        (
          pdf_generation_token is null
          and pdf_generation_cache_version is null
          and pdf_generation_expires_at is null
        )
        or (
          pdf_generation_token is not null
          and pdf_generation_cache_version is not null
          and pdf_generation_cache_version > 0
          and pdf_generation_expires_at is not null
        )
      )
      and (
        pdf_cache_version is null
        or (
          pdf_cache_version > 0
          and pdf_object_key is not null
          and pg_catalog.btrim(pdf_object_key) <> ''
        )
      )
    );

comment on column public.summaries.pdf_cache_version is
  'renderer security/format version; null means the cached PDF is stale';
comment on column public.summaries.pdf_generation_token is
  'service-only fencing token for one active PDF renderer';
comment on column public.summaries.pdf_generation_cache_version is
  'cache version owned by the active PDF generation token';
comment on column public.summaries.pdf_generation_expires_at is
  'expired PDF claims may be safely taken over by another API process';

create or replace function public.invalidate_summary_pdf_cache()
returns trigger
language plpgsql
set search_path = pg_catalog
as $$
begin
  if new.summary_markdown is distinct from old.summary_markdown then
    new.pdf_object_key = null;
    new.pdf_cache_version = null;
    new.pdf_generation_token = null;
    new.pdf_generation_cache_version = null;
    new.pdf_generation_expires_at = null;
  end if;
  return new;
end;
$$;

drop trigger if exists invalidate_summary_pdf_cache_on_content_change
  on public.summaries;
create trigger invalidate_summary_pdf_cache_on_content_change
before update of summary_markdown on public.summaries
for each row
execute function public.invalidate_summary_pdf_cache();

revoke all on function public.invalidate_summary_pdf_cache()
  from public, anon, authenticated;

create or replace function public.prepare_summary_pdf(
  p_summary_id uuid,
  p_cache_version integer,
  p_generation_token uuid
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  summary_row public.summaries;
begin
  if p_summary_id is null or p_generation_token is null then
    raise exception 'summary id and PDF generation token are required'
      using errcode = '22023';
  end if;
  if p_cache_version is null or p_cache_version <= 0 then
    raise exception 'PDF cache version must be positive'
      using errcode = '22023';
  end if;

  select *
  into summary_row
  from public.summaries
  where id = p_summary_id
  for update;

  if not found then
    raise exception 'summary not found' using errcode = 'P0002';
  end if;
  if summary_row.status <> 'ready'
    or pg_catalog.btrim(summary_row.summary_markdown) = ''
  then
    raise exception 'only a ready non-empty summary can generate a PDF'
      using errcode = '55000';
  end if;

  if summary_row.pdf_cache_version = p_cache_version
    and summary_row.pdf_object_key is not null
    and pg_catalog.btrim(summary_row.pdf_object_key) <> ''
  then
    return pg_catalog.jsonb_build_object(
      'resolution_type', 'ready',
      'pdf_object_key', summary_row.pdf_object_key
    );
  end if;

  if summary_row.pdf_generation_token is not null
    and summary_row.pdf_generation_expires_at > pg_catalog.now()
  then
    return pg_catalog.jsonb_build_object(
      'resolution_type', 'in_progress',
      'pdf_object_key', null
    );
  end if;

  update public.summaries
  set pdf_generation_token = p_generation_token,
      pdf_generation_cache_version = p_cache_version,
      pdf_generation_expires_at = pg_catalog.now() + interval '5 minutes'
  where id = p_summary_id;

  return pg_catalog.jsonb_build_object(
    'resolution_type', 'acquired',
    'pdf_object_key', null
  );
end;
$$;

create or replace function public.complete_summary_pdf(
  p_summary_id uuid,
  p_cache_version integer,
  p_generation_token uuid,
  p_pdf_object_key text
)
returns boolean
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  updated_count integer;
begin
  if p_cache_version is null or p_cache_version <= 0 then
    raise exception 'PDF cache version must be positive'
      using errcode = '22023';
  end if;
  if p_pdf_object_key is null or pg_catalog.btrim(p_pdf_object_key) = '' then
    raise exception 'PDF object key is required'
      using errcode = '22023';
  end if;

  update public.summaries
  set pdf_object_key = p_pdf_object_key,
      pdf_cache_version = p_cache_version,
      pdf_generation_token = null,
      pdf_generation_cache_version = null,
      pdf_generation_expires_at = null
  where id = p_summary_id
    and status = 'ready'
    and pdf_generation_token = p_generation_token
    and pdf_generation_cache_version = p_cache_version;

  get diagnostics updated_count = row_count;
  return updated_count = 1;
end;
$$;

create or replace function public.fail_summary_pdf(
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
  update public.summaries
  set pdf_generation_token = null,
      pdf_generation_cache_version = null,
      pdf_generation_expires_at = null
  where id = p_summary_id
    and pdf_generation_token = p_generation_token;

  get diagnostics updated_count = row_count;
  return updated_count = 1;
end;
$$;

revoke all on function public.prepare_summary_pdf(uuid, integer, uuid)
  from public, anon, authenticated;
revoke all on function public.complete_summary_pdf(uuid, integer, uuid, text)
  from public, anon, authenticated;
revoke all on function public.fail_summary_pdf(uuid, uuid)
  from public, anon, authenticated;

grant execute on function public.prepare_summary_pdf(uuid, integer, uuid)
  to service_role;
grant execute on function public.complete_summary_pdf(uuid, integer, uuid, text)
  to service_role;
grant execute on function public.fail_summary_pdf(uuid, uuid)
  to service_role;
