from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.worker import _run_loop

logger = logging.getLogger(__name__)


_ENABLED_VALUES = {"1", "true", "yes", "on"}


def _should_run_embedded_worker() -> bool:
    raw = os.getenv("RUN_WORKER_IN_API", "").strip().lower()
    return raw in _ENABLED_VALUES


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """
    FastAPI lifespan that can embed the worker loop in local development.

    This is intentionally opt-in via RUN_WORKER_IN_API to avoid duplicate
    workers in production deployments.
    """
    worker_task: asyncio.Task[None] | None = None

    if _should_run_embedded_worker():
        settings = get_settings()
        logger.warning(
            "Starting embedded worker in API process (dev-only). Do not enable RUN_WORKER_IN_API in production."
        )
        worker_task = asyncio.create_task(_run_loop(settings))

    try:
        yield
    finally:
        if worker_task is not None:
            logger.warning("Stopping embedded worker")
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker_task
