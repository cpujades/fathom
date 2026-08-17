# Billing and money

**Status:** Current product contract plus a dated planning model.

**Read this to understand:** what users buy, how time is charged, how Polar
becomes trusted local state, and what the business may retain.

## Contents

- [Billing model](#billing-model)
- [Current catalogue](#current-catalogue)
- [Plan files](#plan-files)
- [Checkout trust boundary](#checkout-trust-boundary)
- [Webhooks and reconciliation](#webhooks-and-reconciliation)
- [Usage admission and settlement](#usage-admission-and-settlement)
- [Debt and refunds](#debt)
- [Money terms](#money-terms)
- [Planning snapshot](#planning-snapshot)
- [Evidence required before paid launch](#evidence-required-before-paid-launch)

## Billing model

Talven sells source-video time:

- monthly subscriptions grant renewable time;
- one-time packs grant expiring time;
- usage is stored in seconds;
- one successful job creates one settlement; and
- processing speed does not change billed duration.

A 30-minute source consumes 1,800 seconds whether providers finish in five
minutes or 40 minutes.

## Current catalogue

`scripts/polar/plan_contract.json` is the tracked business contract.

| Offer | Type | Time | EUR | USD | GBP | Carryover or expiry |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Free | Monthly internal plan | 1 hour | €0 | $0 | £0 | Resets monthly |
| Starter | Subscription | 6 hours | €9 | $10 | £8 | Up to one extra monthly allowance |
| Pro | Subscription | 15 hours | €19 | $22 | £17 | Up to one extra monthly allowance |
| Agency | Subscription | 50 hours | €49 | $56 | £42 | Up to one extra monthly allowance |
| Trial Pack | One-time pack | 3 hours | €6 | $7 | £5.50 | 90 days |
| Creator Pack | One-time pack | 10 hours | €18 | $21 | £16 | 90 days |
| Studio Pack | One-time pack | 40 hours | €60 | $69 | £52 | 90 days |

Prices are base prices before applicable customer tax. Polar selects a
configured currency and adds tax under the current exclusive-tax contract.

Changing price, allowance, cadence, carryover, or expiry changes the product
promise. Add a new paid plan version. Do not silently rewrite an old version
that existing orders or subscriptions still reference.

## Plan files

| File | Owner |
| --- | --- |
| `scripts/polar/plan_contract.json` | Tracked plan names, versions, prices, and allowances |
| `scripts/polar/plans.json` | Ignored environment-specific Polar product IDs |
| `scripts/polar/plan_seed.json` | Ignored generator output |
| `scripts/polar/generate_polar_plans.py` | Validation and provider/database synchronization |
| `apps/web/app/content/pricing.ts` | Public presentation; tests keep it aligned |

Validate without changing providers:

    uv run python scripts/polar/generate_polar_plans.py --dry-run

Synchronize the sandbox deliberately:

    uv run python scripts/polar/generate_polar_plans.py --server sandbox

Production requires production credentials, production product IDs or no local
mapping file, a dry run, and explicit `--server production`. A live sync is
an operator action and never runs in pull-request CI.

## Checkout trust boundary

    User chooses a Talven plan UUID
      -> API loads the active Supabase plan
      -> API creates a Polar checkout
      -> browser visits Polar
      -> Polar sends a signed webhook
      -> Talven commits order and credit state
      -> browser reads Talven's local billing state

A browser return from checkout is not payment proof. It only proves that the
browser returned.

Talven trusts:

1. a verified Polar webhook; or
2. a bounded server-side reconciliation against Polar.

The browser never receives the Polar access token.

## Webhooks and reconciliation

Talven verifies the signature over the raw request body before parsing the
event. It records the provider event ID and applies a small idempotent database
transaction.

Important rules:

- repeated delivery of the same event and facts is safe;
- the same event ID with different facts is rejected;
- older events cannot overwrite newer provider state;
- unknown events are recorded as ignored;
- failed deliveries can be redelivered from Polar; and
- a bounded worker maintenance pass repairs missed or interrupted work.

The normal webhook is the immediate path. Reconciliation is the safety path.

## Usage admission and settlement

Admission and charging are separate:

### Admission

Before queueing, Talven checks:

- positive spendable balance;
- current block/debt state;
- no more than three billable jobs in progress; and
- the combined known duration of unsettled work against available
  subscription and pack time.

The database serializes admission and settlement for each user. Two
simultaneous requests cannot both pass a stale balance or pending-work
snapshot.

There is no upfront credit-lot reservation. Admission derives the committed
duration from queued and running jobs that have not settled. Credit remains
visible until successful settlement.

### Settlement

After a valid briefing exists, one atomic command:

1. consumes subscription credit;
2. consumes eligible pack credit;
3. records uncovered time as debt when required for safe finalization;
4. updates the fast entitlement snapshot; and
5. creates the unique `usage_settlements` record.

`usage_settlements` is both the unique charge and the immutable per-briefing
usage-history source. There is no separate `usage_ledger` table.

Replaying settlement returns the existing row. It cannot charge the same job
twice.

The billing page reads usage history in server-side pages of ten. It shows the
source title and the exact subscription, pack, and debt split. Archived jobs
keep their settlement entry but no longer link to a session.

## Debt

The default 600-second debt threshold is a settlement safety buffer for:

- credit that expires or is removed after job admission;
- a refund or reconciliation that changes available credit while work is in
  progress; or
- exceptional recovery when successful work must be finalized safely.

It is not extra advertised usage. A known source must fit the positive balance
at admission. New credit pays debt before it becomes spendable. Reaching the
threshold blocks new work.

Per-credit-lot reservations remain deferred. The current atomic pending-work
guard protects normal parallel submissions without moving credit before a job
succeeds.

## Refunds

Only purchased packs are refundable through the current product.

Starting a refund:

1. waits until the user has no active billable briefings;
2. marks the pack `refund_pending`;
3. removes its remaining seconds from spendable balance; and
4. creates a bounded user-scoped operation for status.

If Polar confirms the refund, the pack becomes `refunded`. If Polar
definitively rejects it, Talven reopens the pack. A timeout remains pending and
does not invite a duplicate refund request.

Refunds do not automatically return Polar's original transaction fee. The
provider's allowed refundable amount, including tax behavior, must be proved
with a taxable sandbox order.

## Money terms

Do not mix these amounts:

| Term | Meaning |
| --- | --- |
| Base price | Talven catalogue price before applicable customer tax |
| Customer tax | VAT, GST, or sales tax collected and remitted by Polar |
| Checkout total | Base price plus applicable tax |
| Polar fee | Percentage and fixed fee calculated under the provider contract |
| Polar balance | Base price after Polar's transaction fee |
| Business contribution | Polar balance minus payout and direct processing cost |
| Owner cash estimate | Contribution minus fixed costs and an IRPF reserve |

Customer tax is not Talven revenue. Contribution is not personal after-tax
income.

## Planning snapshot

**Date:** 2026-08-06.

**Purpose:** planning only. Replace it with provider invoices, telemetry, and
professional tax advice before relying on it.

Main assumptions:

- Spanish consumer and 21% VAT;
- tax-exclusive catalogue prices;
- Polar Early Member fee assumptions;
- complete allowance consumption;
- direct processing reserve of $0.06 per source-audio hour;
- €80 monthly infrastructure;
- €70 monthly gestor;
- €88.64 eligible first-year autónomo contribution; and
- €1 = $1.14 planning exchange rate.

Do not reuse an old contribution table after a price or provider-fee change.
Calculate each current offer from this sequence:

    base price
      - Polar transaction and payout fees
      - direct processing cost for the consumed source hours
      = contribution before fixed costs and personal tax

For example, the EUR Starter base price is EUR 9. A Spanish checkout with 21%
VAT is EUR 10.89 before any provider fees. The VAT portion is not Talven
revenue. At the planning reserve of $0.06 per source hour, complete use of its
six-hour allowance reserves $0.36 for processing. Replace both fee and cost
assumptions with measured production values before launch.

Illustrative 5,000-MAU scenario:

| Item | Planning result |
| --- | ---: |
| Paying users | 650 |
| Base sales | $11,000 |
| Cash before final IRPF reserve | about €7,935 |
| After 30% reserve | about €5,554 |
| After 35% reserve | about €5,158 |

This is not capacity proof and not a tax return. At that scale, real egress,
hosting, support, and provider usage can be materially different.

The zero-customer planning floor was:

- about €40 infrastructure;
- €70 gestor; and
- €88.64 reduced autónomo contribution;
- total about €199/month before personal tax effects.

Recheck eligibility, invoices, exchange rates, provider contracts, and Spanish
tax treatment.

## Evidence required before paid launch

Record:

- one taxable subscription checkout;
- one taxable pack checkout;
- `net_amount`, `tax_amount`, `total_amount`, and tax behavior;
- actual Polar transaction and payout fees;
- cancellation and portal behavior;
- one completed refund and the allowed refundable amount;
- duplicate and delayed webhook recovery;
- source hours and bytes;
- Groq billed seconds and cost;
- OpenRouter tokens and cost;
- cache hit or cold source;
- storage and egress; and
- contribution per completed briefing and per plan.

Use those measurements to replace the dated planning assumptions.

## Next read

[Performance reference](./reference/performance.md)
