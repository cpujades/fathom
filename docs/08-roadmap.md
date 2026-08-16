# Roadmap

**Status:** Active product and deferred-work register.

**Read this to understand:** what comes next, what should wait, and the evidence
that should reactivate deferred work.

The [Launch plan](./07-launch-plan.md) owns launch gates and the scope-freeze
decision. This page owns future product and technical work.

## Contents

- [Rules and status](#rules)
- [Current state](#current-state)
- [Immediate order](#immediate-order)
- [Referrals](#referrals)
- [Ask this episode](#ask-this-episode)
- [Near-term after launch](#near-term-after-launch)
- [Later product direction](#later-product-direction)
- [Product idea register](#product-idea-register)
- [Trigger-based deferrals](#trigger-based-product-deferrals)
- [Boundary-bound work](#boundary-bound-work)
- [Excluded direction](#excluded-direction)
- [Activating a roadmap item](#activating-a-roadmap-item)

## Rules

1. Build one measurable product slice at a time.
2. Write its user contract and acceptance criteria before implementation.
3. Keep private behavior private by default.
4. Reuse compatible ready work without charging or processing it twice.
5. Separate source claims from external verification.
6. Add infrastructure only after a measured trigger.
7. Record whether a completed feature changed activation, retention, revenue,
   reliability, cost, or support.

## Status meanings

- **In progress:** already changing in the current branch.
- **Next candidate:** near-term work, but still subject to the paid-launch scope
  decision.
- **After launch:** useful only after the core product has real users.
- **Trigger-based:** do not schedule until the named evidence exists.
- **Excluded:** outside the foreseeable product boundary.

## Current state

| Capability | Status | Remaining work |
| --- | --- | --- |
| Evidence-backed YouTube briefing | Current | Real-provider and human release proof |
| Markdown download | Current | None for launch |
| Copy Markdown | Current | Authenticated release-candidate proof |
| Private library and archive | Current | Retention and permanent-erasure policy |
| Private PDF | Current | Hosted capacity proof |
| Unlisted sharing | In progress in current launch branch | Authenticated browser and staging proof |
| Save public briefing | In progress in current launch branch | Authenticated browser and staging proof |
| Curated Explore | In progress in current launch branch | Initial catalogue and staging proof |
| Listed source matching | In progress in current launch branch | Candidate proof |
| Usage-history simplification | In progress | Complete migration and all billing/database checks |
| Referrals | Next candidate | Owner scope decision and implementation |
| Ask this episode | Next candidate | Owner scope decision and implementation |

## Immediate order

1. Finish and verify the current publication and billing work.
2. Freeze the invite-only beta scope.
3. Select hosting and launch providers.
4. Run the staging beta.
5. Use beta evidence to confirm whether referrals and Ask this episode remain
   required before paid public launch.
6. Launch the accepted scope.
7. Measure before choosing the next feature.

## Referrals

### Hypothesis

People who share a useful briefing can acquire paying customers. A reward tied
to a first paid subscription can increase this loop without rewarding disposable
signups.

### Smallest honest version

- A normal public link works without a referral.
- The first valid referral is attributed for 30 days.
- Saving a briefing gives no reward.
- Only the referred user's first qualifying paid subscription grants rewards.
- One-time packs do not qualify initially.
- Rewards are fixed promotional seconds in idempotent credit lots.
- Self-referral and repeated webhooks grant nothing.
- Unused promotional credit can be revoked after refund, dispute, or confirmed
  fraud.
- Terms state expiry, non-cash status, and abuse rules.

### Proposed launch values

| First subscription | New subscriber | Referrer |
| --- | ---: | ---: |
| Starter | 1 hour | 1 hour |
| Pro | 3 hours | 1 hour |
| Agency | 5 hours | 1 hour |

Proposed referrer cap: ten rewarded conversions per month without manual
review. Proposed promotional expiry: 90 days.

These values are experiments, not permanent entitlements.

### Acceptance criteria

- Duplicate visits, checkouts, and webhooks cannot grant twice.
- Expired attribution grants nothing.
- Self-referral grants nothing.
- Sandbox purchase, cancellation, refund, and dispute paths are covered.
- Both users see pending, granted, used, expired, or revoked state accurately.
- Metrics contain no unnecessary personal data.

### Success evidence

- share-to-signup conversion;
- referred signup-to-paid conversion;
- reward cost per paying customer;
- fraud and refund rate;
- promotional credit consumption; and
- retained usage from referred customers.

## Ask this episode

### Hypothesis

A private cited question experience increases the value and repeat use of one
briefing.

### Smallest honest version

- One authorized briefing and transcript per conversation.
- Transcript text remains untrusted source content.
- Answers cite immutable transcript segment IDs and timestamp links.
- The model may say that the source lacks enough evidence.
- History, input, output, latency, concurrency, and questions per plan are
  bounded.
- Questions use a separate allowance from audio minutes.
- Conversations are private with an explicit retention and deletion rule.
- The complete bounded transcript is sent to the model.

The MVP does not need a vector database, agent framework, Redis, custom
WebSockets, or cross-episode retrieval.

### Candidate question limits

| Plan | Questions per month |
| --- | ---: |
| Free | 3 |
| Starter | 25 |
| Pro | 100 |
| Agency | 300 |

These are experiment values. Measure tokens, latency, cost, and actual use
before publishing them as a lasting promise.

### Acceptance criteria

- Only an authorized owner or saver can ask.
- Citations map to valid segment IDs and timestamps.
- Unsupported questions abstain instead of inventing evidence.
- Transcript prompt injection cannot replace system rules.
- Retries and duplicate requests cannot double-count.
- Limits and provider failures are understandable.
- Tokens, latency, errors, and cost are measurable.

### Success evidence

- share of ready briefings with a question;
- questions per active user;
- repeat visits after first question;
- citation precision;
- abstention quality;
- cost and p95 latency; and
- paid conversion or retention difference.

## Near-term after launch

Build only when the current product evidence supports the hypothesis.

### Creator and publisher service experiment

**Status:** Proposed. Test it as a small service before building a new product
surface.

Talven can turn one processed episode into several useful outputs:

- evidence-backed briefing;
- show notes and source links;
- newsletter draft;
- social post drafts; and
- sponsor, research, or editorial memo.

This direction reuses the current transcript, evidence, briefing, publication,
export, and sharing work. It can improve margin when customers pay for a saved
workflow and finished deliverables, instead of cheap processing time alone.

Start with three to five YouTube or podcast creators as a manual concierge
test. Do not build team roles, white-label pages, RSS automation, or bulk APIs
until customers pay for the manual result.

Possible offers after evidence:

| Offer | Value | Build only when |
| --- | --- | --- |
| Creator Studio | Self-service episode assets | Creators repeatedly use several outputs |
| Managed creator service | Reviewed deliverables per episode | Manual delivery has healthy contribution and retention |
| Agency or publisher plan | Several shows, team workflow, bulk delivery | One organization has repeated paid demand |

Measure episodes per month, creator time saved, delivery time, revisions,
direct cost, contribution per account, retention, and referrals from published
briefings.

The natural acquisition loop is:

    creator publishes a useful briefing
      -> audience reads or saves it
      -> some readers join Talven
      -> creator receives more reusable assets
      -> creator publishes again

Use this loop in marketing only after real creator results and permission to
show them.

### Owner telemetry

Create one operator view for:

- users, ready briefings, cold sources, and cache hits;
- audio hours, downloaded bytes, provider usage, retries, and cost;
- stage and total latency;
- temporary-audio cleanup;
- database, Storage, egress, and PDF growth;
- Polar sales, tax, fees, refunds, payouts, and contribution;
- sharing, public views, saves, referrals, and Ask use; and
- activation, conversion, and retention.

This is required operational visibility before broad unattended use. A custom
Talven dashboard is not required if an existing observability product can show
the data safely.

### Export improvements

Possible small improvements:

- stable YAML frontmatter;
- safe filename and provenance footer;
- optional Copy plain text; and
- manually verified Notion and Obsidian instructions.

Direct Notion OAuth remains deferred until export usage proves that one-click
delivery would improve retention enough to justify tokens, OAuth, conversion,
retry, and revocation complexity.

### Public sharing improvements

After basic public pages are used:

- native share action;
- OpenGraph presentation;
- downloadable social cards;
- explicit public display name;
- simple report or takedown intake; and
- indexing only after content and privacy review.

Do not add arbitrary quote sharing until selection, attribution, length,
copyright, and safety behavior are explicit.

### Explore improvements

Start with chronological and owner-curated content. Add filters only when the
catalogue needs them.

Later candidates:

- language or channel filters;
- simple popularity based on enough real traffic;
- explicit creator attribution;
- report queue when contact-based handling no longer scales; and
- recommendations only after inventory and behavior justify them.

## Later product direction

### Podcast RSS

Publisher RSS enclosure URLs are the next source adapter. The implementation
needs redirect, SSRF, size, duration, type, ownership, and temporary-object
controls.

### Direct audio uploads

Wait until demand justifies:

- upload abuse protection;
- ownership and consent;
- private storage lifecycle;
- file validation;
- quota and charging behavior; and
- deletion and provider-retention policy.

### Advanced episode research

After single-episode Ask proves retention:

- playback at the cited moment;
- glossary and claim/evidence map;
- quizzes and study cards;
- comparison across episodes;
- external verification that clearly separates source and external claims;
- counterarguments and missing-evidence analysis;
- reusable memos or study guides; and
- team annotations.

Vector retrieval becomes relevant for multi-episode, channel, team, or large
library questions.

### Identity, follows, and digest

Do not create a public profile from a Supabase account automatically.

Public identity requires:

- explicit display name and visibility;
- no email or billing exposure;
- block and report behavior;
- deletion and retention rules; and
- clear public activity choices.

Follows require enough public users and briefings to avoid an empty feed.
Channel follows and email digest come later. They also need notification
preferences, unsubscribe, source discovery, processing budgets, and a
transactional email provider.

## Product idea register

These ideas are recorded so they are not forgotten. None belongs in the paid
launch scope without a separate scope decision.

| Idea | Earliest position | Reason to wait | Smallest useful test |
| --- | --- | --- | --- |
| Briefing styles and templates | Early post-launch candidate | More options can weaken the clear default and multiply quality tests | Offer one alternative template to a small cohort and compare completion and reuse |
| Regenerate a briefing | After styles or clear quality demand | It changes charging, cache identity, provider cost, version history, and publication behavior | One explicit regeneration reason with preview, cost, and preserved old version |
| User-selectable models | Later | Model names are technical, unstable, and create price and quality variance | Test outcome choices such as Fast or Detailed before exposing provider model names |
| Mind maps | After export and reuse evidence | It needs a stable structured representation and a real editing/export use case | Generate one accessible, downloadable map from existing briefing sections |
| Forums and discussions | Trigger-based | Moderation, identity, abuse, notifications, deletion, and empty-community risk are substantial | Start with structured feedback or a limited discussion pilot on Listed briefings |
| Creator workspace or service | Near-term experiment | It needs a sales offer, delivery boundary, rights, support level, and margin proof | Sell a manual-assisted package that reuses briefing, evidence, export, and publishing |

Prefer user outcomes over implementation controls. For example, “Fast” and
“Detailed” are easier to understand than a list of model identifiers. Keep one
high-quality default until evidence shows that choice improves activation,
retention, or revenue.

## Trigger-based product deferrals

| Item | Current decision | Revisit trigger |
| --- | --- | --- |
| Cancel a running job | Do not offer cancellation | Users abandon long jobs or provider cost becomes material |
| Content-suitability rejection | Accept supported sources | Abuse or low-value inputs become material in labeled evidence |
| Permanent self-service erasure | Handle verified requests manually under an approved policy | Request volume or policy requires automation |
| Upfront credit reservations | Admit from current balance; settle after success | Concurrent jobs create unacceptable debt |
| Additional source types | YouTube first | Target users repeatedly need RSS or upload |
| Paid question packs | Included limits only | Ask usage proves demand |
| Comments and likes | Do not build | Explore has real repeat community behavior that needs them |

When activated, define visible behavior, billing/privacy effects, migration,
abuse controls, recovery, and acceptance tests before implementation.

## Trigger-based processing deferrals

| Item | Current decision | Revisit trigger | Minimum safe direction |
| --- | --- | --- | --- |
| Global producer before transcription | Separate user jobs may duplicate first transcription | Duplicate provider cost is measurable | Tenant-neutral source work, fenced takeover, failure and fairness rules |
| Sources longer than two hours | Keep two hours and 100 MB | Target users need longer sources and provider tests pass | Chunk manifest, bounded concurrency, per-chunk retry, offsets, deterministic merge |
| Replace `pytubefix` | Keep current adapter | Failures or maintenance become material | Representative adapter comparison behind current subprocess interface |
| Cache retention redesign | Versioned ready work remains reusable | Storage growth, source removal, or freshness demand | Explicit retention, invalidation, metrics, and privacy compatibility |
| Dedicated PDF worker | Keep bounded API subprocess | PDF CPU, memory, latency, or busy rate becomes material | Isolated queue, capacity, rollback, and unchanged fetch protections |

## Trigger-based infrastructure deferrals

| Item | Current decision | Revisit trigger |
| --- | --- | --- |
| Redis for notifications | Postgres `LISTEN/NOTIFY` wake hint | Measured notification lag or database overhead |
| Redis for cache | Per-process and database-backed current caches | Replicas repeatedly compute an expensive safe shared value |
| Redis for rate limits | Postgres buckets | Measured write contention, latency, or pool pressure |
| External worker queue | Postgres durable queue | Measured claim latency or required priority/routing |
| Supabase Realtime for job wake-up | Backend SSE plus Postgres notifications | Direct listener is unreliable or too expensive on selected host |
| Cloudflare R2 | Private Supabase Storage | Measured egress, recovery, reliability, or plan limits |
| Event-driven billing recovery | Bounded five-minute safety pass | Empty passes create material load or repair delay is unacceptable |

Do not introduce Redis and RabbitMQ for the same role. If a broker becomes
necessary, preserve Postgres as durable product authority until migration,
outbox, reconciliation, idempotency, and rollback are proved.

## Boundary-bound work

These items cannot remain deferred once the named boundary is reached:

| Item | Boundary |
| --- | --- |
| Hosting, domains, and process topology | Before external access |
| Exact origins, trusted proxy, TLS, rate limits, and abuse controls | Before public URL |
| Production SMTP and Auth callbacks | Before public signup |
| Central logs, metrics, and urgent alerts | Before unattended external use |
| Retention schedule and manual privacy-request process | Before public signup |
| Backups, restore, and rollback | Before external users create important data |
| Polar sandbox and production proof | Before paid public launch |
| Real provider quality, cost, latency, and privacy proof | Before paid public launch |

These belong to [Launch plan](./07-launch-plan.md) and
[Deployment and operations](./06-deployment-and-operations.md), not to a
post-launch backlog.

## Account deletion and shared work

Archive is reversible library state. It is not deletion.

Before self-service deletion, decide separately how to handle:

- Auth identity and sessions;
- user-owned jobs and saved publications;
- shared transcripts and summaries used by other users;
- PDFs and temporary audio;
- settlements, orders, refunds, disputes, and tax evidence;
- security and support logs;
- backups; and
- provider-held data.

Current foreign keys cascade Auth deletion through jobs and usage settlements.
Billing orders survive with a null user link. This database behavior does not
cancel Polar subscriptions or clean Storage and provider data, so direct Auth
deletion is not a complete or approved product flow.

A safe future flow needs strong authentication, a possible cooling-off period,
transactional deletion or anonymization, legal/payment exceptions, shared
record dependency checks, Storage cleanup, provider cleanup, backup behavior,
and minimal completion proof.

Do not promise that one button immediately removes every category until the
system and provider contracts can prove it.

## Excluded direction

The current roadmap excludes:

- a general social network;
- direct messages;
- a forum;
- shared live chat;
- autonomous agents as a product goal;
- speculative multi-provider infrastructure;
- automatic public identity;
- ranking before enough inventory and traffic; and
- infrastructure added only because it is fashionable.

Reconsider an excluded idea only after a clear user problem and measurable
benefit exist.

## Activating a roadmap item

1. State the user problem.
2. Record the evidence or trigger.
3. Define the smallest honest user contract.
4. Define one primary success metric and guardrails.
5. Record billing, privacy, abuse, migration, recovery, and support effects.
6. Add acceptance criteria.
7. Implement and test one slice.
8. Measure the result before expanding it.

## Next read

Return to the [reading guide](./00-reading-guide.md), then record questions and
launch decisions beside the owning chapter.
