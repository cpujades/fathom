from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

from fathom.application.billing.recovery import (
    _maintain_billing_maintenance_lease,
    _run_claimed_billing_maintenance,
    reconcile_pending_pack_refunds,
    reconcile_subscription_entitlements,
    run_billing_maintenance,
)
from fathom.core.config import Settings
from fathom.core.errors import ExternalServiceError


class BillingRecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.admin_client = object()
        self.settings = cast(Settings, SimpleNamespace(billing_debt_cap_seconds=600))

    async def test_maintenance_skips_when_another_worker_owns_lease(self) -> None:
        with (
            patch(
                "fathom.application.billing.recovery.claim_billing_maintenance_lease",
                AsyncMock(return_value=False),
            ),
            patch(
                "fathom.application.billing.recovery._run_claimed_billing_maintenance",
                AsyncMock(),
            ) as run_claimed,
            patch(
                "fathom.application.billing.recovery.release_billing_maintenance_lease",
                AsyncMock(),
            ) as release,
        ):
            summary = await run_billing_maintenance(self.admin_client, settings=self.settings)

        self.assertEqual(summary, {"maintenance_skipped": 1})
        run_claimed.assert_not_awaited()
        release.assert_not_awaited()

    async def test_maintenance_releases_owned_lease(self) -> None:
        expected = {"maintenance_skipped": 0, "requeued_unsettled_jobs": 1}
        with (
            patch(
                "fathom.application.billing.recovery.claim_billing_maintenance_lease",
                AsyncMock(return_value=True),
            ) as claim,
            patch(
                "fathom.application.billing.recovery._run_claimed_billing_maintenance",
                AsyncMock(return_value=expected),
            ),
            patch(
                "fathom.application.billing.recovery.release_billing_maintenance_lease",
                AsyncMock(return_value=True),
            ) as release,
        ):
            summary = await run_billing_maintenance(self.admin_client, settings=self.settings)

        self.assertEqual(summary, expected)
        self.assertIsNotNone(claim.await_args)
        self.assertIsNotNone(release.await_args)
        assert claim.await_args is not None
        assert release.await_args is not None
        claim_kwargs = claim.await_args.kwargs
        release_kwargs = release.await_args.kwargs
        self.assertEqual(claim_kwargs["lease_name"], "billing-recovery")
        self.assertEqual(claim_kwargs["lease_token"], release_kwargs["lease_token"])
        self.assertEqual(release_kwargs["lease_name"], "billing-recovery")

    async def test_lease_heartbeat_fails_closed_when_ownership_is_lost(self) -> None:
        with (
            patch("fathom.application.billing.recovery.asyncio.sleep", AsyncMock()),
            patch(
                "fathom.application.billing.recovery.renew_billing_maintenance_lease",
                AsyncMock(return_value=False),
            ),
        ):
            with self.assertRaisesRegex(ExternalServiceError, "lease was lost"):
                await _maintain_billing_maintenance_lease(
                    self.admin_client,
                    lease_token="token-123",
                )

    async def test_lost_lease_cancels_maintenance_and_releases_ownership(self) -> None:
        maintenance_cancelled = False

        async def blocked_maintenance(*_args: object, **_kwargs: object) -> dict[str, int]:
            nonlocal maintenance_cancelled
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                maintenance_cancelled = True
                raise

        with (
            patch(
                "fathom.application.billing.recovery.claim_billing_maintenance_lease",
                AsyncMock(return_value=True),
            ),
            patch(
                "fathom.application.billing.recovery._run_claimed_billing_maintenance",
                side_effect=blocked_maintenance,
            ),
            patch(
                "fathom.application.billing.recovery._maintain_billing_maintenance_lease",
                AsyncMock(side_effect=ExternalServiceError("Billing maintenance lease was lost.")),
            ),
            patch(
                "fathom.application.billing.recovery.release_billing_maintenance_lease",
                AsyncMock(return_value=False),
            ) as release,
        ):
            with self.assertRaisesRegex(ExternalServiceError, "lease was lost"):
                await run_billing_maintenance(self.admin_client, settings=self.settings)

        self.assertTrue(maintenance_cancelled)
        release.assert_awaited_once()

    async def test_claimed_maintenance_reports_recovery_and_diagnostics(self) -> None:
        with (
            patch(
                "fathom.application.billing.recovery.requeue_unsettled_jobs",
                AsyncMock(return_value=2),
            ) as requeue,
            patch(
                "fathom.application.billing.recovery.reclaim_stale_webhook_processing",
                AsyncMock(return_value=1),
            ),
            patch(
                "fathom.application.billing.recovery.reconcile_pending_pack_refunds",
                AsyncMock(return_value=3),
            ),
            patch(
                "fathom.application.billing.recovery.reconcile_subscription_entitlements",
                AsyncMock(return_value=4),
            ),
            patch(
                "fathom.application.billing.recovery.get_billing_webhook_diagnostics",
                AsyncMock(
                    return_value={
                        "failed_count": 2,
                        "deferred_count": 1,
                        "stale_processing_count": 0,
                        "deferred_unknown_order_count": 1,
                    }
                ),
            ),
        ):
            summary = await _run_claimed_billing_maintenance(
                self.admin_client,
                settings=self.settings,
            )

        requeue.assert_awaited_once_with(self.admin_client)
        self.assertEqual(summary["maintenance_skipped"], 0)
        self.assertEqual(summary["requeued_unsettled_jobs"], 2)
        self.assertEqual(summary["reclaimed_webhook_events"], 1)
        self.assertEqual(summary["reconciled_refund_pending_orders"], 3)
        self.assertEqual(summary["reconciled_subscriptions"], 4)
        self.assertEqual(summary["failed_webhook_events"], 2)

    async def test_provider_confirmed_refund_uses_ordered_webhook_transaction(self) -> None:
        order = {
            "id": "order-row-1",
            "polar_order_id": "ord_123",
            "user_id": "user_123",
            "status": "refund_pending",
            "plan_type": "pack",
        }
        provider_order = {
            "id": "ord_123",
            "status": "paid",
            "refunded_amount": 1200,
            "modified_at": "2026-04-01T12:00:00+00:00",
        }
        with (
            patch(
                "fathom.application.billing.recovery.list_refund_pending_pack_orders",
                AsyncMock(return_value=[order]),
            ),
            patch(
                "fathom.application.billing.recovery.polar.get_order",
                AsyncMock(return_value=provider_order),
            ),
            patch(
                "fathom.application.billing.recovery.apply_polar_webhook_transaction",
                AsyncMock(return_value={"resolution_type": "processed", "outcome": "refunded"}),
            ) as apply_transaction,
            patch("fathom.application.billing.recovery.reopen_pack_refund", AsyncMock()) as reopen,
        ):
            reconciled = await reconcile_pending_pack_refunds(
                self.admin_client,
                settings=self.settings,
            )

        self.assertEqual(reconciled, 1)
        reopen.assert_not_awaited()
        self.assertIsNotNone(apply_transaction.await_args)
        assert apply_transaction.await_args is not None
        kwargs = apply_transaction.await_args.kwargs
        self.assertEqual(kwargs["event_type"], "order.refunded")
        self.assertEqual(kwargs["resource_type"], "order")
        self.assertEqual(kwargs["resource_id"], "ord_123")
        self.assertEqual(kwargs["payload"]["provider_total_refunded"], 1200)
        self.assertEqual(kwargs["event_at"], datetime(2026, 4, 1, 12, tzinfo=UTC))

    async def test_paid_provider_state_atomically_reopens_pending_refund(self) -> None:
        order = {
            "id": "order-row-1",
            "polar_order_id": "ord_123",
            "user_id": "user_123",
            "status": "refund_pending",
            "plan_type": "pack",
        }
        with (
            patch(
                "fathom.application.billing.recovery.list_refund_pending_pack_orders",
                AsyncMock(return_value=[order]),
            ),
            patch(
                "fathom.application.billing.recovery.polar.get_order",
                AsyncMock(return_value={"id": "ord_123", "status": "paid", "refunded_amount": 0}),
            ),
            patch(
                "fathom.application.billing.recovery.reopen_pack_refund",
                AsyncMock(return_value={"resolution_type": "reopened"}),
            ) as reopen,
            patch(
                "fathom.application.billing.recovery.apply_polar_webhook_transaction",
                AsyncMock(),
            ) as apply_transaction,
        ):
            reconciled = await reconcile_pending_pack_refunds(
                self.admin_client,
                settings=self.settings,
            )

        self.assertEqual(reconciled, 1)
        reopen.assert_awaited_once_with(
            self.admin_client,
            user_id="user_123",
            polar_order_id="ord_123",
            debt_cap_seconds=600,
        )
        apply_transaction.assert_not_awaited()

    async def test_confirmed_refund_without_provider_timestamp_is_not_applied(self) -> None:
        order = {
            "polar_order_id": "ord_123",
            "user_id": "user_123",
            "status": "refund_pending",
        }
        with (
            patch(
                "fathom.application.billing.recovery.list_refund_pending_pack_orders",
                AsyncMock(return_value=[order]),
            ),
            patch(
                "fathom.application.billing.recovery.polar.get_order",
                AsyncMock(return_value={"id": "ord_123", "status": "paid", "refunded_amount": 1200}),
            ),
            patch(
                "fathom.application.billing.recovery.apply_polar_webhook_transaction",
                AsyncMock(),
            ) as apply_transaction,
        ):
            reconciled = await reconcile_pending_pack_refunds(
                self.admin_client,
                settings=self.settings,
            )

        self.assertEqual(reconciled, 0)
        apply_transaction.assert_not_awaited()

    async def test_subscription_reconciliation_uses_provider_ordering_transaction(self) -> None:
        provider_subscription = {
            "id": "sub_123",
            "customer_external_id": "user_123",
            "product_id": "prod_123",
            "status": "past_due",
            "current_period_start": "2026-04-01T00:00:00+00:00",
            "current_period_end": "2026-05-01T00:00:00+00:00",
            "modified_at": "2026-04-02T00:00:00+00:00",
        }
        with (
            patch(
                "fathom.application.billing.recovery.list_subscription_entitlements_for_reconciliation",
                AsyncMock(
                    return_value=[
                        {
                            "user_id": "user_123",
                            "subscription_status": "active",
                            "polar_subscription_id": "sub_123",
                        }
                    ]
                ),
            ),
            patch(
                "fathom.application.billing.recovery.polar.get_subscription",
                AsyncMock(return_value=provider_subscription),
            ),
            patch(
                "fathom.application.billing.recovery.apply_polar_webhook_transaction",
                AsyncMock(return_value={"resolution_type": "processed", "outcome": "applied"}),
            ) as apply_transaction,
            patch(
                "fathom.application.billing.recovery.schedule_subscription_reconciliation",
                AsyncMock(),
            ) as schedule_reconciliation,
        ):
            started_at = datetime.now(UTC)
            reconciled = await reconcile_subscription_entitlements(
                self.admin_client,
                settings=self.settings,
            )

        self.assertEqual(reconciled, 1)
        self.assertIsNotNone(apply_transaction.await_args)
        assert apply_transaction.await_args is not None
        kwargs = apply_transaction.await_args.kwargs
        self.assertEqual(kwargs["event_type"], "subscription.updated")
        self.assertEqual(kwargs["resource_type"], "subscription")
        self.assertEqual(kwargs["resource_id"], "sub_123")
        self.assertEqual(kwargs["payload"]["status"], "past_due")
        self.assertTrue(kwargs["event_id"].startswith("reconcile:subscription:sub_123:"))
        schedule_reconciliation.assert_awaited_once()
        assert schedule_reconciliation.await_args is not None
        schedule_kwargs = schedule_reconciliation.await_args.kwargs
        self.assertEqual(schedule_kwargs["user_id"], "user_123")
        self.assertGreaterEqual(schedule_kwargs["next_reconcile_at"], started_at + timedelta(hours=6))

    async def test_subscription_without_provider_order_id_is_skipped(self) -> None:
        with (
            patch(
                "fathom.application.billing.recovery.list_subscription_entitlements_for_reconciliation",
                AsyncMock(return_value=[{"user_id": "user_123", "subscription_status": "active"}]),
            ),
            patch("fathom.application.billing.recovery.polar.get_subscription", AsyncMock()) as get_subscription,
        ):
            reconciled = await reconcile_subscription_entitlements(
                self.admin_client,
                settings=self.settings,
            )

        self.assertEqual(reconciled, 0)
        get_subscription.assert_not_awaited()

    async def test_subscription_provider_failure_is_retried_later(self) -> None:
        with (
            patch(
                "fathom.application.billing.recovery.list_subscription_entitlements_for_reconciliation",
                AsyncMock(return_value=[{"user_id": "user_123", "polar_subscription_id": "sub_123"}]),
            ),
            patch(
                "fathom.application.billing.recovery.polar.get_subscription",
                AsyncMock(side_effect=ExternalServiceError("Polar unavailable")),
            ),
            patch(
                "fathom.application.billing.recovery.schedule_subscription_reconciliation",
                AsyncMock(),
            ) as schedule_reconciliation,
            patch(
                "fathom.application.billing.recovery.apply_polar_webhook_transaction",
                AsyncMock(),
            ) as apply_transaction,
        ):
            started_at = datetime.now(UTC)
            reconciled = await reconcile_subscription_entitlements(
                self.admin_client,
                settings=self.settings,
            )

        self.assertEqual(reconciled, 0)
        apply_transaction.assert_not_awaited()
        schedule_reconciliation.assert_awaited_once()
        assert schedule_reconciliation.await_args is not None
        next_reconcile_at = schedule_reconciliation.await_args.kwargs["next_reconcile_at"]
        self.assertGreaterEqual(next_reconcile_at, started_at + timedelta(minutes=15))

    async def test_terminal_subscription_disables_future_provider_polling(self) -> None:
        provider_subscription = {
            "id": "sub_123",
            "customer_external_id": "user_123",
            "product_id": "prod_123",
            "status": "revoked",
            "current_period_start": "2026-04-01T00:00:00+00:00",
            "current_period_end": "2026-05-01T00:00:00+00:00",
            "modified_at": "2026-05-02T00:00:00+00:00",
        }
        with (
            patch(
                "fathom.application.billing.recovery.list_subscription_entitlements_for_reconciliation",
                AsyncMock(return_value=[{"user_id": "user_123", "polar_subscription_id": "sub_123"}]),
            ),
            patch(
                "fathom.application.billing.recovery.polar.get_subscription",
                AsyncMock(return_value=provider_subscription),
            ),
            patch(
                "fathom.application.billing.recovery.apply_polar_webhook_transaction",
                AsyncMock(return_value={"resolution_type": "processed", "outcome": "applied"}),
            ),
            patch(
                "fathom.application.billing.recovery.schedule_subscription_reconciliation",
                AsyncMock(),
            ) as schedule_reconciliation,
        ):
            reconciled = await reconcile_subscription_entitlements(
                self.admin_client,
                settings=self.settings,
            )

        self.assertEqual(reconciled, 1)
        schedule_reconciliation.assert_awaited_once_with(
            self.admin_client,
            user_id="user_123",
            next_reconcile_at=None,
        )
