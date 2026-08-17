from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

from fathom.application.billing.checkout import create_checkout_session
from fathom.application.identity import AuthenticatedUser
from fathom.core.config import Settings

PLAN_ID = "97000000-0000-0000-0000-000000000001"
OPERATION_ID = "97000000-0000-0000-0000-000000000002"


class BillingCheckoutTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.admin_client = object()
        self.auth = AuthenticatedUser(
            access_token="token",
            user_id="97000000-0000-0000-0000-000000000003",
        )
        self.settings = cast(
            Settings,
            SimpleNamespace(
                polar_success_url="https://talven.example/app/billing?checkout=success",
                polar_checkout_return_url=None,
            ),
        )
        self.plan = {
            "is_active": True,
            "plan_type": "pack",
            "polar_product_id": "prod_creator",
            "plan_code": "creator_pack",
            "version": 1,
        }

    async def test_checkout_correlates_operation_in_metadata_and_success_url(self) -> None:
        with (
            patch(
                "fathom.application.billing.checkout.create_supabase_admin_client",
                AsyncMock(return_value=self.admin_client),
            ),
            patch("fathom.application.billing.checkout.fetch_plan_by_id", AsyncMock(return_value=self.plan)),
            patch("fathom.application.billing.checkout.upsert_polar_customer", AsyncMock()),
            patch(
                "fathom.application.billing.checkout.create_billing_sync_operation",
                AsyncMock(return_value=OPERATION_ID),
            ),
            patch(
                "fathom.application.billing.checkout.polar.create_checkout_session",
                AsyncMock(return_value="https://sandbox.polar.sh/checkout/123"),
            ) as create_checkout,
        ):
            response = await create_checkout_session(
                SimpleNamespace(plan_id=PLAN_ID),
                self.auth,
                self.settings,
            )

        self.assertEqual(str(response.operation_id), OPERATION_ID)
        create_checkout.assert_awaited_once()
        call = create_checkout.await_args.kwargs
        self.assertEqual(
            call["success_url"],
            f"https://talven.example/app/billing?checkout=success&billing_operation={OPERATION_ID}",
        )
        self.assertEqual(call["metadata"]["billing_operation_id"], OPERATION_ID)

    async def test_checkout_provider_failure_marks_operation_failed(self) -> None:
        with (
            patch(
                "fathom.application.billing.checkout.create_supabase_admin_client",
                AsyncMock(return_value=self.admin_client),
            ),
            patch("fathom.application.billing.checkout.fetch_plan_by_id", AsyncMock(return_value=self.plan)),
            patch("fathom.application.billing.checkout.upsert_polar_customer", AsyncMock()),
            patch(
                "fathom.application.billing.checkout.create_billing_sync_operation",
                AsyncMock(return_value=OPERATION_ID),
            ),
            patch(
                "fathom.application.billing.checkout.polar.create_checkout_session",
                AsyncMock(side_effect=RuntimeError("provider unavailable")),
            ),
            patch(
                "fathom.application.billing.checkout.resolve_billing_sync_operation",
                AsyncMock(),
            ) as resolve_operation,
        ):
            with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
                await create_checkout_session(
                    SimpleNamespace(plan_id=PLAN_ID),
                    self.auth,
                    self.settings,
                )

        resolve_operation.assert_awaited_once_with(
            self.admin_client,
            operation_id=OPERATION_ID,
            user_id=self.auth.user_id,
            operation_type="checkout",
            plan_id=PLAN_ID,
            status="failed",
            failure_code="checkout_initialization_failed",
        )


if __name__ == "__main__":
    unittest.main()
