# First deployment checklist

**Status:** Required later; no application deployment exists yet
**Last reviewed:** 2026-08-03

Use this page only after the code candidate is accepted and a host is being
chosen. It records the work that is intentionally not configured while Talven
runs locally, so “not deployed yet” does not turn into “forgotten at launch.”

## The smallest correct topology

Run three application processes from the same release revision:

| Process | What it does | Must stay running? |
| --- | --- | --- |
| Next.js web | Public pages, sign-in UI, authenticated workspace | Yes |
| FastAPI API | Authenticated HTTP, SSE, billing, PDFs, Polar webhook | Yes |
| Worker | Claims durable jobs and calls YouTube, Groq, and OpenRouter | Yes; do not use a request-only or scale-to-zero function |

Supabase continues to provide Auth, Postgres, and initially private Storage.
The worker's queue is the Postgres `jobs` table; it does not need Redis. The
worker listens for `job_available` notifications and uses database-calculated
retry timers, so a healthy idle worker does not poll for jobs.

Example: commit `abc123` should build all three processes. Do not deploy web
from `abc123`, API from `def456`, and worker from `789xyz`; mixed contracts make
failures difficult to reproduce.

## Terms that sound more complicated than they are

- **Ingress:** the public front door in front of the API. It accepts HTTPS and
  forwards safe requests to FastAPI. Your hosting platform normally provides
  it.
- **Proxy:** another name for that forwarding layer. Talven must trust forwarded
  client-IP headers only from the actual proxy network.
- **WAF (web application firewall):** an optional filter at the front door that
  blocks obvious abusive traffic. It complements application validation; it
  does not replace authentication, webhook signatures, RLS, or rate limits.

Example: a caller sends `X-Forwarded-For: 1.2.3.4`. If the request came from the
configured hosting proxy, the API may use `1.2.3.4` for rate limiting. If it
came directly from the internet, trusting that header would let an attacker
invent a new IP for every request.

## Order of work

### 1. Create staging first

- Deploy the three processes from one exact commit.
- Use staging/sandbox Supabase, Polar, Groq, and OpenRouter credentials.
- Apply migrations before routing product traffic.
- Verify the hosted migration history matches that exact release; do not treat
  passing local/CI migration tests as proof that the hosted database received
  them. After the migrations are applied, inspect the project's Supabase
  Security Advisor and resolve or explicitly record every RLS, table-privilege,
  exposed-schema, and function warning before enabling external traffic.
- Keep production data and secrets out of staging.
- Record build commands, start commands, CPU/memory limits, and rollback steps.

### 2. Set exact origins and HTTPS

Replace these example domains with the chosen domains:

```dotenv
# Web build
NEXT_PUBLIC_SITE_URL=https://app.example.com
NEXT_PUBLIC_API_BASE_URL=https://api.example.com
NEXT_PUBLIC_SUPABASE_URL=https://project.supabase.co

# API
APP_ENV=staging
CORS_ALLOW_ORIGINS=https://app.example.com
TRUST_PROXY_HEADERS=true
TRUSTED_PROXY_NETWORKS=<only-the-hosting-proxy-network>
POLAR_SUCCESS_URL=https://app.example.com/app/billing
POLAR_CHECKOUT_RETURN_URL=https://app.example.com/app/billing
POLAR_PORTAL_RETURN_URL=https://app.example.com/app/account
```

A hosted production build fails when `NEXT_PUBLIC_SITE_URL` is missing. This
prevents password-reset links, Auth callbacks, and canonical metadata from
silently pointing to `localhost` or an unrelated domain.

Verify in a browser that:

1. the web page is HTTPS;
2. API requests go only to the API HTTPS origin;
3. sign-up, confirmation, sign-in, sign-out, and password recovery return to
   the exact web origin; and
4. an unapproved origin receives no credentialed CORS response.

### 3. Configure public signup honestly

Talven does not have an invitation allowlist. Anyone who finds the public URL
may sign up. Before publishing that URL:

- require email confirmation;
- configure production SMTP and test real delivery;
- configure Supabase bot/CAPTCHA and email-rate protections;
- verify the hosted password policy matches the UI;
- publish support, privacy, and terms paths; and
- test abuse limits with multiple effective client IPs.

### 4. Configure the Polar webhook front door

The webhook endpoint is `POST https://api.example.com/webhooks/polar`.
Ordinary API rate limiting does not apply because legitimate provider bursts
must not be dropped. Safety instead comes from:

- HTTPS;
- the bounded request-body middleware;
- Polar signature verification before business logic;
- transactional event idempotency and ordering; and
- edge connection/body limits that still allow legitimate Polar requests.

Do not create a WAF rule that challenges the webhook with a browser CAPTCHA.
Do not accept a webhook merely because it comes from a familiar IP; the valid
signature is the authority. Send a sandbox event, replay the same event, send
an invalid signature, and confirm respectively: one state change, no duplicate
state change, and rejection.

### 5. Send logs somewhere and create alerts

Talven emits stable event names plus small context fields. The fields are not
decoration; each answers a specific incident question:

| Field | Question it answers |
| --- | --- |
| `event` | What lifecycle action happened? |
| `request_id` | Which API lines belong to one request? |
| `job_id` / `session_id` | Which briefing failed or recovered? |
| `status_code` / `error_code` / `error_type` | Was it a user error, dependency error, or server defect? |
| `duration_ms` / stage elapsed time | Where did the request or job become slow? |
| `attempt` / retry delay | Is a dependency recovering or stuck? |
| lease/requeue counts | Did a crashed worker's work recover safely? |

User IDs, URLs, emails, tokens, cookies, transcript text, summary Markdown,
payloads, and embedded credentials are redacted or excluded. Do not add them
back to make debugging easier.

Choose the free/open-source-compatible log and alert destination only after the
host is known. Before unattended users, create alerts for:

- worker listener reconnect loops or no worker liveness signal;
- an old queued/running job or exhausted job retries;
- repeated API `5xx` responses;
- billing settlement, maintenance, or Polar webhook failures;
- PDF queue saturation or repeated render failures; and
- database/storage capacity thresholds.

For every alert, write who receives it and the first runbook link. An alert
with no owner is only stored noise.

The complete dashboard ownership, metric inventory, review cadence, and
provisional capacity thresholds are in
[Operational metrics and provider review](./operational-metrics-and-provider-review.md).

### 6. Approve retention, backups, and support

Before an external user creates data, record:

- retention periods for accounts, jobs, shared transcripts/summaries, PDFs,
  temporary audio, billing evidence, logs, and backups;
- how a verified privacy/erasure request is received and handled manually;
- provider-held data behavior and legal/payment exceptions;
- enabled database and Storage-object backups (Supabase database backups cover
  Storage metadata, not the stored file objects themselves);
- one successful restore rehearsal; and
- support and incident owners with response expectations.

Example: “PDFs are kept while the reusable summary is retained” is a policy.
“Storage keeps them for a while” is not. Use exact periods or exact events.

### 7. Prove the release candidate

- Run deterministic checks and the disposable database gate.
- Run the authenticated fake-provider journey.
- Run a capped real Groq/OpenRouter set and record quality, cost, and latency.
- Exercise Polar sandbox checkout, webhook, portal, cancellation, and refund.
- Complete authenticated desktop/mobile keyboard and screen-reader review.
- Test worker restart, notification disconnect/reconnect, API rollback, and a
  controlled dependency outage.
- Promote the exact tested revision deliberately; do not rebuild an unknown
  revision for production.

## Supabase Storage versus Cloudflare R2

Keep Supabase Storage for the first deployment unless measurements show a real
cost or limit problem. It already shares the current service identity and all
downloads are private signed URLs.

R2 may later remove temporary-audio egress to the transcription provider or
reduce PDF download egress cost, but it is not a drop-in rename. A safe change
needs a storage adapter, least-privilege R2 credentials, private buckets,
short-lived signed URLs, CORS, cleanup/retention behavior, migration of
existing objects, failure tests, and rollback. Temporary audio and PDFs have
different retention/security needs, so evaluate them separately and do not
move both merely for architectural symmetry.

Compare measured total cost and operational complexity after real usage. The
cheapest price per stored gigabyte is not automatically the cheapest system to
operate safely.
