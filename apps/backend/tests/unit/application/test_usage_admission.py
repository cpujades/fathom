from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

from fathom.application.usage import UsageSnapshot, _get_usage_overview, ensure_usage_allowed
from fathom.core.config import Settings
from fathom.core.errors import (
    BalanceBlockedError,
    InsufficientVideoTimeError,
    NoVideoTimeError,
    SourceDurationUnknownError,
)


class UsageAdmissionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.settings = cast(Settings, SimpleNamespace())

    async def test_usage_overview_identifies_only_active_paid_subscriptions(self) -> None:
        snapshot = UsageSnapshot(
            subscription_remaining=300,
            pack_remaining=120,
            total_remaining=420,
            pack_expires_at=None,
            debt_seconds=0,
            is_blocked=False,
        )

        for status, product_id, amount_cents, expected in (
            ("active", "paid-product", 1_200, True),
            ("active", "internal_free", 0, False),
            ("canceled", "paid-product", 1_200, False),
        ):
            with (
                self.subTest(status=status, product_id=product_id),
                patch(
                    "fathom.application.usage.fetch_entitlement",
                    AsyncMock(
                        return_value={
                            "subscription_plan_id": "plan-1",
                            "subscription_status": status,
                        }
                    ),
                ),
                patch(
                    "fathom.application.usage.fetch_plan_by_id",
                    AsyncMock(
                        return_value={
                            "name": "Creator" if amount_cents else "Free",
                            "polar_product_id": product_id,
                            "amount_cents": amount_cents,
                        }
                    ),
                ),
                patch("fathom.application.usage.get_usage_snapshot", AsyncMock(return_value=snapshot)),
            ):
                overview = await _get_usage_overview(
                    "user-1",
                    self.settings,
                    object(),
                )

            self.assertEqual(overview.has_active_paid_subscription, expected)
            self.assertEqual(overview.total_remaining, 420)

    async def test_zero_balance_cannot_start_work_even_when_debt_cap_is_unused(self) -> None:
        snapshot = UsageSnapshot(
            subscription_remaining=0,
            pack_remaining=0,
            total_remaining=0,
            pack_expires_at=None,
            debt_seconds=0,
            is_blocked=False,
        )

        with patch("fathom.application.usage.get_usage_snapshot", AsyncMock(return_value=snapshot)):
            with self.assertRaises(NoVideoTimeError) as raised:
                await ensure_usage_allowed(
                    user_id="user-1",
                    duration_seconds=300,
                    settings=self.settings,
                )

        self.assertEqual(raised.exception.code, "no_video_time")
        self.assertEqual(raised.exception.details, {"available_seconds": 0})

    async def test_usage_overview_does_not_misclassify_a_plan_lookup_failure_as_free(self) -> None:
        with (
            patch(
                "fathom.application.usage.fetch_entitlement",
                AsyncMock(
                    return_value={
                        "subscription_plan_id": "plan-1",
                        "subscription_status": "active",
                    }
                ),
            ),
            patch(
                "fathom.application.usage.fetch_plan_by_id",
                AsyncMock(side_effect=RuntimeError("catalog unavailable")),
            ),
            patch("fathom.application.usage.get_usage_snapshot", AsyncMock()) as get_snapshot,
        ):
            with self.assertRaisesRegex(RuntimeError, "catalog unavailable"):
                await _get_usage_overview("user-1", self.settings, object())

        get_snapshot.assert_not_awaited()

    async def test_known_video_must_fit_current_balance_without_planned_debt(self) -> None:
        snapshot = UsageSnapshot(
            subscription_remaining=240,
            pack_remaining=0,
            total_remaining=240,
            pack_expires_at=None,
            debt_seconds=0,
            is_blocked=False,
        )

        with patch("fathom.application.usage.get_usage_snapshot", AsyncMock(return_value=snapshot)):
            with self.assertRaises(InsufficientVideoTimeError) as raised:
                await ensure_usage_allowed(
                    user_id="user-1",
                    duration_seconds=300,
                    settings=self.settings,
                )

        self.assertEqual(raised.exception.code, "insufficient_video_time")
        self.assertEqual(
            raised.exception.details,
            {"required_seconds": 300, "available_seconds": 240},
        )

    async def test_known_video_with_enough_current_balance_is_allowed(self) -> None:
        snapshot = UsageSnapshot(
            subscription_remaining=240,
            pack_remaining=60,
            total_remaining=300,
            pack_expires_at=None,
            debt_seconds=0,
            is_blocked=False,
        )

        with patch("fathom.application.usage.get_usage_snapshot", AsyncMock(return_value=snapshot)):
            await ensure_usage_allowed(
                user_id="user-1",
                duration_seconds=300,
                settings=self.settings,
            )

    async def test_unknown_duration_is_rejected_before_reading_balance(self) -> None:
        with patch("fathom.application.usage.get_usage_snapshot", AsyncMock()) as get_snapshot:
            with self.assertRaises(SourceDurationUnknownError) as raised:
                await ensure_usage_allowed(
                    user_id="user-1",
                    duration_seconds=None,
                    settings=self.settings,
                )

        get_snapshot.assert_not_awaited()
        self.assertEqual(raised.exception.code, "source_duration_unknown")

    async def test_existing_debt_block_remains_authoritative(self) -> None:
        snapshot = UsageSnapshot(
            subscription_remaining=600,
            pack_remaining=0,
            total_remaining=600,
            pack_expires_at=None,
            debt_seconds=600,
            is_blocked=True,
        )

        with patch("fathom.application.usage.get_usage_snapshot", AsyncMock(return_value=snapshot)):
            with self.assertRaises(BalanceBlockedError) as raised:
                await ensure_usage_allowed(
                    user_id="user-1",
                    duration_seconds=300,
                    settings=self.settings,
                )

        self.assertEqual(raised.exception.code, "balance_blocked")
        self.assertEqual(raised.exception.details, {"debt_seconds": 600})


if __name__ == "__main__":
    unittest.main()
