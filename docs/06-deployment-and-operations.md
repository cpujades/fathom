# Deployment and operations

**Status:** Application hosting is unselected. Database release workflows exist;
hosted application proof does not.

**Read this to understand:** the required topology, environment separation,
first deployment, release flow, monitoring, backup, and incident response.

## Contents

- [Minimum topology](#minimum-topology)
- [Environment separation](#environment-separation)
- [Provider decision](#provider-decision)
- [Observability decision](#observability-decision)
- [First deployment order](#first-deployment-order)
- [Health and readiness](#health-and-readiness)
- [Release automation](#release-automation)
- [Migration safety](#migration-safety)
- [Operational review](#operational-review)
- [Incident start](#incident-start)
- [Public-launch operational minimum](#public-launch-operational-minimum)

## Minimum topology

Talven needs three independently running application processes:

| Process | Requirement |
| --- | --- |
| Web | Next.js application with public HTTPS URL |
| API | FastAPI service with public HTTPS URL, health checks, and webhook route |
| Worker | Continuous background process; it must not sleep when HTTP traffic stops |

The platform services are:

- Supabase Auth, Postgres, and Storage;
- Groq;
- OpenRouter;
- Polar;
- production SMTP;
- domain and DNS; and
- one central logs, metrics, and alert destination.

The web, API, and worker may share one hosting provider, but they remain
separate process types with separate scaling and health behavior.

## Environment separation

| Environment | Purpose | Database | Polar | Application traffic |
| --- | --- | --- | --- | --- |
| Local | Development | Local Supabase | Optional sandbox | Local processes |
| Pull-request CI | Deterministic proof | Disposable database | Fakes | Clean runners |
| Staging | Exact-candidate rehearsal | Dedicated hosted project | Sandbox | Hosted, gated |
| Production | Real users and money | Separate hosted project | Production | Hosted, public when opened |

Never copy a staging database, secret, webhook secret, or Polar product UUID
into production.

`APP_ENV` controls runtime safety:

- `local`: loopback URLs and disabled rate limiting may be allowed;
- `test`: deterministic test configuration;
- `staging`: exact HTTPS origins, positive rate limiting, hosted database, and
  strict URL checks;
- `production`: all staging rules plus `POLAR_SERVER=production`.

## Provider decision

**Status:** Open. The leading candidate for the first hosted beta is:

- Vercel for the Next.js web application;
- Railway for the FastAPI API and continuous worker;
- Supabase for Auth, Postgres, and Storage;
- Resend for transactional SMTP; and
- Grafana Cloud for operational telemetry.

This is a proposal, not an implementation fact. Confirm it with one staging
deployment and a dated cost estimate.

### Hosting shortlist

| Topology | Benefit | Main cost or risk | Use when |
| --- | --- | --- | --- |
| Vercel web + Railway API/worker | Native Next.js operations plus one host for both Python processes | Two application hosts and two deployment paths | Default candidate for the beta |
| Railway web/API/worker | Fewer providers and private networking between application services | Prove Next.js caching, image behavior, rollbacks, and total resource cost | Operational simplicity wins in staging |
| Cloudflare web + Railway API/worker | Edge delivery and a broad global network | Next.js uses the OpenNext adapter; the Python worker still needs another host | Measured edge latency or egress justifies the extra model |

Railway supports persistent services, separate build/start commands, private
service networking, and resource limits. Its cost is usage-based on top of the
selected plan. Vercel is a strong web host, but Talven's continuous Python
worker must not depend on an HTTP function staying alive. Cloudflare supports
Next.js through OpenNext; its documented compatibility gaps and runtime model
must pass the complete staging journey before selection.

Official decision sources:

- [Railway pricing](https://docs.railway.com/pricing),
  [private networking](https://docs.railway.com/networking/private-networking),
  and [build/start commands](https://docs.railway.com/builds/build-and-start-commands)
- [Vercel function duration](https://vercel.com/docs/functions/configuring-functions/duration)
- [Cloudflare Next.js guide](https://developers.cloudflare.com/workers/framework-guides/web-apps/nextjs/)
- [Supabase production checklist](https://supabase.com/docs/guides/deployment/going-into-prod),
  [database connections](https://supabase.com/docs/guides/database/connecting-to-postgres),
  and [backups](https://supabase.com/docs/guides/platform/backups)

### SMTP shortlist

| Provider | Benefit | Main cost or risk | Initial decision |
| --- | --- | --- | --- |
| Resend | Small API, direct Supabase guide, simple domain setup | Recheck quotas, deliverability, and pricing at selection time | Leading beta candidate |
| Amazon SES | Mature SMTP/API service and a likely low unit cost at volume | New accounts start in a regional sandbox and require more AWS operations | Keep as the scale or cost alternative |

For auth email, use a dedicated sending subdomain, configure SPF/DKIM/DMARC,
and test confirmation and recovery links with link scanners. Disable click
tracking for auth links when the provider recommends it.

Official decision sources:

- [Resend with Supabase](https://resend.com/docs/knowledge-base/getting-started-with-resend-and-supabase)
  and [auth-email deliverability](https://resend.com/docs/knowledge-base/how-do-i-maximize-deliverability-for-supabase-auth-emails)
- [Amazon SES production access](https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html)
  and [email sending methods](https://docs.aws.amazon.com/ses/latest/dg/send-email.html)

### Decision record

Before the first hosted beta, record for every selected provider:

- date and owner;
- staging evidence;
- expected workload and monthly cost envelope;
- deployment, rollback, logs, support, privacy, and regional behavior;
- hard quotas and account-verification requirements; and
- exit path.

Provider terms and prices change. Recheck their official pages on the decision
date.

## Observability decision

**Status:** Proposed. Grafana is not configured in the repository.

Grafana is the dashboard and alert destination. It does not create telemetry by
itself. The proposed beta path is:

    FastAPI and worker -> OpenTelemetry -> Grafana Cloud OTLP
    Next.js browser -> Web Vitals or Grafana Faro -> Grafana Cloud
    Host and Supabase signals -> Grafana Cloud integrations where available

Use Grafana Alloy or another OpenTelemetry Collector when production buffering,
retries, or routing are required. Direct OTLP is acceptable for the first
staging proof.

Keep product funnels separate from high-volume operational metrics. A product
analytics tool or warehouse is usually better for activation, retention, and
feature adoption. Grafana should own latency, errors, queue health, provider
stages, database health, and alerts.

Do not use user IDs, emails, video URLs, job IDs, or publication slugs as metric
labels. They create high-cardinality series and can expose private data. Use
redacted logs or sampled traces for request-level diagnosis.

Official implementation sources:

- [Grafana Cloud OTLP ingestion](https://grafana.com/docs/grafana-cloud/send-data/otlp/send-data-otlp/)
- [Grafana Frontend Observability](https://grafana.com/docs/grafana-cloud/monitor-applications/frontend-observability/introduction/)
- [Grafana Web Vitals](https://grafana.com/docs/grafana-cloud/monitor-applications/frontend-observability/instrument/web-vitals/)

The metric inventory and initial targets are in
[Performance reference](./reference/performance.md#measurement-and-targets).

## First deployment order

### 1. Select domains and topology

Define:

- public web origin;
- API origin;
- staging equivalents;
- process locations and replica ceilings;
- trusted ingress/proxy networks; and
- the owner of each provider account.

### 2. Create hosted service environments

Create separate staging and production:

- Supabase projects;
- Polar organizations or provider contexts;
- application secrets;
- webhook endpoints;
- SMTP configuration; and
- monitoring labels and alert routes.

### 3. Configure Supabase

Database migrations deploy schema and functions. They do not copy hosted Auth
Dashboard settings.

For each hosted project, configure:

- Site URL;
- allowed redirect URLs;
- email confirmation;
- password policy;
- Google OAuth when enabled;
- production SMTP;
- CAPTCHA or bot protection;
- Auth rate limits; and
- Storage backup/retention decisions.

Test a real confirmation email and password recovery link on the exact domain.

### 4. Configure application runtime

Set the variables in [Configuration reference](./reference/configuration.md).

Hosted API and worker requirements include:

- `APP_ENV`;
- exact CORS origins;
- positive rate limit;
- Supabase keys and direct Postgres connection;
- trusted proxy settings when required;
- provider secrets;
- Polar environment and return URLs;
- Explore operator IDs; and
- worker concurrency based on measured capacity.

The web build needs the final public API, Supabase, and site URLs.

### 5. Configure Polar

Use:

- separate sandbox and production access tokens;
- separate product IDs;
- separate webhook endpoints and secrets;
- exact HTTPS return URLs; and
- no webhook redirects.

Run the catalogue dry run before any live synchronization. Prove checkout,
portal, webhook replay, cancellation, tax, currency, and refund in staging
before the controlled production probe.

### 6. Add monitoring and alerts

Send structured application logs and provider/host metrics to one searchable
destination. Keep raw transcripts, briefing Markdown, tokens, signatures,
emails, and complete provider payloads out of logs.

Minimum urgent alerts:

- repeated API 5xx;
- growing or old job queue;
- exhausted worker retries;
- worker or API process restart loop;
- Postgres listener disconnect loop;
- database connection or pool exhaustion;
- repeated Groq/OpenRouter failures;
- stuck settlement or billing reconciliation;
- failed or old Polar webhook;
- PDF saturation;
- backup failure; and
- core frontend journey failure spike.

### 7. Enable and prove recovery

Enable:

- database backups;
- object backup or an explicit object-loss decision;
- application rollback;
- provider configuration recovery; and
- access to release artifacts and migrations.

Complete one restore before external users create important data. Record the
steps, result, recovery time, owner, and remaining gaps.

### 8. Deploy the exact candidate

Deploy the same immutable release to web, API, and worker. Apply only the
migrations included in that release. Record:

- release tag;
- commit;
- database migration result;
- application deployment IDs;
- configuration revision;
- provider destinations; and
- smoke-test evidence.

## Health and readiness

| Route | Purpose | Expected use |
| --- | --- | --- |
| `GET /meta/health` | Process liveness | Platform liveness probe |
| `GET /meta/ready` | Dependency and runtime readiness | Platform readiness probe |
| `GET /meta/status` | Coarse public version and event-delivery state | Safe operator or support check |

Liveness must remain cheap. Readiness may be rate-limited and should fail when
the process cannot safely serve traffic.

## Release automation

Current GitHub flow:

1. Pull requests run quality, generated-contract, database, commit, dependency,
   and security checks.
2. A merge to `main` calculates a semantic version from Conventional Commits,
   updates release artifacts, creates an annotated tag, and publishes a GitHub
   release.
3. Staging accepts an exact release tag and deploys changed Supabase migrations.
4. Production promotion requires an operator-selected exact release tag.

Important limitation: these workflows do not currently deploy the web, API, or
worker to an application host. Hosting automation must be added after the host
is selected.

Production must deploy the tested immutable release tag, not a moving branch.

## Migration safety

- Applied migrations are immutable.
- Staging and production use the same committed history.
- Pull-request CI starts clean and proves the complete history.
- A green disposable database test does not prove the hosted migration ran.
- Review the exact hosted migration output.
- Never reset a shared staging or production database.

`20260815130000_reset_and_harden_schema.sql` begins with a one-time `TRUNCATE`
of mutable application tables. It is acceptable only before the database has
external user data. The owner has accepted this reset for the current
pre-launch schema hardening. Before promoting this release:

1. confirm that the target contains no data that must survive;
2. export any required internal test evidence;
3. decide how to remove matching Auth, Storage, and Polar test resources;
4. apply the migration once; and
5. never reuse this reset approach after external access starts.

The migration comment refers to a guarded provider-resource reset script. No
such script exists in the current working tree. Provider cleanup is therefore
a separate operator action.

Current query, cache, and pagination checks are in
[Performance reference](./reference/performance.md).

## Operational review

### Daily during launch

- urgent alerts;
- oldest queued job;
- recent provider and billing failures;
- web/API/worker availability;
- signup, activation, and completion failures; and
- support requests.

### Weekly

- briefing completion and latency;
- Groq/OpenRouter success, retries, cost, and rate limits;
- cache hits and cold sources;
- queue and SSE health;
- database size, connections, slow queries, and egress;
- Polar orders, refunds, webhooks, and payouts;
- support themes; and
- acquisition, sharing, save, conversion, and retention.

### Monthly

- provider invoices versus telemetry;
- plan contribution;
- capacity and cost forecast;
- backup/restore evidence;
- access and secret review;
- roadmap triggers; and
- provider keep/change decisions.

Provider invoices and dashboards remain the billing and quota authority.
Talven telemetry explains which product behavior produced the usage.

## Incident start

For a job, begin with the privacy-safe timeline:

    PYTHONPATH=apps/backend ./.venv/bin/python \
      -m fathom.application.diagnostics.job_timeline SESSION_UUID

For a bounded system snapshot:

    PYTHONPATH=apps/backend ./.venv/bin/python \
      -m fathom.application.diagnostics.operability \
      --stale-minutes 5 \
      --sample-limit 20

These tools avoid private source URLs, transcript text, briefing content,
credentials, and full provider payloads.

## Incident rules

1. Identify the affected environment and release.
2. Preserve provider event IDs, job IDs, and timestamps.
3. Check authoritative state before changing anything.
4. Repair through existing idempotent commands.
5. Do not edit signed provider payloads.
6. Do not manually force a job or settlement state without proving ownership
   and billing consequences.
7. Stop retries or public access when continued work can increase harm.
8. Record cause, impact, recovery, and prevention.

Common authorities:

| Problem | First authority |
| --- | --- |
| Job not progressing | Job row, lease, event timeline, worker logs |
| Provider failure | Talven attempt logs plus provider request/event ID |
| Usage mismatch | Settlement, credit lots, entitlement snapshot, job |
| Refund pending | Billing operation, order, webhook, Polar |
| Subscription mismatch | Local order/customer state plus Polar |
| Public page unavailable | Publication visibility/moderation plus owner job and summary |
| Auth email failure | Supabase Auth logs, SMTP provider, callback allowlist |

## Public-launch operational minimum

Do not enable unattended public signup until:

- one operator receives urgent alerts;
- logs are searchable and redacted;
- queue, provider, billing, API, and database signals are visible;
- retention and access are defined;
- backup and restore are proved;
- rollback is proved;
- support and privacy requests have an owner; and
- the selected topology has a measured capacity envelope.

## Next read

[Launch plan](./07-launch-plan.md)
