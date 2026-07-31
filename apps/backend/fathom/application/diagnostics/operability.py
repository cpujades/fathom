from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import timedelta
from typing import Any

from fathom.core.config import get_settings
from fathom.services.supabase import create_postgres_connection

DEFAULT_STALE_MINUTES = 5
DEFAULT_SAMPLE_LIMIT = 20
MAX_STALE_MINUTES = 24 * 60
MAX_SAMPLE_LIMIT = 100

_COUNT_FIELDS = (
    "overdue_queued_jobs",
    "expired_running_leases",
    "missing_running_leases",
    "orphaned_pending_summaries",
    "terminal_jobs_missing_settlement",
    "settlement_balance_mismatches",
    "unresolved_webhook_events",
    "stale_processing_webhook_events",
)

_SAMPLE_FIELDS = (
    "job_ids",
    "summary_ids",
    "provider_event_ids",
)

_OPERABILITY_SQL = """
with
issue_jobs as (
  select jobs.id
  from public.jobs as jobs
  where (
    jobs.status = 'queued'
    and coalesce(jobs.run_after, jobs.created_at) <= pg_catalog.now()
    and jobs.updated_at < pg_catalog.now() - $1::interval
  ) or (
    jobs.status = 'running'
    and (
      jobs.lease_expires_at <= pg_catalog.now()
      or jobs.lease_token is null
      or jobs.lease_expires_at is null
    )
  ) or (
    jobs.status = 'succeeded'
    and jobs.usage_settlement_required
    and not exists (
      select 1 from public.usage_settlements
      where usage_settlements.job_id = jobs.id
    )
  )
),
orphaned_summaries as (
  select summaries.id
  from public.summaries as summaries
  where summaries.status = 'pending'
    and not exists (
      select 1
      from public.jobs as jobs
      where jobs.id = summaries.generation_job_id
        and jobs.status = 'running'
        and jobs.lease_token = summaries.generation_token
        and jobs.lease_expires_at > pg_catalog.now()
    )
),
settlement_mismatches as (
  select settlements.id, settlements.job_id
  from public.usage_settlements as settlements
  join public.jobs as jobs on jobs.id = settlements.job_id
  left join lateral (
    select coalesce(sum(ledger.seconds_used), 0)::integer as ledger_seconds
    from public.usage_ledger as ledger
    where ledger.settlement_id = settlements.id
  ) as ledger_totals on true
  where settlements.subscription_seconds
      + settlements.pack_seconds
      + settlements.debt_incurred_seconds <> settlements.duration_seconds
    or settlements.duration_seconds <> greatest(coalesce(jobs.duration_seconds, 0), 0)
    or ledger_totals.ledger_seconds <> settlements.duration_seconds
),
unresolved_webhooks as (
  select events.event_id, events.status, events.received_at
  from public.billing_webhook_events as events
  where events.status in ('failed', 'deferred')
    or (
      events.status = 'processing'
      and events.received_at < pg_catalog.now() - $1::interval
    )
)
select
  pg_catalog.now() as generated_at,
  (
    select count(*) from public.jobs
    where status = 'queued'
      and coalesce(run_after, created_at) <= pg_catalog.now()
      and updated_at < pg_catalog.now() - $1::interval
  )::integer as overdue_queued_jobs,
  (
    select count(*) from public.jobs
    where status = 'running' and lease_expires_at <= pg_catalog.now()
  )::integer as expired_running_leases,
  (
    select count(*) from public.jobs
    where status = 'running'
      and (lease_token is null or lease_expires_at is null)
  )::integer as missing_running_leases,
  (select count(*) from orphaned_summaries)::integer as orphaned_pending_summaries,
  (
    select count(*) from public.jobs as jobs
    where jobs.status = 'succeeded'
      and jobs.usage_settlement_required
      and not exists (
        select 1 from public.usage_settlements
        where usage_settlements.job_id = jobs.id
      )
  )::integer as terminal_jobs_missing_settlement,
  (select count(*) from settlement_mismatches)::integer as settlement_balance_mismatches,
  (select count(*) from unresolved_webhooks)::integer as unresolved_webhook_events,
  (
    select count(*) from unresolved_webhooks where status = 'processing'
  )::integer as stale_processing_webhook_events,
  coalesce(
    (
      select pg_catalog.array_agg(sample.id::text order by sample.id)
      from (select id from issue_jobs order by id limit $2) as sample
    ),
    array[]::text[]
  ) as job_ids,
  coalesce(
    (
      select pg_catalog.array_agg(sample.id::text order by sample.id)
      from (select id from orphaned_summaries order by id limit $2) as sample
    ),
    array[]::text[]
  ) as summary_ids,
  coalesce(
    (
      select pg_catalog.array_agg(sample.event_id order by sample.event_id)
      from (select event_id from unresolved_webhooks order by event_id limit $2) as sample
    ),
    array[]::text[]
  ) as provider_event_ids
"""


async def fetch_operability_report(
    connection: Any,
    *,
    stale_minutes: int = DEFAULT_STALE_MINUTES,
    sample_limit: int = DEFAULT_SAMPLE_LIMIT,
) -> dict[str, Any]:
    _validate_bounds(stale_minutes=stale_minutes, sample_limit=sample_limit)
    row = await connection.fetchrow(
        _OPERABILITY_SQL,
        timedelta(minutes=stale_minutes),
        sample_limit,
    )
    if row is None:
        raise RuntimeError("Database returned an unexpected operability diagnostic shape.")
    try:
        row_data = dict(row)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Database returned an unexpected operability diagnostic shape.") from exc

    counts = {field: int(row_data.get(field) or 0) for field in _COUNT_FIELDS}
    samples = {field: [str(value) for value in (row_data.get(field) or [])][:sample_limit] for field in _SAMPLE_FIELDS}
    return {
        "status": "attention" if any(counts.values()) else "ok",
        "generated_at": row_data.get("generated_at"),
        "stale_after_minutes": stale_minutes,
        "sample_limit": sample_limit,
        "counts": counts,
        "samples": samples,
    }


def _validate_bounds(*, stale_minutes: int, sample_limit: int) -> None:
    if not 1 <= stale_minutes <= MAX_STALE_MINUTES:
        raise ValueError(f"stale_minutes must be between 1 and {MAX_STALE_MINUTES}.")
    if not 1 <= sample_limit <= MAX_SAMPLE_LIMIT:
        raise ValueError(f"sample_limit must be between 1 and {MAX_SAMPLE_LIMIT}.")


async def _fetch_from_environment(*, stale_minutes: int, sample_limit: int) -> dict[str, Any]:
    settings = get_settings()
    async with create_postgres_connection(settings) as connection:
        async with connection.transaction(readonly=True):
            return await fetch_operability_report(
                connection,
                stale_minutes=stale_minutes,
                sample_limit=sample_limit,
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Print a bounded, read-only, privacy-safe Talven operability report.")
    parser.add_argument(
        "--stale-minutes",
        type=int,
        default=DEFAULT_STALE_MINUTES,
        help=f"Age threshold from 1 to {MAX_STALE_MINUTES} minutes.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=DEFAULT_SAMPLE_LIMIT,
        help=f"Maximum IDs per issue category from 1 to {MAX_SAMPLE_LIMIT}.",
    )
    args = parser.parse_args()

    try:
        report = asyncio.run(
            _fetch_from_environment(
                stale_minutes=args.stale_minutes,
                sample_limit=args.sample_limit,
            )
        )
    except Exception as exc:
        print(f"Failed to fetch operability report: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(json.dumps(report, default=str, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
