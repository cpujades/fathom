from __future__ import annotations

import asyncio
import json
import os
import unittest
from typing import Any

import asyncpg

DATABASE_URL = os.getenv("FATHOM_TEST_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "FATHOM_TEST_DATABASE_URL is not configured")
class PolarWebhookConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.connection = await asyncpg.connect(DATABASE_URL)
        await self._cleanup()
        await self.connection.execute(
            """
            insert into public.plans (
              id, name, plan_type, polar_product_id, plan_code, currency,
              amount_cents, billing_interval, version, quota_seconds,
              rollover_cap_seconds, pack_expiry_days
            )
            values (
              '97000000-0000-0000-0000-000000000001',
              'Webhook Concurrency Pack',
              'pack',
              'prod_webhook_concurrency',
              'webhook_concurrency_pack',
              'usd',
              1000,
              null,
              1,
              300,
              0,
              30
            );

            insert into public.entitlements (user_id, debt_seconds, is_blocked)
            values (
              '97000000-0000-0000-0000-000000000002',
              50,
              false
            );
            """
        )

    async def asyncTearDown(self) -> None:
        await self._cleanup()
        await self.connection.close()

    async def _cleanup(self) -> None:
        await self.connection.execute(
            """
            delete from public.billing_webhook_events
            where event_id = 'evt_webhook_concurrency';
            delete from public.credit_lots
            where lot_type = 'pack_order'
              and source_key = 'ord_webhook_concurrency';
            delete from public.billing_orders
            where polar_order_id = 'ord_webhook_concurrency';
            delete from public.polar_customers
            where user_id = '97000000-0000-0000-0000-000000000002';
            delete from public.entitlements
            where user_id = '97000000-0000-0000-0000-000000000002';
            delete from public.plans
            where id = '97000000-0000-0000-0000-000000000001';
            """
        )

    async def test_concurrent_duplicate_deliveries_apply_one_billing_effect(self) -> None:
        first = await asyncpg.connect(DATABASE_URL)
        second = await asyncpg.connect(DATABASE_URL)
        first_transaction = first.transaction()
        committed = False
        event_payload = json.dumps(
            {
                "order_id": "ord_webhook_concurrency",
                "user_id": "97000000-0000-0000-0000-000000000002",
                "product_id": "prod_webhook_concurrency",
                "currency": "usd",
                "paid_amount_cents": 1000,
            }
        )
        statement = """
            select public.apply_polar_webhook_event(
              'evt_webhook_concurrency',
              'order.paid',
              '2026-07-29T15:00:00+00:00',
              'order',
              'ord_webhook_concurrency',
              $1::jsonb,
              600
            )
        """

        try:
            await first_transaction.start()
            first_result = await first.fetchval(statement, event_payload)
            second_task = asyncio.create_task(second.fetchval(statement, event_payload))
            await asyncio.sleep(0.05)
            self.assertFalse(second_task.done(), "duplicate delivery should wait on the resource fence")

            await first_transaction.commit()
            committed = True
            second_result = await asyncio.wait_for(second_task, timeout=2)
        finally:
            if not committed:
                await first_transaction.rollback()
            await first.close()
            await second.close()

        self.assertEqual(_decode_json(first_result)["resolution_type"], "processed")
        self.assertEqual(_decode_json(second_result)["resolution_type"], "already_processed")
        self.assertEqual(
            await self.connection.fetchval(
                "select count(*) from public.billing_webhook_events where event_id = 'evt_webhook_concurrency'"
            ),
            1,
        )
        self.assertEqual(
            await self.connection.fetchval(
                """
                select consumed_seconds
                from public.credit_lots
                where lot_type = 'pack_order'
                  and source_key = 'ord_webhook_concurrency'
                """
            ),
            50,
        )


def _decode_json(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    if isinstance(value, dict):
        return value
    raise AssertionError(f"Unexpected JSON result: {type(value)!r}")


if __name__ == "__main__":
    unittest.main()
