# Product and user workflows

This is the user-facing owner’s guide. It describes what Talven should feel
like at each step, then points to the technical boundary that makes the step
work. The product accepts public YouTube URLs and turns them into validated,
source-linked written briefings.

## 1. Discover, sign up, and return safely

The public site explains the product and sends a new visitor to `/signup` or an
existing user to `/signin`. A pricing selection can carry a bounded plan intent
through authentication, so a user who chooses a plan before signing in returns
to billing with that choice still selected. Arbitrary external redirect URLs
are rejected. Both authentication entry routes ask Supabase for the current
user before rendering: an already-signed-in user goes directly to the safe app
destination, including the exact known paid-plan selection when present.

When a signed-out visitor arrives from a paid pricing choice, both authentication
pages show the product name, catalog price, included time, and monthly or
one-time cadence. The copy makes clear that payment has not started and that
checkout will still be reviewed. Missing, Free, malformed, and unknown plan
values do not produce a product summary.

There is no invitation code or email allowlist in the product. Once a public
deployment URL is announced, any visitor may create an account. Hosted email
confirmation, SMTP, CAPTCHA/bot protection, and Auth rate limits must therefore
be configured before that URL is opened; local UI tests do not provide those
controls.

The supported entry methods are password, magic link, and Google OAuth. A
password sign-up that receives Supabase's existing-account result places a
sign-in action beside the error, preserves the safe destination and known plan,
and transfers only the email through one-use tab storage. The sign-in page
consumes that email immediately; the password remains empty and no email is put
in the URL. Magic-link sign-up uses neutral copy because the same link signs in
an existing user or creates a new user. In the local Supabase stack, email
confirmation is enabled: create a disposable user,
open Inbucket at `http://localhost:54324`, and follow the confirmation link.
Hosted email delivery and redirect allowlists are environment configuration,
not database migrations; see the [hosted Auth runbook](../runbooks/hosted-auth-and-service-probes.md).

After a successful callback, the browser establishes its Supabase session and
opens the intended `/app/**` route. The Next.js proxy protects the page, but the
FastAPI API still verifies the bearer token on every private request.

## 2. Start the first briefing

The workspace at `/app` is deliberately simple: paste a public YouTube URL and
continue. `/app/briefings/new` shows four short visual steps—check source,
transcribe, write, and ready—while the API performs the actual validation.

Before any expensive work is queued, the API:

1. accepts only supported YouTube URL shapes and rejects playlists;
2. canonicalizes the video to `https://www.youtube.com/watch?v=<id>`;
3. reads the source duration and rejects unknown, non-positive, or over-two-hour
   videos; and
4. checks that the user is not blocked and has enough currently available
   video time for the whole source.

For example, a user with 8 minutes remaining may submit a known 7-minute video
but not a known 9-minute video. The separate 600-second debt cap is a safety
buffer during final settlement; it is not advertised or intentionally offered
as extra minutes.

When the combined spendable subscription and pack balance is positive but below
10 minutes, the workspace shows a non-blocking warning. A fitting source stays
enabled. Active paid subscribers open one-time packs first; Free users see the
normal plans-and-packs comparison. Zero balance, outstanding debt, and a debt
block keep their stronger explanations instead. The shared balance says when it
is checking and refreshes after known billing/briefing changes and when a stale
tab regains focus; server admission remains authoritative.

If validation fails, the API returns a stable admission code and bounded
server-computed details where useful: `source_duration_unknown`,
`insufficient_video_time` (`required_seconds` and `available_seconds`),
`no_video_time`, or `balance_blocked` (`debt_seconds`). The page uses the code,
not English-message matching, to choose source or billing recovery while keeping
the URL editable.

## 3. Watch processing and understand the states

The create request returns a session snapshot and sends the browser to
`/app/briefings/sessions/<id>`. The page first reads an authoritative snapshot,
then subscribes to a reconnectable SSE stream. The visible state sequence is:

```text
accepted
  -> resolving source / checking reusable work
  -> transcribing
  -> drafting briefing
  -> finalizing briefing
  -> ready
```

If bounded transcription or writing attempts exhaust an explicit rate limit,
the session exposes `provider_capacity_reached` and uses high-demand copy. A
timeout, network failure, or provider 5xx exposes
`provider_temporarily_unavailable` with neutral availability copy. Neither path
names the provider or blames the source. “Try again” preserves the same source
and opens a confirmation step; it never starts another briefing automatically.
Invalid transcript or briefing responses remain the distinct
`transcription_failed` or `summary_failed` stage errors.

Progress is an explanation of the current stage, not a wall-clock promise. A
quiet stream remains healthy through 15-second keepalives and does not trigger
periodic browser reads. A disconnect or 30 seconds without transport activity
causes one recovery snapshot, then the browser reconnects with `Last-Event-ID`
and replays persisted events. The server validates event payloads before the
browser uses them.

The system does not reveal an unvalidated AI draft as the source of truth. The
worker waits for structured JSON, validates every evidence citation, and then
renders Markdown deterministically. The UI may reveal that complete Markdown
with a typing effect; reduced-motion users see it immediately.

## 4. Read, export, and revisit a briefing

When ready, the user can:

- read the Markdown briefing in the session reader;
- follow timestamp links back to the cited YouTube moments;
- download the Markdown;
- generate or reuse a private PDF; and
- return later from `/app/briefings`.

The library supports search, newest/oldest sorting, pagination, opening a
session, and archiving. Archiving hides a user’s job from the active library;
it does not delete the reusable transcript, summary, billing evidence, or
audit history. Submitting the same source later restores the archived ready
job without regeneration or a second charge.

## 5. Submit the same source again

The API reports one of three resolutions:

| Resolution | User-visible meaning | Billing meaning |
| --- | --- | --- |
| `new` | No reusable work exists; a job is queued | One charge after successful finalization |
| `joined_existing` | The user joined their own active session | No second charge |
| `reused_ready` | A ready briefing was restored or reused | No charge for the same user; one charge for a new user-owned job using shared work |

Two users never share a job, library state, usage record, or billing record.
They may share a ready transcript/summary cache. If two users arrive before a
transcript exists, both may still download/transcribe the source; summary
generation is fenced so only one producer publishes the compatible summary.

## 6. See access, buy time, and request a refund

`/app/billing` loads plans, the current subscription, available video time,
pack balance, debt, expiry, and billing history. The current public catalog is
defined in `scripts/polar/plan_contract.json`:

| Offer | Included time | EUR | USD | GBP | Expiry/renewal |
| --- | ---: | ---: | ---: | ---: | --- |
| Free | 60 minutes | €0 | $0 | £0 | Monthly reset, no carryover |
| Starter | 6 hours | €9 | $10 | £8 | Monthly; one-month carryover |
| Pro | 15 hours | €19 | $22 | £17 | Monthly; one-month carryover |
| Agency | 50 hours | €49 | $56 | £42 | Monthly; one-month carryover |
| Trial Pack | 3 hours | €6 | $7 | £5.50 | Expires after 90 days |
| Creator Pack | 10 hours | €18 | $21 | £16 | Expires after 90 days |
| Studio Pack | 40 hours | €60 | $69 | £52 | Expires after 90 days |

Prices exclude tax. Polar adds applicable tax at checkout and selects EUR for
euro customers, GBP for UK customers, and the organization's default USD price
elsewhere. Every pack expires independently; buying another pack does not
extend an older one. Paid subscription time may carry into the immediately
following billing month only, up to twice the normal monthly allowance.

The UI opens Polar checkout or the customer portal; it never receives the
Polar access token. A successful browser redirect is not the accounting proof.
The signed Polar webhook creates or updates local billing state, and the worker
reconciliation pass repairs missed or delayed provider events. Checkout and
refund requests each receive an opaque, user-scoped sync operation. The billing
page checks that small status resource with bounded backoff, then refreshes the
full billing view once when local state reaches a terminal result. If operation
confirmation times out or cannot be read, the page still reloads the
authoritative balance, subscription, and orders while clearly keeping the
individual operation in a delayed state. Manual refresh performs one operation
check and the same full billing refresh, so an already-applied webhook becomes
visible without inviting a duplicate payment or refund request.

Only purchased packs are refundable. Starting a refund immediately marks the
pack `refund_pending` and removes its remaining seconds from spendable balance.
If Polar confirms the refund, the pack becomes `refunded`; if Polar definitively
rejects it, Talven reopens the pack. A timeout is not treated as rejection, so
the UI says confirmation is taking longer and does not ask the user to submit
the refund twice.

New credits repay outstanding debt before becoming available. When debt reaches
600 seconds, new briefing creation is blocked until credits pay it down.

One billed minute means 60 seconds of source video, not one minute of worker
wall-clock time, model output, or browser activity. Talven stores balances and
settlements in seconds for accuracy. The duration read from YouTube is stored
on the job, used for admission, and used again by the atomic settlement
command. A 30-minute video therefore consumes 1,800 balance seconds—exactly 30
billed minutes—even if its provider calls finish faster or slower.

## 7. Recover from common failures

- **SSE disconnect:** the page reconnects and reconciles; the user does not
  resubmit.
- **Worker/provider retry:** the job remains the same session and retries within
  bounded attempts/deadlines; the user does not pay again.
- **Finalization or settlement delay:** the ready content stays hidden until
  usage settlement is recorded; the worker retries the visible finalization
  state.
- **No credits:** billing explains the remaining balance and offers more video
  time.
- **Password recovery:** the reset form is shown only after Supabase verifies a
  recovery callback and the short-lived recovery marker is present.
- **Archive:** reversible library state, not permanent deletion.

## Deliberate product boundaries

The initial release does not offer running-job cancellation, permanent self-service
erasure, arbitrary non-YouTube sources, podcast Q&A/chat, or 300-minute videos.
These are decisions with charging, privacy, provider, or recovery consequences;
they are recorded in the [deferred work register](../decisions/deferred-work.md).

For the implementation behind these experiences, continue with the
[frontend architecture](../architecture/frontend-auth-and-user-flows.md) and
[system lifecycle](../architecture/system-and-job-lifecycle.md).
