# Long-audio and transcription decision

Status: keep the current provider and two-hour limit for the first bounded
initial release; validate quality/privacy and design chunking before supporting longer
videos.

Provider limits and prices below were reviewed on July 30, 2026. They are
time-sensitive and must be rechecked before a purchase or migration.

## Current pipeline

1. The API reads YouTube metadata and rejects videos over two hours.
2. The worker uses `pytubefix` to select the smallest audio-only stream.
3. Download progress enforces a 100 MB limit, a deadline, and cancellation.
4. The worker uploads the audio to the private `fathom_groq` bucket.
5. A short-lived signed URL is sent to Groq
   `whisper-large-v3-turbo`.
6. Groq returns normalized full text plus segment timestamps.
7. Talven stores the full transcript and immutable ordered segments.
8. Temporary audio deletion is best effort: transient and rate-limit failures
   receive three bounded attempts, and a final failure is logged without
   throwing away an otherwise successful transcript. Hosted bucket lifecycle
   cleanup should be the second line of defense.

“Best effort” means Talven attempts the action and records failure, but does not
fail the primary user outcome solely because that secondary cleanup failed.

## Why the limit is not just a plan setting

At the current low audio bitrates, some long videos remain below 100 MB and
some do not. Groq's documented direct-file limits also depend on account tier.
A single five-hour request creates poor recovery behavior: if a network or
provider failure occurs near the end, the entire transcription may be paid for
and repeated.

A free-versus-paid duration switch does not solve those reliability and cost
problems. Product-plan limits should be added only after the technical pipeline
can safely process the promised duration.

## Provider comparison

| Option | Published transcription price | Long-input fit | Relevant trade-off |
| --- | ---: | --- | --- |
| Groq Whisper Large V3 Turbo | $0.04/audio hour | 25 MB free tier, 100 MB developer tier | Current fastest/cheapest initial-release fit; segment timestamps; no diarization |
| Groq Whisper Large V3 | $0.111/audio hour | Same upload limits | Groq describes higher accuracy; benchmark before paying more |
| AssemblyAI Universal-2 | $0.15/audio hour | Up to 5 GB / 10 hours | Simplest whole-file long-audio alternative; word timestamps; diarization costs extra |
| ElevenLabs Scribe v2 | $0.22/audio hour | File under 5 GB; internally chunks longer audio | Word timestamps and diarization; ordinary zero-retention availability is less favorable |
| Deepgram Nova-3 | $0.462/audio hour, plus optional diarization | Up to 2 GB with a processing wall limit | Mature speech controls but materially higher base cost here |

Approximate transcription-only cost for a five-hour source at those published
rates: Groq Turbo $0.20, Groq Large V3 $0.56, AssemblyAI $0.75, ElevenLabs
$1.10, and Deepgram $2.31 before diarization. Download, storage, summarization,
retries, taxes, and plan minimums are not included.

No provider is “better” without testing Talven's actual content. Speed claims,
word-error rate, speaker overlap, accents, technical names, privacy controls,
and retry behavior matter more than one headline price.

## Recommendation

For the bounded initial release:

- keep Groq Turbo;
- confirm the paid account's current file limit;
- enable Groq Zero Data Retention where available;
- keep the two-hour product limit;
- measure real duration, file size, accuracy, provider latency, and failure
  rates; and
- do not promise diarization or speaker labels.

For longer sources, build provider-independent chunking before choosing a
300-minute limit:

1. create a durable source-processing manifest;
2. split audio into ordered 15-25 minute chunks with a small overlap;
3. persist chunk hashes, status, retry count, and timestamp offset;
4. cap concurrent chunk calls;
5. retry only failed chunks;
6. deterministically remove overlap and merge ordered segments;
7. preserve absolute YouTube timestamps;
8. make a follower reuse the same completed chunks; and
9. evaluate cost and quality before enabling the feature by plan.

AssemblyAI is the smallest-engineering alternative if the immediate goal is
to send one oversize file, but only after privacy and representative quality
checks. It does not remove the long-term recovery and provider-lock-in reasons
to chunk.

## Validation set

Use 10-20 permitted sources covering 30, 60, and 120 minutes before expanding
duration. Include noisy recordings, multiple accents, technical names,
music/background noise, and overlapping speech. Compare:

- missing or incorrect important facts;
- timestamp alignment;
- important-name accuracy;
- real-time factor and tail latency;
- retry/failure rate;
- bytes and cost per audio hour; and
- retention/deletion behavior.

Costed provider evaluation remains opt-in; it should not run on every pull
request.

## Current source references

- [Groq speech-to-text documentation](https://console.groq.com/docs/speech-to-text)
- [Groq data controls](https://console.groq.com/docs/your-data)
- [AssemblyAI pricing](https://www.assemblyai.com/pricing/)
- [AssemblyAI file limits](https://support.assemblyai.com/articles/9208125065-are-there-any-limits-on-file-size-or-file-duration-for-files-submitted-to-the-api)
- [AssemblyAI retention](https://support.assemblyai.com/articles/2240096256-does-assemblyai-offer-zero-data-retention)
- [ElevenLabs speech-to-text API](https://elevenlabs.io/docs/api-reference/speech-to-text/convert)
- [ElevenLabs zero-retention mode](https://elevenlabs.io/docs/eleven-api/resources/zero-retention-mode)
- [Deepgram pre-recorded audio limits](https://developers.deepgram.com/docs/pre-recorded-audio)
- [Deepgram pricing](https://deepgram.com/pricing)
