from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fathom.application.billing.webhooks import _handle_order_paid


class BillingWebhookTests(unittest.IsolatedAsyncioTestCase):
    async def test_order_paid_preserves_refund_pending_status_without_regranting_pack(self) -> None:
        admin_client = object()
        order_payload = {
            "id": "ord_123",
            "customer_external_id": "user_123",
            "product_id": "prod_123",
            "currency": "usd",
            "total_amount": 3000,
        }
        existing_order = {
            "id": "order-row-1",
            "status": "refund_pending",
        }
        plan = {
            "id": "plan_123",
            "plan_type": "pack",
            "currency": "usd",
            "quota_seconds": 3600,
            "pack_expiry_days": 30,
        }

        with (
            patch("fathom.application.billing.webhooks.fetch_plan_by_product_id", AsyncMock(return_value=plan)),
            patch(
                "fathom.application.billing.webhooks.fetch_billing_order_by_polar_id",
                AsyncMock(return_value=existing_order),
            ),
            patch("fathom.application.billing.webhooks.update_billing_order", AsyncMock()) as update_order,
            patch("fathom.application.billing.webhooks.upsert_billing_order", AsyncMock()) as upsert_order,
            patch("fathom.application.billing.webhooks.upsert_polar_customer", AsyncMock()),
            patch("fathom.application.billing.webhooks.upsert_credit_lot", AsyncMock()) as upsert_lot,
            patch("fathom.application.billing.webhooks.apply_debt_paydown_for_lot", AsyncMock()) as paydown,
            patch("fathom.application.billing.webhooks.sync_entitlement_snapshot", AsyncMock()) as sync_snapshot,
        ):
            await _handle_order_paid(
                admin_client,
                order_payload,
                SimpleNamespace(billing_debt_cap_seconds=600),
            )

        update_order.assert_awaited_once()
        update_values = update_order.await_args.kwargs["values"]
        self.assertEqual(update_values["status"], "refund_pending")
        upsert_order.assert_not_awaited()
        upsert_lot.assert_not_awaited()
        paydown.assert_not_awaited()
        sync_snapshot.assert_awaited_once()

    async def test_order_paid_preserves_refunded_status_without_regranting_pack(self) -> None:
        admin_client = object()
        order_payload = {
            "id": "ord_123",
            "customer_external_id": "user_123",
            "product_id": "prod_123",
            "currency": "usd",
            "total_amount": 3000,
        }
        existing_order = {
            "id": "order-row-1",
            "status": "refunded",
        }
        plan = {
            "id": "plan_123",
            "plan_type": "pack",
            "currency": "usd",
            "quota_seconds": 3600,
            "pack_expiry_days": 30,
        }

        with (
            patch("fathom.application.billing.webhooks.fetch_plan_by_product_id", AsyncMock(return_value=plan)),
            patch(
                "fathom.application.billing.webhooks.fetch_billing_order_by_polar_id",
                AsyncMock(return_value=existing_order),
            ),
            patch("fathom.application.billing.webhooks.update_billing_order", AsyncMock()) as update_order,
            patch("fathom.application.billing.webhooks.upsert_billing_order", AsyncMock()) as upsert_order,
            patch("fathom.application.billing.webhooks.upsert_polar_customer", AsyncMock()),
            patch("fathom.application.billing.webhooks.upsert_credit_lot", AsyncMock()) as upsert_lot,
            patch("fathom.application.billing.webhooks.apply_debt_paydown_for_lot", AsyncMock()) as paydown,
            patch("fathom.application.billing.webhooks.sync_entitlement_snapshot", AsyncMock()) as sync_snapshot,
        ):
            await _handle_order_paid(
                admin_client,
                order_payload,
                SimpleNamespace(billing_debt_cap_seconds=600),
            )

        update_order.assert_awaited_once()
        update_values = update_order.await_args.kwargs["values"]
        self.assertEqual(update_values["status"], "refunded")
        upsert_order.assert_not_awaited()
        upsert_lot.assert_not_awaited()
        paydown.assert_not_awaited()
        sync_snapshot.assert_awaited_once()
