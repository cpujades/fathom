from __future__ import annotations

from typing import Any

from fathom.crud.supabase.jobs import fetch_settled_job_for_summary
from fathom.crud.supabase.summaries import fetch_summary


async def fetch_authorized_summary(
    *,
    user_client: Any,
    admin_client: Any,
    user_id: str,
    summary_id: str,
) -> dict[str, Any]:
    """Fetch a shared summary only after proving access through the user's job."""
    await fetch_settled_job_for_summary(user_client, user_id=user_id, summary_id=summary_id)
    return await fetch_summary(admin_client, summary_id)


async def fetch_summary_for_owned_job(
    *,
    admin_client: Any,
    job: dict[str, Any],
) -> dict[str, Any] | None:
    """Fetch the shared summary linked by an already-authorized terminal job."""
    if str(job.get("status") or "") not in {"succeeded", "deleted"}:
        return None

    summary_id = job.get("summary_id")
    if not summary_id:
        return None

    return await fetch_summary(admin_client, str(summary_id))
