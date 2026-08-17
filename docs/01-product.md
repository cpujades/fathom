# Product

**Status:** Current behavior.

**Read this to understand:** what Talven does, what a user can rely on, and
what is not part of the product yet.

## Contents

- [Product in one sentence](#product-in-one-sentence)
- [Current product](#current-product)
- [Main user journey](#main-user-journey)
- [Reuse and duplicate submissions](#reuse-and-duplicate-submissions)
- [Failure and recovery contract](#failure-and-recovery-contract)
- [Current limits](#current-limits)
- [Deliberate exclusions](#deliberate-exclusions)

## Product in one sentence

Talven turns a public YouTube video into a private, evidence-backed written
briefing with timestamp links that open the source at the cited moment.

The product is built for people who want the value of long-form content without
watching the complete source every time.

## Current product

| Capability | Current behavior |
| --- | --- |
| Accounts | Password, magic-link, and Google authentication through Supabase |
| Input | Public YouTube URLs; playlists are rejected |
| Briefing | Structured summary with validated transcript evidence and timestamp links |
| Progress | Reconnectable session progress through server-sent events |
| Library | Search, sort, pagination, archive, and restore |
| Export | Read in the app, copy Markdown, download Markdown, and create a private PDF |
| Sharing | Private by default; the owner can publish an Unlisted link or an operator-approved Listed page |
| Explore | Curated Listed briefings with one controlled topic |
| Save | A signed-in visitor can save a public briefing without another provider call or audio-minute charge |
| Billing | Free monthly allowance, paid subscriptions, one-time packs, refunds, and usage history |

Referrals and Ask this episode are not implemented. They remain part of the
current paid-launch scope decision in [Launch plan](./07-launch-plan.md).

## Main user journey

### 1. Discover and authenticate

The public site sends a new visitor to `/signup` and an existing user to
`/signin`. A selected paid plan can survive authentication as a safe internal
destination. Talven rejects arbitrary external redirects.

The API verifies the Supabase bearer token on every private request. The
frontend session alone is never the backend trust boundary.

### 2. Submit a source

The user pastes a YouTube URL in `/app`. Before creating expensive work, the
API:

1. validates and normalizes the URL;
2. rejects playlists and unsupported URL shapes;
3. reads the source duration;
4. rejects unknown, non-positive, or over-two-hour sources; and
5. atomically checks the user's current spendable balance and active work
   before queueing a billable job.

Example: a user with eight minutes remaining may submit a seven-minute source,
but cannot submit a nine-minute source.

Talven allows up to three billable jobs in progress per user. The combined
duration of work that has not settled must fit the current spendable balance.
Joining the same active source does not create another job or consume another
concurrency slot.

### 3. Process the briefing

The visible stages are:

    accepted
      -> resolving source
      -> transcribing
      -> drafting briefing
      -> finalizing
      -> ready

The worker downloads the smallest suitable audio stream, sends temporary audio
to Groq, sends timestamped transcript segments to OpenRouter, validates the
structured result, renders Markdown, and settles usage.

The complete result stays hidden until validation and usage settlement both
succeed.

### 4. Read and reuse

A ready briefing supports:

- timestamp links to the original YouTube moments;
- Copy Markdown;
- Markdown download;
- private PDF generation;
- archive and restore; and
- later access from the user's library.

Archive removes the user's job from the active library. It does not permanently
delete the account, shared transcript, shared briefing, billing evidence, or
provider records.

### 5. Publish and discover

A briefing starts as Private.

| Visibility | Who can discover it |
| --- | --- |
| Private | Only the owner through an authorized job |
| Unlisted | Anyone who has the unguessable public link |
| Listed | Visitors to Explore and anyone with the public link |

Only the owner can publish or unpublish. Only user IDs in
`EXPLORE_OPERATOR_USER_IDS` can move their own publication to Listed.

Unpublish removes the public page. A private library entry that another user
already saved remains available. A moderation or legal takedown may need a
wider removal policy; that policy is a public-launch decision.

Explore contains only ready, clear, Listed publications. It is a curated
catalogue, not a live feed of user activity.

### 6. Save a public briefing

A signed-in visitor can save a Listed or Unlisted briefing:

- no audio is downloaded again;
- no AI provider is called again;
- no audio minutes are charged;
- repeated saves return the existing library entry; and
- each user keeps separate library, archive, and billing state.

An anonymous visitor signs in and returns to the same public briefing before
saving.

### 7. Buy and use time

The billing page shows subscription time, pack time, debt, purchases, refunds,
and immutable per-briefing usage history.

Talven measures usage in source-video seconds. A 30-minute source consumes
1,800 seconds even when processing takes more or less than 30 minutes.

The normal order is:

1. subscription credit;
2. eligible pack credit; and
3. debt only as a finalization safety buffer.

A known source and the user's other unsettled work must fit the positive
balance at admission. The default 600-second debt threshold is a finalization
safety boundary for exceptional credit changes or recovery. It is not
intentionally spendable extra credit.

## Reuse and duplicate submissions

| Situation | Result | Charge |
| --- | --- | --- |
| First matching submission by this user | New user-owned job | Once after successful finalization |
| Same user submits while work is active | Join the existing job | No second charge |
| Same user submits after success | Reuse or restore the ready job | No second charge |
| Another user saves a public briefing | New private library entry from ready work | No audio-minute charge |
| Another user submits a source with compatible ready cached work | New user-owned job from cache | One settlement for that user |

Users never share jobs, account state, library state, or billing records.
Compatible transcripts and summaries may be reused as shared derived work.

Two users who submit the same uncached source at the same time may still cause
duplicate download and transcription calls. The summary producer is fenced so
only one compatible summary becomes authoritative.

## Failure and recovery contract

- A disconnected event stream reconnects and reconciles with an authoritative
  snapshot.
- Transient provider failures use bounded retries. The user keeps the same job.
- A finalization failure leaves the job retryable and hides the briefing until
  settlement succeeds.
- Audio above 100 MB fails without retry or charge and asks the user for a
  shorter source.
- A failed clipboard operation points the user to Markdown download.
- A PDF capacity limit returns a stable retryable error.
- A refund remains pending while Polar confirmation is uncertain. Talven does
  not ask the user to submit it twice.

## Current limits

| Boundary | Current limit |
| --- | --- |
| Source type | Public YouTube video |
| Source duration | Two hours |
| Downloaded audio | 100,000,000 bytes |
| Concurrent billable jobs per user | Three; unsettled durations must fit the current balance |
| Active worker jobs | Configurable; default 10, allowed 1–64 |
| Provider attempts | Up to three per provider operation |
| Event stream | Renewable lease, bounded replay, one-hour connection lifetime |

Longer sources need chunking, per-chunk retry, timestamp offsets, ordered merge,
and evaluation. Raising only the duration number is unsafe.

## Deliberate exclusions

The current product does not provide:

- permanent self-service account erasure;
- running-job cancellation;
- arbitrary audio uploads or podcast RSS input;
- referrals;
- Ask this episode;
- comments, likes, follows, public activity, or direct messages;
- ranking or recommendation algorithms;
- cross-episode research; or
- direct Notion OAuth.

Launch decisions are in [Launch plan](./07-launch-plan.md). Triggers and future
designs are in [Roadmap](./08-roadmap.md).

## Next read

[Architecture](./02-architecture.md)
