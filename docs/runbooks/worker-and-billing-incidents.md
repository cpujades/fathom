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
