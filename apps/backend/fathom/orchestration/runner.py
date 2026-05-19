from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from fathom.application.billing import run_billing_maintenance
from fathom.core.config import Settings, get_settings
from fathom.core.logging import log_context, setup_logging
from fathom.crud.supabase.job_events import record_job_event_best_effort
from fathom.crud.supabase.jobs import (
    claim_next_job,
    mark_job_failed,
    mark_job_retry,
    requeue_stale_jobs,
)
from fathom.orchestration.jobs import process_job
from fathom.orchestration.observability import (
    elapsed_ms,
    extract_job_error,
)
from fathom.services.supabase import create_supabase_admin_client, listen_for_notifications
from supabase import AsyncClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Worker configuration
# ---------------------------------------------------------------------------
WORKER_IDLE_SLEEP_SECONDS = 1
WORKER_MAX_ATTEMPTS = 3
WORKER_BACKOFF_BASE_SECONDS = 5
WORKER_STALE_AFTER_SECONDS = 300  # 5 minutes
WORKER_SWEEP_INTERVAL_SECONDS = 30.0
WORKER_BILLING_MAINTENANCE_INTERVAL_SECONDS = 60.0
WORKER_JOB_NOTIFY_TIMEOUT_SECONDS = 10.0


def _compute_backoff_seconds(base: int, attempt: int) -> int:
    return int(base * (2 ** max(attempt - 1, 0)))


async def _handle_claimed_job(
    job: dict[str, Any],
    settings: Settings,
    admin_client: AsyncClient,
) -> None:
    attempt_count = int(job.get("attempt_count") or 0)
    job_id = job.get("id")
    if not job_id:
        logger.debug("worker.job.claim_empty")
        return

    logger.debug(
        "worker.job.claimed",
        extra={
            "job_id": job_id,
            "attempt": attempt_count,
            "user_id": job.get("user_id"),
            "url_host": urlparse(str(job.get("url") or "")).netloc.lower(),
        },
    )
    await record_job_event_best_effort(
        admin_client,
        logger,
        job_id=str(job_id),
        event_type="job_claimed",
        stage="running",
        message="Worker claimed the job.",
        metadata={
            "attempt": attempt_count,
            "user_id": job.get("user_id"),
            "url_host": urlparse(str(job.get("url") or "")).netloc.lower(),
        },
    )
    if not job.get("url") or not job.get("user_id"):
        error_message = "Job is missing required fields (url or user_id)."
        logger.error("worker.job.invalid_payload", extra={"job_id": job_id})
        await record_job_event_best_effort(
            admin_client,
            logger,
            job_id=str(job_id),
            event_type="job_failed",
            stage="failed",
            message=error_message,
            metadata={"attempt": attempt_count, "error_code": "invalid_job_payload", "will_retry": False},
        )
        await mark_job_failed(
            admin_client,
            job_id=job_id,
            error_code="invalid_job_payload",
            error_message=error_message,
        )
        return

    if attempt_count > WORKER_MAX_ATTEMPTS:
        error_message = "Job exceeded maximum retry attempts."
        await record_job_event_best_effort(
            admin_client,
            logger,
            job_id=str(job_id),
            event_type="job_failed",
            stage="failed",
            message=error_message,
            metadata={"attempt": attempt_count, "error_code": "max_attempts_exceeded", "will_retry": False},
        )
        await mark_job_failed(
            admin_client,
            job_id=job_id,
            error_code="max_attempts_exceeded",
            error_message=error_message,
        )
        return

    attempt_start = time.perf_counter()
    try:
        with log_context(job_id=job_id, attempt=attempt_count):
            await process_job(job, settings, admin_client)
    except Exception as exc:
        error_code, error_message = extract_job_error(exc)
        await record_job_event_best_effort(
            admin_client,
            logger,
            job_id=str(job_id),
            event_type="job_failed",
            stage="failed",
            message=error_message,
            metadata={
                "attempt": attempt_count,
                "duration_ms": elapsed_ms(attempt_start),
                "error_code": error_code,
                "will_retry": attempt_count < WORKER_MAX_ATTEMPTS,
            },
        )
        logger.exception(
            "worker.job.failed",
            extra={
                "job_id": job_id,
                "attempt": attempt_count,
                "duration_ms": elapsed_ms(attempt_start),
                "error_code": error_code,
                "will_retry": attempt_count < WORKER_MAX_ATTEMPTS,
            },
        )
        if attempt_count < WORKER_MAX_ATTEMPTS:
            backoff_seconds = _compute_backoff_seconds(WORKER_BACKOFF_BASE_SECONDS, attempt_count)
            run_after = datetime.now(UTC) + timedelta(seconds=backoff_seconds)
            await mark_job_retry(
                admin_client,
                job_id=job_id,
                error_code=error_code,
                error_message=error_message,
                run_after=run_after,
            )
        else:
            await mark_job_failed(
                admin_client,
                job_id=job_id,
                error_code=error_code,
                error_message=error_message,
            )


async def _wait_for_job_notification(
    queue: asyncio.Queue[dict[str, Any]],
    *,
    timeout_seconds: float,
) -> bool:
    try:
        payload = await asyncio.wait_for(queue.get(), timeout=timeout_seconds)
        return payload is not None
    except TimeoutError:
        return False
    except Exception as exc:
        logger.warning("worker.job_notification.listen_failed", exc_info=exc)
        return False


def _drain_completed_tasks(tasks: set[asyncio.Task[None]]) -> None:
    done_tasks = {task for task in tasks if task.done()}
    for task in done_tasks:
        tasks.remove(task)
        try:
            task.result()
        except Exception:
            logger.exception("worker.task.crashed")


async def _run_scheduled_maintenance(
    admin_client: AsyncClient,
    *,
    settings: Settings,
    last_sweep_at: float,
    last_billing_maintenance_at: float,
) -> tuple[float, float]:
    now = time.monotonic()
    if now - last_sweep_at >= WORKER_SWEEP_INTERVAL_SECONDS:
        requeued_jobs = await requeue_stale_jobs(admin_client, stale_after_seconds=WORKER_STALE_AFTER_SECONDS)
        log_level = logging.INFO if requeued_jobs else logging.DEBUG
        logger.log(
            log_level,
            "worker.stale_job_sweep.completed",
            extra={
                "stale_after_seconds": WORKER_STALE_AFTER_SECONDS,
                "requeued_jobs": requeued_jobs,
            },
        )
        last_sweep_at = now

    if now - last_billing_maintenance_at >= WORKER_BILLING_MAINTENANCE_INTERVAL_SECONDS:
        await run_billing_maintenance(admin_client, settings=settings)
        last_billing_maintenance_at = now

    return last_sweep_at, last_billing_maintenance_at


async def _run_loop(settings: Settings) -> None:
    admin_client = await create_supabase_admin_client(settings)
    max_concurrent_jobs = max(1, settings.worker_max_concurrent_jobs)
    notify_timeout_seconds = WORKER_JOB_NOTIFY_TIMEOUT_SECONDS
    running_tasks: set[asyncio.Task[None]] = set()
    last_sweep_at = 0.0
    last_billing_maintenance_at = 0.0

    while True:
        try:
            async with listen_for_notifications(settings, "job_created") as queue:
                logger.info("worker.job_listener.ready", extra={"channel": "job_created"})
                while True:
                    _drain_completed_tasks(running_tasks)
                    last_sweep_at, last_billing_maintenance_at = await _run_scheduled_maintenance(
                        admin_client,
                        settings=settings,
                        last_sweep_at=last_sweep_at,
                        last_billing_maintenance_at=last_billing_maintenance_at,
                    )
                    while len(running_tasks) < max_concurrent_jobs:
                        job = await claim_next_job(admin_client)
                        if not job:
                            break

                        task = asyncio.create_task(_handle_claimed_job(job, settings, admin_client))
                        running_tasks.add(task)

                    if running_tasks:
                        await asyncio.sleep(WORKER_IDLE_SLEEP_SECONDS)
                        continue

                    if await _wait_for_job_notification(queue, timeout_seconds=notify_timeout_seconds):
                        continue

                    await asyncio.sleep(WORKER_IDLE_SLEEP_SECONDS)
        except Exception:
            logger.warning("worker.job_listener.reconnecting", extra={"channel": "job_created"}, exc_info=True)
            await asyncio.sleep(WORKER_IDLE_SLEEP_SECONDS)


def main() -> None:
    setup_logging(service="worker")
    settings = get_settings()
    logger.info(
        "worker.started",
        extra={"max_concurrent_jobs": settings.worker_max_concurrent_jobs},
    )
    asyncio.run(_run_loop(settings))


if __name__ == "__main__":
    main()
