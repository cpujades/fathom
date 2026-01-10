-- Seed data for local development.
--
-- This file is executed on `supabase start` (first run) and every `supabase db reset`.
-- Keep it to data inserts (no schema DDL).

-- Example transcript
insert into public.transcripts (id, url_hash, video_id, transcript_text, provider_model)
values (
  gen_random_uuid(),
  'example_url_hash',
  'example_video_id',
  'Hello world transcript...',
  'deepgram'
);

-- Example summary referencing the transcript
insert into public.summaries (id, transcript_id, prompt_key, summary_model, summary_markdown, pdf_object_key)
select
  gen_random_uuid(),
  t.id,
  'default',
  'openai/gpt-4.1-mini',
  '# Example summary

This is a seeded summary.',
  null
from public.transcripts t
where t.url_hash = 'example_url_hash';

-- Example job referencing the summary
insert into public.jobs (status, url, summary_id)
select
  'succeeded',
  'https://example.com/video',
  s.id
from public.summaries s
join public.transcripts t on t.id = s.transcript_id
where t.url_hash = 'example_url_hash'
  and s.prompt_key = 'default'
  and s.summary_model = 'openai/gpt-4.1-mini';
