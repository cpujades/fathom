from __future__ import annotations

import asyncio
import json
import os
import unittest
from typing import Any

import asyncpg

DATABASE_URL = os.getenv("FATHOM_TEST_DATABASE_URL")

USER_ID = "a1000000-0000-0000-0000-000000000001"
TRANSCRIPT_ID = "a2000000-0000-0000-0000-000000000001"
SUMMARY_ID = "a3000000-0000-0000-0000-000000000001"
LOT_ID = "a4000000-0000-0000-0000-000000000001"
JOB_ID = "a5000000-0000-0000-0000-000000000001"
LEASE_TOKEN = "a6000000-0000-0000-0000-000000000001"
POLAR_ORDER_ID = "ord_refund_settlement_concurrency"


@unittest.skipUnless(DATABASE_URL, "FATHOM_TEST_DATABASE_URL is not configured")
class BillingConcurrencyIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.connection = await asyncpg.connect(DATABASE_URL)
        await self._cleanup()
        await self.connection.execute(
            f"""
            insert into auth.users (id) values ('{USER_ID}');

            insert into public.transcripts (
              id, url_hash, video_id, transcript_text, provider_model
            )
            values (
              '{TRANSCRIPT_ID}',
              'billing-refund-concurrency',
              'billing-refund-concurrency',
              'Transcript',
              'test-provider'
            );

            insert into public.summaries (
              id, transcript_id, prompt_key, summary_model,
              summary_markdown, status, status_updated_at, ready_at
            )
            values (
              '{SUMMARY_ID}',
              '{TRANSCRIPT_ID}',
              'billing-refund-concurrency',
              'test-model',
              '# Ready',
              'ready',
              now(),
              now()
            );

            insert into public.entitlements (
              user_id, pack_available_seconds, debt_seconds, is_blocked
            )
            values ('{USER_ID}', 600, 0, false);

            insert into public.billing_orders (
              polar_order_id, user_id, plan_type, currency,
              paid_amount_cents, status
            )
            values ('{POLAR_ORDER_ID}', '{USER_ID}', 'pack', 'usd', 3000, 'paid');

            insert into public.credit_lots (
              id, user_id, lot_type, source_key, granted_seconds,
              expires_at, status
            )
            values (
              '{LOT_ID}',
              '{USER_ID}',
              'pack_order',
              '{POLAR_ORDER_ID}',
              600,
              now() + interval '30 days',
              'active'
            );

            insert into public.jobs (
              id, user_id, status, url, source_key, duration_seconds,
              summary_id, stage, progress, claimed_at, heartbeat_at,
              lease_token, lease_expires_at, usage_settlement_required
            )
            values (
              '{JOB_ID}',
              '{USER_ID}',
              'running',
              'https://www.youtube.com/watch?v=billing-refund-concurrency',
              'youtube:billing-refund-concurrency',
              200,
              '{SUMMARY_ID}',
              'finalizing',
              98,
              now(),
              now(),
              '{LEASE_TOKEN}',
              now() + interval '2 minutes',
              true
            );
            """
        )

    async def asyncTearDown(self) -> None:
        await self._cleanup()
        await self.connection.close()

    async def _cleanup(self) -> None:
        await self.connection.execute(
            f"""
            delete from public.billing_maintenance_leases
            where lease_name = 'billing-concurrency-test';
            delete from public.usage_settlements
            where job_id in (
              select id from public.jobs where user_id = '{USER_ID}'
            );
            delete from public.jobs where user_id = '{USER_ID}';
            delete from public.credit_lots where id = '{LOT_ID}';
            delete from public.billing_orders where polar_order_id = '{POLAR_ORDER_ID}';
            delete from public.entitlements where user_id = '{USER_ID}';
            delete from public.summaries where id = '{SUMMARY_ID}';
            delete from public.transcripts where id = '{TRANSCRIPT_ID}';
            delete from auth.users where id = '{USER_ID}';
            """
        )

    async def test_refund_waits_for_active_job_to_settle_and_finish(self) -> None:
        blocked_before_settlement = _decode_json(
            await self.connection.fetchval(f"select public.begin_pack_refund('{USER_ID}', '{POLAR_ORDER_ID}', 600)")
        )
        settlement = _decode_json(
            await self.connection.fetchval(f"select public.settle_job_usage('{JOB_ID}', '{LEASE_TOKEN}', 600)")
        )
        blocked_before_completion = _decode_json(
            await self.connection.fetchval(f"select public.begin_pack_refund('{USER_ID}', '{POLAR_ORDER_ID}', 600)")
        )
        completed = await self.connection.fetchval(
            f"""
            select public.complete_job_after_settlement(
              '{JOB_ID}', '{SUMMARY_ID}', '{LEASE_TOKEN}'
            )
            """
        )
        refund = _decode_json(
            await self.connection.fetchval(f"select public.begin_pack_refund('{USER_ID}', '{POLAR_ORDER_ID}', 600)")
        )

        self.assertEqual(blocked_before_settlement["resolution_type"], "active_jobs_in_progress")
        self.assertEqual(settlement["resolution_type"], "settled")
        self.assertEqual(settlement["settlement"]["pack_seconds"], 200)
        self.assertEqual(blocked_before_completion["resolution_type"], "active_jobs_in_progress")
        self.assertTrue(completed)
        self.assertEqual(refund["resolution_type"], "started")
        self.assertEqual(refund["remaining_seconds_before_refund"], 400)
        self.assertEqual(refund["refundable_amount_cents"], 2000)
        self.assertEqual(await self._order_status(), "refund_pending")
        self.assertEqual(await self._lot_consumed_seconds(), 200)
        self.assertEqual(await self._pack_available_seconds(), 0)

    async def test_job_admission_and_refund_serialize_for_one_user(self) -> None:
        await self.connection.execute("delete from public.jobs where id = $1", JOB_ID)
        admitter = await asyncpg.connect(DATABASE_URL)
        refunder = await asyncpg.connect(DATABASE_URL)
        admission_transaction = admitter.transaction()
        committed = False
        try:
            await admission_transaction.start()
            admission = _decode_json(
                await admitter.fetchval(
                    """
                    select public.create_or_reuse_settled_job(
                      $1::uuid,
                      'https://www.youtube.com/watch?v=refund-admission-race',
                      'youtube:refund-admission-race',
                      200,
                      null
                    )
                    """,
                    USER_ID,
                )
            )
            refund_task = asyncio.create_task(
                refunder.fetchval(
                    "select public.begin_pack_refund($1::uuid, $2, 600)",
                    USER_ID,
                    POLAR_ORDER_ID,
                )
            )
            await asyncio.sleep(0.05)
            self.assertFalse(refund_task.done(), "refund must wait for the user's admission lock")

            await admission_transaction.commit()
            committed = True
            refund = _decode_json(await asyncio.wait_for(refund_task, timeout=2))
        finally:
            if not committed:
                await admission_transaction.rollback()
            await admitter.close()
            await refunder.close()

        self.assertEqual(admission["resolution_type"], "new")
        self.assertEqual(refund["resolution_type"], "active_jobs_in_progress")
        self.assertEqual(await self._order_status(), "paid")
        self.assertEqual(await self._lot_consumed_seconds(), 0)

    async def test_only_one_concurrent_maintenance_worker_claims_the_lease(self) -> None:
        first = await asyncpg.connect(DATABASE_URL)
        second = await asyncpg.connect(DATABASE_URL)
        first_token = "a7000000-0000-0000-0000-000000000001"
        second_token = "a7000000-0000-0000-0000-000000000002"
        try:
            first_task = asyncio.create_task(
                first.fetchval(
                    """
                    select public.claim_billing_maintenance_lease(
                      'billing-concurrency-test', $1::uuid, interval '2 minutes'
                    )
                    """,
                    first_token,
                )
            )
            second_task = asyncio.create_task(
                second.fetchval(
                    """
                    select public.claim_billing_maintenance_lease(
                      'billing-concurrency-test', $1::uuid, interval '2 minutes'
                    )
                    """,
                    second_token,
                )
            )
            acquired = await asyncio.wait_for(
                asyncio.gather(first_task, second_task),
                timeout=2,
            )
            self.assertEqual(acquired.count(True), 1)
            owner_token = first_token if acquired[0] else second_token
            self.assertTrue(
                await self.connection.fetchval(
                    """
                    select public.release_billing_maintenance_lease(
                      'billing-concurrency-test', $1::uuid
                    )
                    """,
                    owner_token,
                )
            )
        finally:
            await first.close()
            await second.close()

    async def _order_status(self) -> str:
        return await self.connection.fetchval(
            "select status from public.billing_orders where polar_order_id = $1",
            POLAR_ORDER_ID,
        )

    async def _lot_consumed_seconds(self) -> int:
        return await self.connection.fetchval(
            "select consumed_seconds from public.credit_lots where id = $1",
            LOT_ID,
        )

    async def _pack_available_seconds(self) -> int:
        return await self.connection.fetchval(
            "select pack_available_seconds from public.entitlements where user_id = $1",
            USER_ID,
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
