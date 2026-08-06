from __future__ import annotations

from fathom.application.identity import AuthenticatedUser
from fathom.core.config import Settings
from fathom.core.errors import NotFoundError
from fathom.crud.supabase.billing import fetch_billing_sync_operation
from fathom.schemas.billing import BillingSyncOperationResponse
from fathom.services.supabase import create_supabase_admin_client, managed_supabase_client


async def get_billing_sync_operation(
    *,
    operation_id: str,
    auth: AuthenticatedUser,
    settings: Settings,
) -> BillingSyncOperationResponse:
    async with managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client:
        operation = await fetch_billing_sync_operation(
            admin_client,
            operation_id=operation_id,
            user_id=auth.user_id,
        )

    if operation is None:
        # Unknown, expired, and other-user identifiers are intentionally
        # indistinguishable at this boundary.
        raise NotFoundError("Billing operation not found.")

    return BillingSyncOperationResponse(
        operation_id=operation["id"],
        operation_type=operation["operation_type"],
        status=operation["status"],
        failure_code=operation.get("failure_code"),
    )
