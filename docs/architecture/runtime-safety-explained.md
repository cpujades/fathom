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

## Shared processing does not expose a shared database row

Talven may reuse one transcript and one summary when Ana and Bruno submit the
same compatible public video. Each person still has a separate private `jobs`
row and billing settlement. The browser cannot read the shared `summaries`
table at all. FastAPI first proves that the caller owns a successful or archived
job pointing to the summary, then its server-only client reads the summary and
returns only `briefing_id`, `markdown`, and an optional short-lived `pdf_url`.

Before this change, row-level security correctly required Bruno to have his own
successful job, but then allowed him to select the complete shared summary row.
That row could contain Ana's historical producer ID and internal generation or
PDF fields. It was not a leak of Ana's job or billing record, but it was
unnecessary cross-account metadata exposure. The browser's table permission is
now revoked, while normal API access and global reuse still work. The
[cache guide](./cache-and-versioning.md#concrete-two-user-example) gives the
complete fake rows, UUIDs, column values, old query, new response, and Charlie's
denied path.

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
the bounded missing history and an authoritative snapshot fills any gap. Quiet
processing does not poll once per tab: committed job events wake one coordinator
per API process, which fetches once per job and fans out locally. Keepalives
prove a quiet browser transport is still healthy. The 45-second durable
reconciliation remains dormant while the listener is healthy and runs only
during listener loss; a queue-overflow signal also reconciles all local jobs.

Stream opening is also covered by the ordinary per-IP API rate limiter.
`/meta/health` is intentionally exempt so a hosting platform can check whether
the process is alive. `/meta/ready` is rate-limited because it performs real
dependency checks. Local development normally has `RATE_LIMIT=0`; staging and
production must configure a positive value.

### Session ownership is checked before reserving a stream

SSE means Server-Sent Events: the long-lived HTTP connection that carries live
briefing progress to the browser. Each connection consumes one limited stream
slot, so Talven reserves it with a short database lease.

Previously the server reserved a slot and only then, after the streaming
response started, loaded the requested session with the user's token. RLS still
prevented another user's session from being read, so this was not a content
leak. The problem was ordering: a missing, archived, or other user's session
could briefly consume capacity, and an error discovered after streaming began
is harder to return as a normal HTTP error.

Now the server first performs a user-scoped lookup. For example, if Bruno asks
for Ana's session UUID, RLS returns no row and Talven returns `404` before
claiming a stream slot. If Bruno asks for his own active session, Talven then
claims the slot and starts the stream. The already-authorized job row is passed
into the stream so the lookup is not repeated.

## Billing recovery repairs missed or interrupted updates

Polar normally tells Talven about billing changes using webhooks. Webhooks can
arrive late, arrive twice, or be missed during an outage. The existing worker
loop schedules a billing-maintenance pass every five minutes; this is not a
separate dedicated billing process. The pass runs as one supervised background
task, so a slow Polar response does not pause normal briefing job claims. The
pass checks for:

- unfinished webhook processing;
- refunds that stayed pending;
- subscription state that differs from Polar; and
- completed briefings whose billing settlement needs another attempt.

Ordinary queued/running job recovery has its own worker lifecycle and stale-job
sweep. The billing-maintenance pass does not poll or reprocess every normal
briefing once every five minutes.

The five-minute tick is only a cheap opportunity to find work that is due. It
does not mean every subscription is sent to Polar every five minutes:

- webhooks remain the immediate, event-driven path;
- a healthy non-terminal subscription is audited at most once every six hours;
- a failed provider audit is eligible again after 15 minutes, not every pass;
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

### Unexpected downloader IPC failures clean up the child process

The YouTube downloader runs in a separate child process so a difficult media
library call cannot block the main async API or worker event loop. IPC means
"inter-process communication": the parent process sends a small JSON request
through the child's standard input, and the child sends a JSON response back
through standard output.

Timeout and cancellation paths already stopped that child. The missing case was
an unexpected pipe/process error while the parent was exchanging data—for
example, an operating-system `broken pipe` error. The request failed, but the
child might have remained alive without useful work. The parent now catches
that unexpected failure, kills and waits for the child, and returns the normal
safe downloader error. This is process/resource cleanup; it does not expose
the operating-system error or source details to the user.

## Loopback and external URLs

A loopback address always points back to the same machine:

- `http://localhost:3000`
- `http://[::1]:3000`

These are correct for local development. They are invalid for a hosted user,
because that user's `localhost` means their own computer, not Talven's server.
Staging and production therefore require HTTPS external URLs such as
`https://app.talven.ai`, exact CORS origins, and a non-loopback database host.

### Hosted configuration fails early instead of using a plausible wrong value

Local development may use `NEXT_PUBLIC_SITE_URL=http://localhost:3000`. A
hosted frontend must set the exact public origin, for example
`https://app.talven.ai`. This value is used for canonical page metadata and
authentication/recovery destinations. If a hosted build silently fell back to
localhost, a password-recovery link could send a real user to that user's own
computer. The production build now fails when the value is missing, is HTTP on
a non-localhost domain, contains credentials, or contains a path, query, or
fragment. No hosted value needs to be chosen while the project is local; this
guard makes forgetting it at deployment visible.

Supabase's HTTPS URL and API keys are not the same as a direct Postgres
connection. Ordinary Auth/data/storage calls use `SUPABASE_URL` and keys. The
worker's `LISTEN` wake-up connection and readiness schema checks need the
database host, password, user, database name, and port. Staging and production
therefore refuse to start without a non-loopback `SUPABASE_DB_HOST` and
`SUPABASE_DB_PASSWORD`. `SUPABASE_DB_PORT` is simply the database's network
door number; only values from 1 through 65,535 are possible, so values such as
`0` or `70000` are rejected as configuration mistakes. Typical examples are
port `54322` for the local Supabase CLI and `5432` for a hosted database.

These checks do not choose a provider and do not open a port. Once hosting is
selected, its connection details are supplied through secrets/environment
configuration.

## Two loading/download controls now behave honestly

Generating or retrieving a PDF is asynchronous: the browser clicks, waits for
the API, and receives a signed URL later. Browsers often block `window.open`
when it runs after that wait because it no longer looks like the user's direct
click. Talven no longer tries to open the late URL automatically. It displays a
real `Download PDF` link when ready; the user's second click is explicit, so
normal pop-up protection does not block it. This change is about reliable
download UX, not the PDF renderer's content-security boundary.

The billing page has a shared account header while plans and balances load.
Its loading branch previously supplied an empty sign-out callback, so the menu
showed a Sign out action that did nothing. It now retains the actual account
label, balance, and sign-out function from the authenticated app shell. A slow
billing request therefore cannot trap the user behind a dead control.

## What "still pending" means while everything is local

These items are not hidden code changes that can be completed without a host.
They are runtime evidence or operator choices that must exist before external
users are invited:

| Pending proof or choice | What is already implemented | What cannot be proved or configured yet |
| --- | --- | --- |
| Clean Supabase migration/database suites | Migrations and pgTAP tests are committed; PR CI runs them for `supabase/**` changes | The local Docker stack was stopped during this review. A green clean-database PR job supplies this proof; it is not an open design question |
| Groq and OpenRouter candidate rehearsal | Provider clients, deadlines, retries, validation, and fake-provider tests exist; local real calls may already work | On the exact release candidate, record representative short/long sources, output review, latency, provider limits, and bounded test spend |
| Polar sandbox lifecycle | Checkout, portal, signed webhook, refund, replay, and reconciliation code/tests exist; sandbox use may already work locally | On the exact candidate, record one complete sandbox purchase/subscription/refund/cancel flow, including webhook delivery and local state convergence |
| Hosted origins and HTTPS | Strict URL, CORS, proxy, and environment validation is in code | Exact web/API domains, Supabase redirect allow-list, Polar return URLs, TLS, and trusted proxy networks do not exist until a host/domain is selected |
| Worker liveness and alerts | The worker logs startup, listener health, reconnects, claims, retries, lease loss, shutdown, and maintenance | A host must keep the worker process alive; an observability destination and alert recipient must be chosen and a deliberately triggered alert must be received |
| Backups, restore, rollback, and capacity | Durable data/lease/retry behavior and deployment checklists exist | The selected Supabase/hosting plans determine backups and limits; the team must restore a backup, rehearse one rollback, measure representative load, and name the person who responds to incidents |
| Retention/privacy policy | Data categories and the archive-versus-delete distinction are documented | Product/legal decisions must set actual retention periods and user promises before a paid public launch |

A successful local call proves that one call worked from the development
machine. The phrase "candidate rehearsal" means repeating and recording the
complete journey using the exact commit and hosted configuration proposed for
release. It does not mean the provider integrations are assumed broken today.

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

For the initial release, archive remains the product action. Self-service permanent
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
