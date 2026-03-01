from typing import Annotated

from fastapi import APIRouter, Depends, Path

from fathom.api.deps.auth import AuthContext, get_auth_context
from fathom.application.billing import (
    create_checkout_session,
    create_portal_session,
    get_billing_account,
    request_pack_refund,
)
from fathom.application.usage import get_usage_history, get_usage_overview
from fathom.core.config import Settings, get_settings
from fathom.schemas.billing import (
    BillingAccountResponse,
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
    auth: Annotated[AuthContext, Depends(get_auth_context)],
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
    auth: Annotated[AuthContext, Depends(get_auth_context)],
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
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PackRefundResponse:
    return await request_pack_refund(
        polar_order_id=polar_order_id,
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
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[PlanResponse]:
    from fathom.crud.supabase.billing import fetch_active_plans
    from fathom.services.supabase import create_supabase_admin_client

    admin_client = await create_supabase_admin_client(settings)
    plans = await fetch_active_plans(admin_client)
    return [
        PlanResponse(
            plan_id=plan["id"],
            plan_code=plan["plan_code"],
            name=plan["name"],
            plan_type=plan["plan_type"],
            polar_product_id=plan.get("polar_product_id"),
            currency=str(plan.get("currency") or "usd"),
            amount_cents=int(plan.get("amount_cents") or 0),
            billing_interval=plan.get("billing_interval"),
            version=int(plan.get("version") or 1),
            quota_seconds=plan.get("quota_seconds"),
            rollover_cap_seconds=plan.get("rollover_cap_seconds"),
            pack_expiry_days=plan.get("pack_expiry_days"),
            is_active=bool(plan.get("is_active")),
        )
        for plan in plans
    ]


@router.get(
    "/usage",
    response_model=UsageOverviewResponse,
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
    },
)
async def get_usage(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> UsageOverviewResponse:
    overview = await get_usage_overview(auth.user_id, settings)
    return UsageOverviewResponse(
        subscription_plan_name=overview.subscription_plan_name,
        subscription_remaining_seconds=overview.subscription_remaining,
        pack_remaining_seconds=overview.pack_remaining,
        total_remaining_seconds=overview.total_remaining,
        pack_expires_at=overview.pack_expires_at,
        debt_seconds=overview.debt_seconds,
        is_blocked=overview.is_blocked,
    )


@router.get(
    "/history",
    response_model=list[UsageHistoryEntry],
    responses={
        401: {"model": ErrorResponse, "description": "Missing or invalid auth token."},
        500: {"model": ErrorResponse, "description": "Unexpected server error."},
    },
)
async def get_history(
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[UsageHistoryEntry]:
    entries = await get_usage_history(auth.user_id, settings, limit=50)
    return [
        UsageHistoryEntry(
            job_id=entry.get("job_id"),
            seconds_used=int(entry.get("seconds_used") or 0),
            source=str(entry.get("source") or ""),
            created_at=entry.get("created_at"),
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
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BillingAccountResponse:
    return await get_billing_account(auth=auth, settings=settings)
