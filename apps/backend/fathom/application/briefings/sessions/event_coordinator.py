from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fathom.core.config import Settings
from fathom.crud.supabase.job_events import list_job_events_after
from fathom.services.supabase import listen_for_job_event_notifications

logger = logging.getLogger(__name__)

JOB_EVENT_NOTIFICATION_CHANNEL = "job_event_available"
EVENT_BATCH_LIMIT = 100
MAX_FANOUT_EVENTS = 500
NOTIFICATION_COALESCE_SECONDS = 0.01
DISPATCHER_WORKERS = 4
SAFETY_RECONCILE_SECONDS = 45.0
LISTENER_RECONNECT_BASE_SECONDS = 1.0
LISTENER_RECONNECT_MAX_SECONDS = 30.0


@dataclass(frozen=True)
class JobEventUpdate:
    events: tuple[dict[str, Any], ...]
    latest_sequence: int
    reconcile_snapshot: bool


class JobEventSubscription:
    """One non-blocking local fan-out target for an authorized SSE stream."""

    def __init__(self, job_id: str, *, cursor: int) -> None:
        self.job_id = job_id
        self._cursor = max(cursor, 0)
        self._updates: asyncio.Queue[JobEventUpdate] = asyncio.Queue(maxsize=1)

    @property
    def cursor(self) -> int:
        return self._cursor

    def advance(self, cursor: int) -> None:
        self._cursor = max(self._cursor, cursor)

    async def wait(self, timeout_seconds: float) -> JobEventUpdate | None:
        try:
            async with asyncio.timeout(timeout_seconds):
                return await self._updates.get()
        except TimeoutError:
            return None

    def publish(
        self,
        events: Iterable[dict[str, Any]],
        *,
        latest_sequence: int,
        reconcile_snapshot: bool,
    ) -> None:
        unseen = [event for event in events if (_event_sequence(event) or 0) > self._cursor]
        existing: JobEventUpdate | None = None
        if self._updates.full():
            existing = self._updates.get_nowait()

        combined = [*(existing.events if existing else ()), *unseen]
        by_sequence = {
            sequence: event
            for event in combined
            if (sequence := _event_sequence(event)) is not None and sequence > self._cursor
        }
        ordered = tuple(by_sequence[sequence] for sequence in sorted(by_sequence))
        should_reconcile = reconcile_snapshot or bool(existing and existing.reconcile_snapshot)
        newest_sequence = max(
            latest_sequence,
            existing.latest_sequence if existing else 0,
            max(by_sequence, default=0),
        )

        if len(ordered) > MAX_FANOUT_EVENTS:
            # A slow client catches up from the authoritative snapshot without
            # allowing a replica-local buffer to grow without bound.
            ordered = ()
            should_reconcile = True

        if ordered or should_reconcile:
            self._updates.put_nowait(
                JobEventUpdate(
                    events=ordered,
                    latest_sequence=newest_sequence,
                    reconcile_snapshot=should_reconcile,
                )
            )


class JobEventCoordinator:
    """One listener and coalesced event fan-out coordinator per API process."""

    def __init__(
        self,
        settings: Settings,
        admin_client: Any,
        *,
        safety_reconcile_seconds: float = SAFETY_RECONCILE_SECONDS,
    ) -> None:
        self._settings = settings
        self._admin_client = admin_client
        self._safety_reconcile_seconds = safety_reconcile_seconds
        self._subscriptions: dict[str, set[JobEventSubscription]] = {}
        self._pending_reasons: dict[str, set[str]] = {}
        self._pending_jobs: asyncio.Queue[str] = asyncio.Queue()
        self._queued_jobs: set[str] = set()
        self._inflight_jobs: set[str] = set()
        self._shutdown = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []
        self.listener_healthy = False
        self._notification_hints = 0
        self._notification_overflows = 0
        self._refresh_count = 0
        self._refresh_failures = 0
        self._fallback_reconciliations = 0

    async def start(self) -> None:
        if self._tasks:
            return
        self._shutdown.clear()
        self._tasks = [
            asyncio.create_task(self._run_listener(), name="job-event-listener"),
            *(
                asyncio.create_task(
                    self._run_dispatcher(),
                    name=f"job-event-dispatcher-{worker_index + 1}",
                )
                for worker_index in range(DISPATCHER_WORKERS)
            ),
            asyncio.create_task(self._run_safety_reconciliation(), name="job-event-reconciliation"),
        ]
        logger.info("briefing_session.event_coordinator.started")

    async def close(self) -> None:
        if not self._tasks:
            return
        self._shutdown.set()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        self.listener_healthy = False
        logger.info("briefing_session.event_coordinator.stopped")

    @asynccontextmanager
    async def subscribe(self, job_id: str, *, cursor: int) -> AsyncIterator[JobEventSubscription]:
        subscription = JobEventSubscription(job_id, cursor=cursor)
        self._subscriptions.setdefault(job_id, set()).add(subscription)
        try:
            yield subscription
        finally:
            subscribers = self._subscriptions.get(job_id)
            if subscribers is not None:
                subscribers.discard(subscription)
                if not subscribers:
                    self._subscriptions.pop(job_id, None)
                    self._pending_reasons.pop(job_id, None)

    def request_refresh(self, job_id: str, *, reason: str) -> None:
        if job_id not in self._subscriptions:
            return
        reasons = self._pending_reasons.setdefault(job_id, set())
        reasons.add(reason)
        if job_id not in self._queued_jobs and job_id not in self._inflight_jobs:
            self._queued_jobs.add(job_id)
            self._pending_jobs.put_nowait(job_id)

    async def _run_dispatcher(self) -> None:
        while not self._shutdown.is_set():
            job_id: str | None = None
            try:
                job_id = await self._pending_jobs.get()
                self._queued_jobs.discard(job_id)
                if job_id not in self._subscriptions:
                    self._pending_reasons.pop(job_id, None)
                    continue
                self._inflight_jobs.add(job_id)
                await asyncio.sleep(NOTIFICATION_COALESCE_SECONDS)
                reasons = self._pending_reasons.pop(job_id, set())
                if not reasons or job_id not in self._subscriptions:
                    continue
                await self._refresh_job(job_id, reasons=reasons)
                self._refresh_count += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                self._refresh_failures += 1
                logger.warning("briefing_session.event_coordinator.refresh_failed", exc_info=True)
            finally:
                if job_id is not None:
                    self._inflight_jobs.discard(job_id)
                    if (
                        job_id in self._pending_reasons
                        and job_id in self._subscriptions
                        and job_id not in self._queued_jobs
                    ):
                        self._queued_jobs.add(job_id)
                        self._pending_jobs.put_nowait(job_id)

    async def _refresh_job(self, job_id: str, *, reasons: set[str]) -> None:
        subscribers = tuple(self._subscriptions.get(job_id, ()))
        if not subscribers:
            return

        started_at = time.monotonic()
        cursor = min(subscription.cursor for subscription in subscribers)
        events: list[dict[str, Any]] = []
        while len(events) < MAX_FANOUT_EVENTS:
            batch = await list_job_events_after(
                self._admin_client,
                job_id=job_id,
                after_sequence_id=cursor,
                limit=min(EVENT_BATCH_LIMIT, MAX_FANOUT_EVENTS - len(events)),
            )
            if not batch:
                break
            events.extend(batch)
            next_cursor = max((_event_sequence(event) or cursor) for event in batch)
            if next_cursor <= cursor or len(batch) < EVENT_BATCH_LIMIT:
                cursor = next_cursor
                break
            cursor = next_cursor

        for subscription in subscribers:
            subscription.publish(
                events,
                latest_sequence=cursor,
                reconcile_snapshot=True,
            )

        logger.info(
            "briefing_session.event_coordinator.refreshed",
            extra={
                "job_id": job_id,
                "event_count": len(events),
                "subscriber_count": len(subscribers),
                "reasons": sorted(reasons),
                "latency_ms": round((time.monotonic() - started_at) * 1000, 1),
            },
        )

    async def _run_listener(self) -> None:
        reconnect_attempt = 0
        while not self._shutdown.is_set():
            try:
                async with listen_for_job_event_notifications(
                    self._settings,
                    JOB_EVENT_NOTIFICATION_CHANNEL,
                ) as notifications:
                    reconnect_attempt = 0
                    self.listener_healthy = True
                    logger.info(
                        "briefing_session.event_listener.ready",
                        extra={"channel": JOB_EVENT_NOTIFICATION_CHANNEL},
                    )
                    self._request_all(reason="listener_connected")
                    while not self._shutdown.is_set():
                        signal = await notifications.get()
                        if signal == "disconnected":
                            raise ConnectionError("Postgres job-event listener disconnected.")
                        if signal == "overflow":
                            self._notification_overflows += 1
                            self._request_all(reason="notification_overflow")
                            continue
                        self._notification_hints += 1
                        self.request_refresh(signal, reason="notification")
            except asyncio.CancelledError:
                raise
            except Exception:
                self.listener_healthy = False
                reconnect_attempt += 1
                reconnect_delay = min(
                    LISTENER_RECONNECT_MAX_SECONDS,
                    LISTENER_RECONNECT_BASE_SECONDS * (2 ** max(0, reconnect_attempt - 1)),
                )
                self._request_all(reason="listener_disconnected")
                logger.warning(
                    "briefing_session.event_listener.reconnecting",
                    extra={
                        "channel": JOB_EVENT_NOTIFICATION_CHANNEL,
                        "attempt": reconnect_attempt,
                        "reconnect_in_seconds": reconnect_delay,
                    },
                    exc_info=True,
                )
                await self._wait_for_shutdown(reconnect_delay)

    async def _run_safety_reconciliation(self) -> None:
        while not await self._wait_for_shutdown(self._safety_reconcile_seconds):
            if not self.listener_healthy:
                self._fallback_reconciliations += 1
                self._request_all(reason="listener_unavailable_reconciliation")

    def status_snapshot(self) -> dict[str, int | bool]:
        return {
            "listener_healthy": self.listener_healthy,
            "active_jobs": len(self._subscriptions),
            "queued_jobs": len(self._queued_jobs),
            "inflight_jobs": len(self._inflight_jobs),
            "notification_hints": self._notification_hints,
            "notification_overflows": self._notification_overflows,
            "refresh_count": self._refresh_count,
            "refresh_failures": self._refresh_failures,
            "fallback_reconciliations": self._fallback_reconciliations,
        }

    def _request_all(self, *, reason: str) -> None:
        for job_id in tuple(self._subscriptions):
            self.request_refresh(job_id, reason=reason)

    async def _wait_for_shutdown(self, timeout_seconds: float) -> bool:
        try:
            async with asyncio.timeout(timeout_seconds):
                await self._shutdown.wait()
        except TimeoutError:
            return False
        return True


def _event_sequence(event: dict[str, Any]) -> int | None:
    sequence = event.get("sequence_id")
    return sequence if isinstance(sequence, int) and sequence > 0 else None
