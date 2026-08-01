# Hosted Auth and service probes

Use this runbook when configuring a staging or production environment. It
separates settings that live in this repository from settings that must be
configured in Supabase or the hosting platform.

## What is and is not deployed automatically

| Configuration | Source or owner | Automatic deployment behavior |
| --- | --- | --- |
| Local Supabase Auth | `supabase/config.toml` | Applied only to the local Supabase stack after restart |
| Database schema and functions | `supabase/migrations/` | Applied to the linked hosted database by the migration workflow |
| Frontend password checks | `apps/web/app/lib/authPolicy.ts` | Deployed with the web application |
| Hosted Supabase Auth | Supabase Dashboard | Must be configured and verified for each hosted project |
| Auth email delivery | Supabase Dashboard plus SMTP provider | Must be configured and tested for each hosted project |
| Health and readiness probes | Hosting platform | Must target the deployed API origin |

`supabase db push` deploys database migrations. It does not copy the `[auth]`
section of `supabase/config.toml` into a hosted Supabase project.

## Hosted Supabase Auth checklist

Choose the final HTTPS web origin first. The examples below use
`https://app.talven.ai`; replace it with the exact staging or production
origin.

### 1. Configure URLs

In the hosted Supabase project's **Authentication > URL Configuration**:

- set **Site URL** to `https://app.talven.ai`;
- add `https://app.talven.ai/auth/callback` as an exact redirect URL;
- add `https://app.talven.ai/auth/recovery/callback` as an exact redirect URL;
- add separate exact URLs for staging if staging uses a different Supabase
  project; and
- do not add localhost URLs to the production project.

The frontend supplies one of these callback URLs to Supabase. Supabase rejects
the request or falls back incorrectly if the URL is not allowed.

### 2. Configure email and password behavior

In the hosted project's Auth settings:

- enable email/password sign-in;
- require email confirmation;
- set minimum password length to 12;
- require letters and digits;
- enable secure password changes or recent-session reauthentication; and
- keep anonymous sign-in disabled.

The frontend applies the same 12-character-plus-number rule for immediate user
feedback. Hosted Supabase must enforce it too because a browser check alone is
not a security boundary.

### 3. Configure production email delivery

Configure **Authentication > Custom SMTP** with a production mail provider.
Use a sender address on a domain you control and review the confirmation,
recovery, email-change, and password-change templates. Disable provider link
tracking if it rewrites Supabase authentication links.

Never commit SMTP credentials. Keep them in the Supabase project or its secret
manager.

### 4. Prove the real flow

Use a disposable account on the exact deployed web origin:

1. Sign up with email and password.
2. Confirm the email and verify that the link returns to `/auth/callback`.
3. Sign out and sign in again.
4. Request a password reset.
5. Verify that the email returns to `/auth/recovery/callback`.
6. Set a new password and verify that the old password no longer works.
7. Try a password shorter than 12 characters and one without a digit; both
   must be rejected.
8. Verify that an expired or reused recovery link fails safely.

Code and local tests cannot prove SMTP delivery, DNS reputation, template
links, or hosted Dashboard settings. Keep the successful test evidence with
the release candidate.

## API status endpoints

These endpoints have different purposes:

| Endpoint | Purpose | Checks dependencies? | Expected use |
| --- | --- | --- | --- |
| `GET /meta/health` | Confirms the API process can answer HTTP | No | Frequent liveness check |
| `GET /meta/ready` | Confirms the API can safely receive product traffic | Yes | Startup and routing readiness check |
| `GET /meta/status` | Reports application version and process uptime | No | Diagnostics and support |

### What `/meta/ready` checks

Readiness returns HTTP `200` with `{"status":"ok"}` only when:

- Supabase URL and keys are configured;
- PostgREST can read the expected core columns;
- direct TLS-verified Postgres is reachable;
- the required tables and security-definer functions exist; and
- Polar token, webhook secret, success URL, and portal return URL are present
  in staging or production.

It returns HTTP `503` when one of those conditions fails. Logs name the failed
check without exposing credentials.

Readiness deliberately does **not** call YouTube, Groq, OpenRouter, or Polar's
remote API. Calling paid or rate-limited providers from every infrastructure
probe would create cost, noise, and false outages. Provider reachability is
proved through staging rehearsals and monitored through real request outcomes.

### Recommended hosting behavior

Use `/meta/health` to decide whether a process is alive and should be restarted.
Use `/meta/ready` to decide whether it should receive new user traffic.

A reasonable starting configuration is:

- liveness: `/meta/health` every 10-30 seconds;
- readiness: `/meta/ready` every 30 seconds;
- probe timeout: 5-10 seconds; and
- failure threshold: three consecutive failures.

These are starting values, not application constants. Tune them for the
selected platform and measured database latency. Do not restart every replica
immediately because of one brief database outage; readiness should remove an
instance from routing while liveness distinguishes a dead process.

## Application rate limits

`RATE_LIMIT` is the base number of requests per client IP per 60-second window.
It may be `0` locally. Staging and production require a positive value. Counters
are stored in Postgres, so all API replicas share the same limits.

| Request scope | Limit derived from `RATE_LIMIT` | If `RATE_LIMIT=60` |
| --- | ---: | ---: |
| `/meta/health` | Exempt | Exempt |
| Signed Polar webhook | Exempt | Exempt |
| Open an SSE event stream | Base | 60/minute/IP |
| Create a briefing | Base divided by 5 | 12/minute/IP |
| Billing write | Base divided by 3 | 20/minute/IP |
| Any GET, including `/meta/ready` and `/meta/status` | Base multiplied by 4 | 240/minute/IP |
| Other write | Base multiplied by 2 | 120/minute/IP |

The limiter returns HTTP `429` with code `rate_limit_exceeded` after the bucket
is exceeded. An ordinary 30-second readiness probe uses only two of the 240
read requests per minute in the example.

The client-IP boundary is correct only when proxy settings are correct:

- leave `TRUST_PROXY_HEADERS=false` when the API is reached directly;
- behind a trusted ingress, set it to `true` and list only that ingress in
  `TRUSTED_PROXY_NETWORKS`; and
- never trust forwarded headers from arbitrary internet clients.

If every request appears to come from the proxy's IP, unrelated users may
share one rate-limit bucket. If arbitrary forwarded headers are trusted, an
attacker can rotate fake IPs to evade limits. Verify the effective client IP
on the chosen ingress before launch.

## Candidate evidence to retain

- Screenshot or export of hosted Auth URL and password settings.
- SMTP provider and sender domain, without credentials.
- Successful confirmation and recovery timestamps for a disposable account.
- Hosting probe configuration.
- `RATE_LIMIT`, trusted-proxy decision, and effective client-IP test.
- A successful `/meta/ready` response after migrations and a controlled `503`
  rehearsal with one dependency intentionally unavailable.
