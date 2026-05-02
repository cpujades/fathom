from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg
from fastapi import Request

from fathom.core.errors import ExternalServiceError, RateLimitError

RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_CLEANUP_INTERVAL_SECONDS = 300

_last_global_cleanup_at = 0.0


@dataclass(frozen=True)
class RateLimitRule:
    scope: str
    limit_per_minute: int


def _get_rate_limit_ip(request: Request, *, trust_proxy_headers: bool) -> str:
    client_host = request.client.host if request.client else ""
    if not trust_proxy_headers:
        return client_host or "unknown"

    forwarded_for = request.headers.get("x-forwarded-for") or ""
    forwarded_ip = forwarded_for.split(",")[0].strip()
    return forwarded_ip or client_host or "unknown"


def _get_rate_limit_subject(request: Request, *, trust_proxy_headers: bool) -> str:
    ip = _get_rate_limit_ip(request, trust_proxy_headers=trust_proxy_headers)
    return f"ip:{ip}"


def _scale_limit(rate_limit: int, multiplier: int, divisor: int = 1) -> int:
    return max(1, (rate_limit * multiplier) // max(1, divisor))


def _get_rate_limit_rule(request: Request, rate_limit: int) -> RateLimitRule | None:
    if rate_limit <= 0:
        return None

    path = request.url.path
    method = request.method.upper()

    if path.startswith("/meta/"):
        return None
    if path == "/webhooks/polar":
        return None
    if path.startswith("/briefing-sessions/") and path.endswith("/events"):
        return None

    if method == "POST" and path == "/briefing-sessions":
        return RateLimitRule(scope="briefing_create", limit_per_minute=_scale_limit(rate_limit, 1, 5))

    if path.startswith("/billing/") and method != "GET":
        return RateLimitRule(scope="billing_write", limit_per_minute=_scale_limit(rate_limit, 1, 3))

    if method == "GET":
        return RateLimitRule(scope="read", limit_per_minute=_scale_limit(rate_limit, 4))

    return RateLimitRule(scope="write", limit_per_minute=_scale_limit(rate_limit, 2))


async def _cleanup_stale_buckets(pool: asyncpg.Pool) -> None:
    cutoff = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(
        seconds=RATE_LIMIT_CLEANUP_INTERVAL_SECONDS * 2
    )
    async with pool.acquire() as conn:
        await conn.execute(
            """
            delete from public.api_rate_limit_buckets
            where window_start < $1
            """,
            cutoff,
        )


async def _check_rate_limit(
    pool: asyncpg.Pool,
    *,
    subject: str,
    scope: str,
) -> int:
    window_start = datetime.now(UTC).replace(second=0, microsecond=0)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            insert into public.api_rate_limit_buckets (
                subject,
                scope,
                window_start,
                count,
                updated_at
            )
            values ($1, $2, $3, 1, now())
            on conflict (subject, scope, window_start)
            do update
            set count = public.api_rate_limit_buckets.count + 1,
                updated_at = now()
            returning count
            """,
            subject,
            scope,
            window_start,
        )
    if row is None:
        raise ExternalServiceError("Failed to evaluate the request rate limit.")
    return int(row["count"])


async def maybe_enforce_rate_limit(request: Request, rate_limit: int) -> None:
    rule = _get_rate_limit_rule(request, rate_limit)
    if rule is None:
        return

    pool = getattr(request.app.state, "postgres_pool", None)
    if pool is None:
        raise ExternalServiceError("Rate limiting is enabled, but the Postgres pool is not available.")

    trust_proxy_headers = bool(getattr(request.app.state, "trust_proxy_headers", False))
    subject = _get_rate_limit_subject(request, trust_proxy_headers=trust_proxy_headers)
    count = await _check_rate_limit(
        pool,
        subject=subject,
        scope=rule.scope,
    )

    global _last_global_cleanup_at
    now = time.monotonic()
    if now - _last_global_cleanup_at >= RATE_LIMIT_CLEANUP_INTERVAL_SECONDS:
        await _cleanup_stale_buckets(pool)
        _last_global_cleanup_at = now

    if count > rule.limit_per_minute:
        raise RateLimitError("Too many requests.")
