# Paid launch action plan

**Status:** Accepted execution plan
**Last reviewed:** 2026-08-11

This page turns the accepted launch scope into an order of work. It answers
three practical questions:

1. What are we building before the paid public launch?
2. What does each feature have to do before it counts as complete?
3. What proof is required between finished code and public access?

The [growth feature roadmap](./growth-feature-roadmap.md) keeps the deeper
feature proposals and future extensions. The
[pre-production review register](../decisions/pre-production-review-register.md)
and [first deployment checklist](../runbooks/first-deployment-checklist.md) own
the operational, provider, privacy, and hosting proof. This action plan connects
those documents; it does not replace them.

## Accepted launch boundary

The robust MVP for paid launch contains six product capabilities:

1. Copy Markdown.
2. Private-by-default unlisted sharing with publish and unpublish.
3. Save a published briefing to the signed-in user's library.
4. Curated Explore using deliberately listed briefings.
5. Referral attribution and first-paid-subscription rewards.
6. A private, cited **Ask this episode** experience.

Profiles, comments, likes, follower counts, user follows, public activity,
ranking algorithms, cross-episode retrieval, agents, shared chat, and direct
Notion OAuth are outside this launch boundary.

Light audience building, customer conversations, positioning, and waitlist
copy may happen while the MVP is being built. Aggressive promotion and firm
feature promises wait until the features are demonstrable and the staging
candidate is stable.

## What “product contract” and “acceptance criteria” mean

A **product contract** is the exact behavior a user can rely on. It states:

- who may perform an action;
- what appears in the interface;
- what data is created or reused;
- whether time, questions, or money are consumed;
- what happens after unpublish, archive, refund, retry, or duplicate input;
- what remains private; and
- which limits and errors the user sees.

It is not an API schema. It prevents the UI, backend, database, billing logic,
tests, and marketing copy from implementing different interpretations of the
same feature.

**Acceptance criteria** are observable pass/fail examples proving that product
contract. For example:

> Given a ready briefing, when its owner selects Copy Markdown, the exact
> exportable Markdown is copied once and the UI confirms success. If clipboard
> access fails, the UI explains the failure without claiming that copying
> succeeded.

Define these rules before implementing each slice. They do not require a large
design document: one concise contract plus testable examples is enough.

## Workstream A: connected sharing and growth slice

These five capabilities share one public-briefing foundation and should be
built in order.

```text
Copy Markdown
  -> publication foundation
  -> publish and unpublish
  -> save to my library
  -> curated Explore
  -> referrals
```

### 1. Copy Markdown

Talven already downloads a `.md` file. This slice adds clipboard convenience
without changing the saved briefing.

Product contract:

- Show Copy Markdown only when the briefing is ready and Markdown exists.
- Copy the same Markdown content used by the download path.
- Preserve headings and timestamp links.
- Confirm success and report clipboard failure honestly.
- Do not add private signed URLs, secrets, or user identifiers.

Minimum acceptance criteria:

- Ready Markdown copies successfully once.
- Empty or unfinished content cannot claim success.
- Clipboard rejection produces useful recovery copy.
- Download Markdown continues to work unchanged.
- Keyboard and mobile interaction remain accessible.

Implementation status (2026-08-11): merged. Copy and download
share the same export payload, clipboard failures point back to the `.md`
download, and focused frontend tests cover content preservation, empty content,
missing clipboard access, and browser rejection.

### 2. Publish and unpublish sharing

Sharing introduces one reusable visibility model:

| Visibility | Discovery |
| --- | --- |
| Private | Only the owner can open it. |
| Unlisted | Anyone with an unguessable link can open it. |
| Listed | Talven selected it for the curated Explore catalogue. |

Product contract:

- A briefing is private by default.
- Only its owner may publish, change visibility, or unpublish it.
- The public route exposes only the approved briefing presentation and source
  attribution, never account email, billing data, private URLs, or internal
  processing fields.
- An unlisted URL is unguessable and stable until the owner unpublishes.
- Anyone with an Unlisted link can read the public page without an account.
- Sign-in is required only to save it or create a briefing.
- Users cannot add their own publications to Explore.
- Unpublish removes public and Explore access without deleting the owner's
  private briefing.
- Talven never moves a user's Unlisted briefing into Explore without explicit
  owner consent.
- Public pages offer Create new briefing and Save to my library.
- Structured reports remain deferred. The moderation state keeps a direct
  takedown path available to Talven.
- Pilot pages remain `noindex` until indexing is deliberately approved.

Minimum acceptance criteria:

- Private briefings are never returned by public routes or Explore queries.
- Publishing and unpublishing are authorization-protected and idempotent.
- Anonymous, signed-in, owner, non-owner, invalid-slug, and unpublished cases
  have deliberate responses.
- Social metadata contains only approved public fields.
- Talven can block a publication without deleting the underlying briefing.

Implementation status (2026-08-12): implemented in the forward migration
`20260811120000_add_publication_foundation.sql`. It adds one server-only
publication record with stable unguessable slugs; Private, Unlisted, and Listed
visibility; moderation state; and automatic unpublish on owner-job archive.
There is no admin table, public Explore submission queue, or structured report
table. The owner commands, anonymous read API, public page, atomic library save,
curated Explore catalogue, and Listed-only source match are connected to this
foundation. Referrals are not part of this implementation.

### 3. Save to my library

Example: Ana publishes a briefing. Bruno opens it and selects **Save to my
library**. Talven gives Bruno a user-owned library entry that reuses the
compatible ready artifact.

Product contract:

- Anonymous visitors sign in and return to the same public briefing.
- Saving does not download or process the audio again.
- Saving does not consume audio minutes.
- Ana and Bruno never share account, billing, archive, or library state.
- Repeated saves are idempotent and do not create duplicates.
- Bruno may archive or restore his entry without affecting Ana.
- Archiving Bruno's saved entry removes it only from Bruno's active library;
  Ana's publication and the public page remain available.
- If Ana later unpublishes, the public route disappears; an already saved
  private library entry remains available to Bruno.
- A legal, privacy, or safety takedown is different from normal unpublish. Its
  removal scope must be decided before public launch and may include saved
  copies.
- Ask this episode uses Bruno's question allowance when he asks from his saved
  entry.

Minimum acceptance criteria:

- A signed-in visitor can save a compatible listed or unlisted briefing once.
- A duplicate save returns the existing library entry.
- No provider call or audio-minute settlement occurs.
- Tenant isolation holds for read, archive, restore, export, and question use.
- Unpublish removes new public access without corrupting existing private
  library entries.

### 4. Curated Explore

Explore is a catalogue of deliberately listed, completed briefings. It is not
a feed of what users are currently processing.

Product contract:

- Show only ready briefings with Listed visibility.
- Start with a small Talven-curated inventory of high-quality briefings.
- At launch, use briefings created by Talven. Do not promote a user's Unlisted
  briefing without explicit owner consent.
- Do not offer public Explore submissions or a review queue at launch.
- Start with one controlled topic per briefing and visible topic filters. Add
  language or channel only when the catalogue needs them.
- Cards lead to the public briefing and its Save to my library action.
- Optional attribution uses an explicitly chosen public display name, never an
  email address.
- Owners can remove their briefing from Explore by returning to Unlisted, or
  remove all public access by returning to Private.
- There are no comments, follows, likes, public profiles, or private activity.

Minimum acceptance criteria:

- Private, unlisted, failed, archived-only, and unpublished briefings cannot
  leak into Explore.
- Non-operator users cannot set Listed visibility. The backend operator
  allowlist controls Explore access.
- Filters are stable, accessible, and have useful empty states.
- Save from Explore follows the same idempotent, no-minute contract.
- Unlist and takedown changes are reflected promptly.

When a user submits a source that already has a compatible Listed briefing,
Talven should offer **Open briefing** and **Save to my library** before creating
new work. Saving uses no minutes. An Unlisted publication must never be exposed
through this source lookup because possession of its URL is its discovery
boundary. This match is strict for launch: Talven does not offer a duplicate
generation. Add **Create another version** only when users can choose a
different prompt, format, or model.

Each Listed briefing has one controlled topic: Business, Culture, Finance,
Health, Life, Productivity, Psychology, Science, Self-improvement, Society, or
Technology. One source can have only one active Listed publication.

### 5. Referrals

Referrals attach acquisition to the sharing loop rather than rewarding raw
signup volume.

Sharing and referrals are separate. A normal public link works without a
referral. Saving a briefing grants no referral reward. Referral attribution
starts only when a valid referral code is present, and rewards still require a
qualifying first paid subscription.

Product contract:

- Attribute the first valid referral for 30 days.
- Grant rewards only after the referred user completes the first qualifying
  paid subscription purchase.
- Do not reward one-time packs initially.
- Prevent self-referral using proportionate account, email, and payment
  signals.
- Grant fixed promotional seconds through an idempotent credit lot.
- Enforce the approved monthly reward cap.
- Revoke unused promotional credit after a qualifying refund, dispute, or
  confirmed fraud without corrupting legitimate settled usage.
- Explain expiry and non-cash status in plain terms.

Minimum acceptance criteria:

- Replayed visits, checkouts, and webhooks cannot grant duplicate credit.
- Expired attribution and self-referral grant nothing.
- Sandbox purchase, renewal noise, cancellation, refund, and dispute paths are
  covered.
- Both users see accurate pending, granted, used, expired, or revoked state.
- Referral metrics contain no unnecessary personal data.

Reward amounts and the complete proposal live in the
[growth roadmap](./growth-feature-roadmap.md#phase-3-referrals).

## Workstream B: Ask this episode

This feature is independent of public sharing. It can be designed and built in
parallel once the connected slice has stable ownership and briefing contracts.

Product contract:

- One authorized briefing and one transcript per conversation.
- The transcript is untrusted source content, never system instructions.
- Answers cite transcript segments and open the corresponding timestamps.
- The model may say that the episode does not contain enough evidence.
- Conversation history, input size, output size, latency, and questions per
  plan are bounded.
- Questions use a separate allowance from audio minutes.
- Conversations are private and have an explicit retention/deletion rule.
- The MVP uses the complete bounded transcript; it does not require a vector
  database, agent, Redis, custom WebSockets, or cross-episode retrieval.

Minimum acceptance criteria:

- Only an authorized owner or saver may ask about the briefing.
- Cited answers map to valid segment IDs and timestamps.
- Unsupported questions abstain rather than invent episode evidence.
- Transcript prompt-injection examples cannot replace system behavior.
- Duplicate requests and provider retries do not double-count questions.
- Plan limits, provider failure, timeout, and unavailable-transcript states are
  understandable.
- Actual tokens, latency, error rate, and estimated cost are measurable.

Detailed context and evaluation proposals live in
[Ask this episode MVP](./growth-feature-roadmap.md#phase-4-ask-this-episode-mvp).

## Verification and launch runway

Feature completion is followed by proof in this order.

### 1. Automated and internal testing

- Unit, application, API-contract, frontend, database, RLS, billing, and
  migration checks pass.
- Happy paths, authorization, retries, idempotency, mobile behavior, privacy,
  billing consequences, abuse limits, and telemetry are covered.
- Owner testing confirms that visible copy matches the product contracts.

### 2. Invite-only staging beta

- Deploy one exact release across web, API, and worker.
- Use a separate staging Supabase project and Polar sandbox.
- Keep the site invite-only and `noindex`.
- Invite a small family, friends, and selected-user cohort.
- Exercise real Groq/OpenRouter processing under spending caps.
- Collect completion, failure, sharing, saving, referral, and question evidence.
- Fix material defects and repeat the exact affected journeys.

The public waitlist page may already run on the production domain while the
authenticated product remains gated.

### 3. Production rehearsal

- Promote the exact staging-proven release before public launch day.
- Keep production gated while testing real origins, SMTP, Auth callbacks,
  Polar checkout/webhooks, tax/currency, cancellation, refund, logs, alerts,
  backups, and restore.
- Complete one controlled real purchase and refund.
- Confirm no staging credential, callback, database, or provider destination is
  used by production.
- Open public access only after this rehearsal passes.

### 4. Aggressive marketing and launch

- Market real, demonstrable outputs rather than speculative internals.
- Lead with evidence-backed briefings that users can read, question, save, and
  share.
- Use real curated examples, social cards, and Ask this episode demonstrations.
- Invite the waitlist in controlled waves so support and provider capacity are
  observable.
- Track waitlist-to-invite, invite-to-activation, free-to-paid, share-to-signup,
  save, referral purchase, Ask usage, cost, and retention.

## Free access and plan intent

Keep the existing launch model until evidence justifies changing it:

- Talven's Free plan grants one audio hour per month without a payment method.
- A waitlist member may select an intended paid plan before launch.
- The invitation's primary action continues into that selected paid plan.
- A secondary action allows the user to prove the product with the Free plan.
- Do not add a separate Polar card trial or an additional free-hour reward.
- After 30-60 days, review free completion, repeat use, cost, sharing, and
  conversion. If recurring free use does not create conversion or growth,
  evaluate replacing it with a one-time onboarding allowance.

Plan selection on the waitlist records intent, not a binding purchase. Payment
begins only when the invited user completes authenticated checkout.

## Scope-change rule

New ideas go to the growth or deferred-work roadmap unless they are required to
make one of these six capabilities correct, safe, understandable, or
measurable. Do not delay paid launch for profiles, follows, comments, advanced
research, additional source types, or infrastructure whose measured trigger
has not occurred.

## Immediate next action

Apply the forward migration in staging and complete authenticated browser checks
for publish, unpublish, anonymous read, save, archive, Explore, and source match.
Then implement referrals as the next connected slice.

Ask this episode receives its own implementation plan and can proceed as a
separate workstream after the connected ownership contract is stable.
