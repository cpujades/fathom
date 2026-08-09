# Future billing options

This page records billing ideas that are deliberately outside the launch scope.
They should be reconsidered only after real customers show that the fixed
subscriptions and packs do not cover an important usage pattern.

## Launch contract

- Paid subscriptions are the best-value option for regular usage.
- Public one-time packs are available to any authenticated customer at a higher
  price per hour.
- Every pack purchase has its own balance and expires after 90 days. Buying a
  new pack does not extend an older purchase.
- Paid subscription time carries into one additional billing month only. The
  total subscription balance cannot exceed twice the monthly allowance.
- Free time resets without carryover.
- Products use tax-exclusive EUR, USD, and GBP prices. Polar selects EUR for
  euro customers, GBP for UK customers, and the default USD price elsewhere.

| Product | Allowance | EUR | USD | GBP |
| --- | ---: | ---: | ---: | ---: |
| Free | 1 hour/month | €0 | $0 | £0 |
| Starter | 6 hours/month | €9 | $10 | £8 |
| Pro | 15 hours/month | €19 | $22 | £17 |
| Agency | 50 hours/month | €49 | $56 | £42 |
| Trial Pack | 3 hours/90 days | €6 | $7 | £5.50 |
| Creator Pack | 10 hours/90 days | €18 | $21 | £16 |
| Studio Pack | 40 hours/90 days | €60 | $69 | £52 |

## Subscriber-only top-ups

Reconsider discounted subscriber top-ups after launch if customers regularly
run out of subscription time without being ready for the next plan.

Any subscriber price should remain more expensive per hour than the included
subscription allowance. Eligibility also needs to prevent a lower-plan
subscriber from using large discounted top-ups instead of upgrading.

## Custom prepaid packs

A customer-selected number of hours would be a configurable prepaid pack, not
true pay-as-you-go billing. It would require minimum and maximum purchases,
server-authoritative price calculations, refund rules, receipts, webhook
validation, and protection against price or credit manipulation.

Consider it only if fixed packs repeatedly fail to match real purchase sizes.

## Metered pay as you go

True pay as you go charges for the exact amount consumed. It introduces usage
meter reconciliation, failed-payment recovery, spending controls, invoices,
and customer disputes over measured usage.

Do not add it merely to increase pricing flexibility. Reconsider it when there
is evidence that meaningful customers reject both subscriptions and prepaid
packs, or when a high-volume business workflow needs postpaid billing.

## Evidence required before reconsideration

- Pack purchase frequency, size, consumption, and expiry rates.
- Subscription upgrades, downgrades, cancellations, and exhausted balances.
- Requests for custom purchase sizes or postpaid billing.
- Refund and support volume by billing product.
- Gross margin and payment-failure risk for the proposed option.
