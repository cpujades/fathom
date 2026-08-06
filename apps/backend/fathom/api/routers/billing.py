from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from pydantic import TypeAdapter

from fathom.api.deps.auth import get_auth_context
from fathom.application.billing import (
    create_checkout_session,
    create_portal_session,
    get_billing_account,
    get_billing_sync_operation,
    list_billing_plans,
    request_pack_refund,
)
from fathom.application.identity import AuthenticatedUser
from fathom.application.usage import get_usage_history, get_usage_overview
from fathom.core.config import Settings, get_settings
from fathom.schemas.billing import (
    BillingAccountResponse,
    BillingSyncOperationResponse,
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    CustomerPortalSessionResponse,
    PackRefundResponse,
    PlanResponse,
    UsageHistoryEntry,
    UsageOverviewResponse,
)
from fathom.schemas.errors import ErrorResponse

router = APIRouter(prefix="/billing", tags=["billing"])
DATETIME_ADAPTER = TypeAdapter(datetime)


@router.post(
    "/checkout",
    response_model=CheckoutSessionResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        400: {"model": ErrorResponse, "description": "Invalid request payload."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def create_checkout(
    request: CheckoutSessionRequest,
    auth: Annotated[AuthenticatedUser, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CheckoutSessionResponse:
    return await create_checkout_session(request, auth, settings)


@router.post(
    "/portal",
    response_model=CustomerPortalSessionResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def create_portal(
    auth: Annotated[AuthenticatedUser, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CustomerPortalSessionResponse:
    return await create_portal_session(auth, settings)


@router.post(
    "/packs/{polar_order_id}/refund",
    response_model=PackRefundResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        400: {"model": ErrorResponse, "description": "Invalid request payload."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def refund_pack(
    polar_order_id: Annotated[str, Path(min_length=1)],
    auth: Annotated[AuthenticatedUser, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PackRefundResponse:
    return await request_pack_refund(
        polar_order_id=polar_order_id,
        auth=auth,
        settings=settings,
    )


@router.get(
    "/operations/{operation_id}",
    response_model=BillingSyncOperationResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        404: {"model": ErrorResponse, "description": "Billing operation not found."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
    },
)
async def get_operation(
    operation_id: UUID,
    auth: Annotated[AuthenticatedUser, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BillingSyncOperationResponse:
    return await get_billing_sync_operation(
        operation_id=str(operation_id),
        auth=auth,
        settings=settings,
    )


@router.get(
    "/plans",
    response_model=list[PlanResponse],
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
        502: {"model": ErrorResponse, "description": "Upstream provider failed."},
    },
)
async def list_plans(
    auth: Annotated[AuthenticatedUser, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[PlanResponse]:
    return await list_billing_plans(settings)


@router.get(
    "/usage",
    response_model=UsageOverviewResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
    },
)
async def get_usage(
    auth: Annotated[AuthenticatedUser, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UsageOverviewResponse:
    overview = await get_usage_overview(auth.user_id, settings)
    return UsageOverviewResponse(
        subscription_plan_name=overview.subscription_plan_name,
        has_active_paid_subscription=overview.has_active_paid_subscription,
        subscription_remaining_seconds=overview.subscription_remaining,
        pack_remaining_seconds=overview.pack_remaining,
        total_remaining_seconds=overview.total_remaining,
        pack_expires_at=overview.pack_expires_at,
        debt_seconds=overview.debt_seconds,
        is_blocked=overview.is_blocked,
    )


@router.get(
    "/briefings",
    response_model=list[UsageHistoryEntry],
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
    },
)
async def get_briefings(
    auth: Annotated[AuthenticatedUser, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[UsageHistoryEntry]:
    entries = await get_usage_history(auth.user_id, settings, limit=50)
    return [
        UsageHistoryEntry(
            job_id=entry.get("job_id"),
            title=entry.get("title"),
            seconds_used=int(entry.get("seconds_used") or 0),
            source=str(entry.get("source") or ""),
            created_at=DATETIME_ADAPTER.validate_python(entry.get("created_at")),
            session_path=f"/app/briefings/sessions/{entry.get('job_id')}" if entry.get("job_id") else None,
        )
        for entry in entries
    ]


@router.get(
    "/account",
    response_model=BillingAccountResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
    },
)
async def get_account(
    auth: Annotated[AuthenticatedUser, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BillingAccountResponse:
    return await get_billing_account(auth=auth, settings=settings)
