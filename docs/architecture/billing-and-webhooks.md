# Billing and Polar webhooks

Polar is the commerce provider; Supabase is Talven’s local billing state and
usage ledger. The browser starts checkout and displays local state, but only a
verified provider event or a bounded reconciliation pass changes local billing
records.

For the owner setup path across tests, local sandbox, staging, and production,
including product mapping and the exact evidence each environment can provide,
see [Polar environments and testing](../runbooks/polar-environments-and-testing.md).

## Plan and identity mapping

Polar calls an offer a product; Talven stores a versioned plan. A checkout
starts with Talven's `plans.id`, resolves that row's environment-specific
`polar_product_id`, and sends the signed-in Supabase user UUID as
`external_customer_id`. That user UUID is the join between the provider event
and Talven's local billing owner. Sandbox and production use different Polar
product UUIDs for the same Talven plan code and version.

A checkout return page is not payment evidence. It only says the browser came
back. The verified webhook or reconciliation path below must commit the local
order and entitlement before the application treats payment as settled.

## Inbound webhook path

```mermaid
sequenceDiagram
    participant P as Polar
    participant A as POST /webhooks/polar
    participant V as Signature verifier
    participant D as apply_polar_webhook_event RPC
    participant DB as Billing tables

    P->>A: Raw JSON body + webhook headers
    A->>V: Verify body, id, timestamp, signature
    V-->>A: Event id, type, provider facts
    A->>D: Normalized event + provider event time
    D->>DB: Deduplicate, order, apply in one transaction
    D-->>A: processed / already_processed / deferred / failed
    A-->>P: 200 only when the transaction resolved
```

1. The router reads the raw request body. It does not use a user bearer token.
2. `services/polar.py` verifies the signature and timestamp with a five-minute
   tolerance, then parses the event ID and type.
3. The application extracts a provider event time, preferring the event’s own
   timestamp, then provider resource timestamps, then the signed webhook
   timestamp. This timestamp is used to reject stale reordered snapshots.
4. The application normalizes only the facts the database needs. New stored
   payloads remove the top-level email field and do not retain the raw provider
   body as an audit dump.
5. The service-role RPC `apply_polar_webhook_event` records the event and applies
   all local effects transactionally.

Talven applies `customer.created`, `customer.state_changed`, `order.paid`,
`order.refunded`, `subscription.created`, `subscription.active`,
`subscription.uncanceled`, `subscription.canceled`, `subscription.past_due`,
`subscription.updated`, and `subscription.revoked`. Unknown events are recorded
as ignored rather than allowed to mutate billing.

## Idempotency and ordering

`billing_webhook_events.event_id` is the deduplication key. The RPC also takes
an advisory transaction lock for the resource and verifies that a reused event
ID has not been presented with different facts.

The result has four important resolutions:

| Resolution | Meaning | Provider retry? |
| --- | --- | --- |
| `processed` | Event applied or safely ignored | No |
| `already_processed` | Same event was already applied | No; this is a successful replay |
| `deferred` | Usually a refund arrived before its order; the event remains recorded for a later matching order event or exact replay | No retry is required from Polar; Talven returns success and resolves it when the order exists |
| `failed` | Transaction rolled back and the event is diagnosable | Yes after investigation |

Customer and subscription snapshots use `(provider_event_at, event_id)` as a
deterministic ordering fence. A late older event cannot move a current
subscription backward. Orders, refunds, credit lots, and entitlement snapshots
are locked and updated in one transaction.

For `order.paid`, Talven resolves the plan by Polar product ID, upserts the
order, creates a pack credit lot once, pays down debt from newly granted credit,
and refreshes the entitlement snapshot. For `order.refunded`, Talven locks the
order, clamps the refunded amount to the paid amount, revokes remaining pack
credit when the pack becomes refunded, and refreshes spendable balance.

## Refund and subscription repair

The worker runs one supervised billing-maintenance pass every 60 seconds. The
tick is only an opportunity to find due work; it does not call Polar for every
account every minute. A distributed `billing-recovery` lease allows one worker
to run the pass at a time for 120 seconds, renewed every 30 seconds.

Each pass:

- requeues new jobs that unexpectedly lack required usage settlement;
- marks webhook rows stuck in `processing` for more than five minutes as
  retryable failures;
- checks refund-pending orders after a 60-second grace period, up to 100 per
  pass;
- checks due non-terminal subscriptions, up to 20 per pass; and
- records diagnostic counts for received, deferred, failed, and stale events.

Healthy subscriptions are scheduled for another audit at most every six hours.
Provider-audit failures retry after 15 minutes. Terminal subscription states
are removed from future polling. Webhooks remain the fast path; reconciliation
is the repair path for missed, delayed, or ambiguous delivery.

## Local and staging use

Free briefing processing does not need a paid checkout. To exercise billing,
sync the catalog from `scripts/polar/plan_contract.json`, use Polar sandbox,
configure the matching `POLAR_WEBHOOK_SECRET`, and expose the local endpoint
through a deliberate HTTPS tunnel or redeliver an exact sandbox event in a
controlled environment. Never point a sandbox webhook at production data.

The [worker and billing incident runbook](../runbooks/worker-and-billing-incidents.md)
explains safe replay and diagnosis. Do not edit billing rows manually: preserve
the event ID and let the transactional command or maintenance pass converge
the state.

## Proof boundary

Unit tests and fake-provider journeys prove Talven's branching and error
behavior. Disposable database tests prove transactional, idempotency, ordering,
and concurrency rules. Neither proves the Polar Dashboard, a real checkout,
signed network delivery, portal behavior, or taxable refunds. Those require the
bounded sandbox rehearsal in the provider runbook before paid launch.
