from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from supabase import create_client

# Load .env from project root so os.getenv() sees SUPABASE_* and POLAR_* when run as script.
_project_root = Path(__file__).resolve().parent.parent.parent
_env_file = _project_root / ".env"
if _env_file.exists():
    load_dotenv(_env_file)

PLANS_PATH = Path(__file__).parent / "plans.json"
OUTPUT_JSON = Path(__file__).parent / "plan_seed.json"


@dataclass
class PlanRow:
    plan_code: str
    version: int
    name: str
    plan_type: str
    polar_product_id: str | None
    currency: str
    amount_cents: int
    billing_interval: str | None
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


def _api_base(server: str) -> str:
    normalized = server.strip().lower()
    if normalized == "sandbox":
        return "https://sandbox-api.polar.sh"
    if normalized == "production":
        return "https://api.polar.sh"
    if normalized.startswith("http://") or normalized.startswith("https://"):
        return normalized.rstrip("/")
    raise ValueError("POLAR_SERVER must be sandbox, production, or an absolute URL.")


def _polar_request(
    *,
    token: str,
    api_base: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        url=f"{api_base}{path}",
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Fathom-PolarSync/1.0",
        },
        data=data,
    )

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"Polar API error ({exc.code}): {body[:600]}") from exc
    except URLError as exc:
        raise ValueError("Polar API is unreachable.") from exc

    if not raw:
        return {}

    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("Polar API returned an unexpected response shape.")
    return parsed


def _create_polar_product(
    *,
    token: str,
    api_base: str,
    plan: PlanRow,
) -> str:
    is_subscription = plan.plan_type == "subscription"
    price_payload: dict[str, Any] = {
        "type": "recurring" if is_subscription else "one_time",
        "amount_type": "fixed",
        "price_amount": plan.amount_cents,
        "price_currency": plan.currency,
    }
    if is_subscription:
        price_payload["recurring_interval"] = "month"

    payload: dict[str, Any] = {
        "name": plan.name,
        "description": f"Fathom plan {plan.plan_code} v{plan.version}",
        "is_recurring": is_subscription,
        "prices": [price_payload],
        "metadata": {
            "plan_code": plan.plan_code,
            "version": str(plan.version),
            "managed_by": "generate_polar_plans.py",
        },
    }
    if is_subscription:
        payload["recurring_interval"] = "month"
    # Do not set organization_id when using an organization token; Polar forbids it.

    response = _polar_request(
        token=token,
        api_base=api_base,
        method="POST",
        path="/v1/products/",
        payload=payload,
    )
    product_id = response.get("id")
    if not isinstance(product_id, str) or not product_id:
        raise ValueError(f"Polar product creation failed for {plan.plan_code}: missing id in response")
    return product_id


def _extract_prices_from_product(product: dict[str, Any]) -> list[dict[str, Any]]:
    prices = product.get("prices")
    if isinstance(prices, list):
        return [price for price in prices if isinstance(price, dict)]
    if isinstance(prices, dict):
        nested = prices.get("items") or prices.get("nodes")
        if isinstance(nested, list):
            return [price for price in nested if isinstance(price, dict)]
    return []


def _as_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _normalize_price(price: dict[str, Any]) -> tuple[int | None, str | None, str | None]:
    amount = _as_int(price.get("price_amount"))
    if amount is None:
        amount = _as_int(price.get("amount"))
    if amount is None:
        amount = _as_int(price.get("unit_amount"))

    currency_raw = price.get("price_currency") or price.get("currency")
    currency = str(currency_raw).lower() if isinstance(currency_raw, str) and currency_raw else None

    interval_raw = price.get("recurring_interval") or price.get("interval")
    interval = str(interval_raw).lower() if isinstance(interval_raw, str) and interval_raw else None
    return amount, currency, interval


def _ensure_existing_product_matches_plan(
    *,
    token: str,
    api_base: str,
    product_id: str,
    plan: PlanRow,
) -> None:
    product = _polar_request(
        token=token,
        api_base=api_base,
        method="GET",
        path=f"/v1/products/{product_id}/",
    )
    prices = _extract_prices_from_product(product)
    if not prices:
        raise ValueError(f"Polar product {product_id} for {plan.plan_code}@v{plan.version} has no readable prices.")

    expected_interval = "month" if plan.plan_type == "subscription" else None
    for price in prices:
        amount, currency, interval = _normalize_price(price)
        if amount == plan.amount_cents and currency == plan.currency and interval == expected_interval:
            return

    raise ValueError(
        f"Polar product {product_id} for {plan.plan_code}@v{plan.version} has no matching price "
        f"(amount={plan.amount_cents}, currency={plan.currency}, interval={expected_interval}). "
        "Bump plan version or update Polar catalog."
    )


def _validate_plan(raw: dict[str, Any]) -> PlanRow:
    plan_type = raw.get("plan_type")
    amount_cents = raw.get("amount_cents")
    currency = raw.get("currency") or "usd"
    billing_interval = raw.get("billing_interval")

    if not raw.get("plan_code"):
        raise ValueError("Each plan must define plan_code.")
    if not raw.get("name") or plan_type not in {"subscription", "pack"}:
        raise ValueError("Each plan must have name and plan_type.")
    if not isinstance(amount_cents, int) or amount_cents < 0:
        raise ValueError(f"Plan {raw['plan_code']} has invalid amount_cents.")
    if not isinstance(currency, str) or not currency:
        raise ValueError(f"Plan {raw['plan_code']} has invalid currency.")

    version = raw.get("version", 1)
    if not isinstance(version, int) or version <= 0:
        raise ValueError(f"Plan {raw['plan_code']} has invalid version.")

    if plan_type == "subscription" and billing_interval != "month":
        raise ValueError(f"Plan {raw['plan_code']} must use billing_interval='month'.")
    if plan_type == "pack" and billing_interval is not None:
        raise ValueError(f"Plan {raw['plan_code']} must use billing_interval=null.")

    return PlanRow(
        plan_code=str(raw["plan_code"]),
        version=version,
        name=str(raw["name"]),
        plan_type=str(plan_type),
        polar_product_id=raw.get("polar_product_id"),
        currency=currency.lower(),
        amount_cents=amount_cents,
        billing_interval=billing_interval,
        quota_seconds=raw.get("quota_seconds"),
        rollover_cap_seconds=raw.get("rollover_cap_seconds"),
        pack_expiry_days=raw.get("pack_expiry_days"),
    )


def _load_existing_plan_products(supabase: Any) -> dict[tuple[str, int], str]:
    response = supabase.table("plans").select("plan_code,version,polar_product_id").execute()
    rows = response.data or []
    existing: dict[tuple[str, int], str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        plan_code = row.get("plan_code")
        version = row.get("version")
        product_id = row.get("polar_product_id")
        if isinstance(plan_code, str) and isinstance(version, int) and isinstance(product_id, str) and product_id:
            existing[(plan_code, version)] = product_id
    return existing


def _deactivate_missing_plan_versions(supabase: Any, *, keep_keys: set[tuple[str, int]]) -> None:
    response = supabase.table("plans").select("id,plan_code,version,is_active").execute()
    rows = response.data or []
    ids_to_deactivate: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = row.get("id")
        plan_code = row.get("plan_code")
        version = row.get("version")
        if not (isinstance(row_id, str) and isinstance(plan_code, str) and isinstance(version, int)):
            continue
        if not bool(row.get("is_active")):
            continue
        if (plan_code, version) not in keep_keys:
            ids_to_deactivate.append(row_id)

    if not ids_to_deactivate:
        return

    chunk_size = 100
    for start in range(0, len(ids_to_deactivate), chunk_size):
        chunk = ids_to_deactivate[start : start + chunk_size]
        supabase.table("plans").update({"is_active": False}).in_("id", chunk).execute()


def sync_plans(*, dry_run: bool, deactivate_missing: bool, server: str) -> list[PlanRow]:
    raw_plans = _load_plans()
    plans = [_validate_plan(raw) for raw in raw_plans]

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SECRET_KEY")
    if not dry_run and (not supabase_url or not supabase_key):
        raise ValueError("SUPABASE_URL and SUPABASE_SECRET_KEY are required for sync.")

    supabase = create_client(supabase_url, supabase_key) if not dry_run else None
    existing_products: dict[tuple[str, int], str] = {}
    if supabase is not None:
        existing_products = _load_existing_plan_products(supabase)

    token = os.getenv("POLAR_ACCESS_TOKEN", "").strip()
    api_base = _api_base(server)
    if not dry_run and not token:
        raise ValueError("POLAR_ACCESS_TOKEN is required for non-dry-run catalog sync.")

    rows: list[PlanRow] = []
    for plan in plans:
        product_id = plan.polar_product_id or existing_products.get((plan.plan_code, plan.version))

        if plan.plan_type == "subscription" and plan.amount_cents == 0:
            product_id = product_id or "internal_free"

        if not product_id:
            if dry_run:
                product_id = f"prod_{plan.plan_code}_v{plan.version}"
            else:
                if not token:
                    raise ValueError(
                        f"Plan {plan.plan_code} needs a Polar product. Set POLAR_ACCESS_TOKEN for auto-create."
                    )
                product_id = _create_polar_product(
                    token=token,
                    api_base=api_base,
                    plan=plan,
                )
        elif not dry_run and product_id != "internal_free":
            _ensure_existing_product_matches_plan(
                token=token,
                api_base=api_base,
                product_id=product_id,
                plan=plan,
            )

        rows.append(
            PlanRow(
                plan_code=plan.plan_code,
                version=plan.version,
                name=plan.name,
                plan_type=plan.plan_type,
                polar_product_id=product_id,
                currency=plan.currency,
                amount_cents=plan.amount_cents,
                billing_interval=plan.billing_interval,
                quota_seconds=plan.quota_seconds,
                rollover_cap_seconds=plan.rollover_cap_seconds,
                pack_expiry_days=plan.pack_expiry_days,
            )
        )

    payload = [asdict(row) for row in rows]
    OUTPUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if dry_run:
        return rows

    assert supabase is not None
    result = supabase.table("plans").upsert(payload, on_conflict="plan_code,version").execute()
    if getattr(result, "error", None):
        raise ValueError(f"Failed to upsert plans: {result.error}")

    if deactivate_missing:
        keep_keys = {(row.plan_code, row.version) for row in rows}
        _deactivate_missing_plan_versions(supabase, keep_keys=keep_keys)

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Create/Sync Polar catalog and Supabase plans.")
    parser.add_argument("--dry-run", action="store_true", help="Validate input and emit plan_seed.json only.")
    parser.add_argument(
        "--deactivate-missing",
        action="store_true",
        help="Mark DB plans as inactive when their plan_code is missing from plans.json.",
    )
    parser.add_argument(
        "--server",
        default=os.getenv("POLAR_SERVER", "sandbox"),
        help="Polar server: sandbox, production, or custom base URL.",
    )
    args = parser.parse_args()

    rows = sync_plans(dry_run=args.dry_run, deactivate_missing=args.deactivate_missing, server=args.server)

    if args.dry_run:
        print(f"Validated {len(rows)} plans (dry-run).")
    else:
        print(f"Synced {len(rows)} plans to Polar/Supabase.")
    print(f"JSON written to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
