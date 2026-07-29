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
