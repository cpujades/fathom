from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fathom.application.billing.webhooks import handle_polar_webhook
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
