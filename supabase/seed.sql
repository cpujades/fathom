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

-- Example "user id" for local-only seed data (not tied to auth.users)
-- Note: for real requests, `user_id` must match `auth.uid()` (via RLS).
select '00000000-0000-0000-0000-000000000001'::uuid as example_user_id;

-- Example summary referencing the transcript
insert into public.summaries (id, user_id, transcript_id, prompt_key, summary_model, summary_markdown, pdf_object_key)
select
  gen_random_uuid(),
  '00000000-0000-0000-0000-000000000001'::uuid,
  t.id,
  'default',
  'x-ai/grok-4.1-fast',
  '# Example summary

This is a seeded summary.',
  null
from public.transcripts t
where t.url_hash = 'example_url_hash';

-- Example job referencing the summary
insert into public.jobs (user_id, status, url, summary_id)
select
  '00000000-0000-0000-0000-000000000001'::uuid,
  'succeeded',
  'https://example.com/video',
  s.id
from public.summaries s
join public.transcripts t on t.id = s.transcript_id
where t.url_hash = 'example_url_hash'
  and s.prompt_key = 'default'
  and s.summary_model = 'x-ai/grok-4.1-fast';
