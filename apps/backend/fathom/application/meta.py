from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fathom.api import __version__
from fathom.core.config import Settings
from fathom.core.errors import ConfigurationError, NotReadyError
from fathom.schemas.meta import HealthResponse, ReadyResponse, StatusResponse
from fathom.services import polar
from fathom.services.supabase import (
    create_postgres_connection,
    create_supabase_admin_client,
    managed_supabase_client,
)

_START_TIME = time.monotonic()

logger = logging.getLogger(__name__)

_REQUIRED_DATABASE_OBJECTS = (
    "jobs_table",
    "summaries_table",
    "job_events_table",
    "transcript_segments_table",
    "usage_settlements_table",
    "billing_webhook_events_table",
    "billing_maintenance_leases_table",
    "briefing_stream_leases_table",
    "create_or_reuse_settled_job_function",
    "claim_next_settled_job_function",
    "renew_job_lease_function",
    "update_job_with_valid_lease_function",
    "prepare_summary_function",
    "create_transcript_with_segments_function",
    "prepare_summary_pdf_function",
    "complete_summary_pdf_function",
    "fail_summary_pdf_function",
    "settle_job_usage_function",
    "apply_polar_webhook_event_function",
    "begin_pack_refund_function",
    "reopen_pack_refund_function",
    "claim_billing_maintenance_lease_function",
    "renew_billing_maintenance_lease_function",
    "release_billing_maintenance_lease_function",
    "claim_briefing_stream_lease_function",
    "renew_briefing_stream_lease_function",
    "release_briefing_stream_lease_function",
)

_SCHEMA_CHECK_SQL = """
select
  to_regclass('public.jobs') is not null as jobs_table,
  to_regclass('public.summaries') is not null as summaries_table,
  to_regclass('public.job_events') is not null as job_events_table,
  to_regclass('public.transcript_segments') is not null as transcript_segments_table,
  to_regclass('public.usage_settlements') is not null as usage_settlements_table,
  to_regclass('public.billing_webhook_events') is not null as billing_webhook_events_table,
  to_regclass('public.billing_maintenance_leases') is not null as billing_maintenance_leases_table,
  to_regclass('public.briefing_stream_leases') is not null as briefing_stream_leases_table,
  exists (
    select 1 from pg_proc join pg_namespace on pg_namespace.oid = pg_proc.pronamespace
    where pg_namespace.nspname = 'public' and pg_proc.proname = 'create_or_reuse_settled_job'
  ) as create_or_reuse_settled_job_function,
  exists (
    select 1 from pg_proc join pg_namespace on pg_namespace.oid = pg_proc.pronamespace
    where pg_namespace.nspname = 'public' and pg_proc.proname = 'claim_next_settled_job'
  ) as claim_next_settled_job_function,
  exists (
    select 1 from pg_proc join pg_namespace on pg_namespace.oid = pg_proc.pronamespace
    where pg_namespace.nspname = 'public' and pg_proc.proname = 'renew_job_lease'
  ) as renew_job_lease_function,
  exists (
    select 1 from pg_proc join pg_namespace on pg_namespace.oid = pg_proc.pronamespace
    where pg_namespace.nspname = 'public' and pg_proc.proname = 'update_job_with_valid_lease'
  ) as update_job_with_valid_lease_function,
  exists (
    select 1 from pg_proc join pg_namespace on pg_namespace.oid = pg_proc.pronamespace
    where pg_namespace.nspname = 'public' and pg_proc.proname = 'prepare_summary'
  ) as prepare_summary_function,
  exists (
    select 1 from pg_proc join pg_namespace on pg_namespace.oid = pg_proc.pronamespace
    where pg_namespace.nspname = 'public' and pg_proc.proname = 'create_transcript_with_segments'
  ) as create_transcript_with_segments_function,
  exists (
    select 1 from pg_proc join pg_namespace on pg_namespace.oid = pg_proc.pronamespace
    where pg_namespace.nspname = 'public' and pg_proc.proname = 'prepare_summary_pdf'
  ) as prepare_summary_pdf_function,
  exists (
    select 1 from pg_proc join pg_namespace on pg_namespace.oid = pg_proc.pronamespace
    where pg_namespace.nspname = 'public' and pg_proc.proname = 'complete_summary_pdf'
  ) as complete_summary_pdf_function,
  exists (
    select 1 from pg_proc join pg_namespace on pg_namespace.oid = pg_proc.pronamespace
    where pg_namespace.nspname = 'public' and pg_proc.proname = 'fail_summary_pdf'
  ) as fail_summary_pdf_function,
  exists (
    select 1 from pg_proc join pg_namespace on pg_namespace.oid = pg_proc.pronamespace
    where pg_namespace.nspname = 'public' and pg_proc.proname = 'settle_job_usage'
  ) as settle_job_usage_function,
  exists (
    select 1 from pg_proc join pg_namespace on pg_namespace.oid = pg_proc.pronamespace
    where pg_namespace.nspname = 'public' and pg_proc.proname = 'apply_polar_webhook_event'
  ) as apply_polar_webhook_event_function,
  exists (
    select 1 from pg_proc join pg_namespace on pg_namespace.oid = pg_proc.pronamespace
    where pg_namespace.nspname = 'public' and pg_proc.proname = 'begin_pack_refund'
  ) as begin_pack_refund_function,
  exists (
    select 1 from pg_proc join pg_namespace on pg_namespace.oid = pg_proc.pronamespace
    where pg_namespace.nspname = 'public' and pg_proc.proname = 'reopen_pack_refund'
  ) as reopen_pack_refund_function,
  exists (
    select 1 from pg_proc join pg_namespace on pg_namespace.oid = pg_proc.pronamespace
    where pg_namespace.nspname = 'public' and pg_proc.proname = 'claim_billing_maintenance_lease'
  ) as claim_billing_maintenance_lease_function,
  exists (
    select 1 from pg_proc join pg_namespace on pg_namespace.oid = pg_proc.pronamespace
    where pg_namespace.nspname = 'public' and pg_proc.proname = 'renew_billing_maintenance_lease'
  ) as renew_billing_maintenance_lease_function,
  exists (
    select 1 from pg_proc join pg_namespace on pg_namespace.oid = pg_proc.pronamespace
    where pg_namespace.nspname = 'public' and pg_proc.proname = 'release_billing_maintenance_lease'
  ) as release_billing_maintenance_lease_function,
  exists (
    select 1 from pg_proc join pg_namespace on pg_namespace.oid = pg_proc.pronamespace
    where pg_namespace.nspname = 'public' and pg_proc.proname = 'claim_briefing_stream_lease'
  ) as claim_briefing_stream_lease_function,
  exists (
    select 1 from pg_proc join pg_namespace on pg_namespace.oid = pg_proc.pronamespace
    where pg_namespace.nspname = 'public' and pg_proc.proname = 'renew_briefing_stream_lease'
  ) as renew_briefing_stream_lease_function,
  exists (
    select 1 from pg_proc join pg_namespace on pg_namespace.oid = pg_proc.pronamespace
    where pg_namespace.nspname = 'public' and pg_proc.proname = 'release_briefing_stream_lease'
  ) as release_briefing_stream_lease_function
"""


async def health_status() -> HealthResponse:
    logger.info("api.health.ok")
    return HealthResponse(status="ok")


def _is_strict_runtime_env(settings: Settings) -> bool:
    return getattr(settings, "app_env", "local") in {"staging", "production"}


def _require_supabase_config(settings: Settings) -> None:
    if settings.supabase_url and settings.supabase_publishable_key and settings.supabase_secret_key:
        _log_readiness_check("supabase_config", "ok")
        return
    _log_readiness_check("supabase_config", "failed")
    raise NotReadyError("Supabase is not configured.")


def _require_billing_config(settings: Settings) -> None:
    try:
        polar.get_polar_access_token(settings)
        polar.get_polar_webhook_secret(settings)
        polar.get_polar_success_url(settings)
        polar.get_polar_portal_return_url(settings)
    except ConfigurationError as exc:
        _log_readiness_check("billing_config", "failed")
        raise NotReadyError(f"Billing is not configured: {exc.detail}") from exc
    _log_readiness_check("billing_config", "ok")


@asynccontextmanager
async def _postgres_connection(settings: Settings):
    async with create_postgres_connection(settings) as conn:
        yield conn


async def _check_postgrest(settings: Settings) -> None:
    try:
        async with managed_supabase_client(await create_supabase_admin_client(settings)) as client:
            await client.table("jobs").select("id,status,lease_expires_at,usage_settlement_required").limit(1).execute()
            await (
                client.table("summaries")
                .select("id,status,generation_job_id,status_updated_at,pdf_cache_version,pdf_generation_token")
                .limit(1)
                .execute()
            )
            await client.table("job_events").select("id,sequence_id,job_id,event_type,created_at").limit(1).execute()
            await (
                client.table("transcript_segments")
                .select("transcript_id,segment_index,start_seconds,end_seconds")
                .limit(1)
                .execute()
            )
    except Exception as exc:
        logger.warning(
            "api.ready.failed",
            extra={"check": "postgrest_schema", "error_type": type(exc).__name__},
        )
        raise NotReadyError("Supabase is not reachable.") from exc
    _log_readiness_check("postgrest_schema", "ok")


async def _check_postgres(settings: Settings) -> None:
    try:
        async with _postgres_connection(settings) as conn:
            await conn.fetchval("select 1")
            schema_status = await conn.fetchrow(_SCHEMA_CHECK_SQL)
    except ConfigurationError as exc:
        logger.warning("api.ready.failed", extra={"check": "postgres", "error_type": type(exc).__name__})
        raise NotReadyError(f"Direct Postgres is not configured: {exc.detail}") from exc
    except Exception as exc:
        logger.warning("api.ready.failed", extra={"check": "postgres", "error_type": type(exc).__name__})
        raise NotReadyError("Direct Postgres is not reachable.") from exc

    _log_readiness_check("postgres", "ok")
    missing_objects = [name for name in _REQUIRED_DATABASE_OBJECTS if not schema_status or not schema_status.get(name)]
    if missing_objects:
        logger.warning(
            "api.ready.failed",
            extra={"check": "database_schema", "missing_count": len(missing_objects)},
        )
        raise NotReadyError("Database schema is incomplete.")
    _log_readiness_check("database_schema", "ok")


def _log_readiness_check(check: str, result: str) -> None:
    logger.info("api.ready.check", extra={"check": check, "result": result})


async def readiness_status(settings: Settings) -> ReadyResponse:
    _require_supabase_config(settings)

    await _check_postgrest(settings)
    await _check_postgres(settings)

    if _is_strict_runtime_env(settings):
        _require_billing_config(settings)
    else:
        _log_readiness_check("billing_config", "skipped")

    logger.info("api.ready.ok", extra={"provider_reachability": "not_checked"})
    return ReadyResponse(status="ok")


async def status_snapshot() -> StatusResponse:
    uptime_seconds = time.monotonic() - _START_TIME
    logger.info("api.status.snapshot", extra={"uptime_seconds": round(uptime_seconds, 2), "version": __version__})
    return StatusResponse(
        status="ok",
        version=__version__,
        uptime_seconds=uptime_seconds,
    )
