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
  apps.backend.tests.test_usage_settlement_integration \
  apps.backend.tests.test_polar_webhook_integration \
  apps.backend.tests.test_transcript_evidence_integration
```

Acceptance criteria:

- concurrent settlement produces one settlement and one balanced set of ledger
  effects;
- duplicate webhook delivery produces one billing effect and a convergent
  replay result;
- transcript evidence segments preserve ordering and citation resolution;
- every fixture cleans up after itself.

If `FATHOM_TEST_DATABASE_URL` is absent, these tests skip; a skip is not a
passing Gate B result.

## Gate C: one-process crash and recovery check

1. Start the API and exactly one worker against the disposable local database.
2. Submit at most five fixture jobs through fake provider adapters.
3. Stop the worker once during provider work and once during finalization.
4. Restart one worker and wait for one lease sweep and billing-maintenance
   interval.
5. Run the bounded operability report from the incident runbook before and
   after.

Pass only when:

- the stopped worker cannot commit after losing its lease;
- each recoverable job converges through a visible retry/finalization state;
- no ready empty summary is exposed;
- each successful settlement is present exactly once and balances to duration;
- unresolved webhook, orphaned summary, expired lease, and settlement mismatch
  counts return to zero;
- logs contain correlation IDs but no account IDs, source URLs, tokens,
  transcript text, summary Markdown, or webhook payloads.

Gate C is intentionally a manual local rehearsal until fake-provider selection
is exposed as a supported runtime mode. Do not add production-only switches or
provider credentials solely to automate it.

## What this does not prove

This rehearsal does not establish provider latency, paid-model quality,
production throughput, autoscaling, or hosting capacity. Measure those later
in a deliberately capped staging exercise after core correctness is
reassessed. Keep any paid quality evaluation opt-in and use the documented
evaluation cap.
