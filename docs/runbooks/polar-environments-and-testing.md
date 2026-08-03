# Polar environments and testing

This page explains which Polar system Talven uses locally, in automated tests,
in staging, and in production. Polar handles checkout, the hosted customer
portal, and payment events. Supabase remains Talven's own billing ledger and
the source the product UI reads.

## The four billing contexts

| Context | Polar connection | Money or provider calls? | Main purpose |
| --- | --- | --- | --- |
| Unit and browser tests | Fakes and saved fixtures | No | Prove Talven request, error, UI, and recovery behavior |
| Local development | Usually Polar sandbox | Test payments only, when deliberately exercised | Develop the full checkout/webhook journey |
| Hosted staging | Polar sandbox | Test payments only | Prove the exact hosted domains, secrets, webhooks, and portal |
| Production | Polar production | Real payments | Serve paying users |

Free briefing processing does not require Polar checkout. Talven's internal
free plan is enough. Connect the sandbox only when testing billing.

Polar sandbox and production are separate systems. They have separate tokens,
products, product UUIDs, customers, orders, webhook endpoints, and webhook
secrets. A sandbox product UUID or secret must never be copied into production.

## Talven plans and Polar products

Polar calls a purchasable offer a **product**. Talven calls its versioned local
catalog entry a **plan**.

Example:

| Field | Local/staging example | Production example |
| --- | --- | --- |
| Talven `plan_code` | `creator_pack` | `creator_pack` |
| Talven `version` | `1` | `1` |
| Supabase `plans.id` | `11111111-1111-1111-1111-111111111111` | `22222222-2222-2222-2222-222222222222` |
| `plans.polar_product_id` | sandbox product UUID | different production product UUID |

The tracked, non-secret business definition is
`scripts/polar/plan_contract.json`. It defines plan codes, versions, type,
price, allowance, and display behavior. The ignored
`scripts/polar/plans.json` may override only environment-specific Polar product
IDs; it must not become a second business contract.

If price or billing cadence changes materially, create a new plan version and
map it to the corresponding Polar product. Do not edit only Polar and leave the
tracked contract stale. `--deactivate-missing` deactivates missing Talven plan
versions; it does not archive the provider product for you.

## What happens during checkout

```text
Signed-in user chooses a Talven plan UUID
  -> backend loads that plan from Supabase
  -> backend resolves its environment-specific Polar product UUID
  -> backend asks Polar for a checkout URL
  -> browser visits Polar's hosted checkout
  -> Polar sends a signed webhook to Talven
  -> Talven commits the order and entitlement in Supabase
  -> browser reads the resulting local billing state
```

The backend sends the Supabase user UUID as Polar's
`external_customer_id`. For example, user
`aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa` remains the same identity in Talven's
customer, order, subscription, and webhook processing. The Polar access token
never enters the browser.

A successful browser redirect means only that the browser returned from
checkout. It is not proof that Talven recorded payment. The signed webhook, or
a bounded provider reconciliation, must update the local ledger.

The portal endpoint similarly creates a short-lived Polar customer-session URL
on the server. The browser receives only that URL, not the organization token.
Portal changes return to Talven through webhooks and reconciliation.

## Local sandbox setup

1. Create or sign in to the [Polar sandbox](https://sandbox.polar.sh).
2. Create a sandbox organization access token. Keep it in the backend `.env`
   as `POLAR_ACCESS_TOKEN`; never add it to a frontend variable or commit it.
3. Set `POLAR_SERVER=sandbox`.
4. Preview the catalog operation:

   ```bash
   uv run python scripts/polar/generate_polar_plans.py --dry-run
   ```

5. Create or update the sandbox products and local plan mappings:

   ```bash
   uv run python scripts/polar/generate_polar_plans.py --server sandbox
   ```

6. Start the API on `http://localhost:8080`.
7. Use Polar's CLI listener or a deliberate HTTPS tunnel to forward webhook
   delivery to `http://localhost:8080/webhooks/polar`. Put the exact signing
   secret produced for that endpoint in `POLAR_WEBHOOK_SECRET`.
8. Complete a sandbox checkout with Polar's documented test payment details.
9. Verify the return route, one local `billing_orders` row, the expected credit
   or subscription entitlement, portal access, cancellation, and refund.

The webhook secret belongs to one endpoint in one Polar environment. If the
endpoint or environment changes, update the backend secret to match it. Never
point a sandbox webhook at production data.

## Webhook delivery and diagnosis

Configure the final API URL directly; Polar does not follow webhook redirects.
Talven verifies the signature over the raw body before parsing the event. It
then applies a small idempotent database transaction before returning success.

Talven applies these event types:

- `customer.created` and `customer.state_changed`
- `order.paid` and `order.refunded`
- `subscription.created`, `subscription.active`, `subscription.uncanceled`,
  `subscription.canceled`, `subscription.past_due`, `subscription.updated`,
  and `subscription.revoked`

Unknown events are recorded as ignored and do not mutate billing. A repeated
event ID with the same facts is safe. A reused ID with different facts is
rejected.

Polar retries failed deliveries with exponential backoff. Its delivery history
is the first place to inspect an incident: check the final URL, status code,
timeout, signature secret, whether the endpoint was disabled, and the exact
stored event. Fix reachability or configuration first, then redeliver that
exact event. Do not reconstruct or edit a signed payload.

## What each test layer proves

| Evidence | Proves | Does not prove |
| --- | --- | --- |
| Backend/frontend tests | Request construction, signature rejection, normalization, errors, and UI behavior | Real Polar connectivity or Dashboard settings |
| Disposable Supabase/pgTAP CI | Atomic orders, credits, idempotency, event ordering, and concurrency | Webhook delivery from Polar |
| Local fake-provider journey | End-to-end Talven behavior without a live provider | Sandbox checkout, portal, or signed delivery |
| Polar sandbox rehearsal | Real checkout, portal, signature, replay, cancellation, and refund behavior | Production domains and production secrets |
| Exact production-candidate probe | Production URL, token, endpoint, and observability configuration | Ongoing incident detection after launch |

## Required sandbox evidence before paid launch

Record evidence for the exact release candidate, not just an earlier local
build:

- checkout succeeds and returns to the exact staging origin;
- the signed event reaches the exact final webhook URL without a redirect;
- duplicate delivery is harmless and a temporarily failed delivery recovers;
- the portal opens for the same Supabase user and reflects cancellation;
- a refund updates both Polar and Talven once;
- the webhook transaction responds comfortably within Polar's delivery limit;
- secrets, product UUIDs, and callback URLs all belong to the same sandbox; and
- logs identify the provider event and local outcome without recording tokens,
  signatures, email addresses, or the full raw payload.

Two current provider-contract details need explicit sandbox proof:

1. For a taxable order, verify whether Polar's `total_amount` and `net_amount`
   fields include tax, and confirm Talven sends the provider's allowed
   refundable amount. Do not assume a tax-free fixture proves this.
2. Talven currently creates checkout server-side without forwarding the user's
   IP address. Verify the country/currency/tax experience from representative
   locations and record whether the behavior is acceptable before launch.

These are evidence requirements, not claims that the current code is wrong.
They remain open until a real sandbox order proves the contract.

## Moving to production

Create a separate production organization token, products, product mappings,
and webhook endpoint. Set `POLAR_SERVER=production`, use only production
product UUIDs, and configure exact HTTPS success/return URLs. Use a distinct
catalog-administration token for product synchronization where practical, so
the long-lived application token does not need product-writing authority.

Run the sandbox proof first. Then repeat a small exact-domain production probe
with approved monitoring and support ownership. Never test production delivery
against a staging or local database.

## Official Polar references

- [Organization access tokens](https://polar.sh/docs/integrate/oat)
- [Sandbox and test payments](https://polar.sh/docs/integrate/sandbox)
- [Products](https://polar.sh/docs/features/products)
- [Checkout sessions](https://polar.sh/docs/features/checkout/session)
- [Webhook endpoint setup](https://polar.sh/docs/integrate/webhooks/endpoints)
- [Webhook events](https://polar.sh/docs/integrate/webhooks/events)
- [Webhook delivery, retry, and redelivery](https://polar.sh/docs/integrate/webhooks/delivery)
- [Customer portal](https://polar.sh/docs/features/customer-portal/introduction)
- [Refunds](https://polar.sh/docs/features/refunds)

For Talven's transaction and recovery design, continue with
[Billing and Polar webhooks](../architecture/billing-and-webhooks.md). For the
variables, see [Environment configuration](../reference/environment.md).
