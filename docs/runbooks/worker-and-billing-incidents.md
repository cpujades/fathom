# Worker And Billing Incidents

## Jobs stop progressing

1. Check `GET /meta/ready`.
2. Check worker logs.
   - Startup should log `Starting worker loop`.
   - Repeated listener failures should log `job_created listener failed, reconnecting`.
   - Stale recovery should log `worker stale-job sweep complete`.
3. Confirm the worker process is actually running on the platform and has restart-on-failure enabled.

## Refund stays `refund_pending`

1. Check worker logs for `billing maintenance pass`.
2. Inspect the corresponding `billing_orders` row and the latest `billing_webhook_events` row for that Polar order.
3. Compare the local order state against the provider order in Polar.
   - If Polar already shows a refunded amount, the next maintenance pass should converge the local row.

## Subscription state looks wrong

1. Check whether the relevant Polar webhook was delivered and processed.
2. Check worker logs for `billing maintenance pass`.
3. Compare the local entitlement state with the latest Polar subscription state.
4. If webhook delivery was delayed or duplicated, rely on reconciliation rather than manual local edits.

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
