from __future__ import annotations

import asyncio
import json
import sys
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from fathom.services import pdf
from fathom.services.pdf import PDFError


class _FakeHTML:
    instances: list[_FakeHTML] = []
    output = b"%PDF-fake"
    error: Exception | None = None

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.__class__.instances.append(self)

    def write_pdf(self) -> bytes:
        if self.error is not None:
            raise self.error
        return self.output


class _FakeProcess:
    def __init__(
        self,
        *,
        stdout: bytes = b"%PDF-process",
        stderr: bytes = b"",
        returncode: int | None = 0,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.request: bytes | None = None
        self.killed = False

    async def communicate(self, request: bytes) -> tuple[bytes, bytes]:
        self.request = request
        return self.stdout, self.stderr

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    async def wait(self) -> int:
        return self.returncode or 0


class PDFRenderingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        _FakeHTML.instances.clear()
        _FakeHTML.output = b"%PDF-fake"
        _FakeHTML.error = None

    def test_raw_html_is_escaped_and_talven_branding_is_used(self) -> None:
        with patch.dict("sys.modules", {"weasyprint": _weasyprint_module()}):
            rendered = pdf.markdown_to_pdf_bytes(
                "# Briefing\n<script src='https://attacker.example/x.js'>alert(1)</script>"
            )

        self.assertEqual(rendered, b"%PDF-fake")
        html = str(_FakeHTML.instances[0].kwargs["string"])
        self.assertIn("Talven Briefing", html)
        self.assertIn('content: "Talven"', html)
        self.assertNotIn("Fathom Summary", html)
        self.assertNotIn("<script", html)
        self.assertIn("&lt;script", html)

    def test_resource_fetcher_denies_remote_and_local_urls(self) -> None:
        with patch.dict("sys.modules", {"weasyprint": _weasyprint_module()}):
            pdf.markdown_to_pdf_bytes("![remote](https://example.com/image.png)")

        fetcher = _FakeHTML.instances[0].kwargs["url_fetcher"]
        for url in (
            "https://example.com/image.png",
            "file:///etc/passwd",
            "http://127.0.0.1:54321/rest/v1/",
            "data:text/plain,secret",
        ):
            with (
                self.subTest(url=url),
                self.assertRaisesRegex(
                    PDFError,
                    "resources are not permitted",
                ),
            ):
                fetcher(url)

    def test_input_size_is_bounded_by_utf8_bytes(self) -> None:
        oversized = "é" * ((pdf.MAX_PDF_MARKDOWN_BYTES // 2) + 1)

        with self.assertRaisesRegex(PDFError, pdf.PDF_INPUT_TOO_LARGE_MESSAGE):
            pdf.markdown_to_pdf_bytes(oversized)

    def test_output_size_is_bounded(self) -> None:
        _FakeHTML.output = b"x" * (pdf.MAX_PDF_OUTPUT_BYTES + 1)

        with (
            patch.dict("sys.modules", {"weasyprint": _weasyprint_module()}),
            self.assertRaisesRegex(PDFError, pdf.PDF_OUTPUT_TOO_LARGE_MESSAGE),
        ):
            pdf.markdown_to_pdf_bytes("# Briefing")

    def test_render_failure_has_stable_error(self) -> None:
        _FakeHTML.error = RuntimeError("renderer internals")

        with (
            patch.dict("sys.modules", {"weasyprint": _weasyprint_module()}),
            self.assertRaisesRegex(PDFError, pdf.PDF_RENDER_FAILED_MESSAGE) as caught,
        ):
            pdf.markdown_to_pdf_bytes("# Briefing")

        self.assertNotIn("renderer internals", caught.exception.detail)

    async def test_async_render_uses_sanitized_subprocess_boundary(self) -> None:
        process = _FakeProcess()
        create_process = AsyncMock(return_value=process)

        with (
            patch.object(asyncio, "create_subprocess_exec", create_process),
            patch.dict("os.environ", {"OPENROUTER_API_KEY": "secret", "PATH": "/usr/bin"}),
        ):
            rendered = await pdf.render_markdown_pdf_bytes("# Briefing")

        self.assertEqual(rendered, b"%PDF-process")
        self.assertIsNotNone(process.request)
        request = json.loads(process.request or b"{}")
        self.assertEqual(request["markdown"], "# Briefing")
        self.assertEqual(request["title"], "Talven Briefing")
        call = create_process.await_args
        self.assertEqual(call.args[:3], (sys.executable, "-m", "fathom.services.pdf_worker"))
        worker_env = call.kwargs["env"]
        self.assertEqual(worker_env["PATH"], "/usr/bin")
        self.assertNotIn("OPENROUTER_API_KEY", worker_env)

    async def test_render_deadline_has_stable_error(self) -> None:
        process = _FakeProcess(returncode=None)

        async def wait_forever(_request: bytes) -> tuple[bytes, bytes]:
            await asyncio.Future()
            return b"unreachable", b""

        process.communicate = wait_forever  # type: ignore[method-assign]
        with (
            patch.object(
                asyncio,
                "create_subprocess_exec",
                AsyncMock(return_value=process),
            ),
            self.assertRaisesRegex(PDFError, pdf.PDF_RENDER_TIMEOUT_MESSAGE),
        ):
            await pdf.render_markdown_pdf_bytes(
                "# Briefing",
                deadline_seconds=0.001,
            )
        self.assertTrue(process.killed)

    async def test_worker_failure_has_stable_error(self) -> None:
        internal_detail = b"renderer leaked internal detail"
        process = _FakeProcess(stderr=internal_detail, returncode=2)

        with (
            patch.object(
                asyncio,
                "create_subprocess_exec",
                AsyncMock(return_value=process),
            ),
            self.assertRaisesRegex(PDFError, pdf.PDF_RENDER_FAILED_MESSAGE) as caught,
        ):
            await pdf.render_markdown_pdf_bytes("# Briefing")

        self.assertNotIn(internal_detail.decode(), caught.exception.detail)


def _weasyprint_module() -> Any:
    return type("FakeWeasyPrint", (), {"HTML": _FakeHTML})


if __name__ == "__main__":
    unittest.main()
