from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fathom.application.billing.recovery import run_billing_maintenance


class BillingRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_maintenance_applies_provider_confirmed_refund(self) -> None:
        admin_client = object()
        order = {
            "id": "order-row-1",
            "polar_order_id": "ord_123",
            "user_id": "user_123",
            "status": "refund_pending",
            "plan_type": "pack",
            "paid_amount_cents": 3000,
            "refunded_amount_cents": 0,
        }

        with (
            patch("fathom.application.billing.recovery.reclaim_stale_webhook_processing", AsyncMock(return_value=0)),
            patch(
                "fathom.application.billing.recovery.list_refund_pending_pack_orders",
                AsyncMock(return_value=[order]),
            ),
            patch(
                "fathom.application.billing.recovery.list_subscription_entitlements_for_reconciliation",
                AsyncMock(return_value=[]),
            ),
            patch(
                "fathom.application.billing.recovery.list_latest_subscription_orders_for_users",
                AsyncMock(return_value={}),
            ),
            patch(
                "fathom.application.billing.recovery.polar.get_order",
                AsyncMock(return_value={"id": "ord_123", "status": "paid", "refunded_amount": 1200}),
            ),
            patch("fathom.application.billing.recovery.apply_order_refund_state", AsyncMock()) as apply_refund_state,
            patch(
                "fathom.application.billing.recovery.transition_billing_order_status",
                AsyncMock(return_value=False),
            ) as reopen_order,
        ):
            summary = await run_billing_maintenance(
                admin_client,
                settings=SimpleNamespace(billing_debt_cap_seconds=600),
            )

        apply_refund_state.assert_awaited_once()
        reopen_order.assert_not_awaited()
        self.assertEqual(summary["reconciled_refund_pending_orders"], 1)

    async def test_maintenance_reopens_stuck_refund_pending_order_when_provider_shows_paid(self) -> None:
        admin_client = object()
        order = {
            "id": "order-row-1",
            "polar_order_id": "ord_123",
            "user_id": "user_123",
            "status": "refund_pending",
            "plan_type": "pack",
            "paid_amount_cents": 3000,
            "refunded_amount_cents": 0,
        }

        with (
            patch("fathom.application.billing.recovery.reclaim_stale_webhook_processing", AsyncMock(return_value=0)),
            patch(
                "fathom.application.billing.recovery.list_refund_pending_pack_orders",
                AsyncMock(return_value=[order]),
            ),
            patch(
                "fathom.application.billing.recovery.list_subscription_entitlements_for_reconciliation",
                AsyncMock(return_value=[]),
            ),
            patch(
                "fathom.application.billing.recovery.list_latest_subscription_orders_for_users",
                AsyncMock(return_value={}),
            ),
            patch(
                "fathom.application.billing.recovery.polar.get_order",
                AsyncMock(return_value={"id": "ord_123", "status": "paid", "refunded_amount": 0}),
            ),
            patch("fathom.application.billing.recovery.apply_order_refund_state", AsyncMock()) as apply_refund_state,
            patch(
                "fathom.application.billing.recovery.transition_billing_order_status",
                AsyncMock(return_value=True),
            ) as reopen_order,
            patch("fathom.application.billing.recovery.sync_entitlement_snapshot", AsyncMock()) as sync_snapshot,
        ):
            await run_billing_maintenance(admin_client, settings=SimpleNamespace(billing_debt_cap_seconds=600))

        apply_refund_state.assert_not_awaited()
        reopen_order.assert_awaited_once()
        sync_snapshot.assert_awaited_once()

    async def test_maintenance_reconciles_subscription_entitlements_from_provider_truth(self) -> None:
        admin_client = object()
        entitlement = {
            "user_id": "user_123",
            "subscription_plan_id": "plan_123",
            "subscription_status": "active",
        }
        latest_order = {
            "user_id": "user_123",
            "polar_subscription_id": "sub_123",
        }
        provider_subscription = {
            "id": "sub_123",
            "customer_external_id": "user_123",
            "product_id": "prod_123",
            "status": "past_due",
            "current_period_start": "2026-04-01T00:00:00+00:00",
            "current_period_end": "2026-05-01T00:00:00+00:00",
        }

        with (
            patch("fathom.application.billing.recovery.reclaim_stale_webhook_processing", AsyncMock(return_value=0)),
            patch("fathom.application.billing.recovery.list_refund_pending_pack_orders", AsyncMock(return_value=[])),
            patch(
                "fathom.application.billing.recovery.list_subscription_entitlements_for_reconciliation",
                AsyncMock(return_value=[entitlement]),
            ),
            patch(
                "fathom.application.billing.recovery.list_latest_subscription_orders_for_users",
                AsyncMock(return_value={"user_123": latest_order}),
            ),
            patch(
                "fathom.application.billing.recovery.polar.get_subscription",
                AsyncMock(return_value=provider_subscription),
            ),
            patch("fathom.application.billing.recovery.apply_subscription_event", AsyncMock()) as apply_subscription,
        ):
            await run_billing_maintenance(admin_client, settings=SimpleNamespace(billing_debt_cap_seconds=600))

        apply_subscription.assert_awaited_once_with(
            admin_client,
            provider_subscription,
            unittest.mock.ANY,
            event_type="subscription.reconciled",
        )

    async def test_maintenance_skips_subscription_reconciliation_without_provider_subscription_id(self) -> None:
        admin_client = object()
        entitlement = {
            "user_id": "user_123",
            "subscription_plan_id": "plan_123",
            "subscription_status": "active",
        }

        with (
            patch("fathom.application.billing.recovery.reclaim_stale_webhook_processing", AsyncMock(return_value=0)),
            patch("fathom.application.billing.recovery.list_refund_pending_pack_orders", AsyncMock(return_value=[])),
            patch(
                "fathom.application.billing.recovery.list_subscription_entitlements_for_reconciliation",
                AsyncMock(return_value=[entitlement]),
            ),
            patch(
                "fathom.application.billing.recovery.list_latest_subscription_orders_for_users",
                AsyncMock(return_value={}),
            ),
            patch("fathom.application.billing.recovery.polar.get_subscription", AsyncMock()) as get_subscription,
            patch("fathom.application.billing.recovery.apply_subscription_event", AsyncMock()) as apply_subscription,
        ):
            await run_billing_maintenance(admin_client, settings=SimpleNamespace(billing_debt_cap_seconds=600))

        get_subscription.assert_not_awaited()
        apply_subscription.assert_not_awaited()
