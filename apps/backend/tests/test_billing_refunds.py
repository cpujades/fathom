from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fathom.api.deps.auth import AuthContext
from fathom.application.billing.refunds import request_pack_refund
from fathom.core.errors import InvalidRequestError
from fathom.services.polar import PolarInvalidRequestError


class BillingRefundTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_refund_conflict_keeps_order_refund_pending(self) -> None:
        admin_client = object()
        auth = AuthContext(access_token="token", user_id="user_123")
        order = {
            "id": "order-row-1",
            "plan_type": "pack",
            "status": "paid",
            "paid_amount_cents": 3000,
        }
        lot = {
            "granted_seconds": 3600,
            "consumed_seconds": 600,
            "revoked_seconds": 0,
        }

        with (
            patch(
                "fathom.application.billing.refunds.create_supabase_admin_client",
                AsyncMock(return_value=admin_client),
            ),
            patch("fathom.application.billing.refunds.fetch_billing_order_for_user", AsyncMock(return_value=order)),
            patch("fathom.application.billing.refunds.fetch_credit_lot_by_source", AsyncMock(return_value=lot)),
            patch(
                "fathom.application.billing.refunds.transition_billing_order_status",
                AsyncMock(return_value=True),
            ) as transition_status,
            patch("fathom.application.billing.refunds.sync_entitlement_snapshot", AsyncMock()) as sync_snapshot,
            patch(
                "fathom.application.billing.refunds.polar.create_order_refund",
                AsyncMock(side_effect=PolarInvalidRequestError("duplicate", http_status=409)),
            ),
        ):
            with self.assertRaises(InvalidRequestError):
                await request_pack_refund(
                    polar_order_id="ord_123",
                    auth=auth,
                    settings=SimpleNamespace(),
                )

        self.assertEqual(transition_status.await_count, 1)
        sync_snapshot.assert_awaited_once()

    async def test_definitive_refund_failure_reopens_order_and_resyncs(self) -> None:
        admin_client = object()
        auth = AuthContext(access_token="token", user_id="user_123")
        order = {
            "id": "order-row-1",
            "plan_type": "pack",
            "status": "paid",
            "paid_amount_cents": 3000,
        }
        lot = {
            "granted_seconds": 3600,
            "consumed_seconds": 600,
            "revoked_seconds": 0,
        }

        with (
            patch(
                "fathom.application.billing.refunds.create_supabase_admin_client",
                AsyncMock(return_value=admin_client),
            ),
            patch("fathom.application.billing.refunds.fetch_billing_order_for_user", AsyncMock(return_value=order)),
            patch("fathom.application.billing.refunds.fetch_credit_lot_by_source", AsyncMock(return_value=lot)),
            patch(
                "fathom.application.billing.refunds.transition_billing_order_status",
                AsyncMock(side_effect=[True, True]),
            ) as transition_status,
            patch("fathom.application.billing.refunds.sync_entitlement_snapshot", AsyncMock()) as sync_snapshot,
            patch(
                "fathom.application.billing.refunds.polar.create_order_refund",
                AsyncMock(side_effect=PolarInvalidRequestError("bad request", http_status=400)),
            ),
        ):
            with self.assertRaises(PolarInvalidRequestError):
                await request_pack_refund(
                    polar_order_id="ord_123",
                    auth=auth,
                    settings=SimpleNamespace(),
                )

        self.assertEqual(transition_status.await_count, 2)
        self.assertEqual(sync_snapshot.await_count, 2)

    async def test_unknown_refund_outcome_keeps_order_refund_pending(self) -> None:
        admin_client = object()
        auth = AuthContext(access_token="token", user_id="user_123")
        order = {
            "id": "order-row-1",
            "plan_type": "pack",
            "status": "paid",
            "paid_amount_cents": 3000,
        }
        lot = {
            "granted_seconds": 3600,
            "consumed_seconds": 600,
            "revoked_seconds": 0,
        }

        with (
            patch(
                "fathom.application.billing.refunds.create_supabase_admin_client",
                AsyncMock(return_value=admin_client),
            ),
            patch("fathom.application.billing.refunds.fetch_billing_order_for_user", AsyncMock(return_value=order)),
            patch("fathom.application.billing.refunds.fetch_credit_lot_by_source", AsyncMock(return_value=lot)),
            patch(
                "fathom.application.billing.refunds.transition_billing_order_status",
                AsyncMock(return_value=True),
            ) as transition_status,
            patch("fathom.application.billing.refunds.sync_entitlement_snapshot", AsyncMock()) as sync_snapshot,
            patch(
                "fathom.application.billing.refunds.polar.create_order_refund",
                AsyncMock(side_effect=RuntimeError("network wobble")),
            ),
        ):
            with self.assertRaises(RuntimeError):
                await request_pack_refund(
                    polar_order_id="ord_123",
                    auth=auth,
                    settings=SimpleNamespace(),
                )

        self.assertEqual(transition_status.await_count, 1)
        sync_snapshot.assert_awaited_once()
