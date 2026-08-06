# Local Load And Recovery Rehearsal

This is a pre-staging confidence gate, not a throughput benchmark. It proves
bounded concurrency, retry classification, cancellation, fenced recovery,
idempotent summary/settlement/webhook behavior, and privacy-safe diagnostics
without calling Groq, OpenRouter, Polar, or another paid service.

## Gate A: deterministic fake rehearsal

Run from the repository root:

```bash
PYTHONPATH=apps/backend ./.venv/bin/python -m unittest \
  apps.backend.tests.test_recovery_rehearsal \
  apps.backend.tests.test_provider_resilience \
  apps.backend.tests.test_job_leases \
  apps.backend.tests.test_summary_lifecycle \
  apps.backend.tests.test_usage_settlement \
  apps.backend.tests.test_billing_webhooks \
  apps.backend.tests.test_worker_shutdown \
  apps.backend.tests.test_operability_diagnostics
```

The synthetic load is capped at 20 jobs and four concurrent fake provider
operations. Its failure schedule is deterministic:

- three permanent failures receive one attempt and remain failed;
- three transient failures retry once and converge;
- the remaining jobs succeed;
- observed provider concurrency never exceeds four.

Accept the gate only when the suite passes without network access and finishes
comfortably inside 60 seconds on a development machine. A slower result is a
signal to inspect local contention; it is not evidence of production capacity.

## Gate B: disposable local database concurrency

Use a dedicated local Supabase database with all migrations applied. Never
point this at production or a shared staging database because the fixtures
create and remove reserved test UUIDs.

```bash
FATHOM_TEST_DATABASE_URL=postgresql://... \
PYTHONPATH=apps/backend ./.venv/bin/python -m unittest \
  apps.backend.tests.test_billing_concurrency_integration \
  apps.backend.tests.test_usage_settlement_integration \
  apps.backend.tests.test_polar_webhook_integration \
  apps.backend.tests.test_transcript_evidence_integration
```

Acceptance criteria:

- refund initiation and settlement serialize on the billing order in both
  commit orders, so the provider quote uses the post-settlement remainder or
  the settlement excludes the refund-pending pack;
- two concurrent maintenance workers produce exactly one lease owner;
- concurrent settlement produces one settlement and one balanced set of ledger
  effects;
- duplicate webhook delivery produces one billing effect and a convergent
  replay result;
- transcript evidence segments preserve ordering and citation resolution;
- every fixture cleans up after itself.

If `FATHOM_TEST_DATABASE_URL` is absent, these tests skip; a skip is not a
passing Gate B result.

## Gate C: authenticated product and recovery rehearsal

Gate C is an opt-in integration test against a disposable, fully migrated local
Supabase project. It uses test-only dependency injection at the existing
download, transcription, and summarization boundaries; there is no runtime
fake-provider setting.

Start only the local services needed by Auth, PostgREST, Storage, and the
database. Exclude analytics and its Docker-socket dependency:

```bash
supabase start \
  -x logflare,vector,studio,mailpit,realtime,imgproxy,postgres-meta,edge-runtime
```

Read that disposable project's local status and set these variables without
copying them into a tracked file:

- `FATHOM_GATE_C_SUPABASE_URL`
- `FATHOM_GATE_C_PUBLISHABLE_KEY`
- `FATHOM_GATE_C_SECRET_KEY`
- `FATHOM_GATE_C_DATABASE_URL`

Then run:

```bash
FATHOM_RUN_GATE_C=1 \
PYTHONPATH=apps/backend ./.venv/bin/python -m unittest \
  apps.backend.tests.test_gate_c_e2e
```

The test creates an isolated local Auth user and session, exercises authenticated
session creation, a fake worker success, persisted SSE replay after reconnect,
Markdown and PDF retrieval, archive and restore, billing reads and settlement,
a transient retry, and a permanent provider failure. It also prints
`GATE_C_EVENT_METRIC` for the Postgres notification-to-SSE delivery path.

Pass only when:

- the full test passes instead of skipping;
- persisted event IDs remain ordered across reconnect and the terminal snapshot
  contains the completed briefing;
- PDF, archive, restore, and billing fixtures converge through the public API;
- retry succeeds on its second claim and settles exactly once;
- permanent failure is visible and creates no settlement;
- the event metric reports notification-driven delivery within the bounded
  local latency threshold, without a one-second per-viewer poll;
- the fixture removes its Auth user, database rows, and stored PDF; and
- stopping the disposable project does not stop or reset another local project.

Stop the disposable project with `supabase stop --no-backup`, then remove only
its temporary project directory. The ordinary test suite skips Gate C when its
explicit opt-in and isolated settings are absent.

## What this does not prove

This rehearsal does not establish provider latency, paid-model quality,
production throughput, autoscaling, or hosting capacity. Measure those later
in a deliberately capped staging exercise after core correctness is
reassessed. Keep any paid quality evaluation opt-in and use the documented
evaluation cap.
