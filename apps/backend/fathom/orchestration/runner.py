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
    fetch_next_queued_job_delay_seconds,
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
    BackoffPolicy,
    ProviderOperationError,
    compute_retry_delay,
)
from fathom.services.supabase import (
    create_supabase_admin_client,
    listen_for_notifications,
    managed_supabase_client,
)
from fathom.services.supabase.postgres import PostgresNotificationSignal
from supabase import AsyncClient

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Worker configuration
# ---------------------------------------------------------------------------
WORKER_MAX_ATTEMPTS = 3
WORKER_SHUTDOWN_GRACE_SECONDS = 30.0
WORKER_BACKOFF_BASE_SECONDS = 5
WORKER_STALE_AFTER_SECONDS = 300  # 5 minutes
WORKER_LEASE_SECONDS = 120
WORKER_HEARTBEAT_INTERVAL_SECONDS = 30.0
WORKER_SWEEP_INTERVAL_SECONDS = 30.0
WORKER_BILLING_MAINTENANCE_INTERVAL_SECONDS = 300.0
WORKER_LISTENER_RECONNECT_BASE_SECONDS = 1.0
WORKER_LISTENER_RECONNECT_MAX_SECONDS = 30.0
WORKER_RETRY_BACKOFF = BackoffPolicy(
    backoff_base_seconds=WORKER_BACKOFF_BASE_SECONDS,
    backoff_max_seconds=60,
)


def _compute_backoff_seconds(
    attempt: int,
    *,
    retry_after_seconds: float | None = None,
) -> float:
    return compute_retry_delay(
        WORKER_RETRY_BACKOFF,
        attempt=attempt,
        retry_after_seconds=retry_after_seconds,
    )


def _should_retry_failure(exc: Exception, *, attempt_count: int) -> bool:
    if attempt_count >= WORKER_MAX_ATTEMPTS:
        return False
    return not isinstance(exc, ProviderOperationError)


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


async def _wait_for_signal(
    signal: asyncio.Queue[PostgresNotificationSignal],
    shutdown_event: asyncio.Event,
) -> PostgresNotificationSignal | None:
    signal_task = asyncio.create_task(signal.get())
    shutdown_task = asyncio.create_task(shutdown_event.wait())
    try:
        done, _ = await asyncio.wait({signal_task, shutdown_task}, return_when=asyncio.FIRST_COMPLETED)
        if signal_task in done and not shutdown_event.is_set():
            return signal_task.result()
        return None
    finally:
        signal_task.cancel()
        shutdown_task.cancel()
        await asyncio.gather(signal_task, shutdown_task, return_exceptions=True)


async def _wait_for_shutdown(shutdown_event: asyncio.Event, timeout_seconds: float) -> bool:
    try:
        async with asyncio.timeout(timeout_seconds):
            await shutdown_event.wait()
    except TimeoutError:
        return False
    return True


def _listener_reconnect_delay(attempt: int) -> float:
    return min(
        WORKER_LISTENER_RECONNECT_MAX_SECONDS,
        WORKER_LISTENER_RECONNECT_BASE_SECONDS * (2 ** max(0, attempt - 1)),
    )


async def _run_job_listener(
    settings: Settings,
    *,
    wake_event: asyncio.Event,
    shutdown_event: asyncio.Event,
) -> None:
    reconnect_attempt = 0
    while not shutdown_event.is_set():
        try:
            async with listen_for_notifications(settings, "job_available") as notification_signal:
                reconnect_attempt = 0
                logger.info("worker.job_listener.ready", extra={"channel": "job_available"})
                # Notifications are not durable. Reconcile once after every
                # connection so work created during a disconnect is recovered.
                wake_event.set()
                while not shutdown_event.is_set():
                    listener_signal = await _wait_for_signal(notification_signal, shutdown_event)
                    if listener_signal is None:
                        return
                    if listener_signal == "disconnected":
                        raise ConnectionError("Postgres notification connection closed.")
                    wake_event.set()
        except Exception:
            reconnect_attempt += 1
            reconnect_in_seconds = _listener_reconnect_delay(reconnect_attempt)
            # A failed notification channel must not stop the durable queue.
            # This degraded wake performs one recovery claim pass per reconnect
            # attempt, with bounded exponential backoff rather than constant polling.
            wake_event.set()
            logger.warning(
                "worker.job_listener.reconnecting",
                extra={
                    "channel": "job_available",
                    "attempt": reconnect_attempt,
                    "reconnect_in_seconds": reconnect_in_seconds,
                },
                exc_info=True,
            )
            if await _wait_for_shutdown(shutdown_event, reconnect_in_seconds):
                return


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
    billing_maintenance_task: asyncio.Task[dict[str, int]] | None,
) -> tuple[float, float, asyncio.Task[dict[str, int]] | None, bool]:
    billing_maintenance_task = _drain_billing_maintenance_task(billing_maintenance_task)
    now = time.monotonic()
    work_requeued = False
    if now - last_sweep_at >= WORKER_SWEEP_INTERVAL_SECONDS:
        requeued_jobs = await requeue_stale_jobs(admin_client, stale_after_seconds=WORKER_STALE_AFTER_SECONDS)
        work_requeued = requeued_jobs > 0
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

    if (
        billing_maintenance_task is None
        and now - last_billing_maintenance_at >= WORKER_BILLING_MAINTENANCE_INTERVAL_SECONDS
    ):
        billing_maintenance_task = asyncio.create_task(
            run_billing_maintenance(admin_client, settings=settings),
            name="billing-maintenance",
        )
        last_billing_maintenance_at = now

    return last_sweep_at, last_billing_maintenance_at, billing_maintenance_task, work_requeued


def _drain_billing_maintenance_task(
    task: asyncio.Task[dict[str, int]] | None,
) -> asyncio.Task[dict[str, int]] | None:
    if task is None or not task.done():
        return task

    try:
        task.result()
    except asyncio.CancelledError:
        logger.info("billing.maintenance.cancelled")
    except Exception:
        logger.exception("billing.maintenance.crashed")
    return None


async def _shutdown_billing_maintenance_task(task: asyncio.Task[dict[str, int]] | None) -> None:
    if task is None:
        return

    if not task.done():
        task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    _drain_billing_maintenance_task(task)


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
    max_concurrent_jobs = settings.worker_max_concurrent_jobs
    running_tasks: set[asyncio.Task[None]] = set()
    billing_maintenance_task: asyncio.Task[dict[str, int]] | None = None
    last_sweep_at = 0.0
    last_billing_maintenance_at = 0.0
    scheduler_failure_attempt = 0
    claim_requested = True
    next_queue_wake_at: float | None = None
    wake_event = asyncio.Event()
    listener_task = asyncio.create_task(
        _run_job_listener(
            settings,
            wake_event=wake_event,
            shutdown_event=shutdown_event,
        ),
        name="job-listener",
    )

    try:
        while not shutdown_event.is_set():
            try:
                _drain_completed_tasks(running_tasks)
                (
                    last_sweep_at,
                    last_billing_maintenance_at,
                    billing_maintenance_task,
                    work_requeued,
                ) = await _run_scheduled_maintenance(
                    admin_client,
                    settings=settings,
                    last_sweep_at=last_sweep_at,
                    last_billing_maintenance_at=last_billing_maintenance_at,
                    billing_maintenance_task=billing_maintenance_task,
                )
                if claim_requested or work_requeued:
                    next_queue_wake_at = await _claim_available_jobs(
                        admin_client,
                        settings=settings,
                        shutdown_event=shutdown_event,
                        running_tasks=running_tasks,
                        max_concurrent_jobs=max_concurrent_jobs,
                    )
                scheduler_failure_attempt = 0
            except Exception:
                scheduler_failure_attempt += 1
                logger.warning(
                    "worker.scheduler.cycle_failed",
                    extra={"attempt": scheduler_failure_attempt},
                    exc_info=True,
                )
                retry_delay = _listener_reconnect_delay(scheduler_failure_attempt)
                await _wait_for_work(
                    wake_event=wake_event,
                    shutdown_event=shutdown_event,
                    running_tasks=running_tasks,
                    billing_maintenance_task=billing_maintenance_task,
                    timeout_seconds=retry_delay,
                    next_queue_wake_at=next_queue_wake_at,
                )
                claim_requested = not shutdown_event.is_set()
                continue

            if shutdown_event.is_set():
                break

            claim_requested = await _wait_for_work(
                wake_event=wake_event,
                shutdown_event=shutdown_event,
                running_tasks=running_tasks,
                billing_maintenance_task=billing_maintenance_task,
                timeout_seconds=_seconds_until_maintenance(
                    last_sweep_at=last_sweep_at,
                    last_billing_maintenance_at=last_billing_maintenance_at,
                    billing_maintenance_task=billing_maintenance_task,
                ),
                next_queue_wake_at=next_queue_wake_at,
            )
    finally:
        listener_task.cancel()
        await asyncio.gather(listener_task, return_exceptions=True)
        await _shutdown_billing_maintenance_task(billing_maintenance_task)
        await _shutdown_running_tasks(
            running_tasks,
            grace_seconds=WORKER_SHUTDOWN_GRACE_SECONDS,
        )


async def _claim_available_jobs(
    admin_client: AsyncClient,
    *,
    settings: Settings,
    shutdown_event: asyncio.Event,
    running_tasks: set[asyncio.Task[None]],
    max_concurrent_jobs: int,
) -> float | None:
    while not shutdown_event.is_set() and len(running_tasks) < max_concurrent_jobs:
        job = await claim_next_job(
            admin_client,
            lease_seconds=WORKER_LEASE_SECONDS,
        )
        if not job:
            delay_seconds = await fetch_next_queued_job_delay_seconds(admin_client)
            return time.monotonic() + delay_seconds if delay_seconds is not None else None

        task = asyncio.create_task(
            _handle_claimed_job(job, settings, admin_client),
            name=f"job-{job.get('id', 'unknown')}",
        )
        running_tasks.add(task)

    return None


def _seconds_until_maintenance(
    *,
    last_sweep_at: float,
    last_billing_maintenance_at: float,
    billing_maintenance_task: asyncio.Task[dict[str, int]] | None,
) -> float:
    deadlines = [last_sweep_at + WORKER_SWEEP_INTERVAL_SECONDS]
    if billing_maintenance_task is None:
        deadlines.append(last_billing_maintenance_at + WORKER_BILLING_MAINTENANCE_INTERVAL_SECONDS)
    return max(0.0, min(deadlines) - time.monotonic())


async def _wait_for_work(
    *,
    wake_event: asyncio.Event,
    shutdown_event: asyncio.Event,
    running_tasks: set[asyncio.Task[None]],
    billing_maintenance_task: asyncio.Task[dict[str, int]] | None,
    timeout_seconds: float,
    next_queue_wake_at: float | None,
) -> bool:
    wake_task = asyncio.create_task(wake_event.wait())
    shutdown_task = asyncio.create_task(shutdown_event.wait())
    watched_tasks: set[asyncio.Task[Any]] = {
        wake_task,
        shutdown_task,
        *running_tasks,
    }
    if billing_maintenance_task is not None:
        watched_tasks.add(billing_maintenance_task)

    queue_delay_seconds = max(0.0, next_queue_wake_at - time.monotonic()) if next_queue_wake_at is not None else None
    effective_timeout = (
        min(timeout_seconds, queue_delay_seconds) if queue_delay_seconds is not None else timeout_seconds
    )

    try:
        done, _ = await asyncio.wait(
            watched_tasks,
            timeout=effective_timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if shutdown_task in done or shutdown_event.is_set():
            return False
        if wake_task in done:
            wake_event.clear()
            return True
        if any(task in done for task in running_tasks):
            return True
        return next_queue_wake_at is not None and time.monotonic() >= next_queue_wake_at
    finally:
        wake_task.cancel()
        shutdown_task.cancel()
        await asyncio.gather(wake_task, shutdown_task, return_exceptions=True)


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
    settings = get_settings()
    setup_logging(service="worker", app_env=settings.app_env)
    logger.info(
        "worker.started",
        extra={"max_concurrent_jobs": settings.worker_max_concurrent_jobs},
    )
    asyncio.run(_run_worker(settings))


if __name__ == "__main__":
    main()
