from __future__ import annotations

import json
import unittest

from starlette.requests import Request

from fathom.core.errors import InsufficientVideoTimeError
from fathom.core.handlers import handle_app_error


class ErrorContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_admission_error_keeps_stable_code_and_bounded_details(self) -> None:
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/briefing-sessions",
                "query_string": b"",
                "headers": [],
                "scheme": "http",
                "server": ("localhost", 80),
                "client": ("localhost", 1234),
            }
        )
        response = await handle_app_error(
            request,
            InsufficientVideoTimeError(
                "This video needs more time than is currently available.",
                details={"required_seconds": 2_520, "available_seconds": 1_080},
            ),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            json.loads(response.body),
            {
                "error": {
                    "code": "insufficient_video_time",
                    "message": "This video needs more time than is currently available.",
                    "details": {
                        "required_seconds": 2_520,
                        "available_seconds": 1_080,
                    },
                }
            },
        )


if __name__ == "__main__":
    unittest.main()
