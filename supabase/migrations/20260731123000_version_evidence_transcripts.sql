-- Preserve timestamped transcript caches under the evidence-required contract.
-- Legacy rows without segments remain on the old key and are never reused.

update public.transcripts as transcript
set provider_model = 'groq:whisper-large-v3-turbo:segments-v1'
where transcript.provider_model = 'groq:whisper-large-v3-turbo'
  and exists (
    select 1
    from public.transcript_segments as segment
    where segment.transcript_id = transcript.id
  )
  and not exists (
    select 1
    from public.transcripts as current_contract
    where current_contract.url_hash = transcript.url_hash
      and current_contract.provider_model = 'groq:whisper-large-v3-turbo:segments-v1'
  );
