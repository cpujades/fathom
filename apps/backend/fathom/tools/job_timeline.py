from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from fathom.application.diagnostics.job_timeline import fetch_job_timeline, format_job_timeline
from fathom.core.config import get_settings
from fathom.services.supabase import create_supabase_admin_client


def main() -> None:
    parser = argparse.ArgumentParser(description="Show a local/admin timeline for a Talven briefing session.")
    parser.add_argument("session_id", help="Briefing session/job UUID.")
    parser.add_argument("--json", action="store_true", help="Print the raw timeline snapshot as JSON.")
    args = parser.parse_args()

    try:
        snapshot = asyncio.run(_fetch_snapshot(args.session_id))
    except Exception as exc:
        print(f"Failed to fetch job timeline: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        print(json.dumps(snapshot, indent=2, sort_keys=True, default=str))
        return

    print(format_job_timeline(snapshot))


async def _fetch_snapshot(session_id: str) -> dict[str, Any]:
    settings = get_settings()
    admin_client = await create_supabase_admin_client(settings)
    return await fetch_job_timeline(admin_client, session_id=session_id)


if __name__ == "__main__":
    main()
