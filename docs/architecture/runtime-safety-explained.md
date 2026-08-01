# Runtime safety, in plain language

This page explains the controls that are easiest to misunderstand during a
deployment review. It describes current behavior, not future promises.

## Browser data is scoped to the signed-in account

The web app keeps a small, short-lived cache so moving between screens feels
fast. That cache is now addressed by:

1. the signed-in Supabase user ID; and
2. an internal generation number that changes when the authentication state
   changes.

The generation number is not a Supabase session ID. It is simply a counter the
browser uses to reject an old request after sign-out or account switching.

Example: Ana starts loading her billing page, signs out, and Bruno signs in on
the same browser before Ana's request returns. Ana's late response is discarded
instead of appearing in Bruno's screen. Two people on separate computers never
shared this browser cache in the first place. Backend ownership checks and
database RLS remain the security boundary for every device.

## Password recovery has two configuration layers

The web app provides the user flow: request a reset email, accept only a valid
Supabase recovery session, require at least 12 characters and one digit, update
the password, and close the one-time recovery state.

`supabase/config.toml` is the tracked reference for the **local Supabase stack**.
It currently enables email confirmation, a 12-character minimum,
`letters_digits`, and secure password changes. Restart the local stack after
changing this file.

A hosted Supabase project has its own Auth settings. Database migrations and
`supabase db push` do not copy the local Auth section to that hosted project.
Before staging or production, mirror and verify these settings in the Supabase
Dashboard:

- Site URL and exact allowed redirect URLs, including `/auth/callback` and
  `/auth/recovery/callback` on the deployed web origin;
- email confirmation;
- minimum password length 12 and letters plus digits;
- secure password change; and
- a production SMTP service and tested email templates.

This means the code path is ready, but a real reset email is not proven until a
test user receives and completes it on the exact deployed domain.
Follow the step-by-step [hosted Auth and service-probe runbook](../runbooks/hosted-auth-and-service-probes.md)
when configuring each environment.

## A job lease prevents an old worker from overwriting a new worker

When a worker takes a job, the database gives it a random lease token and an
expiry time based on the database clock. The worker renews that lease while it
is healthy. Every later job update must present the same current token.

Example: Worker A takes a job and then loses its network connection. Its lease
expires, so Worker B safely takes over with a new token. If Worker A wakes up
and tries to save an old result, the database rejects token A. Only Worker B can
finish the job. Using the database clock prevents two machines with slightly
different system clocks from disagreeing about expiry.

## Streaming is bounded and reconnectable

SSE is the long-lived connection that sends progress updates to the briefing
screen. Defaults are:

| Control | Default | Meaning |
| --- | ---: | --- |
| Active streams per user | 3 | A fourth simultaneous progress stream is refused temporarily |
| Active streams per client IP | 12 | Bounds shared load from one network address |
| Lease duration | 90 seconds | A crashed connection disappears unless it renews |
| Maximum connection lifetime | 1 hour | The browser reconnects instead of holding one connection forever |

Example: one user opens the same active briefing in three tabs. Those tabs can
stream. A fourth open receives a temporary rate-limit response. Closing a tab
releases its lease; a crashed tab ages out. On reconnect, `Last-Event-ID` replays
the bounded missing history and an authoritative snapshot fills any gap.

Stream opening is also covered by the ordinary per-IP API rate limiter.
`/meta/health` is intentionally exempt so a hosting platform can check whether
the process is alive. `/meta/ready` is rate-limited because it performs real
dependency checks. Local development normally has `RATE_LIMIT=0`; staging and
production must configure a positive value.

## Billing recovery repairs missed or interrupted updates

Polar normally tells Talven about billing changes using webhooks. Webhooks can
arrive late, arrive twice, or be missed during an outage. The existing worker
loop schedules a billing-maintenance pass every 60 seconds; this is not a
separate dedicated billing process. The pass runs as one supervised background
task, so a slow Polar response does not pause normal briefing job claims. The
pass checks for:

- unfinished webhook processing;
- refunds that stayed pending;
- subscription state that differs from Polar; and
- completed briefings whose billing settlement needs another attempt.

Ordinary queued/running job recovery has its own worker lifecycle and stale-job
sweep. The billing-maintenance pass does not poll or reprocess every normal
briefing once per minute.

The 60-second tick is only a cheap opportunity to find work that is due. It
does not mean every subscription is sent to Polar once per minute:

- webhooks remain the immediate, event-driven path;
- a healthy non-terminal subscription is audited at most once every six hours;
- a failed provider audit is eligible again after 15 minutes, not every minute;
- each pass claims at most 20 due subscriptions; and
- revoked, ended, and inactive subscriptions are removed from provider polling.

The next audit time is stored in Postgres. It survives restarts, is shared by
all worker replicas, and prevents an old or newly started worker from forgetting
the delay. This is intentionally a targeted safety net rather than continuous
polling of healthy accounts.

Example: Polar completes a refund, but Talven is restarting when the webhook
arrives. The pack remains `refund_pending`. A later maintenance pass asks Polar
for the order, sees the refunded amount, and safely converges the local record.

Several workers may run, but a 120-second database lease lets only one perform
this maintenance at a time. It renews every 30 seconds. If that worker crashes,
another worker may continue after expiry. This avoids two workers applying the
same repair concurrently. The in-process task is also single-flight: a new pass
is not started while the previous one is still running, and shutdown cancels it
cleanly before the shared database client closes.

## Refund state and spendable balance

Refunds use three visible states:

| State | Purchased-packs screen | Spendable balance |
| --- | --- | ---: |
| `paid` | Normal pack with refund action when eligible | Included |
| `refund_pending` | Greyed out with a pending message | Excluded immediately |
| `refunded` | Removed from active purchased packs; retained in billing history | Excluded |

If Polar definitively rejects the refund, the database reopens the pack and
its remaining balance becomes available again. A network timeout is not treated
as a rejection because Polar may still have accepted the refund.

Refund and briefing settlement lock billing records in the same database order.
Example: a user submits a briefing while requesting a refund. Whichever
transaction acquires the relevant lock first completes against one consistent
balance; the other then sees the updated state. The same pack cannot be both
spent and refunded from two stale snapshots.

## The 10-minute debt threshold is not free credit

A user needs a positive balance to submit. When YouTube reports a duration, the
whole duration must fit the current balance. There is no arbitrary 3-, 5-, or
10-minute minimum because that would reject a short video that the remaining
balance can fully cover.

The 600-second debt threshold is only a settlement safety buffer. It protects a
valid completed briefing if, for example, two concurrent jobs both passed an
earlier balance check or a refund removed spendable credit before one job
settled. New work is blocked when the debt threshold is reached, and new credits
repay debt before becoming spendable.

Example: a user has 8 minutes. A known 7-minute video is accepted; a known
9-minute video is rejected before provider work starts. The user is not invited
to intentionally consume the separate 10-minute safety buffer.

If Talven cannot determine a positive video duration, it now rejects the source
before creating work. Treating an unknown duration as zero would allow an
unmetered briefing. The 10-minute threshold does not deliberately admit a video
that is longer than the user's balance.

## Source metadata and evidence deadlines

YouTube metadata lookup has a 30-second overall deadline. Audio download has a
separate 10-minute deadline. Thirty seconds is deliberately generous for one
metadata lookup, but it is still a starting value: staging measurements must
confirm it against the intended regions and hosting network.

New transcripts must contain timestamp segments before a briefing can become
ready. Missing or empty evidence triggers a retry/failure instead of publishing
an uncited fallback. Existing ready briefings remain readable through their
owned jobs. For a fresh production database, there are no legacy rows to
migrate; all newly processed sources use the evidence-aware path.

## Loopback and external URLs

A loopback address always points back to the same machine:

- `http://localhost:3000`
- `http://127.0.0.1:3000`
- `http://[::1]:3000`

These are correct for local development. They are invalid for a hosted user,
because that user's `localhost` means their own computer, not Talven's server.
Staging and production therefore require HTTPS external URLs such as
`https://app.talven.ai`, exact CORS origins, and a non-loopback database host.

## Archive, deletion, and retention are different

A public YouTube video is public, but the fact that a particular account
submitted it is account-related information. Talven also handles email and Auth
state, library/archive choices, usage and debt records, Polar customer/order
identifiers, request security metadata, and generated exports. Reusable
transcripts and summaries may be shared derived records, while each user's job,
access, and billing remain separate.

- **Archive** hides a briefing from the active library and can be reversed.
- **Delete** permanently erases a record and may affect shared cache or audit
  relationships.
- **Retention** means how long each category is kept before deletion.

For the pilot, archive remains the product action. Self-service permanent
deletion is intentionally not improvised because billing, fraud prevention,
account data, temporary audio, logs, and shared derived content need different
retention rules. Those rules and the public privacy promise must be approved
before a paid public launch.

## Why CI actions use commit SHAs

A tag such as `v7` is a human-friendly pointer that can move. A full commit SHA
selects one immutable source snapshot, so a third-party action cannot silently
change between two runs with the same workflow file. The comment keeps the
readable release line next to the exact SHA.

The Supabase CLI is similarly pinned to version `2.111.0` in migration
workflows. This is the tested repository version, not a claim that it will
always be the newest release. Upgrade it deliberately, review release notes,
and rerun the clean-database checks.

The release workflow uses GitHub's short-lived scoped `github.token` for
checkout and API reads. The protected `main` ruleset requires a separate valid
`RELEASE_AUTOMATION_TOKEN` belonging to an administrator/bypass identity for
the generated release commit and tag push. Before any release write, the
workflow reports whether that secret is missing, invalid/expired, or read-only. See the
[release automation runbook](../runbooks/release-automation.md).

## Related operator documentation

- [System and job lifecycle](./system-and-job-lifecycle.md)
- [Security and data access](./security-and-data-access.md)
- [Briefing product behavior](../product/briefing-behavior.md)
- [Worker and billing incidents](../runbooks/worker-and-billing-incidents.md)
- [Pre-production review register](../decisions/pre-production-review-register.md)
- [Hosted Auth and service probes](../runbooks/hosted-auth-and-service-probes.md)
- [Release automation](../runbooks/release-automation.md)
