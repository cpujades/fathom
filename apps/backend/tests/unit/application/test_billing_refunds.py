from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

from fathom.application.billing.refunds import request_pack_refund
from fathom.application.identity import AuthenticatedUser
from fathom.core.config import Settings
from fathom.core.errors import ActiveBriefingsRefundError, ExternalServiceError, InvalidRequestError
from fathom.services.polar import PolarInvalidRequestError


class BillingRefundTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.admin_client = object()
        self.auth = AuthenticatedUser(access_token="token", user_id="user_123")
        self.settings = cast(Settings, SimpleNamespace())
        self.started = {
            "resolution_type": "started",
            "refundable_amount_cents": 2250,
            "remaining_seconds_before_refund": 2700,
        }
        self.operation_id = "97000000-0000-0000-0000-000000000001"
        self.create_operation = self.enterContext(
            patch(
                "fathom.application.billing.refunds.create_billing_sync_operation",
                AsyncMock(return_value=self.operation_id),
            )
        )
        self.resolve_operation = self.enterContext(
            patch(
                "fathom.application.billing.refunds.resolve_billing_sync_operation",
                AsyncMock(return_value="resolved"),
            )
        )

    async def test_refund_uses_authoritative_amount_from_atomic_command(self) -> None:
        with (
            patch(
                "fathom.application.billing.refunds.create_supabase_admin_client",
                AsyncMock(return_value=self.admin_client),
            ),
            patch(
                "fathom.application.billing.refunds.begin_pack_refund",
                AsyncMock(return_value=self.started),
            ) as begin_refund,
            patch(
                "fathom.application.billing.refunds.polar.create_order_refund",
                AsyncMock(return_value={"id": "refund_123"}),
            ) as create_refund,
        ):
            response = await request_pack_refund(
                polar_order_id="ord_123",
                auth=self.auth,
                settings=self.settings,
            )

        begin_refund.assert_awaited_once_with(
            self.admin_client,
            user_id="user_123",
            polar_order_id="ord_123",
            debt_cap_seconds=600,
        )
        create_refund.assert_awaited_once_with(
            self.settings,
            polar_order_id="ord_123",
            amount_cents=2250,
        )
        self.assertEqual(response.requested_amount_cents, 2250)
        self.assertEqual(response.remaining_seconds_before_refund, 2700)
        self.assertEqual(str(response.operation_id), self.operation_id)

    async def test_duplicate_refund_conflict_keeps_order_refund_pending(self) -> None:
        with (
            patch(
                "fathom.application.billing.refunds.create_supabase_admin_client",
                AsyncMock(return_value=self.admin_client),
            ),
            patch(
                "fathom.application.billing.refunds.begin_pack_refund",
                AsyncMock(return_value=self.started),
            ),
            patch("fathom.application.billing.refunds.reopen_pack_refund", AsyncMock()) as reopen_refund,
            patch(
                "fathom.application.billing.refunds.polar.create_order_refund",
                AsyncMock(side_effect=PolarInvalidRequestError("duplicate", http_status=409)),
            ),
        ):
            response = await request_pack_refund(
                polar_order_id="ord_123",
                auth=self.auth,
                settings=self.settings,
            )

        reopen_refund.assert_not_awaited()
        self.assertEqual(response.status, "pending_webhook_confirmation")

    async def test_definitive_refund_failure_atomically_reopens_order(self) -> None:
        with (
            patch(
                "fathom.application.billing.refunds.create_supabase_admin_client",
                AsyncMock(return_value=self.admin_client),
            ),
            patch(
                "fathom.application.billing.refunds.begin_pack_refund",
                AsyncMock(return_value=self.started),
            ),
            patch(
                "fathom.application.billing.refunds.reopen_pack_refund",
                AsyncMock(return_value={"resolution_type": "reopened"}),
            ) as reopen_refund,
            patch(
                "fathom.application.billing.refunds.polar.create_order_refund",
                AsyncMock(side_effect=PolarInvalidRequestError("bad request", http_status=400)),
            ),
        ):
            with self.assertRaises(PolarInvalidRequestError):
                await request_pack_refund(
                    polar_order_id="ord_123",
                    auth=self.auth,
                    settings=self.settings,
                )

        reopen_refund.assert_awaited_once_with(
            self.admin_client,
            user_id="user_123",
            polar_order_id="ord_123",
            debt_cap_seconds=600,
        )

    async def test_unknown_refund_outcome_keeps_order_refund_pending(self) -> None:
        with (
            patch(
                "fathom.application.billing.refunds.create_supabase_admin_client",
                AsyncMock(return_value=self.admin_client),
            ),
            patch(
                "fathom.application.billing.refunds.begin_pack_refund",
                AsyncMock(return_value=self.started),
            ),
            patch("fathom.application.billing.refunds.reopen_pack_refund", AsyncMock()) as reopen_refund,
            patch(
                "fathom.application.billing.refunds.polar.create_order_refund",
                AsyncMock(side_effect=RuntimeError("network wobble")),
            ),
        ):
            response = await request_pack_refund(
                polar_order_id="ord_123",
                auth=self.auth,
                settings=self.settings,
            )

        reopen_refund.assert_not_awaited()
        self.assertEqual(str(response.operation_id), self.operation_id)
        self.assertEqual(response.status, "pending_webhook_confirmation")

    async def test_database_resolution_is_mapped_without_calling_polar(self) -> None:
        cases = {
            "not_found": "Pack order not found.",
            "not_pack": "Only pack orders can be refunded from this endpoint.",
            "already_pending": "Refund is already in progress for this order.",
            "already_refunded": "This order has already been refunded.",
            "lot_not_found": "Pack lot not found for this order.",
            "not_refundable": "Order is not refundable.",
            "nothing_remaining": "No refundable amount remaining for this pack order.",
        }
        for resolution_type, message in cases.items():
            with self.subTest(resolution_type=resolution_type):
                with (
                    patch(
                        "fathom.application.billing.refunds.create_supabase_admin_client",
                        AsyncMock(return_value=self.admin_client),
                    ),
                    patch(
                        "fathom.application.billing.refunds.begin_pack_refund",
                        AsyncMock(return_value={"resolution_type": resolution_type}),
                    ),
                    patch(
                        "fathom.application.billing.refunds.polar.create_order_refund",
                        AsyncMock(),
                    ) as create_refund,
                ):
                    with self.assertRaisesRegex(InvalidRequestError, message.replace(".", r"\.")):
                        await request_pack_refund(
                            polar_order_id="ord_123",
                            auth=self.auth,
                            settings=self.settings,
                        )
                create_refund.assert_not_awaited()

    async def test_active_briefings_block_refund_with_user_facing_conflict(self) -> None:
        with (
            patch(
                "fathom.application.billing.refunds.create_supabase_admin_client",
                AsyncMock(return_value=self.admin_client),
            ),
            patch(
                "fathom.application.billing.refunds.begin_pack_refund",
                AsyncMock(return_value={"resolution_type": "active_jobs_in_progress"}),
            ),
            patch(
                "fathom.application.billing.refunds.polar.create_order_refund",
                AsyncMock(),
            ) as create_refund,
        ):
            with self.assertRaisesRegex(
                ActiveBriefingsRefundError,
                r"Wait for your active briefings to finish before requesting this refund\.",
            ) as raised:
                await request_pack_refund(
                    polar_order_id="ord_123",
                    auth=self.auth,
                    settings=self.settings,
                )

        self.assertEqual(raised.exception.code, "active_briefings_refund_blocked")
        self.assertEqual(raised.exception.status_code, 409)
        self.resolve_operation.assert_awaited_once_with(
            self.admin_client,
            operation_id=self.operation_id,
            user_id="user_123",
            operation_type="refund",
            polar_order_id="ord_123",
            status="failed",
            failure_code="refund_not_started",
        )
        create_refund.assert_not_awaited()

    async def test_invalid_authoritative_amount_fails_closed(self) -> None:
        invalid_started = {
            "resolution_type": "started",
            "refundable_amount_cents": 0,
            "remaining_seconds_before_refund": 2700,
        }
        with (
            patch(
                "fathom.application.billing.refunds.create_supabase_admin_client",
                AsyncMock(return_value=self.admin_client),
            ),
            patch(
                "fathom.application.billing.refunds.begin_pack_refund",
                AsyncMock(return_value=invalid_started),
            ),
            patch(
                "fathom.application.billing.refunds.polar.create_order_refund",
                AsyncMock(),
            ) as create_refund,
        ):
            with self.assertRaises(ExternalServiceError):
                await request_pack_refund(
                    polar_order_id="ord_123",
                    auth=self.auth,
                    settings=self.settings,
                )

        create_refund.assert_not_awaited()
