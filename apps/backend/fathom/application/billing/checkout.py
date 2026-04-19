from __future__ import annotations

import logging

from pydantic import HttpUrl, TypeAdapter

from fathom.api.deps.auth import AuthContext
from fathom.application.billing.parsing import as_str
from fathom.core.config import Settings
from fathom.core.errors import InvalidRequestError
from fathom.crud.supabase.billing import fetch_plan_by_id, upsert_polar_customer
from fathom.schemas.billing import CheckoutSessionRequest, CheckoutSessionResponse, CustomerPortalSessionResponse
from fathom.services import polar
from fathom.services.supabase import create_supabase_admin_client

logger = logging.getLogger(__name__)
HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)


async def create_checkout_session(
    request: CheckoutSessionRequest,
    auth: AuthContext,
    settings: Settings,
) -> CheckoutSessionResponse:
    plan_id = str(request.plan_id)
    admin_client = await create_supabase_admin_client(settings)
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

    checkout_url = await polar.create_checkout_session(
        settings,
        product_id=product_id,
        external_customer_id=auth.user_id,
        metadata={
            "user_id": auth.user_id,
            "plan_id": plan_id,
            "plan_code": str(plan.get("plan_code") or ""),
            "version": str(plan.get("version") or 1),
            "plan_type": plan_type,
        },
    )

    logger.info("polar checkout session created", extra={"user_id": auth.user_id, "plan_id": plan_id})
    return CheckoutSessionResponse(checkout_url=HTTP_URL_ADAPTER.validate_python(checkout_url))


async def create_portal_session(auth: AuthContext, settings: Settings) -> CustomerPortalSessionResponse:
    admin_client = await create_supabase_admin_client(settings)
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
