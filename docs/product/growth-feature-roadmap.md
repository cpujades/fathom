# Growth and product feature roadmap

**Status:** Proposed; nothing on this page is implemented unless the current
workflow documentation says otherwise
**Last reviewed:** 2026-08-05

This page preserves the smallest useful versions of Talven's sharing, export,
referral, episode-chat, discovery, and follow-up ideas. It is a product
sequence, not authorization to implement every item at once.

The product wedge is an evidence-backed, timestamp-verifiable briefing that a
person can reuse and share. The growth loop should strengthen that artifact
before Talven attempts a forum or broad social network.

## Principles

- Private by default; publishing is explicit and reversible.
- Reuse compatible cached work instead of charging or processing it twice.
- Make source claims visibly different from external verification.
- Use fixed seconds for credits; avoid ambiguous promises such as “one free
  podcast.”
- Add acquisition and retention features in measurable slices.
- Preserve tenant boundaries even when a briefing also has a public view.
- Public derived content still needs reporting and takedown, even without
  comments.

## Sequence

1. Cost telemetry and temporary-audio lifecycle cleanup.
2. Copy/download Markdown improvements for Obsidian, Notion, and other editors.
3. Opt-in unlisted share pages and social cards.
4. Referral attribution and first-purchase promotional credits.
5. Full-context, cited “Ask this episode” MVP.
6. Opt-in Explore/discovery and “save to my library.”
7. Lightweight public identity and follows, only after public inventory exists.
8. Channel follows and a weekly digest.
9. Cross-episode retrieval, research tools, and advanced collaboration.

Direct Notion OAuth is intentionally absent from the near-term sequence.
Copy/paste and Markdown import cover the initial need without token storage,
OAuth, block conversion, retries, and revocation handling.

## Phase 0: owner telemetry and cleanup

This is internal product infrastructure, not visible marketing, but it protects
every later experiment.

### Cost dashboard

Show:

- briefings, users, cold sources, and cache hits by day/month;
- audio hours and bytes by plan and user;
- Groq audio seconds/cost and OpenRouter tokens/cost per briefing;
- provider retries, failures, latency, and p95 completion time;
- temporary audio created/deleted/orphaned bytes;
- PDF count and bytes;
- Supabase/Railway egress estimate;
- allocated database disk, live database bytes, and the largest table/index
  pairs;
- Polar base sales, tax, fees, refunds, payouts, and contribution; and
- referral credits granted, consumed, expired, or revoked.

The dashboard must never log provider secrets, raw transcripts, full billing
payloads, or unnecessary customer PII.

Use Supabase's Usage dashboard/invoice as the authority for billable egress.
Export or reproduce the operational trend in Grafana so Talven can alert and
forecast before the quota is reached. Sentry may complement that view for
exceptions and traces, but it is not the billing or capacity source of truth.

### Audio lifecycle

- Keep immediate deletion with bounded retry.
- Delete any private `groq-audio/*` object older than a conservative safety
  window such as 24 hours, excluding objects referenced by active work.
- Alert on orphan count/bytes and repeated cleanup failures.
- Record cleanup evidence before assuming Storage is temporary.

### Database lifecycle

- Measure rows plus table and index bytes before redesigning the schema.
- Treat a 90-day TTL for ordinary `job_events` belonging to terminal jobs as a
  proposal to validate against support and SSE replay needs; never prune
  queued, running, or recoverable-job events.
- Preserve billing orders, settlements, ledger, refunds, and webhook evidence
  for the approved accounting/audit period rather than applying the event TTL
  to every append-only table.
- Keep timestamped transcript segments while they power evidence links and
  episode Q&A; reducing their row count would remove product value.
- Physically purge only data whose privacy, shared-cache, foreign-key, and
  backup consequences have been approved.

## Parallel processing foundation: sources and chunking

This technical track can proceed independently of the user-facing growth
phases. The accepted source direction is documented in
[Audio acquisition and temporary delivery](../decisions/audio-acquisition-and-delivery.md).

- Keep bounded YouTube ingestion for the first release.
- Add publisher podcast RSS enclosure URLs as the next source adapter, with
  redirect, SSRF, byte, duration, and content-type controls.
- Add direct user audio uploads after upload abuse, ownership, privacy, and
  lifecycle rules are explicit.
- Normalize speech audio and introduce a durable, provider-independent
  chunking manifest before promising inputs beyond the current two-hour or
  100,000,000-byte boundary.
- Use ordered 15-25 minute chunks with small overlap, absolute timestamp
  offsets, bounded concurrency, per-chunk retry, deterministic overlap removal,
  and cache-compatible chunk hashes.
- Keep synchronous Groq/Cloudflare inference inside the background worker; the
  product remains asynchronous through its durable job and SSE progress.
- Warn at 50% Supabase egress, benchmark R2 around a 70% forecast, and make the
  move/no-move decision before a repeated 80% forecast. Do not add R2 merely to
  avoid a few dollars of occasional overage.

## Phase 1: Markdown and clipboard export

Talven already downloads the generated Markdown. The MVP extends that existing
path rather than adding an external integration.

### Actions

- **Copy Markdown** to the clipboard with visible success/failure feedback.
- **Download `.md`** using the existing browser path.
- Optionally offer **Copy plain text** only if users request it.

### Markdown envelope

Add stable YAML frontmatter where supported:

```yaml
---
title: "Episode title"
source_url: "https://www.youtube.com/watch?v=..."
source_channel: "Channel name"
source_published_at: "2026-08-05"
briefed_at: "2026-08-05T12:00:00Z"
language: "en"
talven_briefing_id: "..."
tags:
  - topic
---
```

Preserve timestamp links, stable headings, a safe filename, and a short Talven
provenance footer. Omit unavailable metadata rather than inventing it. Do not
place private signed URLs or user identifiers in the export.

### Obsidian and Notion decision

- Obsidian already accepts `.md`; copy/download plus frontmatter is sufficient.
- Notion users can paste or import the Markdown in the first release; validate
  the exact formatting and document the simplest working flow.
- Defer direct Notion OAuth until measured export usage proves that one-click
  delivery materially improves retention.

## Phase 2: unlisted public briefing and social sharing

An owner explicitly publishes a private briefing to an unguessable public
slug, for example:

```text
https://talven.example/b/{public-slug}?ref={referral-code}
```

### Public page

- Briefing title, source channel, and source link.
- Summary, takeaways, and bounded timestamped evidence.
- “Create your own briefing.”
- “Save this briefing to my library.”
- Copy link and native device share.
- Optional attribution using a user-chosen public display name, never email.
- Explicit unpublish, report, and takedown actions.
- `noindex` during the pilot; index only after content/privacy review.

“Save to my library” should attach the viewer to an already compatible cached
briefing without spending minutes or re-running providers. If the cached
artifact is incompatible with the current prompt/model/evidence contract,
Talven must regenerate or explain why.

### Social presentation

- OpenGraph image and metadata for link unfurls.
- WhatsApp, X, LinkedIn, and generic native-share actions.
- Downloadable 1080x1350 portrait card and 1080x1920 story card for Instagram
  or other image-first networks.
- Cards include title, one bounded takeaway, channel/source, and Talven mark.

Sharing an arbitrary quote is deferred. It needs safe quote selection, exact
source attribution, length limits, and copyright/product review. Start with a
generated takeaway card and add selectable quotes only after the basic page is
used.

### Acceptance signals

- share-page publication rate;
- share-link views and unique viewers;
- viewer-to-signup conversion;
- save-to-library rate;
- referral-attributed first paid purchase; and
- report/unpublish rate.

## Phase 3: referrals

Referral rewards activate only after the referred user completes a first paid
subscription purchase. One-off packs do not qualify in the first version.

### Proposed first-purchase bonus

| Referred user's first subscription | New subscriber bonus | Referrer bonus | Maximum direct processing reserve |
| --- | ---: | ---: | ---: |
| Starter | 1 hour | 1 hour | about $0.12 |
| Pro | 3 hours | 1 hour | about $0.24 |
| Agency | 5 hours | 1 hour | about $0.36 |

The new-subscriber bonus is deliberately more aggressive on larger plans while
the referrer receives one predictable hour for every qualifying conversion.
These are proposed launch values, not a permanent entitlement promise.

### Rules

- Attribution lasts 30 days from the first valid referral visit.
- The referral relation is immutable after a qualifying purchase.
- No self-referral by account, verified email, payment identity, or other
  proportionate fraud signals.
- Email verification and CAPTCHA are required.
- One reward per referred person and first qualifying subscription.
- Referrer limit: ten rewarded conversions/month without manual review.
- Grant seconds through an idempotent promotional credit lot.
- Promotional credits should have an explicit expiry, proposed at 90 days.
- Refund, dispute, or fraudulent-payment handling revokes unused promotional
  credit without corrupting already settled legitimate usage.
- Terms explain that promotional credits are non-cash, non-transferable, and
  can be withdrawn for abuse.

Do not grant both sides on signup alone. Disposable accounts would turn a cheap
reward into unlimited capacity abuse.

## Phase 4: “Ask this episode” MVP

The first version does not need a vector database or agent.

### Context contract

- Put behavioral and safety rules in system instructions.
- Treat the transcript as untrusted source data in a separate, clearly
  delimited content block; never let transcript text become system
  instructions.
- Label every segment with an immutable ID and absolute time range.
- Require answers to cite segment IDs and timestamp links.
- Permit an explicit “the episode does not provide enough evidence” answer.
- Keep the conversation scoped to one authorized briefing.
- Bound history and output so repeated questions do not grow without limit.

Example source envelope:

```text
[S001 | 00:00:00-00:00:22]
Transcript text...

[S002 | 00:00:22-00:00:51]
Transcript text...
```

### Candidate question allowances

These are experiment values to validate against usage and cost, not final
pricing promises:

| Plan | Candidate included questions/month |
| --- | ---: |
| Free | 3 trial questions |
| Starter | 25 |
| Pro | 100 |
| Agency | 300 |

At the current model prices, full-context episode questions are cheap, but
Talven must record actual input/output tokens and control long conversation
history before publishing these limits. A later add-on can sell question packs
only if usage proves demand.

### Acceptance evidence

- segment/timestamp citation precision;
- unsupported-answer abstention;
- prompt-injection resistance from transcript content;
- per-question token/cost and p95 latency;
- plan-limit and concurrent-request enforcement; and
- human evaluation across English, Spanish, long episodes, and technical
  content.

## Advanced episode research studio

After the single-episode MVP proves retention, possible layers are:

- answers that open playback at the exact cited moment;
- claim/evidence map and automatic glossary;
- beginner/expert explanations, quizzes, and spaced-repetition cards;
- comparison and contradiction detection across episodes;
- multiple episodes or entire channels in one conversation;
- external web research that separates “the guest says” from “independent
  evidence shows”;
- counterarguments, missing-evidence analysis, and personalized briefings;
- creation of memos, study guides, social threads, or Markdown notes;
- voice conversation tied to timestamped playback; and
- shared annotations and team knowledge.

Retrieval/vector storage becomes justified for multi-episode, channel, team,
or large-library questions—not for the bounded single-episode MVP.

## Phase 5: Explore and lightweight social discovery

The first discovery surface contains no comments or forum.

### Explore MVP

- Only explicitly opted-in or Talven-curated public briefings appear.
- Filter by source channel, topic, language, recency, and popularity.
- Show “This episode has already been briefed—read instantly or save it to
  your library.”
- Reuse compatible cached artifacts without charging minutes.
- Show optional “Shared by {public display name}” attribution.
- Allow an owner to remove a briefing from Explore while keeping it unlisted,
  or make it private again.
- Include report/takedown and a small admin review queue.

Start with chronological and manually curated sections. Ranking, likes, and
recommendation algorithms are unnecessary until enough public inventory and
traffic exist.

### Identity and follows

A Supabase account is authentication, not automatically a safe public profile.
Before “Shared by user X,” add an explicit public display name and visibility
choice. Never expose email, billing identity, private library, or activity by
default.

Following people is smaller than a forum but not free. It needs:

- a follower graph;
- public/private identity and activity choices;
- unfollow and block;
- feed pagination and cache behavior;
- account deletion handling;
- notification preferences; and
- abuse/reporting boundaries.

Add follows only after Explore has enough users and public briefings to avoid
an empty feed. The initial feed can show only newly published public briefings
from followed people; no direct messages, comments, or notifications.

## Phase 6: channel follows and digest

- A user follows a YouTube channel or podcast source.
- Talven discovers new episode metadata without automatically spending hours.
- The weekly digest shows new candidates and existing community briefings.
- Generate a full briefing on click, or precompute only when aggregate demand
  crosses a measured threshold.
- Respect unsubscribe, notification frequency, processing budget, duplicate
  detection, and source suitability.

This phase needs Resend's application API rather than only Supabase Auth SMTP.
At thousands of weekly recipients, expect to leave Resend's free email quota.

## Growth loop

```text
Create an evidence-backed briefing
-> ask cited questions
-> copy, export, or publish
-> another person reads the public artifact
-> signs up through the referral
-> purchases and both parties receive bounded credit
-> saves an existing briefing or creates another
-> opts into Explore and follows useful people/channels
-> returns through the digest
```

The immediate experiment is whether people share and save the artifact. Do not
build the later social graph or research agent before that behavior exists.
