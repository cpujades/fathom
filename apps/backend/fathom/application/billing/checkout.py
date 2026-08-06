from __future__ import annotations

import logging
from urllib.parse import urlsplit, urlunsplit

from pydantic import HttpUrl, TypeAdapter

from fathom.application.billing.parsing import as_str
from fathom.application.identity import AuthenticatedUser
from fathom.core.config import Settings
from fathom.core.errors import InvalidRequestError
from fathom.crud.supabase.billing import (
    create_billing_sync_operation,
    fetch_plan_by_id,
    resolve_billing_sync_operation,
    upsert_polar_customer,
)
from fathom.schemas.billing import CheckoutSessionRequest, CheckoutSessionResponse, CustomerPortalSessionResponse
from fathom.services import polar
from fathom.services.supabase import create_supabase_admin_client, managed_supabase_client
from supabase import AsyncClient

logger = logging.getLogger(__name__)
HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)


async def create_checkout_session(
    request: CheckoutSessionRequest,
    auth: AuthenticatedUser,
    settings: Settings,
) -> CheckoutSessionResponse:
    plan_id = str(request.plan_id)
    async with managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client:
        return await _create_checkout_session(plan_id, auth, settings, admin_client)


async def _create_checkout_session(
    plan_id: str,
    auth: AuthenticatedUser,
    settings: Settings,
    admin_client: AsyncClient,
) -> CheckoutSessionResponse:
    plan = await fetch_plan_by_id(admin_client, plan_id)
    if not plan.get("is_active"):
        raise InvalidRequestError("Plan is not active.")

    plan_type = str(plan["plan_type"])
    product_id = as_str(plan.get("polar_product_id"))
    if plan_type not in {"subscription", "pack"}:
        raise InvalidRequestError("Plan type is invalid.")
    if plan_type == "subscription" and product_id == "internal_free":
        raise InvalidRequestError("Free plan does not require checkout.")
    if not product_id:
        raise InvalidRequestError("Plan is missing a Polar product id.")

    await upsert_polar_customer(
        admin_client,
        user_id=auth.user_id,
        external_customer_id=auth.user_id,
    )

    operation_id = await create_billing_sync_operation(
        admin_client,
        user_id=auth.user_id,
        operation_type="checkout",
        plan_id=plan_id,
    )
    try:
        checkout_url = await polar.create_checkout_session(
            settings,
            product_id=product_id,
            external_customer_id=auth.user_id,
            success_url=_checkout_success_url(settings, operation_id),
            metadata={
                "user_id": auth.user_id,
                "plan_id": plan_id,
                "plan_code": str(plan.get("plan_code") or ""),
                "version": str(plan.get("version") or 1),
                "plan_type": plan_type,
                "billing_operation_id": operation_id,
            },
        )
    except Exception:
        try:
            await resolve_billing_sync_operation(
                admin_client,
                operation_id=operation_id,
                user_id=auth.user_id,
                operation_type="checkout",
                plan_id=plan_id,
                status="failed",
                failure_code="checkout_initialization_failed",
            )
        except Exception:
            logger.warning(
                "billing.checkout.operation_resolution_failed",
                exc_info=True,
            )
        raise

    logger.info(
        "billing.checkout.created",
        extra={"plan_type": plan_type},
    )
    return CheckoutSessionResponse(
        checkout_url=HTTP_URL_ADAPTER.validate_python(checkout_url),
        operation_id=operation_id,
    )


def _checkout_success_url(settings: Settings, operation_id: str) -> str:
    success_url = polar.get_polar_success_url(settings)
    parsed = urlsplit(success_url)
    operation_query = f"billing_operation={operation_id}"
    query = f"{parsed.query}&{operation_query}" if parsed.query else operation_query
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment))


async def create_portal_session(auth: AuthenticatedUser, settings: Settings) -> CustomerPortalSessionResponse:
    async with managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client:
        return await _create_portal_session(auth, settings, admin_client)


async def _create_portal_session(
    auth: AuthenticatedUser,
    settings: Settings,
    admin_client: AsyncClient,
) -> CustomerPortalSessionResponse:
    await upsert_polar_customer(
        admin_client,
        user_id=auth.user_id,
        external_customer_id=auth.user_id,
    )

    portal_url = await polar.create_customer_portal_session(
        settings,
        external_customer_id=auth.user_id,
    )

    return CustomerPortalSessionResponse(portal_url=HTTP_URL_ADAPTER.validate_python(portal_url))
