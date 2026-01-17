from __future__ import annotations

from uuid import UUID

from app.api.deps.auth import AuthContext
from app.core.config import Settings
from app.crud.supabase.jobs import fetch_job
from app.schemas.jobs import JobStatusResponse
from app.services.supabase import create_supabase_user_client


async def get_job_status(job_id: UUID, auth: AuthContext, settings: Settings) -> JobStatusResponse:
    client = await create_supabase_user_client(settings, auth.access_token)
    job = await fetch_job(client, str(job_id))

    return JobStatusResponse(
        job_id=job["id"],
        status=job["status"],
        summary_id=job.get("summary_id"),
        error_code=job.get("error_code"),
        error_message=job.get("error_message"),
    )
