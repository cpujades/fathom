# User workflow improvement register

**Status:** Active product UX register
**Last reviewed:** 2026-08-05

This document tracks places where the current user journey works but is not yet
as clear, direct, or reassuring as it should be. It follows the sections in
[Product and user workflows](./user-workflows.md).

The workflow guide remains the source of truth for behavior that exists today.
Items here move through the status lifecycle below; an original gap can remain
documented after implementation so its rationale is not lost. Each item records:

- the original gap;
- why that experience is weaker than it should be;
- what should happen instead; and
- the minimum implementation and acceptance evidence needed to close it.

## Status meanings

- **Open:** the gap exists in the current code and has not been implemented.
- **In progress:** implementation has started but is not fully verified.
- **Needs human review:** automated checks pass, but the experience still needs
  a real desktop/mobile usability review.
- **Complete:** the behavior, focused regression tests, and human review are
  complete.

## 1. Discover, sign up, and return safely

### AUTH-UX-01: Already-authenticated users are sent to sign-up

**Status:** In progress

**Original gap**

Every public paid-plan link points to `/signup` with a safe billing destination
and plan intent. The Free link also points to `/signup`. The `/app/**` proxy
protects authenticated routes, but `/signup` and `/signin` do not redirect a
browser that already has a valid session. Consequently, a signed-in user who
selects a public pricing option sees an account-creation form again.

**Why this is bad**

- It asks a known user to perform an irrelevant task: create or access an
  account they are already using.
- It can make the user wonder whether Talven lost their session or whether they
  are about to create a duplicate account.
- It adds unnecessary friction immediately before a high-intent billing action
  and can cause checkout abandonment.

**What should happen**

A user with a valid session should bypass both authentication entry pages. A
paid selection should go directly to
`/app/billing?intent=paid&plan=<safe_plan_code>`, where the chosen product is
ready to review. A normal or Free entry should go to `/app`.

**What we need to implement**

1. Make `/signup` and `/signin` session-aware using a server-verified Supabase
   user/session check.
2. Reuse the existing safe destination and plan-intent validation; do not trust
   or forward arbitrary redirect URLs or query parameters.
3. Redirect authenticated users before rendering the auth form to avoid a
   visible flash of the wrong page.
4. Keep this protection at the auth-entry boundary even if pricing buttons also
   become session-aware, because users can open saved or copied URLs directly.

**Acceptance evidence**

- A signed-in user selecting each paid subscription and pack reaches billing
  without seeing sign-up or sign-in, and the exact product remains selected.
- A signed-in user selecting Free reaches the app.
- Signed-out users still see the correct auth entry page.
- Unsafe destinations and malformed plan codes still fall back safely.

### AUTH-UX-02: Sign-up does not show the selected product

**Status:** In progress

**Original gap**

Talven preserves `intent=paid` and the plan code invisibly through sign-up,
sign-in, email confirmation, magic link, and Google OAuth. The generic sign-up
page does not tell the user which product they selected. The selection becomes
visible only after authentication, on the billing page.

**Why this is bad**

- The user loses visual continuity after pressing a specific pricing button.
- A generic form can make them question whether their selection was forgotten.
- The missing price and billing type make it harder to notice that they chose a
  subscription rather than a one-time pack, or vice versa.

**What should happen**

When a valid paid intent is present, the auth page should show a compact summary
such as:

```text
Continue with Creator Pack
$15 one-time - 10 hours
You will review the details before checkout.
```

This is context, not a payment confirmation. The user must still review the
authenticated billing page and explicitly open checkout.

**What we need to implement**

1. Resolve the bounded plan code against Talven's known public pricing catalog;
   never display a product name or price taken directly from the URL.
2. Show the product name, price, included time, and either monthly or one-time
   billing language on both sign-up and sign-in when a valid intent exists.
3. State clearly that payment has not started and checkout will still be
   reviewed.
4. Render no product summary for missing, malformed, or unknown plan codes.

**Acceptance evidence**

- All three paid subscriptions and all three packs show the correct summary.
- The Free and ordinary auth flows remain uncluttered.
- Altered or unknown URL values cannot create misleading product copy.
- The summary is keyboard accessible and announced in a sensible reading order.

### AUTH-UX-03: Password users recover manually from duplicate sign-up

**Status:** In progress

**Original gap**

If Supabase reports that a password-sign-up email already belongs to an
account, Talven tells the user to sign in instead. A sign-in link at the bottom
of the page preserves the safe destination and pricing intent, but the user
must find that link, change pages, and enter their email and password again.

Talven must not add a separate public “does this email exist?” lookup. Supabase
intentionally limits account-existence information to reduce account
enumeration risk.

**Why this is bad**

- A common mistake—choosing sign-up instead of sign-in—turns into a partial
  restart of the flow.
- The recovery action is separated from the error that explains the problem.
- Re-entering the email adds avoidable work and makes the preserved pricing
  intent less obvious.

**What should happen**

When the existing-account condition is available, the error should include an
immediate action such as “Sign in to continue with Creator Pack.” That action
should retain the safe destination and plan selection and prefill the email on
the sign-in page. The password must remain empty.

**What we need to implement**

1. Place an inline sign-in action next to the duplicate-account explanation.
2. Preserve `next`, `intent`, and the validated plan code with the existing URL
   helpers.
3. Transfer the email through short-lived client-side state, such as
   `sessionStorage`, rather than putting personal information in the URL,
   browser history, analytics, or server logs.
4. Clear the transferred email after it is read and never transfer the password.
5. Do not automatically attempt sign-in with the password entered as a proposed
   new password; it may not be the existing account password.

**Acceptance evidence**

- A duplicate password sign-up presents the recovery action beside the error.
- Sign-in opens with the email prefilled, the password empty, and the exact plan
  intent preserved.
- Refreshing or starting an unrelated sign-in does not retain stale email data.
- The behavior does not introduce an account-discovery endpoint or expose an
  email in a URL.

### AUTH-UX-04: Magic-link sign-up uses inaccurate account-creation copy

**Status:** In progress

**Original gap**

Magic-link mode on `/signup` calls Supabase's OTP sign-in operation with user
creation allowed. The same operation can continue an existing account or
create a new one. After the email is sent, Talven always says, “Check your inbox
to continue with account creation.” That statement is inaccurate for an
existing user.

**Why this is bad**

- Existing users may think Talven is creating a duplicate account.
- The message describes an internal assumption instead of the next action the
  user actually needs to take.
- It makes the otherwise useful combined sign-in/sign-up magic-link behavior
  feel inconsistent.

**What should happen**

Use neutral, accurate language for both cases, for example:

```text
Check your inbox to continue with Talven.
The link will sign you in; if you are new, it will create your account.
```

**What we need to implement**

1. Replace the account-creation-only success message with neutral copy.
2. Keep the message as an announced status update and retain the current safe
   callback and plan intent.
3. Review the related button and helper text so the page does not make a second
   contradictory claim about what the magic link will do.

**Acceptance evidence**

- The same message is truthful for a new email and an existing email.
- The status is announced to assistive technology.
- Following the email link still restores the intended app or billing route.

## 2. Start the first briefing

### Product rule to preserve: debt is not user-selectable credit

Talven must continue requiring a known video's complete duration to fit the
user's current positive balance before work starts. The default 600-second debt
threshold is only a final-settlement safety buffer for already-admitted work,
such as two concurrent jobs that passed the same earlier balance snapshot or a
refund that removed credit after admission.

Users must never be invited to borrow against that threshold. New subscription
or pack time repays existing debt before becoming spendable, and already-
admitted concurrent jobs may take aggregate debt beyond the threshold. The
threshold blocks later admission; it is not a purchasable allowance or a hard
limit that discards a valid completed briefing.

The low-balance warning proposed below also uses ten minutes, but it is a
separate product UX threshold. Its implementation must not reuse or expose the
backend debt-cap setting as though the two concepts were the same.

### BRIEFING-UX-01: Low balance has no proactive, plan-aware warning

**Status:** In progress

**Original gap**

The authenticated header shows total available video time, and the workspace
shows the same combined subscription-plus-pack balance beside “Start
briefing.” The workspace explains debt and offers “Add time” after the user has
no spendable time or the account is blocked. It does not warn a user whose
balance is positive but running low.

The shared balance is refreshed on session startup and after known actions such
as a completed briefing or a billing-page update. It is not a continuously
streamed value, so it can temporarily be absent while loading or become stale
until another refresh after an external change.

The current billing link opens the offers section in its default subscription
mode. That is not the most relevant first view for someone who already has a
paid subscription and only needs a one-time top-up.

**Why this is bad**

- The first warning can arrive only when the next briefing is already blocked.
- Users cannot plan a top-up before interrupting their work.
- Sending an active subscriber first to another subscription choice is
  confusing when a pack is the natural add-on.
- A missing or stale header value weakens confidence that the displayed balance
  is authoritative.

**What should happen**

When combined spendable time is greater than zero but below ten minutes, show a
non-blocking warning such as:

```text
Only 8 minutes of video time remain.
Add time now so your next briefing is not interrupted.
```

The warning must not stop a source that fits the remaining balance and must not
mention or imply that the debt buffer is available to spend.

Recovery should reflect the current subscription:

- **Active paid subscription:** make “Add a one-time pack” the primary action
  and open the pack offers first. The user should not be encouraged to buy a
  second subscription.
- **Free plan, with or without existing pack time:** use neutral language such
  as “See plans and packs” and keep both monthly and one-time options easy to
  compare.
- **Zero balance or outstanding debt:** use the stronger existing blocked/no-
  time explanation rather than the low-balance warning.

**What we need to implement**

1. Introduce an explicit frontend product constant such as
   `LOW_BALANCE_WARNING_SECONDS = 600`; keep it independent from
   the backend `BILLING_DEBT_CAP_SECONDS` code constant even though both
   currently equal ten minutes.
2. Base the warning on `total_remaining_seconds`, which already sums spendable
   subscription and active pack time. Do not add debt to this number.
3. Use the current subscription state to choose the CTA label and initial
   billing offer mode.
4. Add a validated billing-view parameter or equivalent navigation state so an
   active subscriber's CTA can open one-time packs first. Do not automatically
   choose a product or start checkout.
5. Show an explicit checking state when the shared balance is unknown. Refresh
   after known balance mutations and when a stale app regains focus, while
   retaining the backend admission check as the authority.
6. Keep the warning accessible, visually noticeable without resembling an
   error, and free from repeated announcements during ordinary rerenders.

**Acceptance evidence**

- `10m` or more shows no low-balance warning; `9m 59s` through `1s` does.
- A fitting short source remains enabled while the warning is visible.
- Zero time and debt conditions use their stronger recovery states instead.
- The displayed number equals subscription time plus active spendable pack
  time, excluding expired, refunded, and refund-pending packs.
- A paid subscriber's primary CTA opens packs; a Free user's CTA exposes both
  subscriptions and packs without starting checkout.
- Loading, stale-focus refresh, completed-briefing refresh, and billing-update
  behavior have focused tests and a human mobile/desktop review.

### BRIEFING-UX-02: Admission errors use generic source copy and brittle text matching

**Status:** In progress

**Original gap**

The backend correctly rejects an unknown-duration source, a source longer than
the available balance, an account with no remaining time, and an account whose
debt block is active. However, the creation page introduces every error with
“Needs a better source” and “Try a public YouTube URL,” even when the source is
valid and billing is the real problem.

The frontend decides whether to show “Get more video time” by searching the
human-readable error sentence for particular phrases. One current mismatch is:

```text
Backend:  You have no remaining video time.
Frontend detector expects: no remaining credits
```

The normal workspace prevents most zero-balance submissions, but a stale or
unavailable client snapshot can still reach the authoritative server check and
then show the error without the billing CTA.

**Why this is bad**

- A valid source is blamed for an account problem.
- Users may retry the same URL instead of taking the action that resolves the
  failure.
- Changing copy can silently remove the correct CTA because behavior depends
  on fragments of English text.
- “Credits,” “video time,” “top up,” and “negative balance” are used
  inconsistently across the same journey.

**What should happen**

Each admission failure should have a truthful explanation and recovery:

| Condition | User-facing direction | Recovery |
| --- | --- | --- |
| Unsupported or unreadable source | Explain which public YouTube source is supported | Edit or replace the URL |
| Duration cannot be verified | Explain that Talven cannot safely calculate the required time | Try another source |
| Video exceeds available time | Show required duration and current available time | Add time or choose a shorter video |
| No time remains | State that the balance is zero | See plans and packs |
| Outstanding debt prevents work | Explain the amount that new time must repay first | Add time |

For example:

```text
This video needs 42 minutes, but 18 minutes are available.
Add video time or choose a shorter source.
```

**What we need to implement**

1. Return stable machine-readable admission codes, such as
   `source_duration_unknown`, `insufficient_video_time`, `no_video_time`, and
   `balance_blocked`, instead of classifying all of them only as
   `invalid_request`.
2. Include bounded structured details such as `required_seconds`,
   `available_seconds`, and `debt_seconds` when relevant. Continue computing
   these values on the server.
3. Add the error contract to the generated API schema/client and map each code
   to deliberate frontend copy and actions.
4. Remove billing behavior that depends on searching English error messages.
5. Render source-specific headings only for source failures. Billing failures
   should use headings such as “More video time needed” or “Briefing creation
   paused.”
6. Route billing CTAs through the plan-aware behavior in `BRIEFING-UX-01` and
   keep the editable URL or shorter-source recovery available where useful.

**Acceptance evidence**

- Every server admission code produces the intended heading, explanation, and
  action without inspecting message text.
- A longer-than-balance video displays both required and available time and is
  rejected before provider work begins.
- Zero balance and debt-block responses always include a working billing CTA.
- Source errors never advertise billing unless billing is independently the
  problem, and billing errors never say the source is invalid.
- Backend contract tests, generated-client drift checks, frontend presentation
  tests, and authenticated browser paths use the exact same error payloads.

### BRIEFING-UX-03: Provider-capacity failures suggest changing the source

**Status:** In progress

**Original gap**

Talven retries transient Groq and OpenRouter failures before failing the job.
If all provider attempts are exhausted because of a rate limit or temporary
capacity problem, the backend retains that distinction internally but exposes
the normal stage-level `transcription_failed` or `summary_failed` code. The
frontend therefore tells the user to try again, but may also recommend another,
shorter, or cleaner source.

**Why this is bad**

- The source is not the problem, so changing it may produce the same failure.
- Provider names and internal capacity details should not be exposed, but the
  user still needs reassurance that their source is valid.
- A generic stage failure cannot support deliberate retry timing or recovery
  copy without inspecting English error text.

**What should happen**

After transient provider attempts are exhausted, show neutral capacity copy:

```text
Talven is handling unusually high demand. Your source is fine.
Please try again in a few minutes.
```

The primary action should be **Try again** with the same source. Do not say
“too many users,” name Groq or OpenRouter, or recommend a different source
unless the source independently failed validation.

**What we need to implement**

1. Preserve a stable provider failure reason such as
   `provider_temporarily_unavailable` or `provider_capacity_reached` when the
   bounded provider attempts are exhausted.
2. Map that code ahead of generic transcription and summary failures in the
   frontend presentation layer.
3. Keep permanent invalid-response or evidence-contract failures mapped to
   their truthful stage-specific recovery instead of treating every provider
   failure as capacity.
4. Provide a same-source retry action without automatically resubmitting or
   starting another paid operation.

**Acceptance evidence**

- Simulated Groq and OpenRouter rate limits produce the neutral high-demand
  message without provider names or source-changing advice.
- Permanent transcript/summary failures retain their distinct copy.
- The retry action preserves the original source but requires an explicit user
  confirmation before starting a new briefing.

## 3. Watch processing and understand the states

### PROCESSING-UX-01: Session recovery treats quiet progress as an unhealthy stream

**Status:** In progress

**Original gap**

The session page receives progress through SSE, and the backend sends a
keepalive comment every 15 seconds so intermediaries do not leave an idle
connection silent indefinitely. The frontend records activity only when it
parses a meaningful status, content, or snapshot event; it does not record the
keepalive itself. If no meaningful event arrives for ten seconds, the browser
fetches another authoritative session snapshot even when the SSE transport is
healthy and the worker is simply still transcribing or drafting.

**Why this is bad**

- A legitimately quiet processing stage is confused with a broken connection.
- Healthy sessions make avoidable HTTP reads and database queries.
- The fallback consumes the ordinary read rate-limit bucket and scales with
  every open processing tab.
- Connection health and product-state progress are two different signals, but
  the current browser logic uses one timestamp for both.

**What should happen**

Use SSE events for state changes, keepalives for transport health, and an
authoritative snapshot only during initial load or recovery. For example, if
OpenRouter drafts for 45 seconds without changing the visible state, received
keepalives should prove that the stream remains connected without triggering
repeated snapshot requests. If no bytes or keepalives arrive for a bounded
stale period, such as 30 seconds, the browser should close the stale stream,
fetch one snapshot, reconnect with `Last-Event-ID`, and replay missed persisted
events. Continued reconnect failures should use bounded backoff rather than
aggressive permanent polling.

**What we need to implement**

1. Make the SSE reader report transport activity for every received chunk or
   keepalive, separately from meaningful state-event activity.
2. Replace the periodic quiet-state snapshot rule with a bounded transport-
   stale timer based on missed keepalives.
3. On transport staleness, abort the old stream, fetch one authoritative
   snapshot, and reconnect with the last valid event cursor.
4. Preserve the existing persisted-event replay, terminal-state handling,
   ownership checks, reconnect backoff, and visible reconnecting message.
5. Keep a much slower optional reconciliation only if staging evidence shows
   that a healthy transport can still miss state; do not add it by assumption.

**Acceptance evidence**

- A healthy quiet stream receives keepalives without issuing repeated snapshot
  requests.
- A dropped or stalled stream performs one recovery snapshot, reconnects with
  `Last-Event-ID`, and reaches the same final state without duplicated content.
- Invalid events, delayed keepalives, repeated disconnects, terminal events,
  and tab closure have focused deterministic tests.
- Staging evidence shows the expected stream-open, snapshot-read, reconnect,
  and HTTP `429` rates for one tab and the configured per-user/IP stream caps.

### PROCESSING-UX-02: Open SSE streams query for events every second

**Status:** In progress

**Original gap**

Each open processing stream queries persisted `job_events` once per second and
rebuilds an authoritative snapshot every ten seconds. These internal database
queries do not consume the browser-facing HTTP rate limit, but their number
grows with the number and duration of open processing streams.

**Why this is bad**

- Quiet jobs still produce repeated empty database queries.
- Concurrent users and tabs multiply the query load.
- A new event can wait almost one second even though Postgres already knows
  exactly when it was written.
- Each API replica repeats the work independently for its local streams.

**What should happen**

Keep SSE as the browser transport and `job_events` as the durable source of
truth, but make the backend event-driven. When an event is persisted, emit a
Postgres `NOTIFY` containing only the affected job or session identifier. One
supervised `LISTEN` connection per API replica receives that wake-up, coalesces
bursts, fetches the persisted events once for that job on that replica, and
fans them out to its matching authorized SSE streams. The worker and API remain
separate processes, so their Postgres listeners remain separate too.

This iteration should remain Postgres `LISTEN/NOTIFY` plus the existing SSE
browser contract. Do not introduce Redis, RabbitMQ, Supabase Realtime, or a new
WebSocket server as part of this improvement without separate measured need.

Notifications are only wake-up hints, not the event record. Preserve the
initial snapshot, durable `Last-Event-ID` replay, 15-second keepalives, terminal
handling, stream leases, authorization and tenant isolation. If the listener
disconnects or a notification is missed, reconnect it and use a slow bounded
30-to-60-second reconciliation query until notification delivery is healthy.

**What we need to implement**

1. Publish a dedicated job-event notification after each durable event write.
2. Add one supervised listener and replica-local stream coordinator per API
   process.
3. Coalesce notifications and fetch each affected job's persisted events once
   per API replica before local fan-out.
4. Replace the one-second per-stream event poll with notification wake-ups and
   a slow recovery-only reconciliation interval.
5. Preserve replay, keepalive, stream-cap, disconnect, authorization, and
   terminal-state behavior.

**Acceptance evidence**

- An idle open stream performs no one-second event queries.
- One event causes at most one durable-event fetch per affected job and API
  replica, even with several matching tabs.
- Event latency is equal to or better than the current polling path.
- Multi-user, multi-tab, and multi-replica tests prove isolation and local
  fan-out behavior.
- Listener disconnect, reconnect, missed-notification, burst, and slow-client
  tests prove that durable replay and safety reconciliation prevent data loss.
- Staging metrics show event-query volume, listener health, delivery latency,
  reconnects, and reconciliation fallback usage.

## 4. Read, export, and revisit a briefing

No improvement items have been recorded yet.

## 5. Submit the same source again

No improvement items have been recorded yet.

## 6. See access, buy time, and request a refund

### BILLING-UX-01: Checkout and refund confirmation repeatedly reload all billing data

**Status:** In progress

**Original gap**

After Polar redirects a successful checkout back to Talven, the billing page
checks every 2.5 seconds until a recent order appears, for at most 20 attempts.
After a pack refund is requested, it checks at the same interval until that
order becomes refunded, for at most 24 attempts. Each check calls the shared
billing loader, which requests plans, usage, and account data in parallel even
though the browser only needs to know whether one purchase or refund has
finished synchronizing.

The polling is bounded and exists for a valid reason: the browser can return
from checkout, or receive the initial refund response, before Polar's webhook
has updated Talven's authoritative billing records. However, the current loop
uses a fixed interval and repeatedly reloads more data than the confirmation
requires.

**Why this is bad**

- One logical status check creates three authenticated API reads and associated
  database work.
- Plans, which rarely change during a session, are re-requested every 2.5
  seconds while waiting for one order.
- A fixed interval checks just as aggressively near the end of the recovery
  window as it does immediately after the user returns.
- Checkout currently identifies success by searching for a recent order after
  a browser timestamp, which is less explicit than following one server-issued
  operation identifier.

**What should happen**

Treat each checkout or refund as one bounded billing-sync operation. The server
should issue an opaque identifier that belongs to the authenticated user. The
browser should check one small status resource for that operation immediately,
then with bounded exponential backoff, for example after 1, 2, 4, and 5
seconds, with 5 seconds as the cap. The response needs only a state such as
`pending`, `succeeded`, or `failed` and a safe failure code.

Polar's webhook remains the authority that completes the operation. When the
small status resource reports success, the browser should perform one full
billing refresh to display the new order, pack or subscription, and available
time. It should then stop checking. This remains bounded polling, rather than a
new billing SSE system, but it is targeted, progressively slower, and much
cheaper than repeatedly loading the complete billing page.

For example:

```text
Checkout returns with operation op_123
GET op_123 -> pending
wait 1 second
GET op_123 -> pending
wait 2 seconds
Polar webhook completes op_123
GET op_123 -> succeeded
GET the full billing snapshot once and stop
```

**What we need to implement**

1. Correlate checkout creation and refund requests with a server-issued opaque
   operation identifier. Reuse an existing provider/order identifier only if
   it can be exposed safely and checked strictly within the current user.
2. Add a narrow authenticated status endpoint that returns only the current
   user's operation state and bounded failure information.
3. Make Polar webhook processing and existing billing reconciliation update or
   resolve the same operation state idempotently.
4. Replace the fixed 2.5-second loops with a shared bounded backoff helper. Stop
   on success, failure, timeout, unmount, or user change, and avoid overlapping
   requests.
5. On success, load the full billing snapshot exactly once. Do not repeatedly
   reload plans while waiting.
6. Show accurate `syncing`, `completed`, `failed`, and `taking longer` copy. A
   timeout must not claim that a successful Polar payment or refund failed.

**Acceptance evidence**

- Each wait attempt makes one small authenticated status request rather than
  three full billing requests.
- Checkout and refund results are correlated to the exact current-user
  operation, including two purchases close together or activity in two tabs.
- Webhook-before-return, return-before-webhook, duplicate webhook, page reload,
  timeout, and failed-operation paths have focused tests.
- A successful operation triggers one authoritative usage/account refresh and
  shows the correct time and order state without a manual reload.
- Unknown, expired, or other-user operation identifiers reveal no billing
  information.

### BILLING-DOC-01: The workflow guide equates one billed minute with one second

**Status:** Needs human review

**Original gap**

The workflow guide says that one billed “minute” means one second of source
duration. The following sentence correctly says that a 30-minute video consumes
1,800 balance seconds, so the two statements contradict each other.

**Why this is bad**

- It can make readers think Talven charges 60 billed minutes for one minute of
  video.
- It obscures the otherwise simple rule that billing follows source duration.
- It mixes the user-facing unit, minutes, with the storage unit, seconds.

**What should happen**

The guide should say that one billed minute equals 60 seconds of source video.
It should explain separately that Talven stores balances and settlements in
seconds for accuracy. A 30-minute source therefore consumes 1,800 balance
seconds, which is exactly 30 billed minutes, regardless of processing time.

**What we need to implement**

1. Correct the billing-unit paragraph in `user-workflows.md` without changing
   the underlying billing behavior.
2. Keep the contrast with worker wall-clock time, model output, and browser
   activity.
3. Confirm that the surrounding examples and plan allowances use consistent
   minute, hour, and second conversions.

**Acceptance evidence**

- The guide never equates one minute with one second.
- A 30-minute source is consistently described as 30 billed minutes or 1,800
  balance seconds.
- The documentation remains aligned with settlement by source-duration seconds.

## 7. Recover from common failures

No improvement items have been recorded yet.

## 8. Post-implementation review — 2026-08-05 12:49 CEST

This section records the P1 and P2 findings from the first complete review of
the implementations above. They are review findings for the developer to
confirm against the current code, not assumptions that every concern is
automatically correct. P3 cleanup and future optimizations are intentionally
excluded from this merge gate.

The overall implementation direction is sound. No tenant-isolation regression,
billing-data exposure, or unnecessary Redis, RabbitMQ, Supabase Realtime, or
WebSocket architecture was found. The findings below should be resolved or
explicitly disproved before this work is merged.

### REVIEW-01: A billing operation read can make the bounded polling loop hang

**Severity:** P1

**Assessment:** Confirmed and resolved in code. Reads now have a five-second
timeout, share the operation abort signal, retry only transient HTTP failures,
and stop immediately on terminal failures.

`billingOperationSync.ts` bounds the delays between reads, but awaits
`loadOperation()` without a per-request timeout. `useBillingController.ts`
creates an `AbortController`, but does not pass its signal to the generated
client request for `GET /billing/operations/{operation_id}`.

- One stalled HTTP request can leave the UI in `syncing` indefinitely even
  though the delay schedule is bounded.
- Unmounting, changing user, or beginning a replacement operation cancels the
  waits but not the request already in flight.
- Every thrown error is treated as retryable, so terminal responses such as an
  invalid operation identifier or failed authorization can consume the entire
  retry window.

**What to verify or change**

1. Pass the operation-level abort signal to the HTTP request.
2. Give each read a bounded request timeout.
3. Retry only transient network, timeout, rate-limit, and appropriate server
   failures; stop on terminal authentication, authorization, validation, and
   not-found responses.

**Closure:** Tests prove that a hung read times out, unmount/replacement aborts
the active request, terminal responses stop immediately, and transient failures
retain the capped five-second backoff.

### REVIEW-02: Billing can claim that access was refreshed after refresh failed

**Severity:** P2

**Assessment:** Confirmed and resolved in code. Provider completion and local
snapshot freshness are separate states, and a failed snapshot refresh presents
an explicit retry without claiming that the visible balance is current.

After a billing operation becomes terminal, `startBillingOperationSync()` calls
`loadBilling(false, true)` but ignores its nullable result. It then marks the
operation `synced` or `failed`. The rendered copy says that access is updated
below or that billing details were refreshed below.

The provider operation may genuinely be complete while the authoritative
usage/account refresh has failed. In that case the message overstates what the
screen currently proves and can leave a stale balance or order state visible.

**What to verify or change**

Represent provider-operation completion and local snapshot-refresh completion
as separate results. If the operation is confirmed but refresh fails, say that
the payment or refund is confirmed but the latest account details could not be
loaded, and offer an explicit refresh action.

**Closure:** A successful refresh shows normal completed copy, while a failed
refresh never claims that the displayed access or billing details are current.

### REVIEW-03: The plan-aware top-up recommendation is not always authoritative

**Severity:** P2

**Assessment:** Partly confirmed. The swallowed plan lookup and stale
page-local CTA precedence were real and are resolved by failing the overview
read safely and using the shared usage snapshot alone. The cancellation premise
was not correct for Polar's scheduled-cancellation contract: access remains
`active` until period end and becomes `canceled` when it ends. The misleading
frontend label for an already canceled subscription was real and now says
“Canceled.”

Three paths need review together:

1. `_get_usage_overview()` catches every plan lookup exception and silently
   leaves `has_active_paid_subscription` false.
2. The homepage merges refreshed shared balance, debt, and blocked state, but
   chooses the billing CTA using its older page-local subscription value before
   the shared value.
3. The backend treats only `subscription_status == "active"` as paid, while the
   frontend describes `canceled` as “Cancels at period end.” If Polar preserves
   paid access through `period_end`, a canceled-but-still-entitled subscriber
   would be routed as a non-subscriber.

An existing subscriber can be shown subscription offers instead of the pack
top-up path, which is the opposite of the intended plan-aware UX.

**What to verify or change**

1. Do not silently turn an unknown plan lookup result into a definitive free
   state; log and expose an explicit unknown state or fail the request safely.
2. Use one authoritative shared usage snapshot for both the balance and paid-
   subscription CTA decision; remove redundant page-local usage state if it no
   longer has an independent purpose.
3. Verify Polar's real canceled-at-period-end semantics and classify current
   entitlement using status plus period dates rather than copy assumptions.

**Closure:** Focus refresh, cross-tab billing changes, checkout return,
cancellation at period end, and plan-lookup failure all produce deliberate,
tested CTAs.

### REVIEW-04: API readiness does not prove that event notifications work

**Severity:** P2

**Assessment:** Confirmed and resolved in code. Readiness requires the
notification function and trigger and reports event delivery as `healthy` or
`degraded`. Listener loss remains deliberately degraded rather than unready
because durable replay and fallback reconciliation preserve correctness. The
public status response now exposes only that coarse state; detailed per-replica
diagnostics remain available to operators in structured logs.

**Original review finding**

The API starts `JobEventCoordinator` but does not wait for its Postgres listener
to become healthy. The readiness schema check does not include the new
notification function/trigger, and `/meta/ready` does not inspect listener
health.

An instance can report ready while the intended event-driven delivery path is
unavailable. Processing still recovers through the slow safety path, but
operators cannot distinguish normal notification delivery from degraded mode.

**Implemented resolution**

`GET /meta/status` remains unauthenticated for hosting and support checks, but
its response is limited to status, version, uptime, and overall event-delivery
health. The application still captures active, queued, and in-flight jobs,
notification hints and overflows, refresh activity, failures, and fallback
reconciliation in the structured `api.status.snapshot` log entry. This keeps
the operational signal without publishing internal load patterns.

**Implemented and verified**

1. Notification-object readiness checks and the deliberate
   `healthy`/`degraded` behavior.
2. Unauthenticated health and status responses limited to status, version,
   uptime, and overall `healthy` or `degraded` event delivery.
3. Detailed event-delivery counters retained in structured logs and covered by
   an observability test.

**Closure:** An unauthenticated endpoint test proves that detailed workload and
delivery counters are not public; an observability or protected-endpoint test
proves that operators retain access to them; existing tests continue to prove
missing notification objects, listener startup failure, recovery, and the
chosen ready-versus-degraded behavior.

### REVIEW-05: Healthy SSE delivery still runs unconditional reconciliation

**Severity:** P2

**Assessment:** Confirmed and resolved in code. The periodic sweep runs only
while the listener is unhealthy, queue overflow emits a full-reconciliation
signal, and four bounded dispatchers prevent unrelated jobs from blocking one
another while preserving single-job serialization. Staging load evidence is
still required before this parent workflow item can leave **In progress**.

`JobEventCoordinator.start()` always starts the 45-second safety-reconciliation
task, and that task requests every locally subscribed job regardless of
`listener_healthy`. The dispatcher refreshes one job at a time. The Postgres
listener queue is bounded and drops a notification when full, relying on later
reconciliation for recovery.

- It deviates from PROCESSING-UX-02, which specifies recovery-only
  reconciliation while notification delivery is unhealthy.
- Healthy streams still create periodic event and snapshot work.
- One slow job refresh can delay unrelated jobs on the same API replica.
- Burst behavior has not been measured, so the 1,024-entry queue and serial
  dispatcher are assumptions rather than proven capacity decisions.

**What to verify or change**

Gate reconciliation on listener health, or document the permanent 45-second
sweep as an intentional measured safety trade-off. Preserve recovery from
missed or dropped notifications. If load evidence requires it, add bounded
per-job dispatcher concurrency without allowing duplicate refreshes for one
job.

**Closure:** A healthy listener performs no recovery sweep unless intentionally
documented; listener failure and queue overflow still converge from persisted
events; and a burst/load test measures latency, queue depth, dropped hints,
database reads, and several simultaneous jobs/tabs.

### REVIEW-06: Billing-operation correlation failures can pass silently

**Severity:** P2

**Assessment:** Confirmed and resolved in code. Checkout operation resolution
is an atomic database command that validates owner, type, transition, plan, and
order.
Missing or mismatched correlation is logged without rolling back a valid
authoritative billing transaction, and refund resolution verifies that matching
rows were returned. Timeout, read-failure, and manual-refresh paths now reload
the authoritative billing snapshot without claiming the individual operation
was confirmed.

**Original review finding**

Webhook processing updates `billing_sync_operations`, but the update helper
does not verify that it affected the expected row. Checkout resolution filters
the operation identifier and optionally the user, but does not assert the
expected operation type, pending state, or plan/order correlation.

If provider metadata is missing, stale, or inconsistent, authoritative billing
may update successfully while the browser operation remains pending. The
webhook can still return success, hiding the correlation failure until the UI
times out.

**Implemented resolution**

When the authoritative webhook transaction succeeds but operation metadata is
missing or mismatched, the operation correctly remains `pending`. After polling
times out or reading the operation fails, the browser now performs one full
authoritative refresh of plans, usage, subscription, packs, and orders. Manual
**Refresh status and billing details** makes one bounded operation read and then
performs the same full refresh, avoiding another long polling window. The notice
keeps operation confirmation and snapshot freshness separate, says when the
displayed details are current, and never encourages a duplicate payment or
refund request.

**Implemented and verified**

1. Atomic database validation and observable correlation-failure logging remain
   unchanged.
2. Timeout and read-failure outcomes each perform one authoritative full
   billing snapshot refresh without claiming operation confirmation.
3. **Refresh status and billing details** performs one operation check followed
   by the authoritative snapshot refresh even while the operation is pending.
4. Copy explicitly distinguishes delayed operation confirmation from current,
   refreshing, or unavailable billing details and never encourages duplicate
   payment.

**Closure:** Focused tests cover this sequence: the webhook applies billing,
correlation metadata is missing or mismatched, the operation remains pending,
and timeout or manual refresh still updates the authoritative billing snapshot
without offering a duplicate payment. Existing tests continue to cover normal
terminal operations, duplicate webhooks, already-terminal and nearby
operations, and observable correlation failures. The handler-level manual
refresh regression asserts exactly one operation read followed by exactly one
authoritative snapshot refresh.

### REVIEW-07: Generic transient provider failures are described as high demand

**Severity:** P2

**Assessment:** Confirmed and resolved in code. Explicit rate limits use the
capacity message and stable `provider_capacity_reached` code; network, timeout,
and provider 5xx failures use neutral temporary-unavailability copy; permanent
invalid outputs retain stage-specific failures.

`extract_job_error()` maps both explicit provider rate limits and every generic
transient provider failure to the same “Talven is handling unusually high
demand” message. Transient failures can also be timeouts, network/DNS errors, or
provider `5xx` responses.

The source-retry action is correct, but the explanation can claim a cause the
system does not know.

**What to verify or change**

- Use high-demand/capacity copy only for explicit rate-limit or capacity
  evidence.
- Use neutral temporarily-unavailable copy for other transient failures.
- Preserve stage-specific copy for permanent transcript, summary, validation,
  or evidence-contract failures.

**Closure:** Separate tests cover rate limits, timeouts, network errors, provider
`5xx`, and permanent invalid responses through the worker-to-browser contract.

### REVIEW-08: A video above the product duration cap receives misleading copy

**Severity:** P2

**Assessment:** Confirmed and resolved in code. Sources above the limit return
`source_too_long` with bounded `maximum_seconds` details and a truthful shorter-
source recovery message. The exact boundary remains accepted.

`validate_video_duration()` raises generic `invalid_request` when a source is
above `MAX_VIDEO_DURATION_SECONDS`. The frontend maps that code to “Source not
supported” and says Talven needs a readable public YouTube URL.

The URL may be public, readable, and otherwise fully supported; the actual
reason is that the video exceeds Talven's maximum supported duration.

**What to verify or change**

Add a stable code such as `source_too_long`, include a bounded
`maximum_seconds` detail, and show truthful maximum-duration copy with an action
to choose a shorter source.

**Closure:** A valid source exactly at the cap succeeds; a source above it shows
the duration-limit message and never suggests that its URL is unreadable.

### REVIEW-09: The register and statuses overstate the current implementation

**Severity:** P2 documentation and verification issue

**Assessment:** Confirmed and resolved for document semantics. Historical
sections are labeled **Original gap**, incomplete workflow items are **In
progress**, and **Needs human review** is reserved for items whose remaining
gate is genuinely human review. Missing external, browser, pgTAP, multi-replica,
and staging evidence remains visible rather than being treated as complete.

The register says each section describes “what happens now,” but those sections
still describe the original defects after implementation. It also defines
“Needs human review” as meaning automated checks are complete and only the real
desktop/mobile usability review remains. Important acceptance paths are still
missing, including:

- complete signed-in/signed-out auth routing for every product;
- a real duplicate-signup response through email transfer and preserved intent;
- focus, cross-tab, completed-briefing, and billing usage refreshes;
- worker error to browser presentation for provider failures;
- stale SSE to one snapshot to `Last-Event-ID` replay without duplication;
- billing webhook-before-return, return-before-webhook, reload, multiple tabs,
  failed refresh, and nearby operations;
- runtime pgTAP notification delivery and multi-replica/load behavior.

The document is misleading to a developer deciding whether an item is complete,
and “Needs human review” currently hides automated/integration work that still
remains.

**What to verify or change**

1. Rename the existing “What happens now” sections to “Original gap,” or add an
   explicit implemented-behavior section to each item.
2. Keep items with unresolved code findings or missing automated acceptance
   evidence as **In progress**.
3. Use **Needs human review** only when the documented automated evidence is
   complete, then use **Complete** after the required desktop/mobile review.

**Closure:** Every status matches its code, automated evidence, and human-review
state, and the current-behavior guide no longer contradicts this register.

## Closing an item

An item should move to **Complete** only after:

1. the current-behavior guide is updated to describe the new behavior;
2. focused tests cover the navigation, safety, and accessibility contract;
3. the complete path is exercised locally with new and existing users; and
4. the result passes a short human desktop and mobile review.
