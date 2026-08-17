# Talven documentation

**Purpose:** Give the owner and developers one short, ordered path through the
product, system, launch, and roadmap.

**Authority:** current accepted product and repository behavior.

## Contents

- [Documentation map](#documentation-map)
- [Recommended paths](#recommended-paths)
- [How to interpret status](#how-to-interpret-status)
- [Documentation rules](#documentation-rules)

## Documentation map

The main guide has eight chapters. Each subject has one owner:

| Chapter | Owns | Does not own |
| --- | --- | --- |
| [01 Product](./01-product.md) | Current user experience and product rules | Implementation detail or future ideas |
| [02 Architecture](./02-architecture.md) | Components, responsibilities, data flow, and security boundaries | Provider comparisons or setup commands |
| [03 Processing and providers](./03-processing-and-providers.md) | Audio, transcription, briefing generation, limits, and provider decisions | Customer pricing or deployment |
| [04 Billing and money](./04-billing-and-money.md) | Plans, credits, checkout, settlement, refunds, and economics | Provider setup commands |
| [05 Development](./05-development.md) | Local setup, checks, migrations, and change workflow | Hosted operations |
| [06 Deployment and operations](./06-deployment-and-operations.md) | Environments, hosting, releases, monitoring, backup, and incidents | Product roadmap |
| [07 Launch plan](./07-launch-plan.md) | Scope freeze, launch gates, proof, and launch sequence | Post-launch feature design |
| [08 Roadmap](./08-roadmap.md) | Deferred work, triggers, and future feature order | Current behavior or launch proof |

The reference pages contain exact facts that do not belong in the main story:

- [API reference](./reference/api.md)
- [Configuration reference](./reference/configuration.md)
- [Data model reference](./reference/data-model.md)
- [Performance reference](./reference/performance.md)

## Recommended paths

### Owner path

Read end to end in this order:

1. [Product](./01-product.md)
2. [Architecture](./02-architecture.md)
3. [Data model reference](./reference/data-model.md)
4. [Processing and providers](./03-processing-and-providers.md)
5. [Billing and money](./04-billing-and-money.md)
6. [Performance reference](./reference/performance.md)
7. [Deployment and operations](./06-deployment-and-operations.md)
8. [Launch plan](./07-launch-plan.md)
9. [Roadmap](./08-roadmap.md)

This path explains what Talven is, what must stop before launch, what remains
open, and what comes after launch.

### Developer path

For implementation work, read:

1. [Architecture](./02-architecture.md)
2. [Data model reference](./reference/data-model.md)
3. [Processing and providers](./03-processing-and-providers.md)
4. [Development](./05-development.md)

Open a reference page only when the task needs exact routes, variables, tables,
pagination, cache, performance, or migration rules.

## How to interpret status

- **Current:** implemented and part of the accepted product behavior.
- **In progress:** being built or verified, but not part of the accepted
  product behavior yet.
- **Required before beta:** must be complete before external invite-only use.
- **Required before public launch:** may wait during private testing, but must
  be resolved before public signup or payment.
- **Deferred:** do not build until the named trigger occurs.
- **Proposed:** an idea that still needs an owner decision and evidence.

Code, migrations, tests, tracked configuration, and deployed provider settings
remain the executable sources of truth. Documentation explains them; it does
not replace them.

## Documentation rules

Keep this structure small:

1. Put current user behavior only in the product chapter.
2. Put launch blockers only in the launch chapter.
3. Put future work only in the roadmap.
4. Link to a reference instead of repeating exact tables, routes, or variables.
5. Label proposed behavior clearly.
6. Update the owning page when behavior changes.
7. Prefer short tables, lists, examples, and diagrams over long prose.

The root [README](../README.md) remains the short repository entry point.

## Next read

[Product](./01-product.md)
