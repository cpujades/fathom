from __future__ import annotations

import asyncio
import logging
import signal
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from fathom.application.billing import run_billing_maintenance
from fathom.core.config import Settings, get_settings
from fathom.core.errors import UsageSettlementError
from fathom.core.logging import log_context, setup_logging
from fathom.crud.supabase.job_events import record_job_event_best_effort
from fathom.crud.supabase.jobs import (
    JobLeaseLostError,
    claim_next_job,
    mark_job_failed,
    mark_job_finalization_retry,
    mark_job_retry,
    renew_job_lease,
    requeue_stale_jobs,
)
from fathom.orchestration.jobs import process_job
from fathom.orchestration.observability import (
    elapsed_ms,
    extract_job_error,
)
from fathom.services.provider_resilience import (
    ProviderOperationError,
    RetryPolicy,
    compute_retry_delay,
)
from fathom.services.supabase import (
    create_supabase_admin_client,
    listen_for_notifications,
    managed_supabase_client,
)
from supabase import AsyncClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Worker configuration
# ---------------------------------------------------------------------------
WORKER_IDLE_SLEEP_SECONDS = 1
WORKER_MAX_ATTEMPTS = 3
WORKER_BACKOFF_BASE_SECONDS = 5
WORKER_STALE_AFTER_SECONDS = 300  # 5 minutes
WORKER_LEASE_SECONDS = 120
WORKER_HEARTBEAT_INTERVAL_SECONDS = 30.0
WORKER_SWEEP_INTERVAL_SECONDS = 30.0
WORKER_BILLING_MAINTENANCE_INTERVAL_SECONDS = 60.0
WORKER_JOB_NOTIFY_TIMEOUT_SECONDS = 10.0
WORKER_RETRY_POLICY = RetryPolicy(
    deadline_seconds=3600,
    max_attempts=WORKER_MAX_ATTEMPTS,
    backoff_base_seconds=WORKER_BACKOFF_BASE_SECONDS,
    backoff_max_seconds=60,
)


def _compute_backoff_seconds(
    attempt: int,
    *,
    retry_after_seconds: float | None = None,
) -> float:
    return compute_retry_delay(
        WORKER_RETRY_POLICY,
        attempt=attempt,
        retry_after_seconds=retry_after_seconds,
    )


def _should_retry_failure(exc: Exception, *, attempt_count: int) -> bool:
    if attempt_count >= WORKER_MAX_ATTEMPTS:
        return False
    return not isinstance(exc, ProviderOperationError) or exc.retryable


async def _handle_claimed_job(
    job: dict[str, Any],
    settings: Settings,
    admin_client: AsyncClient,
) -> None:
    attempt_count = int(job.get("attempt_count") or 0)
    job_id = str(job.get("id") or "")
    if not job_id:
        logger.debug("worker.job.claim_empty")
        return
    lease_token = str(job.get("lease_token") or "")
    if not lease_token:
        logger.error("worker.job.lease_missing", extra={"job_id": job_id})
        return

    logger.debug(
        "worker.job.claimed",
        extra={
            "job_id": job_id,
            "attempt": attempt_count,
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
            lease_token=lease_token,
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
            lease_token=lease_token,
            error_code="max_attempts_exceeded",
            error_message=error_message,
        )
        return

    attempt_start = time.perf_counter()
    try:
        with log_context(job_id=job_id, attempt=attempt_count):
            await _run_job_with_heartbeat(job, settings, admin_client)
    except JobLeaseLostError:
        logger.warning(
            "worker.job.lease_lost",
            extra={
                "job_id": job_id,
                "attempt": attempt_count,
                "duration_ms": elapsed_ms(attempt_start),
            },
        )
        return
    except Exception as exc:
        error_code, error_message = extract_job_error(exc)
        will_retry = _should_retry_failure(exc, attempt_count=attempt_count)
        provider_failure_kind = exc.kind.value if isinstance(exc, ProviderOperationError) else None
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
                "will_retry": will_retry,
                "provider_failure_kind": provider_failure_kind,
            },
        )
        logger.exception(
            "worker.job.failed",
            extra={
                "job_id": job_id,
                "attempt": attempt_count,
                "duration_ms": elapsed_ms(attempt_start),
                "error_code": error_code,
                "will_retry": will_retry,
                "provider_failure_kind": provider_failure_kind,
            },
        )
        try:
            if will_retry:
                retry_after_seconds = exc.retry_after_seconds if isinstance(exc, ProviderOperationError) else None
                backoff_seconds = _compute_backoff_seconds(
                    attempt_count,
                    retry_after_seconds=retry_after_seconds,
                )
                run_after = datetime.now(UTC) + timedelta(seconds=backoff_seconds)
                if isinstance(exc, UsageSettlementError):
                    await mark_job_finalization_retry(
                        admin_client,
                        job_id=job_id,
                        lease_token=lease_token,
                        error_code=error_code,
                        error_message=error_message,
                        run_after=run_after,
                    )
                else:
                    await mark_job_retry(
                        admin_client,
                        job_id=job_id,
                        lease_token=lease_token,
                        error_code=error_code,
                        error_message=error_message,
                        run_after=run_after,
                    )
            else:
                await mark_job_failed(
                    admin_client,
                    job_id=job_id,
                    lease_token=lease_token,
                    error_code=error_code,
                    error_message=error_message,
                )
        except JobLeaseLostError:
            logger.warning(
                "worker.job.failure_not_recorded_after_lease_loss",
                extra={"job_id": job_id, "attempt": attempt_count},
            )


async def _run_job_with_heartbeat(
    job: dict[str, Any],
    settings: Settings,
    admin_client: AsyncClient,
) -> None:
    job_id = str(job["id"])
    lease_token = str(job["lease_token"])
    processing_task = asyncio.create_task(
        process_job(job, settings, admin_client),
        name=f"job-{job_id}-processing",
    )
    heartbeat_task = asyncio.create_task(
        _maintain_job_lease(
            admin_client,
            job_id=job_id,
            lease_token=lease_token,
        ),
        name=f"job-{job_id}-heartbeat",
    )

    try:
        done, _ = await asyncio.wait(
            {processing_task, heartbeat_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
    except asyncio.CancelledError:
        processing_task.cancel()
        heartbeat_task.cancel()
        await asyncio.gather(
            processing_task,
            heartbeat_task,
            return_exceptions=True,
        )
        raise
    if processing_task in done:
        try:
            await processing_task
        finally:
            await _stop_heartbeat(heartbeat_task)
        return

    processing_task.cancel()
    try:
        await processing_task
    except asyncio.CancelledError:
        pass
    await heartbeat_task


async def _maintain_job_lease(
    admin_client: AsyncClient,
    *,
    job_id: str,
    lease_token: str,
) -> None:
    while True:
        await asyncio.sleep(WORKER_HEARTBEAT_INTERVAL_SECONDS)
        renewed = await renew_job_lease(
            admin_client,
            job_id=job_id,
            lease_token=lease_token,
            lease_seconds=WORKER_LEASE_SECONDS,
        )
        if not renewed:
            raise JobLeaseLostError(f"Job lease lost for {job_id}.")


async def _stop_heartbeat(task: asyncio.Task[None]) -> None:
    if not task.done():
        task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.debug("worker.job.heartbeat_stopped", exc_info=True)


async def _wait_for_job_notification(
    queue: asyncio.Queue[dict[str, Any]],
    *,
    timeout_seconds: float,
    shutdown_event: asyncio.Event | None = None,
) -> bool:
    if shutdown_event is None:
        shutdown_event = asyncio.Event()

    notification_task = asyncio.create_task(queue.get())
    shutdown_task = asyncio.create_task(shutdown_event.wait())
    try:
        done, _ = await asyncio.wait(
            {notification_task, shutdown_task},
            timeout=timeout_seconds,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if shutdown_task in done:
            return False
        if notification_task not in done:
            return False
        return notification_task.result() is not None
    except Exception as exc:
        logger.warning("worker.job_notification.listen_failed", exc_info=exc)
        return False
    finally:
        notification_task.cancel()
        shutdown_task.cancel()
        await asyncio.gather(
            notification_task,
            shutdown_task,
            return_exceptions=True,
        )


def _drain_completed_tasks(tasks: set[asyncio.Task[None]]) -> None:
    done_tasks = {task for task in tasks if task.done()}
    for task in done_tasks:
        tasks.remove(task)
        try:
            task.result()
        except asyncio.CancelledError:
            logger.info("worker.task.cancelled")
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


async def _shutdown_running_tasks(
    tasks: set[asyncio.Task[None]],
    *,
    grace_seconds: float,
) -> None:
    _drain_completed_tasks(tasks)
    if not tasks:
        logger.info("worker.shutdown.completed", extra={"remaining_jobs": 0})
        return

    logger.info(
        "worker.shutdown.draining",
        extra={"active_jobs": len(tasks), "grace_seconds": grace_seconds},
    )
    _, pending = await asyncio.wait(tasks, timeout=grace_seconds)
    _drain_completed_tasks(tasks)
    if pending:
        logger.warning(
            "worker.shutdown.cancelling",
            extra={
                "remaining_jobs": len(pending),
                "recovery": "lease_expiry",
            },
        )
        # Fenced mutations prevent stale work from committing after cancellation.
        # The next worker sweep requeues each job once its renewable lease expires.
        for task in pending:
            task.cancel()

    await asyncio.gather(*pending, return_exceptions=True)
    tasks.difference_update(pending)
    logger.info("worker.shutdown.completed", extra={"remaining_jobs": 0})


async def _run_loop(
    settings: Settings,
    *,
    shutdown_event: asyncio.Event | None = None,
) -> None:
    if shutdown_event is None:
        shutdown_event = asyncio.Event()

    async with managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client:
        await _run_loop_with_client(settings, shutdown_event=shutdown_event, admin_client=admin_client)


async def _run_loop_with_client(
    settings: Settings,
    *,
    shutdown_event: asyncio.Event,
    admin_client: AsyncClient,
) -> None:
    max_concurrent_jobs = max(1, settings.worker_max_concurrent_jobs)
    notify_timeout_seconds = WORKER_JOB_NOTIFY_TIMEOUT_SECONDS
    running_tasks: set[asyncio.Task[None]] = set()
    last_sweep_at = 0.0
    last_billing_maintenance_at = 0.0

    try:
        while not shutdown_event.is_set():
            try:
                async with listen_for_notifications(settings, "job_created") as queue:
                    logger.info("worker.job_listener.ready", extra={"channel": "job_created"})
                    while not shutdown_event.is_set():
                        _drain_completed_tasks(running_tasks)
                        last_sweep_at, last_billing_maintenance_at = await _run_scheduled_maintenance(
                            admin_client,
                            settings=settings,
                            last_sweep_at=last_sweep_at,
                            last_billing_maintenance_at=last_billing_maintenance_at,
                        )
                        while not shutdown_event.is_set() and len(running_tasks) < max_concurrent_jobs:
                            job = await claim_next_job(
                                admin_client,
                                lease_seconds=WORKER_LEASE_SECONDS,
                            )
                            if not job:
                                break

                            task = asyncio.create_task(
                                _handle_claimed_job(job, settings, admin_client),
                                name=f"job-{job.get('id', 'unknown')}",
                            )
                            running_tasks.add(task)

                        if running_tasks:
                            await asyncio.sleep(WORKER_IDLE_SLEEP_SECONDS)
                            continue

                        if await _wait_for_job_notification(
                            queue,
                            timeout_seconds=notify_timeout_seconds,
                            shutdown_event=shutdown_event,
                        ):
                            continue

                        if not shutdown_event.is_set():
                            await asyncio.sleep(WORKER_IDLE_SLEEP_SECONDS)
            except Exception:
                logger.warning(
                    "worker.job_listener.reconnecting",
                    extra={"channel": "job_created"},
                    exc_info=True,
                )
                if not shutdown_event.is_set():
                    await asyncio.sleep(WORKER_IDLE_SLEEP_SECONDS)
    finally:
        await _shutdown_running_tasks(
            running_tasks,
            grace_seconds=settings.worker_shutdown_grace_seconds,
        )


async def _run_worker(settings: Settings) -> None:
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    installed_signals: list[signal.Signals] = []

    def request_shutdown() -> None:
        if not shutdown_event.is_set():
            logger.info("worker.shutdown.requested")
        shutdown_event.set()

    for shutdown_signal in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(shutdown_signal, request_shutdown)
        except NotImplementedError:  # pragma: no cover - Windows event loops
            logger.warning(
                "worker.shutdown.signal_unsupported",
                extra={"signal": shutdown_signal.name},
            )
        else:
            installed_signals.append(shutdown_signal)

    try:
        await _run_loop(settings, shutdown_event=shutdown_event)
    finally:
        for shutdown_signal in installed_signals:
            loop.remove_signal_handler(shutdown_signal)


def main() -> None:
    setup_logging(service="worker")
    settings = get_settings()
    logger.info(
        "worker.started",
        extra={"max_concurrent_jobs": settings.worker_max_concurrent_jobs},
    )
    asyncio.run(_run_worker(settings))


if __name__ == "__main__":
    main()
