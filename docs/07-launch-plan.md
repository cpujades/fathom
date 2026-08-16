# Launch plan

**Status:** Active owner plan.

**Read this to understand:** where development should stop, what the current
candidate contains, which decisions remain open, and what must be proved before
marketing.

## Contents

- [Launch principle](#launch-principle)
- [Current position](#current-position)
- [Product scope decision](#product-scope-decision)
- [Recommended sequence](#recommended-sequence)
- [Required gates](#required-gates)
- [Reputation protection](#reputation-protection)
- [Initial release rhythm](#initial-release-rhythm)

## Launch principle

Talven should launch in controlled stages. A serious launch does not require
every future feature. It requires:

- one clear product promise;
- correct privacy and billing boundaries;
- reliable core journeys;
- real provider and hosted-environment proof;
- understandable failures;
- support and recovery ownership; and
- enough measurement to detect harm quickly.

The first external users should see a small, finished product. They should not
be the first people to test authentication email, payment webhooks, backups, or
basic mobile usability.

## Current position

- the application runs locally;
- application hosting is not selected;
- Copy Markdown is implemented;
- Private, Unlisted, and Listed publications are implemented;
- public briefing pages, save to library, curated Explore, and Listed source
  matching are implemented;
- authenticated browser proof for the publication slice is still required;
- `usage_settlements` provides immutable usage history, with atomic admission
  protection for parallel jobs;
- referrals are not implemented;
- Ask this episode is not implemented; and
- production SMTP, observability, backups, restore, provider rehearsals, and
  public support/privacy decisions are not proved.

Code completion alone does not make this a public release candidate.

## Product scope decision

The existing accepted paid-launch plan contains six capabilities:

| Capability | Current status | Needed for |
| --- | --- | --- |
| Copy Markdown | Implemented | Core usefulness |
| Publish and unpublish | Implemented; candidate proof pending | Sharing |
| Save public briefing | Implemented; candidate proof pending | Reuse and activation |
| Curated Explore | Implemented; candidate proof pending | Demonstration and discovery |
| Referrals | Not implemented | Acquisition experiment |
| Ask this episode | Not implemented | Paid differentiation and retention experiment |

There are two honest launch boundaries:

### Boundary A: invite-only product beta

Freeze new feature development after the current candidate is verified. Use
the beta to prove that people:

- complete a briefing;
- understand its evidence;
- export or share it;
- save an existing public briefing;
- return to the library; and
- understand the pricing and credit model.

Referrals and Ask this episode are not required for this private beta.

### Boundary B: paid public launch

The current accepted plan includes referrals and Ask this episode before broad
paid promotion. This remains the default until the owner changes it.

Before building both, use the invite-only beta to answer:

1. Do users value the briefing itself?
2. Do they share or save it without incentives?
3. Does Ask this episode solve a repeated user problem?
4. Is referral attribution important for the first acquisition channel?

If the evidence is weak, adding both features before launch increases scope
without proving product value. If the evidence is strong, their product
contracts and acceptance criteria are already defined in
[Roadmap](./08-roadmap.md).

## Recommended sequence

### Stage 0: finish the local candidate

1. Verify publication, usage history, and parallel-job admission end to end.
2. Confirm that the one-time schema reset can discard every existing app row
   in its first target environment.
3. Run backend, frontend, generated-contract, and database checks.
4. Test the complete authenticated journey locally.
5. Fix material product, security, billing, and accessibility defects.
6. Freeze new feature work for the beta candidate.

The local candidate is complete when the existing scope works. It is not
complete because every roadmap item has been built.

### Stage 1: choose launch infrastructure

Decide and record:

- web host;
- API host;
- continuous worker host;
- Supabase staging and production projects;
- production SMTP provider;
- Polar sandbox and production organizations;
- central logs, metrics, and alerts;
- domain and DNS;
- backup and restore controls; and
- support and incident ownership.

Use real limits, pricing, regions, privacy terms, and operational effort at the
time of selection. Do not copy old provider-price assumptions into the final
decision.

### Stage 2: deploy invite-only staging

Deploy one exact release:

- separate staging database and secrets;
- Polar sandbox;
- real Groq and OpenRouter calls under spending caps;
- final-style HTTPS origins and Auth callbacks;
- invite-only access;
- `noindex`; and
- central logs and basic alerts.

Invite a small, known group. Keep the cohort small enough that one owner can
observe failures and speak to users.

### Stage 3: collect beta evidence

Record:

| Area | Minimum evidence |
| --- | --- |
| Activation | Signup to first ready briefing |
| Reliability | Completion, retry, reconnect, and failure rates |
| Quality | Human usefulness and timestamp-citation accuracy |
| Performance | End-to-end and stage latency by source length |
| Cost | Groq seconds, OpenRouter tokens, storage, egress, and cost per briefing |
| Sharing | Publish rate, public views, and save rate |
| Retention | Repeat briefing creation and library return |
| Billing | Sandbox checkout, webhook, cancellation, pack refund, and reconciliation |
| Support | Common questions, confusing states, and recovery time |

Fix defects that affect trust, money, privacy, data loss, or the central
workflow. Put optional improvements in the roadmap.

### Stage 4: confirm the paid-launch boundary

After beta, make one explicit decision:

- launch the proven core product; or
- complete referrals and Ask this episode first.

Record the reason and evidence. Do not let the choice remain implicit while
development continues.

### Stage 5: production rehearsal

Promote the exact staging-proven release while public access remains closed.
Prove:

- final HTTPS origins and redirects;
- Supabase email confirmation and password recovery through production SMTP;
- one controlled real Polar purchase and refund;
- signed production webhooks without redirects;
- tax and currency presentation;
- logs and alerts;
- database and Storage backups;
- one restore;
- application rollback;
- privacy, retention, erasure-request, refund, and support procedures; and
- desktop, mobile, keyboard, screen-reader, and reduced-motion journeys.

No staging secret, callback, product ID, database, or provider destination may
remain in production.

### Stage 6: public launch and marketing

Open access in controlled waves:

1. invite the existing waitlist;
2. observe activation, provider capacity, errors, and support load;
3. expand only while the product remains stable; and
4. market real examples and outcomes.

Do not market speculative features as available. Use real public briefings,
source evidence, exports, Explore examples, and Ask demonstrations only when
each feature is live.

## Required gates

### Pull-request gate

- Backend lint, format, type checks, and tests pass.
- Frontend lint, tests, type checks, and production build pass.
- OpenAPI and generated client are current.
- A clean disposable database applies every migration and passes database
  tests and lint.
- Any destructive migration is explicitly accepted for the exact target and
  release boundary.
- The diff contains no secrets, unrelated generated changes, or accidental
  provider and domain changes.

### Invite-only beta gate

- Pull-request gate passes on the exact release.
- Complete authenticated journey passes with fake providers.
- Capped real Groq and OpenRouter rehearsal passes.
- Publication, save, Explore, archive, export, billing, and recovery journeys
  pass on desktop and mobile.
- Staging Auth email and callbacks work.
- Logs reach one searchable destination.
- Urgent alerts reach the owner.
- Staging data and secrets are separate from production.

### Public signup gate

- Exact origins, HTTPS, trusted proxies, rate limits, and abuse controls are
  verified.
- Production SMTP, confirmation, recovery, and OAuth callbacks work.
- Privacy, terms, retention, manual erasure requests, support contact, and
  response ownership are published and honest.
- Database and object backup controls are enabled and one restore is proved.
- Central monitoring and incident alerts are active.
- Capacity is measured on the selected topology.

### Paid public-launch gate

- Polar sandbox proof passes on the exact candidate.
- One controlled production purchase, cancellation, webhook, portal, and
  refund pass.
- Tax, currency, refund amount, product IDs, and checkout copy are correct.
- Real provider quality, latency, cost, and privacy settings are accepted.
- Human UX and accessibility review passes.
- Rollback and restore are proved.
- The final product-scope decision is recorded.

## Reputation protection

Treat these as release blockers:

- cross-user data exposure;
- double charging or incorrect refunds;
- publishing private content;
- lost completed work;
- ungrounded or broken evidence links;
- misleading success states;
- unusable authentication or recovery;
- missing support for a payment or privacy problem;
- no way to detect material failures; and
- no tested restore or rollback.

Treat these as normal post-launch improvements:

- more source types;
- advanced search or ranking;
- social features;
- direct integrations;
- perfect performance;
- speculative infrastructure; and
- features without a measured user problem.

## Initial release rhythm

For the first month after launch:

- plan work weekly;
- keep each user-facing release small;
- release a finished slice when its checks and rollback path are ready;
- avoid several unrelated high-risk changes in one release;
- publish short release notes for visible changes;
- review product and operational metrics weekly; and
- review the roadmap monthly.

Urgent security, billing, privacy, or availability fixes do not wait for the
normal rhythm.

This is a starting operating model. Change it when real support load, usage,
team size, and deployment reliability provide better evidence.

## Next read

[Roadmap](./08-roadmap.md)
