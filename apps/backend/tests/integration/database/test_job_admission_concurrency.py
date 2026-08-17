from __future__ import annotations

import asyncio
import json
import os
import unittest
from typing import Any

import asyncpg

DATABASE_URL = os.getenv("FATHOM_TEST_DATABASE_URL")
USER_ID = "a8000000-0000-0000-0000-000000000001"


@unittest.skipUnless(DATABASE_URL, "FATHOM_TEST_DATABASE_URL is not configured")
class JobAdmissionConcurrencyIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.connection = await asyncpg.connect(DATABASE_URL)
        await self._cleanup()
        await self.connection.execute(
            "insert into auth.users (id) values ($1::uuid)",
            USER_ID,
        )
        await self.connection.execute(
            """
            insert into public.entitlements (
              user_id, subscription_available_seconds, pack_available_seconds,
              debt_seconds, is_blocked
            )
            values ($1::uuid, 100, 0, 0, false)
            """,
            USER_ID,
        )

    async def asyncTearDown(self) -> None:
        await self._cleanup()
        await self.connection.close()

    async def _cleanup(self) -> None:
        await self.connection.execute(
            "delete from public.jobs where user_id = $1::uuid",
            USER_ID,
        )
        await self.connection.execute(
            "delete from public.entitlements where user_id = $1::uuid",
            USER_ID,
        )
        await self.connection.execute(
            "delete from auth.users where id = $1::uuid",
            USER_ID,
        )

    async def test_concurrent_admissions_cannot_commit_the_same_balance_twice(self) -> None:
        first = await asyncpg.connect(DATABASE_URL)
        second = await asyncpg.connect(DATABASE_URL)
        try:
            first_call = asyncio.create_task(self._admit(first, "concurrent-a"))
            second_call = asyncio.create_task(self._admit(second, "concurrent-b"))
            results = await asyncio.wait_for(
                asyncio.gather(first_call, second_call),
                timeout=5,
            )
        finally:
            await first.close()
            await second.close()

        resolutions = sorted(result["resolution_type"] for result in results)
        self.assertEqual(resolutions, ["new", "video_time_committed"])
        rejected = next(result for result in results if result["resolution_type"] == "video_time_committed")
        self.assertEqual(rejected["details"]["pending_seconds"], 80)
        self.assertEqual(rejected["details"]["available_seconds"], 20)
        self.assertEqual(
            await self.connection.fetchval(
                "select count(*) from public.jobs where user_id = $1::uuid",
                USER_ID,
            ),
            1,
        )

    async def _admit(self, connection: asyncpg.Connection, video_id: str) -> dict[str, Any]:
        value = await connection.fetchval(
            """
            select public.create_or_reuse_settled_job(
              $1::uuid,
              $2::text,
              $3::text,
              80,
              null
            )
            """,
            USER_ID,
            f"https://www.youtube.com/watch?v={video_id}",
            f"youtube:{video_id}",
        )
        return json.loads(value) if isinstance(value, str) else value


if __name__ == "__main__":
    unittest.main()
