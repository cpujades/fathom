-- Persist provider timestamp evidence as immutable transcript segments.
-- Existing transcript rows remain valid and intentionally receive no synthetic backfill.

create table if not exists public.transcript_segments (
  transcript_id uuid not null
    references public.transcripts (id) on delete cascade,
  segment_index integer not null,
  start_seconds double precision not null,
  end_seconds double precision not null,
  segment_text text not null,
  created_at timestamptz not null default pg_catalog.now(),
  primary key (transcript_id, segment_index),
  constraint transcript_segments_index_non_negative
    check (segment_index >= 0),
  constraint transcript_segments_start_non_negative
    check (start_seconds >= 0),
  constraint transcript_segments_end_not_before_start
    check (end_seconds >= start_seconds),
  constraint transcript_segments_text_non_empty
    check (pg_catalog.btrim(segment_text) <> '')
);

alter table public.transcript_segments enable row level security;

create or replace function public.create_transcript_with_segments(
  p_url_hash text,
  p_video_id text,
  p_transcript_text text,
  p_provider_model text,
  p_segments jsonb,
  p_source_title text,
  p_source_author text,
  p_source_description text,
  p_source_keywords text[],
  p_source_views bigint,
  p_source_likes bigint,
  p_source_length_seconds integer
)
returns jsonb
language plpgsql
security definer
set search_path = pg_catalog
as $$
declare
  transcript_row public.transcripts%rowtype;
  transcript_created boolean := false;
  segment_payload jsonb;
  segment_ordinality bigint;
  parsed_index integer;
  parsed_start double precision;
  parsed_end double precision;
  parsed_text text;
begin
  if p_url_hash is null or pg_catalog.btrim(p_url_hash) = '' then
    raise exception 'url hash is required' using errcode = '22023';
  end if;
  if p_transcript_text is null or pg_catalog.btrim(p_transcript_text) = '' then
    raise exception 'transcript text is required' using errcode = '22023';
  end if;
  if p_provider_model is null or pg_catalog.btrim(p_provider_model) = '' then
    raise exception 'provider model is required' using errcode = '22023';
  end if;
  if p_segments is null or pg_catalog.jsonb_typeof(p_segments) <> 'array' then
    raise exception 'segments must be a JSON array' using errcode = '22023';
  end if;

  insert into public.transcripts (
    url_hash,
    video_id,
    transcript_text,
    provider_model,
    source_title,
    source_author,
    source_description,
    source_keywords,
    source_views,
    source_likes,
    source_length_seconds
  )
  values (
    p_url_hash,
    p_video_id,
    p_transcript_text,
    p_provider_model,
    p_source_title,
    p_source_author,
    p_source_description,
    p_source_keywords,
    p_source_views,
    p_source_likes,
    p_source_length_seconds
  )
  on conflict (url_hash, provider_model) do nothing
  returning * into transcript_row;

  transcript_created := found;

  if not transcript_created then
    select transcripts.*
    into transcript_row
    from public.transcripts as transcripts
    where transcripts.url_hash = p_url_hash
      and transcripts.provider_model = p_provider_model
    limit 1;
  end if;

  if transcript_row.id is null then
    raise exception 'failed to resolve transcript after insert conflict';
  end if;

  if transcript_created then
    for segment_payload, segment_ordinality in
      select segment.value, segment.ordinality
      from pg_catalog.jsonb_array_elements(p_segments)
        with ordinality as segment(value, ordinality)
    loop
      if pg_catalog.jsonb_typeof(segment_payload) <> 'object'
        or pg_catalog.jsonb_typeof(segment_payload -> 'segment_index') <> 'number'
        or pg_catalog.jsonb_typeof(segment_payload -> 'start_seconds') <> 'number'
        or pg_catalog.jsonb_typeof(segment_payload -> 'end_seconds') <> 'number'
        or pg_catalog.jsonb_typeof(segment_payload -> 'text') <> 'string'
      then
        raise exception 'invalid transcript segment payload' using errcode = '22023';
      end if;

      parsed_index := (segment_payload ->> 'segment_index')::integer;
      parsed_start := (segment_payload ->> 'start_seconds')::double precision;
      parsed_end := (segment_payload ->> 'end_seconds')::double precision;
      parsed_text := pg_catalog.btrim(segment_payload ->> 'text');

      if parsed_index <> segment_ordinality - 1
        or parsed_start < 0
        or parsed_end < parsed_start
        or parsed_text = ''
      then
        raise exception 'invalid transcript segment values' using errcode = '22023';
      end if;

      insert into public.transcript_segments (
        transcript_id,
        segment_index,
        start_seconds,
        end_seconds,
        segment_text
      )
      values (
        transcript_row.id,
        parsed_index,
        parsed_start,
        parsed_end,
        parsed_text
      );
    end loop;
  end if;

  return pg_catalog.to_jsonb(transcript_row);
end;
$$;

revoke all on table public.transcript_segments
from public, anon, authenticated, service_role;

grant select on table public.transcript_segments
to service_role;

revoke all on function public.create_transcript_with_segments(
  text, text, text, text, jsonb, text, text, text, text[], bigint, bigint, integer
)
from public, anon, authenticated;

grant execute on function public.create_transcript_with_segments(
  text, text, text, text, jsonb, text, text, text, text[], bigint, bigint, integer
)
to service_role;
