from __future__ import annotations

import gc
import os
import pathlib
import re
import secrets
import time
import unittest
import uuid
import warnings
from collections.abc import AsyncGenerator
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import asyncpg
import httpx
from starlette.requests import Request

from fathom.api.deps.auth import AuthContext
from fathom.application.briefings import sessions as session_application
from fathom.core.config import Settings, get_settings
from fathom.crud.supabase.jobs import claim_next_job
from fathom.orchestration.runner import _handle_claimed_job
from fathom.schemas.briefing_contract import (
    BriefingContract,
    DetailedSection,
    EvidenceBullet,
    EvidencePoint,
)
from fathom.schemas.transcripts import TranscriptionResult, TranscriptSegment
from fathom.services.downloader import DownloadResult, VideoMetadata
from fathom.services.provider_resilience import ProviderFailureKind
from fathom.services.summarizer import SummarizationError
from fathom.services.supabase import close_supabase_client, create_supabase_admin_client
from fathom.services.transcriber import TranscriptionError
from supabase import AsyncClient as SupabaseAsyncClient

REQUIRED_GATE_C_ENV = (
    "FATHOM_GATE_C_SUPABASE_URL",
    "FATHOM_GATE_C_PUBLISHABLE_KEY",
    "FATHOM_GATE_C_SECRET_KEY",
    "FATHOM_GATE_C_DATABASE_URL",
)
GATE_C_ENABLED = os.getenv("FATHOM_RUN_GATE_C") == "1" and all(os.getenv(name) for name in REQUIRED_GATE_C_ENV)
SSE_ID_PATTERN = re.compile(r"^id: (\d+)$", re.MULTILINE)


@unittest.skipUnless(
    GATE_C_ENABLED,
    "FATHOM_RUN_GATE_C and isolated local Supabase settings are required",
)
class AuthenticatedGateCE2ETests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.warning_context = warnings.catch_warnings(record=True)
        self.caught_warnings = self.warning_context.__enter__()
        warnings.simplefilter("always", ResourceWarning)
        self.run_id = uuid.uuid4().hex
        self.user_id: str | None = None
        self.plan_id = str(uuid.uuid4())
        self.http: httpx.AsyncClient | None = None
        self.connection: asyncpg.Connection | None = None
        self.admin_client: SupabaseAsyncClient | None = None
        self.test_video_ids = (
            f"g{self.run_id[:10]}",
            f"r{self.run_id[:10]}",
            f"f{self.run_id[:10]}",
        )
        self.settings = Settings.model_validate(
            {
                "OPENROUTER_API_KEY": "gate-c-fake-openrouter",
                "GROQ_API_KEY": "gate-c-fake-groq",
                "SUPABASE_URL": os.environ["FATHOM_GATE_C_SUPABASE_URL"],
                "SUPABASE_PUBLISHABLE_KEY": os.environ["FATHOM_GATE_C_PUBLISHABLE_KEY"],
                "SUPABASE_SECRET_KEY": os.environ["FATHOM_GATE_C_SECRET_KEY"],
                "SUPABASE_DB_PASSWORD": "postgres",
                "SUPABASE_DB_HOST": "127.0.0.1",
                "APP_ENV": "local",
                "RATE_LIMIT": 0,
            }
        )

        try:
            self.connection = await asyncpg.connect(os.environ["FATHOM_GATE_C_DATABASE_URL"])
            await self._insert_free_plan()
            self.admin_client = await create_supabase_admin_client(self.settings)
            access_token = await self._create_ephemeral_auth_session()

            with patch.dict(
                os.environ,
                {
                    "OPENROUTER_API_KEY": self.settings.openrouter_api_key,
                    "GROQ_API_KEY": self.settings.groq_api_key,
                    "SUPABASE_URL": self.settings.supabase_url,
                    "SUPABASE_PUBLISHABLE_KEY": (self.settings.supabase_publishable_key),
                    "SUPABASE_SECRET_KEY": self.settings.supabase_secret_key,
                },
            ):
                from fathom.api.app import create_app

            get_settings.cache_clear()
            app = create_app(self.settings)
            app.dependency_overrides[get_settings] = lambda: self.settings
            self.http = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://gate-c.local",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=20,
            )
            self.auth = AuthContext(
                access_token=access_token,
                user_id=cast(str, self.user_id),
            )
        except Exception:
            await self._cleanup()
            self.warning_context.__exit__(None, None, None)
            raise

    async def asyncTearDown(self) -> None:
        try:
            await self._cleanup()
            gc.collect()
            resource_warnings = [
                str(caught.message) for caught in self.caught_warnings if issubclass(caught.category, ResourceWarning)
            ]
            self.assertEqual(resource_warnings, [])
        finally:
            self.warning_context.__exit__(None, None, None)

    async def test_authenticated_product_and_recovery_journeys(self) -> None:
        api = self._api()
        good_video, retry_video, failed_video = self.test_video_ids

        unauthenticated = await api.post(
            "/briefing-sessions",
            headers={"Authorization": ""},
            json={"url": self._video_url(good_video)},
        )
        self.assertEqual(unauthenticated.status_code, 401)

        good_session = await self._create_session(good_video)
        good_session_id = str(good_session["session_id"])
        stream = cast(
            AsyncGenerator[str, None],
            session_application._session_event_stream(
                session_id=uuid.UUID(good_session_id),
                auth=self.auth,
                settings=self.settings,
                request=cast(Request, _StreamRequest()),
            ),
        )
        self.assertEqual(await anext(stream), "retry: 2000\n\n")
        initial_snapshot = await anext(stream)
        self.assertIn("event: session.snapshot", initial_snapshot)
        initial_cursor = _event_id(initial_snapshot)

        await self._process_next_job(
            transcription=_successful_transcription(),
            summary=_briefing_contract(),
        )

        poll = AsyncMock(wraps=session_application.list_job_events_after)
        with patch.object(session_application, "list_job_events_after", poll):
            poll_started = time.perf_counter()
            first_live_event = await anext(stream)
            poll_elapsed = time.perf_counter() - poll_started
        self.assertGreaterEqual(poll_elapsed, 0.85)
        self.assertLess(poll_elapsed, 2.5)
        self.assertEqual(poll.await_count, 1)
        self.assertIn("event: session.event", first_live_event)
        reconnect_cursor = _event_id(first_live_event)
        self.assertGreater(reconnect_cursor, initial_cursor)
        await stream.aclose()
        print(f"GATE_C_POLL_METRIC elapsed_seconds={poll_elapsed:.3f} queries=1 viewers=1 interval_seconds=1.0")

        reconnect_chunks = [
            chunk
            async for chunk in session_application._session_event_stream(
                session_id=uuid.UUID(good_session_id),
                auth=self.auth,
                settings=self.settings,
                request=cast(
                    Request,
                    _StreamRequest(last_event_id=str(reconnect_cursor)),
                ),
            )
        ]
        reconnect_body = "".join(reconnect_chunks)
        replayed_ids = [int(match) for match in SSE_ID_PATTERN.findall(reconnect_body) if int(match) > reconnect_cursor]
        self.assertTrue(replayed_ids)
        self.assertEqual(replayed_ids, sorted(replayed_ids))
        self.assertIn("event: session.snapshot", reconnect_body)
        self.assertIn("Gate C briefing", reconnect_body)

        ready_snapshot = await api.get(f"/briefing-sessions/{good_session_id}")
        self.assertEqual(ready_snapshot.status_code, 200)
        self.assertEqual(ready_snapshot.json()["state"], "ready")
        briefing_id = str(ready_snapshot.json()["briefing_id"])

        briefing = await api.get(f"/briefings/{briefing_id}")
        self.assertEqual(briefing.status_code, 200)
        self.assertIn("Gate C briefing", briefing.json()["markdown"])

        pdf = await api.post(f"/briefings/{briefing_id}/pdf")
        self.assertEqual(pdf.status_code, 200, pdf.text)
        signed_pdf_url = str(pdf.json()["pdf_url"])
        async with httpx.AsyncClient(timeout=20) as signed_client:
            downloaded_pdf = await signed_client.get(signed_pdf_url)
        self.assertEqual(downloaded_pdf.status_code, 200)
        self.assertTrue(downloaded_pdf.content.startswith(b"%PDF"))

        archived = await api.delete(f"/briefing-sessions/{good_session_id}")
        self.assertEqual(archived.status_code, 204)
        hidden = await api.get(f"/briefing-sessions/{good_session_id}")
        self.assertEqual(hidden.status_code, 404)

        restored = await api.post(
            "/briefing-sessions",
            json={"url": self._video_url(good_video)},
        )
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(str(restored.json()["session_id"]), good_session_id)
        self.assertEqual(restored.json()["state"], "ready")
        self.assertEqual(restored.json()["resolution_type"], "reused_ready")

        retry_session = await self._create_session(retry_video)
        retry_session_id = str(retry_session["session_id"])
        await self._process_next_job(
            transcription=TranscriptionError(
                "Gate C transient transcription failure.",
                kind=ProviderFailureKind.TRANSIENT,
            ),
            summary=_briefing_contract(),
            zero_worker_backoff=True,
        )
        retry_queued = await self._job_row(retry_session_id)
        self.assertEqual(retry_queued["status"], "queued")
        self.assertEqual(retry_queued["stage"], "queued")
        self.assertEqual(retry_queued["attempt_count"], 1)
        self.assertEqual(retry_queued["error_code"], "transcription_failed")

        await self._process_next_job(
            transcription=_successful_transcription(),
            summary=_briefing_contract(),
        )
        retry_ready = await self._job_row(retry_session_id)
        self.assertEqual(retry_ready["status"], "succeeded")
        self.assertEqual(retry_ready["attempt_count"], 2)

        failed_session = await self._create_session(failed_video)
        failed_session_id = str(failed_session["session_id"])
        await self._process_next_job(
            transcription=_successful_transcription(),
            summary=SummarizationError(
                "Gate C permanent summary failure.",
                kind=ProviderFailureKind.PERMANENT,
            ),
        )
        failed_row = await self._job_row(failed_session_id)
        self.assertEqual(failed_row["status"], "failed")
        self.assertEqual(failed_row["error_code"], "summary_failed")
        failed_stream = await api.get(
            f"/briefing-sessions/{failed_session_id}/events",
            headers={"Last-Event-ID": "0"},
        )
        self.assertEqual(failed_stream.status_code, 200)
        self.assertIn("event: session.snapshot", failed_stream.text)
        self.assertIn('"state":"failed"', failed_stream.text)

        usage = await api.get("/billing/usage")
        self.assertEqual(usage.status_code, 200, usage.text)
        self.assertEqual(usage.json()["total_remaining_seconds"], 3360)
        plans = await api.get("/billing/plans")
        self.assertEqual(plans.status_code, 200)
        self.assertTrue(any(plan["polar_product_id"] == "internal_free" for plan in plans.json()))
        usage_history = await api.get("/billing/briefings")
        self.assertEqual(usage_history.status_code, 200)
        self.assertEqual(len(usage_history.json()), 2)

        connection = self._connection()
        settlement_rows = await connection.fetch(
            """
            select job_id, duration_seconds
            from public.usage_settlements
            where user_id = $1
            order by settled_at
            """,
            uuid.UUID(cast(str, self.user_id)),
        )
        self.assertEqual(len(settlement_rows), 2)
        self.assertEqual(
            {str(row["job_id"]) for row in settlement_rows},
            {good_session_id, retry_session_id},
        )
        self.assertTrue(all(int(row["duration_seconds"]) == 120 for row in settlement_rows))
        self.assertEqual(
            await connection.fetchval(
                """
                select count(*)
                from public.usage_settlements
                where user_id = $1
                  and job_id = $2
                """,
                uuid.UUID(cast(str, self.user_id)),
                uuid.UUID(retry_session_id),
            ),
            1,
        )
        self.assertEqual(
            await connection.fetchval(
                """
                select count(*)
                from public.usage_settlements
                where user_id = $1
                  and job_id = $2
                """,
                uuid.UUID(cast(str, self.user_id)),
                uuid.UUID(failed_session_id),
            ),
            0,
        )

    async def _create_session(self, video_id: str) -> dict[str, Any]:
        with patch.object(
            session_application,
            "fetch_video_metadata_with_deadline",
            new=AsyncMock(
                return_value=VideoMetadata(
                    video_id=video_id,
                    duration_seconds=120,
                    title=f"Gate C {video_id}",
                )
            ),
        ):
            response = await self._api().post(
                "/briefing-sessions",
                json={"url": self._video_url(video_id)},
            )
        self.assertEqual(response.status_code, 200, response.text)
        return cast(dict[str, Any], response.json())

    async def _process_next_job(
        self,
        *,
        transcription: TranscriptionResult | Exception,
        summary: BriefingContract | Exception,
        zero_worker_backoff: bool = False,
    ) -> None:
        admin_client = self._admin_client()
        claimed = await claim_next_job(admin_client, lease_seconds=120)
        self.assertIsNotNone(claimed)

        transcription_fake = AsyncMock(
            side_effect=transcription if isinstance(transcription, Exception) else None,
            return_value=None if isinstance(transcription, Exception) else transcription,
        )
        summary_fake = AsyncMock(
            side_effect=summary if isinstance(summary, Exception) else None,
            return_value=None if isinstance(summary, Exception) else summary,
        )
        backoff = 0 if zero_worker_backoff else 5
        with (
            patch(
                "fathom.orchestration.transcripts.download_audio_with_deadline",
                side_effect=_fake_download_audio,
            ),
            patch(
                "fathom.orchestration.transcripts.transcribe_url_with_resilience",
                transcription_fake,
            ),
            patch(
                "fathom.orchestration.summaries.summarize_transcript_with_evidence",
                summary_fake,
            ),
            patch(
                "fathom.orchestration.runner._compute_backoff_seconds",
                return_value=backoff,
            ),
        ):
            await _handle_claimed_job(
                cast(dict[str, Any], claimed),
                self.settings,
                admin_client,
            )

    async def _job_row(self, job_id: str) -> asyncpg.Record:
        row = await self._connection().fetchrow(
            """
            select id, status, stage, attempt_count, error_code, summary_id
            from public.jobs
            where id = $1
            """,
            uuid.UUID(job_id),
        )
        self.assertIsNotNone(row)
        return cast(asyncpg.Record, row)

    async def _insert_free_plan(self) -> None:
        await self._connection().execute(
            """
            insert into public.plans (
              id, name, plan_type, polar_product_id, plan_code, currency,
              amount_cents, billing_interval, version, quota_seconds,
              rollover_cap_seconds, is_active
            )
            values (
              $1, 'Gate C Free', 'subscription', 'internal_free',
              $2, 'usd', 0, 'month', 1, 3600, 0, true
            )
            """,
            uuid.UUID(self.plan_id),
            f"gate_c_free_{self.run_id}",
        )

    async def _create_ephemeral_auth_session(self) -> str:
        admin_client = self._admin_client()
        email = f"gate-c-{self.run_id}@example.test"
        password = secrets.token_urlsafe(24)
        created = await admin_client.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
            }
        )
        if created.user is None:
            self.fail("Supabase Auth did not return the ephemeral user.")
        self.user_id = str(created.user.id)

        async with httpx.AsyncClient(timeout=20) as auth_client:
            signed_in = await auth_client.post(
                f"{self.settings.supabase_url.rstrip('/')}/auth/v1/token",
                params={"grant_type": "password"},
                headers={
                    "apikey": self.settings.supabase_publishable_key,
                    "Content-Type": "application/json",
                },
                json={
                    "email": email,
                    "password": password,
                },
            )
        signed_in.raise_for_status()
        access_token = signed_in.json().get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise AssertionError("Supabase Auth did not return an ephemeral session.")
        return access_token

    async def _cleanup(self) -> None:
        first_error: Exception | None = None
        try:
            if self.http is not None:
                await self.http.aclose()
        except Exception as exc:
            first_error = exc

        try:
            await self._cleanup_storage()
        except Exception as exc:
            first_error = first_error or exc

        try:
            await self._cleanup_database()
        except Exception as exc:
            first_error = first_error or exc

        try:
            if self.admin_client is not None and self.user_id is not None:
                await self.admin_client.auth.admin.delete_user(self.user_id)
        except Exception as exc:
            first_error = first_error or exc

        try:
            if self.admin_client is not None:
                await close_supabase_client(self.admin_client)
        except Exception as exc:
            first_error = first_error or exc

        try:
            if self.connection is not None and not self.connection.is_closed():
                await self.connection.close()
        except Exception as exc:
            first_error = first_error or exc

        if first_error is not None:
            raise first_error

    async def _cleanup_storage(self) -> None:
        if self.connection is None or self.connection.is_closed():
            return
        rows = await self.connection.fetch(
            """
            select pdf_object_key
            from public.summaries
            where user_id = $1
              and pdf_object_key is not null
            """,
            uuid.UUID(self.user_id) if self.user_id else uuid.UUID(int=0),
        )
        keys = [str(row["pdf_object_key"]) for row in rows if row["pdf_object_key"]]
        if keys and self.admin_client is not None:
            await self.admin_client.storage.from_("fathom").remove(keys)

    async def _cleanup_database(self) -> None:
        if self.connection is None or self.connection.is_closed():
            return
        user_id = uuid.UUID(self.user_id) if self.user_id else uuid.UUID(int=0)
        statements: tuple[tuple[str, tuple[Any, ...]], ...] = (
            ("delete from public.usage_ledger where user_id = $1", (user_id,)),
            (
                "delete from public.usage_settlements where user_id = $1",
                (user_id,),
            ),
            ("delete from public.jobs where user_id = $1", (user_id,)),
            ("delete from public.summaries where user_id = $1", (user_id,)),
            (
                "delete from public.transcripts where video_id = any($1::text[])",
                (list(self.test_video_ids),),
            ),
            ("delete from public.credit_lots where user_id = $1", (user_id,)),
            ("delete from public.entitlements where user_id = $1", (user_id,)),
            ("delete from public.billing_orders where user_id = $1", (user_id,)),
            ("delete from public.polar_customers where user_id = $1", (user_id,)),
            (
                "delete from public.plans where id = $1",
                (uuid.UUID(self.plan_id),),
            ),
        )
        async with self.connection.transaction():
            for statement, arguments in statements:
                await self.connection.execute(statement, *arguments)

    def _api(self) -> httpx.AsyncClient:
        if self.http is None:
            raise AssertionError("Gate C API client is not initialized.")
        return self.http

    def _admin_client(self) -> SupabaseAsyncClient:
        if self.admin_client is None:
            raise AssertionError("Gate C admin client is not initialized.")
        return self.admin_client

    def _connection(self) -> asyncpg.Connection:
        if self.connection is None:
            raise AssertionError("Gate C database connection is not initialized.")
        return self.connection

    @staticmethod
    def _video_url(video_id: str) -> str:
        return f"https://www.youtube.com/watch?v={video_id}"


class _StreamRequest:
    def __init__(self, *, last_event_id: str | None = None) -> None:
        self.headers = {"last-event-id": last_event_id} if last_event_id is not None else {}

    async def is_disconnected(self) -> bool:
        return False


def _fake_download_audio(
    url: str,
    output_dir: str,
    **_: Any,
) -> DownloadResult:
    video_id = url.rsplit("v=", maxsplit=1)[-1]
    path = pathlib.Path(output_dir) / f"{video_id}.mp3"
    path.write_bytes(b"gate-c-fake-audio")
    return DownloadResult(
        path=path,
        video_id=video_id,
        mime_type="audio/mpeg",
        subtype="mp3",
        filesize_bytes=path.stat().st_size,
        title=f"Gate C source {video_id}",
        author="Talven Test",
        description="Ephemeral Gate C fixture.",
        keywords=["gate-c"],
        views=1,
        likes=1,
        length_seconds=120,
    )


def _successful_transcription() -> TranscriptionResult:
    segments = (
        TranscriptSegment(
            segment_index=0,
            start_seconds=0,
            end_seconds=30,
            text="The source explains the first verified Gate C point.",
        ),
        TranscriptSegment(
            segment_index=1,
            start_seconds=30,
            end_seconds=60,
            text="The source supports a second concrete point.",
        ),
        TranscriptSegment(
            segment_index=2,
            start_seconds=60,
            end_seconds=90,
            text="The source identifies a practical next step.",
        ),
        TranscriptSegment(
            segment_index=3,
            start_seconds=90,
            end_seconds=120,
            text="The source closes with a measurable outcome.",
        ),
    )
    return TranscriptionResult(
        text=" ".join(segment.text for segment in segments),
        segments=segments,
    )


def _briefing_contract() -> BriefingContract:
    return BriefingContract(
        title="Gate C briefing",
        brief=EvidencePoint(
            text="A verified briefing produced through the fake provider boundary.",
            segment_indexes=(0, 1),
        ),
        key_takeaways=(
            EvidenceBullet(
                label="Evidence",
                text="The first claim is grounded.",
                segment_indexes=(0,),
            ),
            EvidenceBullet(
                label="Specificity",
                text="The second claim remains concrete.",
                segment_indexes=(1,),
            ),
            EvidenceBullet(
                label="Action",
                text="The next step is explicit.",
                segment_indexes=(2,),
            ),
            EvidenceBullet(
                label="Outcome",
                text="The result is measurable.",
                segment_indexes=(3,),
            ),
        ),
        detailed_briefing=(
            DetailedSection(
                heading="What the source establishes",
                paragraphs=(
                    EvidencePoint(
                        text="The source supports the Gate C success path.",
                        segment_indexes=(0, 1),
                    ),
                ),
            ),
        ),
        highlights_and_quotes=(),
        action_items=(
            EvidenceBullet(
                label="Verify",
                text="Review the persisted result.",
                segment_indexes=(2,),
            ),
        ),
        next_steps=(),
        open_questions=(),
        references=(),
    )


def _event_id(chunk: str) -> int:
    match = SSE_ID_PATTERN.search(chunk)
    if match is None:
        raise AssertionError(f"SSE chunk did not contain an id: {chunk[:120]!r}")
    return int(match.group(1))


if __name__ == "__main__":
    unittest.main()
