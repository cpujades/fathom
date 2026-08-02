from __future__ import annotations

from fathom.core.config import Settings
from fathom.crud.supabase.billing import fetch_active_plans
from fathom.schemas.billing import PlanResponse
from fathom.services.supabase import create_supabase_admin_client, managed_supabase_client


async def list_billing_plans(settings: Settings) -> list[PlanResponse]:
    async with managed_supabase_client(await create_supabase_admin_client(settings)) as admin_client:
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
