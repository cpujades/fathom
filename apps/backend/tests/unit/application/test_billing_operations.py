from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

from fathom.application.billing.operations import get_billing_sync_operation
from fathom.application.identity import AuthenticatedUser
from fathom.core.config import Settings
from fathom.core.errors import NotFoundError
from fathom.crud.supabase.billing_operations import resolve_billing_sync_operation


class BillingOperationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.admin_client = object()
        self.auth = AuthenticatedUser(access_token="token", user_id="user_123")
        self.settings = cast(Settings, SimpleNamespace())

    async def test_status_is_loaded_only_for_the_authenticated_user(self) -> None:
        operation_id = "97000000-0000-0000-0000-000000000002"
        fetch_operation = AsyncMock(
            return_value={
                "id": operation_id,
                "operation_type": "checkout",
                "status": "succeeded",
                "failure_code": None,
            }
        )
        with (
            patch(
                "fathom.application.billing.operations.create_supabase_admin_client",
                AsyncMock(return_value=self.admin_client),
            ),
            patch(
                "fathom.application.billing.operations.fetch_billing_sync_operation",
                fetch_operation,
            ),
        ):
            response = await get_billing_sync_operation(
                operation_id=operation_id,
                auth=self.auth,
                settings=self.settings,
            )

        fetch_operation.assert_awaited_once_with(
            self.admin_client,
            operation_id=operation_id,
            user_id="user_123",
        )
        self.assertEqual(response.status, "succeeded")

    async def test_unknown_expired_and_other_user_operations_share_not_found_response(self) -> None:
        with (
            patch(
                "fathom.application.billing.operations.create_supabase_admin_client",
                AsyncMock(return_value=self.admin_client),
            ),
            patch(
                "fathom.application.billing.operations.fetch_billing_sync_operation",
                AsyncMock(return_value=None),
            ),
        ):
            with self.assertRaisesRegex(NotFoundError, "Billing operation not found"):
                await get_billing_sync_operation(
                    operation_id="97000000-0000-0000-0000-000000000002",
                    auth=self.auth,
                    settings=self.settings,
                )

    async def test_resolution_returns_the_database_correlation_outcome(self) -> None:
        execute = AsyncMock(return_value=SimpleNamespace(data="correlation_mismatch"))
        client = SimpleNamespace(rpc=lambda *_args, **_kwargs: SimpleNamespace(execute=execute))

        result = await resolve_billing_sync_operation(
            client,
            operation_id="97000000-0000-0000-0000-000000000002",
            user_id="97000000-0000-0000-0000-000000000003",
            operation_type="checkout",
            plan_id="97000000-0000-0000-0000-000000000004",
            polar_order_id="ord_123",
            status="succeeded",
        )

        self.assertEqual(result, "correlation_mismatch")
        execute.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
