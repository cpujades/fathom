from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fathom.application.billing.webhooks import _handle_order_paid, handle_polar_webhook
from fathom.core.errors import ExternalServiceError

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "polar_webhook_replay.json"


class BillingWebhookTests(unittest.IsolatedAsyncioTestCase):
    async def test_replay_fixtures_are_normalized_and_sent_to_one_transaction_command(self) -> None:
        fixture = json.loads(FIXTURE_PATH.read_text())
        events = fixture["events"]
        apply_transaction = AsyncMock(
            side_effect=[
                {"resolution_type": "processed", "outcome": "applied"},
                {"resolution_type": "processed", "outcome": "applied"},
                {"resolution_type": "processed", "outcome": "applied"},
                {"resolution_type": "processed", "outcome": "applied"},
            ]
        )

        with (
            patch(
                "fathom.application.billing.webhooks.polar.verify_and_parse_webhook",
                side_effect=events,
            ),
            patch(
                "fathom.application.billing.webhooks.create_supabase_admin_client",
                AsyncMock(return_value=object()),
            ),
            patch(
                "fathom.application.billing.webhooks.apply_polar_webhook_transaction",
                apply_transaction,
            ),
        ):
            for event in events:
                await handle_polar_webhook(
                    b"fixture",
                    {"webhook-id": event["id"]},
                    SimpleNamespace(billing_debt_cap_seconds=600),
                )

        self.assertEqual(apply_transaction.await_count, len(events))
        paid_call = apply_transaction.await_args_list[0].kwargs
        self.assertEqual(paid_call["event_id"], "evt_order_paid_001")
        self.assertEqual(paid_call["resource_type"], "order")
        self.assertEqual(paid_call["resource_id"], "ord_replay_001")
        self.assertEqual(paid_call["payload"]["paid_amount_cents"], 3000)
        self.assertNotIn("metadata", paid_call["payload"])

        refund_call = apply_transaction.await_args_list[1].kwargs
        self.assertEqual(refund_call["payload"]["provider_total_refunded"], 3000)
        self.assertEqual(refund_call["payload"]["refund_delta_cents"], 0)

        active_call = apply_transaction.await_args_list[2].kwargs
        revoked_call = apply_transaction.await_args_list[3].kwargs
        self.assertLess(active_call["event_at"], revoked_call["event_at"])
        self.assertEqual(active_call["resource_id"], revoked_call["resource_id"])

    async def test_duplicate_resolution_is_acknowledged_without_reapplying_in_python(self) -> None:
        event = json.loads(FIXTURE_PATH.read_text())["events"][0]
        apply_transaction = AsyncMock(return_value={"resolution_type": "already_processed", "outcome": "applied"})

        with (
            patch(
                "fathom.application.billing.webhooks.polar.verify_and_parse_webhook",
                return_value=event,
            ),
            patch(
                "fathom.application.billing.webhooks.create_supabase_admin_client",
                AsyncMock(return_value=object()),
            ),
            patch(
                "fathom.application.billing.webhooks.apply_polar_webhook_transaction",
                apply_transaction,
            ),
        ):
            await handle_polar_webhook(
                b"fixture",
                {"webhook-id": event["id"]},
                SimpleNamespace(billing_debt_cap_seconds=600),
            )

        apply_transaction.assert_awaited_once()

    async def test_transaction_failure_returns_retryable_webhook_error(self) -> None:
        event = json.loads(FIXTURE_PATH.read_text())["events"][0]

        with (
            patch(
                "fathom.application.billing.webhooks.polar.verify_and_parse_webhook",
                return_value=event,
            ),
            patch(
                "fathom.application.billing.webhooks.create_supabase_admin_client",
                AsyncMock(return_value=object()),
            ),
            patch(
                "fathom.application.billing.webhooks.apply_polar_webhook_transaction",
                AsyncMock(return_value={"resolution_type": "failed", "outcome": "rolled_back"}),
            ),
        ):
            with self.assertRaises(ExternalServiceError):
                await handle_polar_webhook(
                    b"fixture",
                    {"webhook-id": event["id"]},
                    SimpleNamespace(billing_debt_cap_seconds=600),
                )

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
