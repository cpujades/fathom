from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any
from unittest import TestCase
from unittest.mock import call, patch

from scripts.polar import generate_polar_plans as generator


def _starter_plan() -> generator.PlanRow:
    return generator.PlanRow(
        plan_code="starter",
        version=2,
        name="Starter",
        plan_type="subscription",
        polar_product_id="polar-starter-v2",
        currency="usd",
        amount_cents=1000,
        prices={"usd": 1000, "eur": 900, "gbp": 800},
        billing_interval="month",
        quota_seconds=21600,
        rollover_cap_seconds=21600,
        pack_expiry_days=None,
    )


def _raw_starter_plan() -> dict[str, Any]:
    plan = _starter_plan()
    return {
        "plan_code": plan.plan_code,
        "version": plan.version,
        "name": plan.name,
        "plan_type": plan.plan_type,
        "currency": plan.currency,
        "amount_cents": plan.amount_cents,
        "prices": plan.prices,
        "billing_interval": plan.billing_interval,
        "quota_seconds": plan.quota_seconds,
        "rollover_cap_seconds": plan.rollover_cap_seconds,
        "pack_expiry_days": plan.pack_expiry_days,
    }


def _raw_free_plan(*, version: int = 1) -> dict[str, Any]:
    return {
        "plan_code": "free",
        "version": version,
        "name": "Free",
        "plan_type": "subscription",
        "currency": "usd",
        "amount_cents": 0,
        "prices": {"usd": 0, "eur": 0, "gbp": 0},
        "billing_interval": "month",
        "quota_seconds": 3600,
        "rollover_cap_seconds": 0,
        "pack_expiry_days": None,
    }


def _polar_prices(*, include_gbp: bool = True) -> list[dict[str, Any]]:
    prices = [
        {
            "price_amount": 1000,
            "price_currency": "usd",
            "recurring_interval": "month",
            "tax_behavior": "exclusive",
        },
        {
            "price_amount": 900,
            "price_currency": "eur",
            "recurring_interval": "month",
            "tax_behavior": "exclusive",
        },
    ]
    if include_gbp:
        prices.append(
            {
                "price_amount": 800,
                "price_currency": "gbp",
                "recurring_interval": "month",
                "tax_behavior": "exclusive",
            }
        )
    return prices


class _PlansTable:
    def __init__(self) -> None:
        self.payload: list[dict[str, Any]] | None = None
        self.on_conflict: str | None = None

    def upsert(self, payload: list[dict[str, Any]], *, on_conflict: str) -> _PlansTable:
        self.payload = payload
        self.on_conflict = on_conflict
        return self

    def execute(self) -> SimpleNamespace:
        return SimpleNamespace(data=self.payload, error=None)


class _Supabase:
    def __init__(self) -> None:
        self.plans = _PlansTable()

    def table(self, name: str) -> _PlansTable:
        if name != "plans":
            raise AssertionError(f"Unexpected table: {name}")
        return self.plans


class PolarPlanGeneratorTests(TestCase):
    def test_internal_free_plan_remains_the_singleton_version(self) -> None:
        with self.assertRaisesRegex(ValueError, "must remain at version 1"):
            generator._validate_plan(_raw_free_plan(version=2))

    def test_product_assignment_conflict_stops_before_polar_creation(self) -> None:
        supabase = _Supabase()
        new_plan = _raw_starter_plan()
        conflicting_plan = _raw_starter_plan()
        conflicting_plan.update(
            {
                "plan_code": "pro",
                "name": "Pro",
                "polar_product_id": "shared-product",
            }
        )

        with (
            patch.object(generator, "_load_plans", return_value=[new_plan, conflicting_plan]),
            patch.object(generator, "create_client", return_value=supabase),
            patch.object(
                generator,
                "_load_existing_plans",
                return_value=[
                    generator.StoredPlan(
                        id="pro-v1",
                        plan_code="pro",
                        version=1,
                        polar_product_id="shared-product",
                        is_active=False,
                    )
                ],
            ),
            patch.object(generator, "_create_polar_product") as create_product,
            patch.object(generator, "_ensure_existing_product_matches_plan") as verify_product,
            patch.dict(
                os.environ,
                {
                    "SUPABASE_URL": "https://example.supabase.co",
                    "SUPABASE_SECRET_KEY": "secret",
                    "POLAR_ACCESS_TOKEN": "token",
                },
            ),
            self.assertRaisesRegex(ValueError, "already belongs to pro@v1"),
        ):
            generator.sync_plans(dry_run=False, retire_missing=False, server="sandbox")

        create_product.assert_not_called()
        verify_product.assert_not_called()

    def test_creates_all_localized_prices_as_tax_exclusive(self) -> None:
        with patch.object(generator, "_polar_request", return_value={"id": "polar-starter-v2"}) as request:
            product_id = generator._create_polar_product(
                token="token",
                api_base="https://sandbox-api.polar.sh",
                plan=_starter_plan(),
            )

        self.assertEqual(product_id, "polar-starter-v2")
        payload = request.call_args.kwargs["payload"]
        self.assertTrue(payload["is_recurring"])
        self.assertEqual(payload["recurring_interval"], "month")
        self.assertEqual(
            payload["prices"],
            [
                {
                    "type": "recurring",
                    "amount_type": "fixed",
                    "price_amount": 1000,
                    "price_currency": "usd",
                    "tax_behavior": "exclusive",
                    "recurring_interval": "month",
                },
                {
                    "type": "recurring",
                    "amount_type": "fixed",
                    "price_amount": 900,
                    "price_currency": "eur",
                    "tax_behavior": "exclusive",
                    "recurring_interval": "month",
                },
                {
                    "type": "recurring",
                    "amount_type": "fixed",
                    "price_amount": 800,
                    "price_currency": "gbp",
                    "tax_behavior": "exclusive",
                    "recurring_interval": "month",
                },
            ],
        )

    def test_accepts_an_existing_product_with_every_expected_price(self) -> None:
        with patch.object(generator, "_polar_request", return_value={"prices": _polar_prices()}):
            generator._ensure_existing_product_matches_plan(
                token="token",
                api_base="https://sandbox-api.polar.sh",
                product_id="polar-starter-v2",
                plan=_starter_plan(),
            )

    def test_rejects_an_existing_product_missing_one_currency(self) -> None:
        with (
            patch.object(generator, "_polar_request", return_value={"prices": _polar_prices(include_gbp=False)}),
            self.assertRaisesRegex(ValueError, "gbp 800"),
        ):
            generator._ensure_existing_product_matches_plan(
                token="token",
                api_base="https://sandbox-api.polar.sh",
                product_id="polar-starter-v2",
                plan=_starter_plan(),
            )

    def test_rejects_an_existing_product_with_non_exclusive_tax(self) -> None:
        prices = _polar_prices()
        prices[0]["tax_behavior"] = "location"
        with (
            patch.object(generator, "_polar_request", return_value={"prices": prices}),
            self.assertRaisesRegex(ValueError, "usd 1000.*exclusive"),
        ):
            generator._ensure_existing_product_matches_plan(
                token="token",
                api_base="https://sandbox-api.polar.sh",
                product_id="polar-starter-v2",
                plan=_starter_plan(),
            )

    def test_archives_a_polar_product_with_the_provider_archive_field(self) -> None:
        with patch.object(generator, "_polar_request", return_value={"is_archived": True}) as request:
            generator._set_polar_product_archived(
                token="token",
                api_base="https://sandbox-api.polar.sh",
                product_id="polar-starter-v1",
                is_archived=True,
            )

        request.assert_called_once_with(
            token="token",
            api_base="https://sandbox-api.polar.sh",
            method="PATCH",
            path="/v1/products/polar-starter-v1/",
            payload={"is_archived": True},
        )

    def test_retirement_preflight_rejects_a_mismatched_provider_product(self) -> None:
        old_plan = generator.StoredPlan(
            id="starter-v1",
            plan_code="starter",
            version=1,
            polar_product_id="polar-starter-v1",
            is_active=True,
        )
        mismatched_product = {
            "metadata": {
                "managed_by": generator.POLAR_MANAGED_BY,
                "plan_code": "pro",
                "version": "1",
            },
            "is_archived": False,
        }

        with (
            patch.object(generator, "_polar_request", return_value=mismatched_product),
            self.assertRaisesRegex(ValueError, "retirement stopped before making changes"),
        ):
            generator._preflight_retirements(
                token="token",
                api_base="https://sandbox-api.polar.sh",
                plans=[old_plan],
            )

    def test_private_mapping_cannot_override_localized_prices(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            contract_path = root / "plan_contract.json"
            overrides_path = root / "plans.json"
            contract_path.write_text(json.dumps([_raw_starter_plan()]), encoding="utf-8")
            overrides_path.write_text(
                json.dumps(
                    [
                        {
                            "plan_code": "starter",
                            "version": 2,
                            "prices": {"usd": 1, "eur": 1, "gbp": 1},
                            "polar_product_id": "polar-starter-v2",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            with (
                patch.object(generator, "PLAN_CONTRACT_PATH", contract_path),
                patch.object(generator, "POLAR_PRODUCT_OVERRIDES_PATH", overrides_path),
                self.assertRaisesRegex(ValueError, "may only override polar_product_id"),
            ):
                generator._load_plans()

    def test_supabase_keeps_one_reference_row_without_the_price_map(self) -> None:
        supabase = _Supabase()
        with TemporaryDirectory() as directory:
            output_path = Path(directory) / "plan_seed.json"
            with (
                patch.object(generator, "_load_plans", return_value=[_raw_starter_plan()]),
                patch.object(generator, "create_client", return_value=supabase),
                patch.object(
                    generator,
                    "_load_existing_plans",
                    return_value=[
                        generator.StoredPlan(
                            id="starter-v2",
                            plan_code="starter",
                            version=2,
                            polar_product_id="polar-starter-v2",
                            is_active=True,
                        )
                    ],
                ),
                patch.object(
                    generator,
                    "_ensure_existing_product_matches_plan",
                    return_value={"is_archived": False},
                ),
                patch.object(generator, "OUTPUT_JSON", output_path),
                patch.dict(
                    os.environ,
                    {
                        "SUPABASE_URL": "https://example.supabase.co",
                        "SUPABASE_SECRET_KEY": "secret",
                        "POLAR_ACCESS_TOKEN": "token",
                    },
                ),
            ):
                rows = generator.sync_plans(
                    dry_run=False,
                    retire_missing=False,
                    server="sandbox",
                )

        self.assertEqual(len(rows), 1)
        self.assertEqual(supabase.plans.on_conflict, "plan_code,version")
        assert supabase.plans.payload is not None
        self.assertEqual(len(supabase.plans.payload), 1)
        self.assertNotIn("prices", supabase.plans.payload[0])
        self.assertEqual(supabase.plans.payload[0]["currency"], "usd")
        self.assertEqual(supabase.plans.payload[0]["amount_cents"], 1000)

    def test_recovers_a_created_product_from_metadata_before_creating_another(self) -> None:
        supabase = _Supabase()
        with TemporaryDirectory() as directory:
            output_path = Path(directory) / "plan_seed.json"
            with (
                patch.object(generator, "_load_plans", return_value=[_raw_starter_plan()]),
                patch.object(generator, "create_client", return_value=supabase),
                patch.object(generator, "_load_existing_plans", return_value=[]),
                patch.object(
                    generator,
                    "_discover_managed_product_id",
                    return_value="recovered-polar-starter-v2",
                ) as discover_product,
                patch.object(generator, "_create_polar_product") as create_product,
                patch.object(
                    generator,
                    "_ensure_existing_product_matches_plan",
                    return_value={"is_archived": False},
                ),
                patch.object(generator, "OUTPUT_JSON", output_path),
                patch.dict(
                    os.environ,
                    {
                        "SUPABASE_URL": "https://example.supabase.co",
                        "SUPABASE_SECRET_KEY": "secret",
                        "POLAR_ACCESS_TOKEN": "token",
                    },
                ),
            ):
                rows = generator.sync_plans(
                    dry_run=False,
                    retire_missing=False,
                    server="sandbox",
                )

        discover_product.assert_called_once()
        create_product.assert_not_called()
        self.assertEqual(rows[0].polar_product_id, "recovered-polar-starter-v2")
        assert supabase.plans.payload is not None
        self.assertEqual(supabase.plans.payload[0]["polar_product_id"], "recovered-polar-starter-v2")

    def test_retirement_includes_inactive_rows_so_a_failed_run_can_be_retried(self) -> None:
        old_plan = generator.StoredPlan(
            id="starter-v1",
            plan_code="starter",
            version=1,
            polar_product_id="polar-starter-v1",
            is_active=False,
        )

        retired = generator._plans_to_retire([old_plan], keep_keys={("starter", 2)})

        self.assertEqual(retired, [old_plan])

    def test_retirement_deactivates_supabase_before_archiving_polar(self) -> None:
        supabase = _Supabase()
        current_plan = generator.StoredPlan(
            id="starter-v2",
            plan_code="starter",
            version=2,
            polar_product_id="polar-starter-v2",
            is_active=True,
        )
        old_plan = generator.StoredPlan(
            id="starter-v1",
            plan_code="starter",
            version=1,
            polar_product_id="polar-starter-v1",
            is_active=True,
        )
        retirement_target = generator.RetirementTarget(plan=old_plan, is_archived=False)
        operation_order: list[str] = []

        with TemporaryDirectory() as directory:
            output_path = Path(directory) / "plan_seed.json"
            with (
                patch.object(generator, "_load_plans", return_value=[_raw_starter_plan()]),
                patch.object(generator, "create_client", return_value=supabase),
                patch.object(generator, "_load_existing_plans", return_value=[current_plan, old_plan]),
                patch.object(
                    generator,
                    "_preflight_retirements",
                    return_value=[retirement_target],
                ) as preflight,
                patch.object(
                    generator,
                    "_ensure_existing_product_matches_plan",
                    return_value={"is_archived": False},
                ),
                patch.object(
                    generator,
                    "_deactivate_plan_versions",
                    side_effect=lambda *_: operation_order.append("deactivate"),
                ) as deactivate,
                patch.object(
                    generator,
                    "_archive_retired_products",
                    side_effect=lambda **_: operation_order.append("archive"),
                ) as archive,
                patch.object(generator, "OUTPUT_JSON", output_path),
                patch.dict(
                    os.environ,
                    {
                        "SUPABASE_URL": "https://example.supabase.co",
                        "SUPABASE_SECRET_KEY": "secret",
                        "POLAR_ACCESS_TOKEN": "token",
                    },
                ),
            ):
                generator.sync_plans(
                    dry_run=False,
                    retire_missing=True,
                    server="sandbox",
                )

        preflight.assert_called_once_with(
            token="token",
            api_base="https://sandbox-api.polar.sh",
            plans=[old_plan],
        )
        deactivate.assert_called_once_with(supabase, [old_plan])
        archive.assert_called_once_with(
            token="token",
            api_base="https://sandbox-api.polar.sh",
            targets=[retirement_target],
        )
        self.assertEqual(operation_order, ["deactivate", "archive"])

    def test_archiving_skips_products_already_archived_by_a_previous_run(self) -> None:
        archived = generator.RetirementTarget(
            plan=generator.StoredPlan(
                id="starter-v1",
                plan_code="starter",
                version=1,
                polar_product_id="polar-starter-v1",
                is_active=False,
            ),
            is_archived=True,
        )
        active = generator.RetirementTarget(
            plan=generator.StoredPlan(
                id="pro-v1",
                plan_code="pro",
                version=1,
                polar_product_id="polar-pro-v1",
                is_active=False,
            ),
            is_archived=False,
        )

        with patch.object(generator, "_set_polar_product_archived") as set_archived:
            generator._archive_retired_products(
                token="token",
                api_base="https://sandbox-api.polar.sh",
                targets=[archived, active],
            )

        self.assertEqual(
            set_archived.call_args_list,
            [
                call(
                    token="token",
                    api_base="https://sandbox-api.polar.sh",
                    product_id="polar-pro-v1",
                    is_archived=True,
                )
            ],
        )


if __name__ == "__main__":
    import unittest

    unittest.main()
