# Worker And Billing Incidents

## Start with a bounded snapshot

From the repository root, with the backend environment configured:

```bash
PYTHONPATH=apps/backend ./.venv/bin/python \
  -m fathom.application.diagnostics.operability \
  --stale-minutes 5 \
  --sample-limit 20
```

This command opens a read-only database transaction and returns counts plus at
most 20 job, summary, or provider-event IDs. It never returns account IDs,
source URLs, transcript text, summary Markdown, credentials, or provider
payloads. Raising either bound above its documented maximum is rejected.

For one affected session, inspect its privacy-safe lifecycle:

```bash
PYTHONPATH=apps/backend ./.venv/bin/python \
  -m fathom.application.diagnostics.job_timeline SESSION_UUID
```

Capture the snapshot, the API `X-Request-Id`, and the relevant job, summary, or
provider-event ID in the incident notes. Never paste lease/generation tokens,
authorization headers, raw webhooks, transcripts, or briefing content.

## Jobs stop progressing

1. Check `GET /meta/ready`.
2. Run the bounded operability snapshot above.
3. Check worker logs for `worker.started`, `worker.job_listener.ready`,
   `worker.stale_job_sweep.completed`, lease-loss events, and the affected
   `job_id`.
4. Confirm exactly one intended worker pool is running.
5. Do not update a job row manually. Allow the expired lease to fence the old
   worker and let one normal worker sweep requeue it. Run the snapshot again
   after one sweep interval to prove convergence.

## Refund stays `refund_pending`

1. Check the bounded webhook counts and provider-event IDs.
2. Check worker logs for `billing.maintenance.completed`.
   A worker that logs `billing.maintenance.lease_not_acquired` skipped safely
   because another worker owns the distributed maintenance pass.
3. Inspect the corresponding `billing_orders` row and the latest
   `billing_webhook_events` row for that Polar order.
4. Compare the local order state against the provider order in Polar.
   - If Polar already shows a refunded amount, the next maintenance pass should converge the local row.
   - If Polar still shows `paid`, the maintenance pass reopens the pack through
     the transactional refund command; do not flip the order or lot manually.

## Subscription state looks wrong

1. Check whether the relevant Polar webhook was delivered and processed.
2. Check worker logs for `billing.maintenance.completed`.
3. Compare the local entitlement state with the latest Polar subscription state.
4. If webhook delivery was delayed or duplicated, rely on reconciliation rather than manual local edits.
   Reconciliation is applied through the same provider timestamp fence and
   resource lock as a normal webhook.

## Webhook replay

1. Record the provider event ID and current operability snapshot.
2. Prove duplicate/reordered delivery locally without a provider call:

   ```bash
   PYTHONPATH=apps/backend ./.venv/bin/python -m unittest \
     apps.backend.tests.test_billing_webhooks \
     apps.backend.tests.test_polar_webhook_integration
   ```

   The integration test is skipped when the local database role-test
   environment is not configured.
3. In staging, redeliver only the exact provider event from Polar. Do not build
   a new payload, edit the stored normalized facts, or reuse a signature.
4. Confirm `billing.webhook.resolved` for the same `provider_event_id`, then
   rerun the bounded snapshot. `already_processed` is a successful idempotent
   replay; a persistent `failed`/`deferred` result needs investigation.

## Settlement mismatch

1. `terminal_jobs_missing_settlement` should converge through the normal
   billing maintenance pass, which requeues the job into visible finalization.
2. A non-zero `settlement_balance_mismatches` count is an invariant violation,
   not a routine retry. Stop manual repair, preserve the IDs and logs, and
   investigate the settlement and linked ledger rows in a read-only
   transaction.
3. Never delete a settlement, change credit lots, flip
   `usage_settlement_required`, or manufacture ledger rows.

## One-pass reconciliation discipline

Use the existing worker recovery loop as the only repair path:

1. Save a before snapshot.
2. Run one intended worker for one stale-job sweep and one billing-maintenance
   interval.
   Multiple worker replicas are safe, but only the current distributed lease
   owner runs billing maintenance; the others skip that interval.
3. Stop or leave that worker running normally; do not launch repeated manual
   maintenance loops.
4. Save an after snapshot and compare counts and IDs.
5. Escalate non-convergent or invariant-mismatch cases. The diagnostic commands
   themselves are intentionally read-only.

## API vs worker vs provider

- `GET /meta/health` failing:
  - API problem.
- `GET /meta/health` passing, `GET /meta/ready` passing, but jobs do not move:
  - likely worker problem.
- API and worker look healthy, but billing state is stale:
  - webhook/provider/reconciliation problem.

## Job leases and summary ownership

- A worker may mutate a running job only while its job lease token is current
  and the lease has not expired.
- A `pending` summary has a live producer only when `generation_job_id` points
  to a `running` job, `generation_token` matches that job's current lease
  token, and `lease_expires_at` is still in the future.
- Draft, ready, and failed summary transitions are fenced by that generation
  token and the live job lease. An expired producer cannot keep writing.
- If the owner fails normally, the summary becomes `failed`. If the process
  crashes or loses its lease before cleanup, the row remains `pending` but is
  considered orphaned. The next valid producer atomically takes ownership,
  clears partial output, and retries using the stable summary ID.
- Only `ready` summaries with non-empty Markdown are cacheable. The lifecycle
  migration classifies a legacy non-empty row as `ready` only when a succeeded
  or archived job proves completion. Interrupted or orphaned non-empty drafts,
  plus empty or whitespace-only rows, become `failed`; jobs that previously
  exposed an empty summary as successful are marked failed with
  `legacy_empty_summary`.

## Usage settlement and finalization

- New jobs require exactly one `usage_settlements` row before terminal success.
  Its subscription, pack, and newly incurred debt components must add up to the
  job duration. Linked `usage_ledger` rows are unique per settlement and source.
- Settlement is post-processing, as before: admission does not reserve credit.
  Admission requires a positive balance and a known source duration must fit
  the current balance. Debt is only a finalization safety buffer for balance
  races or duration differences; it is not intentionally spendable usage.
  The command consumes subscription credit first, then eligible pack credit,
  then records uncovered duration as debt. Refund-pending packs remain excluded.
- Credit-lot mutations, debt, the entitlement snapshot, settlement audit row,
  and ledger rows commit in one transaction while the worker lease is current.
  Replaying the command returns the existing settlement without another charge.
- A job with a ready summary but incomplete settlement remains `finalizing`.
  Normal failures queue a short retry; an expired worker lease is reclaimed by
  the stale-job sweep. Billing maintenance also requeues any new terminal job
  whose required settlement is unexpectedly missing.
- Historical jobs and jobs created by a rolling old application instance are
  explicitly settlement-exempt because charging them again cannot be proven
  safe. Old workers cannot claim new settlement-required jobs. Do not flip that
  flag manually. Reconcile a suspected legacy discrepancy from provider,
  ledger, and entitlement evidence.
