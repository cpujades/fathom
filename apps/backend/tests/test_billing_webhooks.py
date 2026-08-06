from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, patch

from fathom.application.billing.webhooks import handle_polar_webhook
from fathom.core.errors import ExternalServiceError

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "polar_webhook_replay.json"


class BillingWebhookTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.resolve_checkout_operation = self.enterContext(
            patch(
                "fathom.application.billing.webhooks.resolve_billing_sync_operation",
                AsyncMock(return_value="resolved"),
            )
        )
        self.resolve_refund_operations = self.enterContext(
            patch(
                "fathom.application.billing.webhooks.resolve_refund_sync_operations",
                AsyncMock(return_value=1),
            )
        )

    async def test_paid_order_resolves_exact_metadata_operation_for_event_owner(self) -> None:
        event = json.loads(FIXTURE_PATH.read_text())["events"][0]
        operation_id = "97000000-0000-0000-0000-000000000001"
        plan_id = "97000000-0000-0000-0000-000000000002"
        event["data"]["metadata"] = {"billing_operation_id": operation_id, "plan_id": plan_id}

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
                AsyncMock(return_value={"resolution_type": "processed", "outcome": "applied"}),
            ),
        ):
            await handle_polar_webhook(
                b"fixture",
                {"webhook-id": event["id"]},
                SimpleNamespace(),
            )

        self.resolve_checkout_operation.assert_awaited_once_with(
            ANY,
            operation_id=operation_id,
            user_id=event["data"]["customer_external_id"],
            operation_type="checkout",
            plan_id=plan_id,
            polar_order_id=event["data"]["id"],
            status="succeeded",
        )

    async def test_correlation_mismatch_is_observable_without_rolling_back_billing(self) -> None:
        event = json.loads(FIXTURE_PATH.read_text())["events"][0]
        event["data"]["metadata"] = {
            "billing_operation_id": "97000000-0000-0000-0000-000000000001",
            "plan_id": "97000000-0000-0000-0000-000000000002",
        }
        apply_transaction = AsyncMock(return_value={"resolution_type": "processed", "outcome": "applied"})
        self.resolve_checkout_operation.return_value = "correlation_mismatch"

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
            self.assertLogs("fathom.application.billing.webhooks", level="WARNING") as logs,
        ):
            await handle_polar_webhook(b"fixture", {"webhook-id": event["id"]}, SimpleNamespace())

        apply_transaction.assert_awaited_once()
        self.assertTrue(any("operation_correlation_mismatch" in entry for entry in logs.output))

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
                    SimpleNamespace(),
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
                SimpleNamespace(),
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
                    SimpleNamespace(),
                )
