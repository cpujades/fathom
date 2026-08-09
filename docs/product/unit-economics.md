# Unit economics and owner cash model

**Status:** Planning model, not booked financial results
**Last reviewed:** 2026-08-06

This page makes Talven's pricing arithmetic explicit. It separates customer
tax, Polar fees, provider costs, business contribution, autónomo costs, and
personal income-tax reserves. Recheck provider pricing, the Polar Dashboard,
the exchange rate, and Spanish tax treatment before relying on it for a launch
or tax filing.

The tracked plan catalog remains
[`scripts/polar/plan_contract.json`](../../scripts/polar/plan_contract.json).
The catalog amounts are base prices before applicable customer tax when Polar
uses tax-exclusive behavior.

## Terms that must not be mixed

- **Base price:** Talven's catalog amount, such as `$9.00` for Starter.
- **Customer tax:** VAT, GST, or sales tax calculated for the buyer's
  jurisdiction. Polar collects and remits it as Merchant of Record. It is not
  Talven revenue.
- **Customer checkout total:** base price plus applicable tax when pricing is
  tax-exclusive.
- **Polar transaction fee:** Early Member percentage and fixed fee, calculated
  on the complete customer checkout total, including tax.
- **Polar balance:** base price minus Polar's transaction fee. Customer tax is
  already excluded.
- **Business contribution:** Polar balance minus payout and direct processing
  costs, before fixed overhead, autónomo contributions, and IRPF.
- **Owner cash estimate:** business contribution minus the chosen fixed costs
  and a planning reserve for IRPF. It is not a tax return.

The original July/August planning calculation that produced `$7.44` for a
Spanish Starter sale treated `$9` as a VAT-inclusive customer total. That is
not the intended model. With tax-exclusive pricing, `$9` is the base price and
a Spanish customer pays `$10.89` before any discount.

## Polar Early Member contract

For the grandfathered organization:

| Transaction | US card | Non-US card |
| --- | ---: | ---: |
| One-time purchase | 4% + $0.40 | 5.5% + $0.40 |
| Recurring subscription | 4.5% + $0.40 | 6% + $0.40 |

The additions are 0.5% for a recurring payment and 1.5% for a non-US card.
Refunds do not return the original transaction fee. Upgrading the Polar
organization to a paid Polar pricing tier permanently retires Early Member
pricing, so do not upgrade without a fresh comparison.

Official references:

- [Polar Merchant of Record fees](https://polar.sh/docs/merchant-of-record/fees)
- [Polar tax-inclusive and tax-exclusive pricing](https://polar.sh/docs/features/tax-inclusive-pricing)
- [Polar balance](https://polar.sh/docs/features/finance/balance)
- [Polar payouts](https://polar.sh/docs/features/finance/payouts)

### Exact Starter example

For a `$9` Spanish Starter subscription paid with a non-US card:

```text
Base price                                      $9.0000
Spanish VAT, 21%                                $1.8900
Customer checkout total                        $10.8900

Polar base fee, 4% of $10.89                    $0.4356
Polar international-card fee, 1.5%             $0.1634
Polar recurring fee, 0.5%                      $0.0545
Polar fixed fee                                 $0.4000
Total Polar transaction fee                    $1.0534

Polar balance before payout                    $7.9466
Processing reserve, 6 hours x $0.06            $0.3600
Contribution before shared payout cost         $7.5866
```

Polar calculates the percentages on `$10.89`, not only on the `$9` base. A
Delaware customer using a US card would pay `$9`, incur about `$0.805` of
Polar fees, and leave about `$7.835` after the same processing reserve.

If the commercial target were literally `$9` after Polar, a Spanish Starter
base would need to be about `$10.14` before processing or `$10.52` after the
current processing reserve. The current `$9` price is intentionally retained;
this distinction exists only to make “receive $9” precise.

## Tax behavior and the catalog script

The owner has set the production organization's default tax behavior to
**Exclusive**. Products without a price-level override therefore inherit
exclusive behavior. No application change is required for that inheritance.

The current generator creates fixed USD prices with amount, currency, product
metadata, and monthly interval where applicable. It does not send
`tax_behavior`, so the Dashboard setting remains authoritative. Relevant Polar
fields that are intentionally absent or inherited are:

| Field | Current treatment | Decision |
| --- | --- | --- |
| `prices[].tax_behavior` | Explicitly `exclusive` for every localized price | Keeps the tax-exclusive base price reproducible even if the organization default changes later. |
| `visibility` | Omitted; Polar default applies | Review public/private behavior before production catalog sync; not a pricing calculation. |
| `recurring_interval_count` | Omitted; defaults to one | Correct for monthly plans. |
| `trial_interval` / `trial_interval_count` | Omitted | Talven owns Free and promotional credits; do not create a second trial system in Polar. |
| benefits/meters/seats | Omitted | Talven's credit ledger owns entitlement and usage. Add only for a deliberate billing-model migration. |
| media and custom checkout fields | Omitted | Marketing/extra-data features; avoid unnecessary checkout PII. |

Polar also supports price types such as custom, free, seat-based, and metered,
but Talven's fixed-price catalog should remain minimal. See the
[Create Product API](https://polar.sh/docs/api-reference/products/create-product)
and [Products guide](https://polar.sh/docs/features/products).

After any catalog or Dashboard change, prove one subscription and one pack in
sandbox and production. A Spanish `$9` exclusive checkout should report:

```text
net_amount   = 900
tax_amount   = 189
total_amount = 1089
tax_behavior = exclusive
```

Check each product for a price-level override because an override wins over the
organization default. EU-facing pages must still show the final tax-inclusive
total clearly before the buyer becomes bound.

## Per-plan economics

Assumptions:

- Spanish consumer, 21% VAT, non-US card;
- tax-exclusive catalog prices;
- Polar Early Member subscription fees;
- the complete monthly allowance is consumed; and
- direct processing reserve of `$0.06` per audio hour.

Payout fees, fixed infrastructure, gestor, autónomo, and IRPF are excluded from
this per-order table because they are shared monthly costs.

| Plan | Customer pays | Polar balance | Processing | Contribution | Contribution / base price |
| --- | ---: | ---: | ---: | ---: | ---: |
| Starter, $9 / 6h | $10.89 | $7.95 | $0.36 | **$7.59** | **84.3%** |
| Pro, $19 / 15h | $22.99 | $17.22 | $0.90 | **$16.32** | **85.9%** |
| Agency, $49 / 50h | $59.29 | $45.04 | $3.00 | **$42.04** | **85.8%** |

The paid subscription mix used below is 60% Starter, 30% Pro, and 10%
Agency. It averages `$16` of base sales and 13.1 included hours per subscriber.
The pack mix averages `$20` and 14.6 hours.

## Monthly scenario assumptions

- Exchange planning rate: `€1 = $1.14`.
- All sales are modeled as Spanish/non-US-card transactions. A geographic mix
  can produce lower customer tax and lower Polar card fees.
- Paying customers consume their entire allowance.
- A free active user consumes 0.25 audio hour/month. The current Free ceiling
  is one hour/month.
- Direct AI/processing reserve: `$0.06` per audio hour.
- Polar makes one payout per month.
- Payout estimate: 0.25% payout fee, 0.25% EU cross-border conversion, `$0.25`
  per payout, and `$2` per active-payout month. If no cross-border conversion
  applies, remove the second 0.25%.
- Infrastructure: **€80/month**, as an owner planning assumption.
- Gestor/accountant: **€70/month**.
- Eligible first-year autónomo reduced quota: **€88.64/month**.

“Paid conversion” means the share of monthly active users who purchase in that
month. The 60/30/10 plan mix applies only to subscribers, not to Free users.

## Zero-customer monthly floor

The public-production stack has a lower fixed floor than the €80 scenario
allowance. Using the same planning exchange rate, and assuming usage remains
inside both base plans:

| Item with no customers | Monthly cash |
| --- | ---: |
| Railway Pro minimum, including its first $20 of metered usage | $20 |
| Supabase Pro, including one Micro project through its compute credit | $25 |
| Resend Free, Polar Early Member, Groq, and OpenRouter with no usage | $0 |
| Domain, monthly equivalent of an annual renewal | about $1 |
| **Infrastructure cash floor** | **about $46 / €40** |
| Sensible infrastructure budget | **€50** |

Therefore “roughly €50 with no clients” is a sound owner budget, but it is not
the entire fixed cost of operating as a registered autónomo. If the owner is
already registered and eligible for the first-year reduced contribution:

```text
Infrastructure floor at the planning exchange rate     about €40.35
Gestor                                                     €70.00
Reduced autónomo contribution                              €88.64
Whole-business cash floor                                about €198.99/month

Using the rounded €50 infrastructure budget              €208.64/month
```

The exact card charge can differ because of vendor VAT treatment, exchange
rate/card spread, and the fact that a domain is usually paid annually. The €50
infrastructure budget is intended to absorb that small uncertainty; invoices
and the gestor remain authoritative for deductible/input-VAT treatment.

There is no Polar payout or transaction fee without a sale, and no IRPF on
nonexistent profit. Filing/accounting obligations and the autónomo contribution
can still continue while the activity is registered. The optional $10/month
Supabase custom domain would raise the infrastructure floor to about €49 before
the gestor and autónomo contribution; it is not needed for the first release.

Railway Hobby can reduce a private pre-launch environment to a $5 minimum, but
the production recommendation remains Pro for the commercial support/limits
boundary. Supabase Free also reduces pre-launch cash, but its 50 MB Storage
upload limit does not satisfy Talven's current 100,000,000-byte source contract.

## Detailed 5,000-MAU scenario

This scenario contains 500 subscribers, 150 pack purchasers, and 4,350 Free
active users: 650 payers, or 13% of MAU.

| Line | Formula | Result |
| --- | --- | ---: |
| Base sales | subscriptions + packs before customer tax | $11,000 |
| VAT collected on top | 21% of base sales; Polar remits it | $2,310 |
| Customer checkouts | base sales + VAT | $13,310 |
| Polar transaction fees | Early Member fees on checkout totals | -$1,040.45 |
| Approximate monthly payout | 0.5% of balance + $2.25 | -$52.05 |
| Received by business | after customer tax, Polar, and payout | **€8,690.79** |
| 9,827.5 processing hours | paid allowances + 0.25h per Free user | -€517.24 |
| Infrastructure | planning assumption | -€80.00 |
| Gestor | planning assumption | -€70.00 |
| First-year autónomo | eligible reduced quota | -€88.64 |
| Cash before final IRPF | not personal take-home yet | **€7,934.91** |

The `$2,310` VAT line is relevant because customers pay it and Polar processes
it, but it is not Talven revenue or an expense paid from the `$11,000` base.
It also increases the amount on which Polar's percentage fee is calculated.

The payout line is not a fee for every customer. Polar accumulates the balance
and charges withdrawal/payout fees when it sends money to the owner. One
monthly payout makes the fixed portion negligible. In this scenario, the
0.25% payout fee is about `$24.90`, the assumed 0.25% EU conversion is another
`$24.90`, and the monthly/per-payout fixed amount is `$2.25`.

## Owner-cash scenarios

The 3,000- and 5,000-subscriber rows hold paid conversion at 13% to expose the
otherwise hidden Free-user cost. They therefore imply about 23,077 and 38,462
MAU respectively. There are no pack purchasers in those two rows.

| Scenario | Paying users | Free active users | Base sales | Cash before IRPF | After 20% reserve | After 30% reserve | After 35% reserve |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 5,000 MAU / mixed 650 payers | 650 | 4,350 | $11,000 | €7,935 | €6,348 | €5,554 | €5,158 |
| 3,000 paying subscribers at 13% conversion | 3,000 | 20,077 | $48,000 | €35,233 | €28,186 | €24,663 | €22,901 |
| 5,000 paying subscribers at 13% conversion | 5,000 | 33,462 | $80,000 | €58,881 | €47,105 | €41,217 | €38,273 |

The corresponding owner cash margins, divided by base sales after converting
those base sales to euros, are:

| Scenario | 20% reserve | 25% reserve | 30% reserve | 35% reserve |
| --- | ---: | ---: | ---: | ---: |
| 5,000 MAU / mixed 650 payers | 65.8% | **61.7%** | 57.6% | 53.5% |
| 3,000 paying subscribers | 66.9% | 62.8% | **58.6%** | 54.4% |
| 5,000 paying subscribers | 67.1% | 62.9% | **58.7%** | 54.5% |

The previously quoted approximately `€5,914` used €100 infrastructure, €100
gestor, the €88.64 reduced quota, and a 25% reserve. Its margin against base
sales was about 61.3%. With the requested €80 infrastructure and €70 gestor,
the same 25% reserve produces `€5,951`, or a 61.7% planning margin.

The €80 assumption is plausible for the 5,000-MAU scenario only if measured
audio sizes and provider usage stay near the model. It is not capacity proof
for 3,000-5,000 paying subscribers and 44,000-74,000 audio hours/month. At that
scale, Supabase and Railway egress alone can exceed €80. Replacing €80 with an
observed €300-600 bill would reduce the high-volume margins by less than one
percentage point, but the capacity and reliability work would be material.

## Autónomo and IRPF treatment

The first-year row must use `€88.64`, not `€607`, when the owner qualifies for
the reduced first-registration quota. The approximately `€607` value is the
normal minimum monthly contribution for the highest 2026 net-income bracket;
it is useful for a later-year sensitivity, not the eligible first year.

The 20%, 25%, 30%, and 35% columns are **IRPF cash reserves**, not corporation
tax rates. An autónomo is a person subject to progressive IRPF. Modelo 130
normally asks for a quarterly payment equal to 20% of cumulative positive net
activity income, but that is a payment on account. The final annual bill also
depends on other salary/income, personal and family circumstances, deductions,
the autonomous-community scale, and how many months the activity operated.

At the high annual profits implied by these scenarios, treating 20% as the
final tax is likely optimistic. Use the 30-35% columns for downside liquidity
planning until a gestor models the owner's real annual return. Official
references:

- [AEAT Modelo 130 instructions](https://sede.agenciatributaria.gob.es/Sede/impuestos-tasas/impuesto-sobre-renta-personas-fisicas/modelo-130-irpf______esionales-estimacion-directa-fraccionado_/instrucciones.html)
- [Importass autónomo guide and reduced quota](https://portal.seg-social.gob.es/wps/wcm/connect/importass/importass_contenidos/colectivos/trabajo%20autonomo/guia)

## What to replace with measured data

Before paid launch, capture at least:

- checkout `net_amount`, `tax_amount`, `total_amount`, country, card surcharge,
  and Polar fee for representative subscription and pack orders;
- payout currency, actual payout fee, and whether cross-border conversion was
  charged;
- downloaded bytes and duration;
- Groq model, billed audio seconds, retries, and latency;
- OpenRouter model, input/output tokens, retries, and cost;
- cache-hit/cold-source status;
- Supabase and Railway egress per job;
- durable database and PDF bytes per briefing; and
- refunds, disputes, referral credits, and promotional-credit consumption.

The model is a decision aid until invoices and per-job telemetry can reconcile
those assumptions.
