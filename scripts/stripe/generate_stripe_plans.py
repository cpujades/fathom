from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import stripe

from supabase import create_client

PLANS_PATH = Path(__file__).parent / "plans.json"
OUTPUT_JSON = Path(__file__).parent / "plan_seed.json"


@dataclass
class PlanRow:
    name: str
    plan_type: str
    stripe_price_id: str | None
    quota_seconds: int | None
    rollover_cap_seconds: int | None
    pack_expiry_days: int | None
    is_active: bool = True


def _load_plans() -> list[dict[str, Any]]:
    raw = PLANS_PATH.read_text(encoding="utf-8")
    plans = json.loads(raw)
    if not isinstance(plans, list) or not plans:
        raise ValueError("plans.json must be a non-empty array.")
    return plans


def _normalize_currency(currency: str | None) -> str:
    return (currency or "usd").lower()


def _create_price(
    plan: dict[str, Any],
    *,
    stripe_client: stripe.StripeClient,
) -> str:
    product = stripe_client.v1.products.create(
        params={
            "name": f"{plan['name']}",
            "metadata": {
                "plan_type": plan["plan_type"],
                "quota_seconds": str(plan.get("quota_seconds") or ""),
                "rollover_cap_seconds": str(plan.get("rollover_cap_seconds") or ""),
                "pack_expiry_days": str(plan.get("pack_expiry_days") or ""),
            },
        }
    )

    price_payload: dict[str, Any] = {
        "unit_amount": plan["amount_cents"],
        "currency": _normalize_currency(plan.get("currency")),
        "product": product.id,
    }

    if plan["plan_type"] == "subscription":
        price_payload["recurring"] = {"interval": plan.get("interval") or "month"}

    price = stripe_client.v1.prices.create(params=price_payload)
    return price.id


def seed_plans(*, dry_run: bool) -> list[PlanRow]:
    plans = _load_plans()

    stripe_key = os.getenv("STRIPE_SECRET_KEY")
    stripe_client: stripe.StripeClient | None = None
    if not dry_run:
        if not stripe_key:
            raise ValueError("STRIPE_SECRET_KEY is required to create Stripe prices.")
        stripe_client = stripe.StripeClient(stripe_key)

    rows: list[PlanRow] = []
    for plan in plans:
        plan_type = plan.get("plan_type")
        amount_cents = plan.get("amount_cents")

        if not plan.get("name") or plan_type not in {"subscription", "pack"}:
            raise ValueError("Each plan must have name and plan_type.")
        if amount_cents is None or amount_cents < 0:
            raise ValueError(f"Plan {plan['name']} missing amount_cents.")

        price_id = plan.get("stripe_price_id")
        if plan_type == "subscription" and amount_cents == 0:
            price_id = price_id or "internal_free"
        elif dry_run:
            price_id = price_id or f"price_{plan['name'].lower().replace(' ', '_')}"
        elif not price_id:
            if not stripe_client:
                raise ValueError("Stripe client unavailable.")
            price_id = _create_price(plan, stripe_client=stripe_client)

        rows.append(
            PlanRow(
                name=plan["name"],
                plan_type=plan_type,
                stripe_price_id=price_id,
                quota_seconds=plan.get("quota_seconds"),
                rollover_cap_seconds=plan.get("rollover_cap_seconds"),
                pack_expiry_days=plan.get("pack_expiry_days"),
            )
        )

    return rows


def main() -> None:
    rows = seed_plans(dry_run=False)

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SECRET_KEY")
    if not supabase_url or not supabase_key:
        raise ValueError("SUPABASE_URL and SUPABASE_SECRET_KEY are required to upsert plans.")

    supabase = create_client(supabase_url, supabase_key)
    payload = [row.__dict__ for row in rows]
    result = supabase.table("plans").upsert(payload, on_conflict="stripe_price_id").execute()
    if getattr(result, "error", None):
        raise ValueError(f"Failed to upsert plans: {result.error}")

    OUTPUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"Seeded {len(rows)} plans.")
    print(f"JSON written to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
