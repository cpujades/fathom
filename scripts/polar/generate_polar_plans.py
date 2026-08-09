from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from supabase import create_client

# Load .env from project root so os.getenv() sees SUPABASE_* and POLAR_* when run as script.
_project_root = Path(__file__).resolve().parent.parent.parent
_env_file = _project_root / ".env"
if _env_file.exists():
    load_dotenv(_env_file)

PLAN_CONTRACT_PATH = Path(__file__).parent / "plan_contract.json"
POLAR_PRODUCT_OVERRIDES_PATH = Path(__file__).parent / "plans.json"
OUTPUT_JSON = Path(__file__).parent / "plan_seed.json"
INTERNAL_FREE_PRODUCT_ID = "internal_free"
INTERNAL_FREE_PLAN_KEY = ("free", 1)
POLAR_MANAGED_BY = "generate_polar_plans.py"

_PUBLIC_PLAN_FIELDS = (
    "plan_code",
    "version",
    "name",
    "plan_type",
    "currency",
    "amount_cents",
    "prices",
    "billing_interval",
    "quota_seconds",
    "rollover_cap_seconds",
    "pack_expiry_days",
)


@dataclass
class PlanRow:
    plan_code: str
    version: int
    name: str
    plan_type: str
    polar_product_id: str | None
    currency: str
    amount_cents: int
    prices: dict[str, int]
    billing_interval: str | None
    quota_seconds: int | None
    rollover_cap_seconds: int | None
    pack_expiry_days: int | None
    is_active: bool = True


@dataclass(frozen=True)
class StoredPlan:
    id: str
    plan_code: str
    version: int
    polar_product_id: str | None
    is_active: bool


@dataclass(frozen=True)
class RetirementTarget:
    plan: StoredPlan
    is_archived: bool


def _load_plan_array(path: Path) -> list[dict[str, Any]]:
    raw = path.read_text(encoding="utf-8")
    plans = json.loads(raw)
    if not isinstance(plans, list) or not plans:
        raise ValueError(f"{path.name} must be a non-empty array.")
    if not all(isinstance(plan, dict) for plan in plans):
        raise ValueError(f"{path.name} must contain only plan objects.")
    return plans


def _load_plans() -> list[dict[str, Any]]:
    contract = _load_plan_array(PLAN_CONTRACT_PATH)
    if not POLAR_PRODUCT_OVERRIDES_PATH.exists():
        return contract

    contract_by_key = {(str(plan.get("plan_code")), int(plan.get("version", 1))): plan for plan in contract}
    for override in _load_plan_array(POLAR_PRODUCT_OVERRIDES_PATH):
        key = (str(override.get("plan_code")), int(override.get("version", 1)))
        plan = contract_by_key.get(key)
        if plan is None:
            raise ValueError(f"plans.json contains unknown plan {key[0]}@v{key[1]}.")

        for field in _PUBLIC_PLAN_FIELDS:
            if field in override and override[field] != plan.get(field):
                raise ValueError(f"plans.json may only override polar_product_id; {key[0]}@v{key[1]} changes {field}.")

        product_id = override.get("polar_product_id")
        if product_id is not None and (not isinstance(product_id, str) or not product_id.strip()):
            raise ValueError(f"Plan {key[0]}@v{key[1]} has an invalid polar_product_id override.")
        if product_id:
            plan["polar_product_id"] = product_id

    return contract


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
            "User-Agent": "Talven-PolarSync/1.0",
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
    price_payloads: list[dict[str, Any]] = []
    for currency, amount_cents in plan.prices.items():
        price_payload: dict[str, Any] = {
            "type": "recurring" if is_subscription else "one_time",
            "amount_type": "fixed",
            "price_amount": amount_cents,
            "price_currency": currency,
            "tax_behavior": "exclusive",
        }
        if is_subscription:
            price_payload["recurring_interval"] = "month"
        price_payloads.append(price_payload)

    payload: dict[str, Any] = {
        "name": plan.name,
        "description": f"Talven plan {plan.plan_code} v{plan.version}",
        "is_recurring": is_subscription,
        "prices": price_payloads,
        "metadata": {
            "plan_code": plan.plan_code,
            "version": str(plan.version),
            "managed_by": POLAR_MANAGED_BY,
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


def _extract_product_items(response: dict[str, Any]) -> list[dict[str, Any]]:
    items = response.get("items")
    if not isinstance(items, list):
        raise ValueError("Polar product list returned an unexpected response shape.")
    return [item for item in items if isinstance(item, dict)]


def _list_managed_products(
    *,
    token: str,
    api_base: str,
    plan: PlanRow,
) -> list[dict[str, Any]]:
    query = {
        "metadata[managed_by]": POLAR_MANAGED_BY,
        "metadata[plan_code]": plan.plan_code,
        "metadata[version]": str(plan.version),
        "limit": "100",
    }
    products: list[dict[str, Any]] = []
    page = 1
    while True:
        query["page"] = str(page)
        response = _polar_request(
            token=token,
            api_base=api_base,
            method="GET",
            path=f"/v1/products/?{urlencode(query)}",
        )
        products.extend(_extract_product_items(response))

        pagination = response.get("pagination")
        max_page = pagination.get("max_page") if isinstance(pagination, dict) else None
        if not isinstance(max_page, int) or page >= max_page:
            return products
        page += 1


def _discover_managed_product_id(
    *,
    token: str,
    api_base: str,
    plan: PlanRow,
) -> str | None:
    products = _list_managed_products(token=token, api_base=api_base, plan=plan)
    candidates = [product for product in products if isinstance(product.get("id"), str)]
    active = [product for product in candidates if not bool(product.get("is_archived"))]

    if len(active) == 1:
        return str(active[0]["id"])
    if len(active) > 1:
        raise ValueError(
            f"Polar contains multiple active managed products for {plan.plan_code}@v{plan.version}. "
            "Archive the duplicates before rerunning."
        )
    if len(candidates) == 1:
        return str(candidates[0]["id"])
    if len(candidates) > 1:
        raise ValueError(
            f"Polar contains multiple archived managed products for {plan.plan_code}@v{plan.version}. "
            "Add the intended product id to plans.json before rerunning."
        )
    return None


def _as_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _normalize_price(
    price: dict[str, Any],
) -> tuple[int | None, str | None, str | None, str | None]:
    amount = _as_int(price.get("price_amount"))
    if amount is None:
        amount = _as_int(price.get("amount"))
    if amount is None:
        amount = _as_int(price.get("unit_amount"))

    currency_raw = price.get("price_currency") or price.get("currency")
    currency = str(currency_raw).lower() if isinstance(currency_raw, str) and currency_raw else None

    interval_raw = price.get("recurring_interval") or price.get("interval")
    interval = str(interval_raw).lower() if isinstance(interval_raw, str) and interval_raw else None
    tax_behavior_raw = price.get("tax_behavior")
    tax_behavior = str(tax_behavior_raw).lower() if isinstance(tax_behavior_raw, str) and tax_behavior_raw else None
    return amount, currency, interval, tax_behavior


def _ensure_existing_product_matches_plan(
    *,
    token: str,
    api_base: str,
    product_id: str,
    plan: PlanRow,
) -> dict[str, Any]:
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
    normalized_prices = {_normalize_price(price) for price in prices}
    missing_prices = [
        (amount_cents, currency, expected_interval, "exclusive")
        for currency, amount_cents in plan.prices.items()
        if (amount_cents, currency, expected_interval, "exclusive") not in normalized_prices
    ]
    if not missing_prices:
        return product

    expected = ", ".join(
        f"{currency} {amount_cents} ({interval or 'one-time'}, exclusive)"
        for amount_cents, currency, interval, _ in missing_prices
    )
    raise ValueError(
        f"Polar product {product_id} for {plan.plan_code}@v{plan.version} is missing expected prices: "
        f"{expected}. Bump plan version or update the Polar catalog."
    )


def _set_polar_product_archived(
    *,
    token: str,
    api_base: str,
    product_id: str,
    is_archived: bool,
) -> None:
    product = _polar_request(
        token=token,
        api_base=api_base,
        method="PATCH",
        path=f"/v1/products/{product_id}/",
        payload={"is_archived": is_archived},
    )
    if product.get("is_archived") is not is_archived:
        state = "archived" if is_archived else "active"
        raise ValueError(f"Polar product {product_id} was not confirmed as {state}.")


def _validate_plan(raw: dict[str, Any]) -> PlanRow:
    plan_type = raw.get("plan_type")
    amount_cents = raw.get("amount_cents")
    currency = raw.get("currency") or "usd"
    billing_interval = raw.get("billing_interval")

    if not raw.get("plan_code"):
        raise ValueError("Each plan must define plan_code.")
    plan_code = str(raw["plan_code"])
    if not raw.get("name") or plan_type not in {"subscription", "pack"}:
        raise ValueError("Each plan must have name and plan_type.")
    if not isinstance(amount_cents, int) or amount_cents < 0:
        raise ValueError(f"Plan {raw['plan_code']} has invalid amount_cents.")
    if not isinstance(currency, str) or not currency:
        raise ValueError(f"Plan {raw['plan_code']} has invalid currency.")

    prices_raw = raw.get("prices") or {currency: amount_cents}
    if not isinstance(prices_raw, dict) or not prices_raw:
        raise ValueError(f"Plan {raw['plan_code']} must define at least one localized price.")

    prices: dict[str, int] = {}
    for price_currency, price_amount in prices_raw.items():
        if not isinstance(price_currency, str) or len(price_currency) != 3 or not price_currency.isalpha():
            raise ValueError(f"Plan {raw['plan_code']} has an invalid localized currency.")
        if not isinstance(price_amount, int) or price_amount < 0:
            raise ValueError(f"Plan {raw['plan_code']} has an invalid {price_currency.lower()} localized price.")
        prices[price_currency.lower()] = price_amount

    normalized_currency = currency.lower()
    if prices.get(normalized_currency) != amount_cents:
        raise ValueError(
            f"Plan {raw['plan_code']} default amount must match its {normalized_currency} localized price."
        )

    version = raw.get("version", 1)
    if not isinstance(version, int) or version <= 0:
        raise ValueError(f"Plan {plan_code} has invalid version.")

    product_id = raw.get("polar_product_id")
    if plan_code == INTERNAL_FREE_PLAN_KEY[0]:
        if plan_type != "subscription" or amount_cents != 0:
            raise ValueError("Plan free must remain a zero-price subscription.")
        if version != INTERNAL_FREE_PLAN_KEY[1]:
            raise ValueError("Plan free uses the singleton internal_free product and must remain at version 1.")
        if product_id is not None and product_id != INTERNAL_FREE_PRODUCT_ID:
            raise ValueError("Plan free must use the internal_free product id.")
    elif plan_type == "subscription" and amount_cents == 0:
        raise ValueError("Only plan free may be a zero-price subscription.")

    if plan_type == "subscription" and billing_interval != "month":
        raise ValueError(f"Plan {raw['plan_code']} must use billing_interval='month'.")
    if plan_type == "pack" and billing_interval is not None:
        raise ValueError(f"Plan {raw['plan_code']} must use billing_interval=null.")

    return PlanRow(
        plan_code=plan_code,
        version=version,
        name=str(raw["name"]),
        plan_type=str(plan_type),
        polar_product_id=product_id,
        currency=normalized_currency,
        amount_cents=amount_cents,
        prices=prices,
        billing_interval=billing_interval,
        quota_seconds=raw.get("quota_seconds"),
        rollover_cap_seconds=raw.get("rollover_cap_seconds"),
        pack_expiry_days=raw.get("pack_expiry_days"),
    )


def _load_existing_plans(supabase: Any) -> list[StoredPlan]:
    response = supabase.table("plans").select("id,plan_code,version,polar_product_id,is_active").execute()
    rows = response.data or []
    existing: list[StoredPlan] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = row.get("id")
        plan_code = row.get("plan_code")
        version = row.get("version")
        product_id = row.get("polar_product_id")
        if not (isinstance(row_id, str) and isinstance(plan_code, str) and isinstance(version, int)):
            continue
        existing.append(
            StoredPlan(
                id=row_id,
                plan_code=plan_code,
                version=version,
                polar_product_id=product_id if isinstance(product_id, str) and product_id else None,
                is_active=bool(row.get("is_active")),
            )
        )
    return existing


def _existing_product_map(existing_plans: list[StoredPlan]) -> dict[tuple[str, int], str]:
    return {
        (plan.plan_code, plan.version): plan.polar_product_id
        for plan in existing_plans
        if plan.polar_product_id is not None
    }


def _validate_product_assignments(
    plans: list[PlanRow],
    existing_products: dict[tuple[str, int], str],
) -> None:
    existing_owners = {product_id: key for key, product_id in existing_products.items()}
    desired_owners: dict[str, tuple[str, int]] = {}

    for plan in plans:
        key = (plan.plan_code, plan.version)
        product_id = plan.polar_product_id or existing_products.get(key)
        if key == INTERNAL_FREE_PLAN_KEY:
            product_id = INTERNAL_FREE_PRODUCT_ID
        if not product_id:
            continue

        existing_owner = existing_owners.get(product_id)
        if existing_owner is not None and existing_owner != key:
            raise ValueError(
                f"Product id {product_id} already belongs to "
                f"{existing_owner[0]}@v{existing_owner[1]}; it cannot also belong to "
                f"{key[0]}@v{key[1]}. Use a new Polar product for a new paid plan version."
            )

        desired_owner = desired_owners.get(product_id)
        if desired_owner is not None and desired_owner != key:
            raise ValueError(
                f"Product id {product_id} is assigned to both "
                f"{desired_owner[0]}@v{desired_owner[1]} and {key[0]}@v{key[1]}."
            )
        desired_owners[product_id] = key


def _plans_to_retire(
    existing_plans: list[StoredPlan],
    *,
    keep_keys: set[tuple[str, int]],
) -> list[StoredPlan]:
    return [plan for plan in existing_plans if (plan.plan_code, plan.version) not in keep_keys]


def _preflight_retirements(
    *,
    token: str,
    api_base: str,
    plans: list[StoredPlan],
) -> list[RetirementTarget]:
    targets: list[RetirementTarget] = []
    for plan in plans:
        product_id = plan.polar_product_id
        if product_id is None or product_id == INTERNAL_FREE_PRODUCT_ID:
            continue

        product = _polar_request(
            token=token,
            api_base=api_base,
            method="GET",
            path=f"/v1/products/{product_id}/",
        )
        metadata = product.get("metadata")
        expected_metadata = {
            "managed_by": POLAR_MANAGED_BY,
            "plan_code": plan.plan_code,
            "version": str(plan.version),
        }
        if not isinstance(metadata, dict) or any(
            metadata.get(key) != value for key, value in expected_metadata.items()
        ):
            raise ValueError(
                f"Polar product {product_id} does not identify itself as "
                f"{plan.plan_code}@v{plan.version}; retirement stopped before making changes."
            )
        targets.append(RetirementTarget(plan=plan, is_archived=bool(product.get("is_archived"))))
    return targets


def _deactivate_plan_versions(supabase: Any, plans: list[StoredPlan]) -> None:
    ids_to_deactivate = [plan.id for plan in plans if plan.is_active]

    if not ids_to_deactivate:
        return

    chunk_size = 100
    for start in range(0, len(ids_to_deactivate), chunk_size):
        chunk = ids_to_deactivate[start : start + chunk_size]
        supabase.table("plans").update({"is_active": False}).in_("id", chunk).execute()


def _archive_retired_products(
    *,
    token: str,
    api_base: str,
    targets: list[RetirementTarget],
) -> None:
    for target in targets:
        product_id = target.plan.polar_product_id
        if target.is_archived or product_id is None:
            continue
        _set_polar_product_archived(
            token=token,
            api_base=api_base,
            product_id=product_id,
            is_archived=True,
        )


def sync_plans(*, dry_run: bool, retire_missing: bool, server: str) -> list[PlanRow]:
    raw_plans = _load_plans()
    plans = [_validate_plan(raw) for raw in raw_plans]

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SECRET_KEY")
    if not dry_run and (not supabase_url or not supabase_key):
        raise ValueError("SUPABASE_URL and SUPABASE_SECRET_KEY are required for sync.")

    supabase = create_client(supabase_url, supabase_key) if not dry_run else None
    existing_plans: list[StoredPlan] = []
    existing_products: dict[tuple[str, int], str] = {}
    if supabase is not None:
        existing_plans = _load_existing_plans(supabase)
        existing_products = _existing_product_map(existing_plans)

    _validate_product_assignments(plans, existing_products)

    token = os.getenv("POLAR_ACCESS_TOKEN", "").strip()
    api_base = _api_base(server)
    if not dry_run and not token:
        raise ValueError("POLAR_ACCESS_TOKEN is required for non-dry-run catalog sync.")

    keep_keys = {(plan.plan_code, plan.version) for plan in plans}
    plans_to_retire = _plans_to_retire(existing_plans, keep_keys=keep_keys) if retire_missing else []
    retirement_targets: list[RetirementTarget] = []
    if not dry_run and retire_missing:
        retirement_targets = _preflight_retirements(
            token=token,
            api_base=api_base,
            plans=plans_to_retire,
        )

    existing_owners = {product_id: key for key, product_id in existing_products.items()}

    rows: list[PlanRow] = []
    for plan in plans:
        key = (plan.plan_code, plan.version)
        product_id = plan.polar_product_id or existing_products.get(key)

        if key == INTERNAL_FREE_PLAN_KEY:
            product_id = INTERNAL_FREE_PRODUCT_ID

        if not product_id:
            if dry_run:
                product_id = f"prod_{plan.plan_code}_v{plan.version}"
            else:
                product_id = _discover_managed_product_id(token=token, api_base=api_base, plan=plan)
                if product_id is None:
                    product_id = _create_polar_product(
                        token=token,
                        api_base=api_base,
                        plan=plan,
                    )

                existing_owner = existing_owners.get(product_id)
                if existing_owner is not None and existing_owner != key:
                    raise ValueError(
                        f"Polar product {product_id} already belongs to "
                        f"{existing_owner[0]}@v{existing_owner[1]} in Supabase."
                    )

                product = _ensure_existing_product_matches_plan(
                    token=token,
                    api_base=api_base,
                    product_id=product_id,
                    plan=plan,
                )
                if bool(product.get("is_archived")):
                    _set_polar_product_archived(
                        token=token,
                        api_base=api_base,
                        product_id=product_id,
                        is_archived=False,
                    )
        elif not dry_run and product_id != INTERNAL_FREE_PRODUCT_ID:
            product = _ensure_existing_product_matches_plan(
                token=token,
                api_base=api_base,
                product_id=product_id,
                plan=plan,
            )
            if bool(product.get("is_archived")):
                _set_polar_product_archived(
                    token=token,
                    api_base=api_base,
                    product_id=product_id,
                    is_archived=False,
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
                prices=plan.prices,
                billing_interval=plan.billing_interval,
                quota_seconds=plan.quota_seconds,
                rollover_cap_seconds=plan.rollover_cap_seconds,
                pack_expiry_days=plan.pack_expiry_days,
            )
        )

    output_payload = [asdict(row) for row in rows]
    database_payload = [{key: value for key, value in row.items() if key != "prices"} for row in output_payload]
    OUTPUT_JSON.write_text(json.dumps(output_payload, indent=2), encoding="utf-8")

    if dry_run:
        return rows

    assert supabase is not None
    result = supabase.table("plans").upsert(database_payload, on_conflict="plan_code,version").execute()
    if getattr(result, "error", None):
        raise ValueError(f"Failed to upsert plans: {result.error}")

    if retire_missing:
        _deactivate_plan_versions(supabase, plans_to_retire)
        _archive_retired_products(
            token=token,
            api_base=api_base,
            targets=retirement_targets,
        )

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Create/Sync Polar catalog and Supabase plans.")
    parser.add_argument("--dry-run", action="store_true", help="Validate input and emit plan_seed.json only.")
    parser.add_argument(
        "--retire-missing",
        action="store_true",
        help="Deactivate missing Supabase plan versions and archive their Polar products.",
    )
    parser.add_argument(
        "--server",
        default=os.getenv("POLAR_SERVER", "sandbox"),
        help="Polar server: sandbox, production, or custom base URL.",
    )
    args = parser.parse_args()

    rows = sync_plans(dry_run=args.dry_run, retire_missing=args.retire_missing, server=args.server)

    if args.dry_run:
        print(f"Validated {len(rows)} plans (dry-run).")
    else:
        print(f"Synced {len(rows)} plans to Polar/Supabase.")
    print(f"JSON written to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
