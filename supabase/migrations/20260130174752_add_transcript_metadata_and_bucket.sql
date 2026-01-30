-- Add source metadata fields for transcripts (YouTube).

alter table public.transcripts
  add column if not exists source_title text,
  add column if not exists source_author text,
  add column if not exists source_description text,
  add column if not exists source_keywords text[],
  add column if not exists source_views bigint,
  add column if not exists source_likes bigint,
  add column if not exists source_length_seconds integer;


insert into storage.buckets (id, name, public)
values ('fathom_groq', 'fathom_groq', false)
on conflict (id) do nothing;
