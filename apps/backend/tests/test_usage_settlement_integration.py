from __future__ import annotations

import asyncio
import json
import os
import unittest
from typing import Any

import asyncpg

DATABASE_URL = os.getenv("FATHOM_TEST_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "FATHOM_TEST_DATABASE_URL is not configured")
class UsageSettlementConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.connection = await asyncpg.connect(DATABASE_URL)
        await self._cleanup()
        await self.connection.execute(
            """
            insert into auth.users (id)
            values ('93000000-0000-0000-0000-000000000001');

            insert into public.transcripts (
              id, url_hash, video_id, transcript_text, provider_model
            )
            values (
              '91000000-0000-0000-0000-000000000001',
              'usage-concurrency',
              'usage-concurrency',
              'Transcript',
              'test-provider'
            );

            insert into public.summaries (
              id, transcript_id, prompt_key, summary_model,
              summary_markdown, status, status_updated_at, ready_at
            )
            values (
              '92000000-0000-0000-0000-000000000001',
              '91000000-0000-0000-0000-000000000001',
              'usage-concurrency',
              'test-model',
              '# Ready',
              'ready',
              now(),
              now()
            );

            insert into public.entitlements (
              user_id, subscription_available_seconds, pack_available_seconds,
              debt_seconds, is_blocked
            )
            values (
              '93000000-0000-0000-0000-000000000001',
              120,
              0,
              0,
              false
            );

            insert into public.credit_lots (
              id, user_id, lot_type, source_key, granted_seconds,
              expires_at, status
            )
            values (
              '94000000-0000-0000-0000-000000000001',
              '93000000-0000-0000-0000-000000000001',
              'subscription_cycle',
              'subscription:concurrency',
              120,
              now() + interval '30 days',
              'active'
            );

            insert into public.jobs (
              id, user_id, status, url, source_key, duration_seconds,
              summary_id, stage, progress, claimed_at, heartbeat_at,
              lease_token, lease_expires_at, usage_settlement_required
            )
            values (
              '95000000-0000-0000-0000-000000000001',
              '93000000-0000-0000-0000-000000000001',
              'running',
              'https://www.youtube.com/watch?v=usage-concurrency',
              'youtube:usage-concurrency',
              120,
              '92000000-0000-0000-0000-000000000001',
              'finalizing',
              98,
              now(),
              now(),
              '96000000-0000-0000-0000-000000000001',
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
            """
            delete from public.usage_settlements
            where job_id = '95000000-0000-0000-0000-000000000001';
            delete from public.jobs
            where id = '95000000-0000-0000-0000-000000000001';
            delete from public.credit_lots
            where id = '94000000-0000-0000-0000-000000000001';
            delete from public.entitlements
            where user_id = '93000000-0000-0000-0000-000000000001';
            delete from public.summaries
            where id = '92000000-0000-0000-0000-000000000001';
            delete from public.transcripts
            where id = '91000000-0000-0000-0000-000000000001';
            delete from auth.users
            where id = '93000000-0000-0000-0000-000000000001';
            """
        )

    async def test_concurrent_settlers_serialize_to_one_charge(self) -> None:
        first = await asyncpg.connect(DATABASE_URL)
        second = await asyncpg.connect(DATABASE_URL)
        first_transaction = first.transaction()
        committed = False
        try:
            await first_transaction.start()
            first_result = await first.fetchval(
                """
                select public.settle_job_usage(
                  '95000000-0000-0000-0000-000000000001',
                  '96000000-0000-0000-0000-000000000001',
                  600
                )
                """
            )
            second_task = asyncio.create_task(
                second.fetchval(
                    """
                    select public.settle_job_usage(
                      '95000000-0000-0000-0000-000000000001',
                      '96000000-0000-0000-0000-000000000001',
                      600
                    )
                    """
                )
            )
            await asyncio.sleep(0.05)
            self.assertFalse(second_task.done(), "second settler should wait on the locked job")

            await first_transaction.commit()
            committed = True
            second_result = await asyncio.wait_for(second_task, timeout=2)
        finally:
            if not committed:
                await first_transaction.rollback()
            await first.close()
            await second.close()

        first_payload = _decode_json(first_result)
        second_payload = _decode_json(second_result)
        self.assertEqual(first_payload["resolution_type"], "settled")
        self.assertEqual(second_payload["resolution_type"], "already_settled")
        self.assertEqual(
            await self.connection.fetchval(
                """
                select count(*)
                from public.usage_settlements
                where job_id = '95000000-0000-0000-0000-000000000001'
                """
            ),
            1,
        )
        self.assertEqual(
            await self.connection.fetchval(
                """
                select consumed_seconds
                from public.credit_lots
                where id = '94000000-0000-0000-0000-000000000001'
                """
            ),
            120,
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
