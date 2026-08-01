from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

from fathom.application.usage import UsageSnapshot, ensure_usage_allowed
from fathom.core.config import Settings
from fathom.core.errors import InvalidRequestError


class UsageAdmissionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.settings = cast(Settings, SimpleNamespace(billing_debt_cap_seconds=600))

    async def test_zero_balance_cannot_start_work_even_when_debt_cap_is_unused(self) -> None:
        snapshot = UsageSnapshot(
            subscription_remaining=0,
            pack_remaining=0,
            total_remaining=0,
            pack_expires_at=None,
            debt_seconds=0,
            is_blocked=False,
        )

        with (
            patch("fathom.application.usage.get_usage_snapshot", AsyncMock(return_value=snapshot)),
            self.assertRaisesRegex(InvalidRequestError, "no remaining video time"),
        ):
            await ensure_usage_allowed(
                user_id="user-1",
                duration_seconds=300,
                settings=self.settings,
            )

    async def test_known_video_must_fit_current_balance_without_planned_debt(self) -> None:
        snapshot = UsageSnapshot(
            subscription_remaining=240,
            pack_remaining=0,
            total_remaining=240,
            pack_expires_at=None,
            debt_seconds=0,
            is_blocked=False,
        )

        with (
            patch("fathom.application.usage.get_usage_snapshot", AsyncMock(return_value=snapshot)),
            self.assertRaisesRegex(InvalidRequestError, "Insufficient credits"),
        ):
            await ensure_usage_allowed(
                user_id="user-1",
                duration_seconds=300,
                settings=self.settings,
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
        with (
            patch("fathom.application.usage.get_usage_snapshot", AsyncMock()) as get_snapshot,
            self.assertRaisesRegex(InvalidRequestError, "determine this video's length"),
        ):
            await ensure_usage_allowed(
                user_id="user-1",
                duration_seconds=None,
                settings=self.settings,
            )

        get_snapshot.assert_not_awaited()

    async def test_existing_debt_block_remains_authoritative(self) -> None:
        snapshot = UsageSnapshot(
            subscription_remaining=600,
            pack_remaining=0,
            total_remaining=600,
            pack_expires_at=None,
            debt_seconds=600,
            is_blocked=True,
        )

        with (
            patch("fathom.application.usage.get_usage_snapshot", AsyncMock(return_value=snapshot)),
            self.assertRaisesRegex(InvalidRequestError, "negative balance"),
        ):
            await ensure_usage_allowed(
                user_id="user-1",
                duration_seconds=300,
                settings=self.settings,
            )


if __name__ == "__main__":
    unittest.main()
