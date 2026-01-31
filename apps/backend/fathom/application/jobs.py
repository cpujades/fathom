from __future__ import annotations

import logging
from uuid import UUID

from fathom.api.deps.auth import AuthContext
from fathom.core.config import Settings
from fathom.core.logging import log_context
from fathom.crud.supabase.jobs import fetch_job
from fathom.schemas.jobs import JobStatusResponse
from fathom.services.supabase import create_supabase_user_client

logger = logging.getLogger(__name__)


async def get_job_status(job_id: UUID, auth: AuthContext, settings: Settings) -> JobStatusResponse:
    job_id_str = str(job_id)
    with log_context(job_id=job_id_str, user_id=auth.user_id):
        client = await create_supabase_user_client(settings, auth.access_token)
        job = await fetch_job(client, job_id_str)
        status = job["status"]
        logger.info("job status fetched", extra={"status": status, "summary_id": job.get("summary_id")})

        return JobStatusResponse(
            job_id=job["id"],
            status=status,
            summary_id=job.get("summary_id"),
            error_code=job.get("error_code"),
            error_message=job.get("error_message"),
            stage=job.get("stage"),
            progress=job.get("progress"),
            status_message=job.get("status_message"),
        )
