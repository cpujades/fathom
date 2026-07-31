from __future__ import annotations

import asyncio
import json
import sys
import unittest
from typing import Any
from unittest.mock import AsyncMock, patch

from fathom.services import pdf
from fathom.services.pdf import PDFBusyError, PDFError


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
        communication_error: Exception | None = None,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self.communication_error = communication_error
        self.request: bytes | None = None
        self.killed = False

    async def communicate(self, request: bytes) -> tuple[bytes, bytes]:
        self.request = request
        if self.communication_error is not None:
            raise self.communication_error
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

    def test_only_safe_web_and_internal_links_remain_clickable(self) -> None:
        with patch.dict("sys.modules", {"weasyprint": _weasyprint_module()}):
            pdf.markdown_to_pdf_bytes(
                "\n".join(
                    (
                        "[safe](https://example.com/reference)",
                        "[section](#details)",
                        "[script](javascript:alert(1))",
                        "[file](file:///etc/passwd)",
                        "[data](data:text/html,unsafe)",
                        "[loopback](http://127.0.0.1:54321/rest/v1/)",
                        "[numeric-loopback](http://2130706433/)",
                        "[mixed-radix-loopback](http://127.0x0.0.1/)",
                        "[hex-loopback](http://0x7f.0.0.1/)",
                        "[encoded-loopback](http://%31%32%37.0.0.1/)",
                        "[metadata](http://169.254.169.254/latest/meta-data/)",
                        "[metadata-host](http://instance-data.ec2.internal/latest/meta-data/)",
                    )
                )
            )

        html = str(_FakeHTML.instances[0].kwargs["string"])
        self.assertIn('href="https://example.com/reference"', html)
        self.assertIn('href="#details"', html)
        self.assertNotIn('href="javascript:', html)
        self.assertNotIn('href="file:', html)
        self.assertNotIn('href="data:', html)
        self.assertNotIn('href="http://127.0.0.1', html)
        self.assertNotIn('href="http://2130706433', html)
        self.assertNotIn('href="http://127.0x0.0.1', html)
        self.assertNotIn('href="http://0x7f.0.0.1', html)
        self.assertNotIn('href="http://%31%32%37.0.0.1', html)
        self.assertNotIn('href="http://169.254.169.254', html)
        self.assertNotIn('href="http://instance-data.ec2.internal', html)
        self.assertIn(">script</a>", html)

    def test_markdown_attribute_css_is_not_enabled(self) -> None:
        with patch.dict("sys.modules", {"weasyprint": _weasyprint_module()}):
            pdf.markdown_to_pdf_bytes('# Heading {style="position:fixed;background:url(file:///etc/passwd)"}')

        html = str(_FakeHTML.instances[0].kwargs["string"])
        self.assertNotIn('style="position:', html)
        self.assertIn("Heading {style=&quot;position:fixed", html)

    def test_supported_markdown_tables_code_and_footnotes_are_preserved(self) -> None:
        with patch.dict("sys.modules", {"weasyprint": _weasyprint_module()}):
            pdf.markdown_to_pdf_bytes(
                "| Topic | Detail |\n"
                "| --- | --- |\n"
                "| Safety | Preserved |\n\n"
                "```python\nprint('safe')\n```\n\n"
                "Evidence[^1]\n\n"
                "[^1]: Transcript evidence."
            )

        html = str(_FakeHTML.instances[0].kwargs["string"])
        self.assertIn("<table>", html)
        self.assertIn('class="codehilite"', html)
        self.assertIn('class="footnote"', html)

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

    async def test_async_render_terminates_child_after_communication_error(self) -> None:
        process = _FakeProcess(
            returncode=None,
            communication_error=RuntimeError("pipe failed"),
        )

        with (
            patch.object(
                asyncio,
                "create_subprocess_exec",
                AsyncMock(return_value=process),
            ),
            self.assertRaisesRegex(PDFError, pdf.PDF_RENDER_FAILED_MESSAGE),
        ):
            await pdf.render_markdown_pdf_bytes("# Briefing")

        self.assertTrue(process.killed)
        self.assertEqual(process.returncode, -9)

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

    async def test_render_concurrency_is_bounded_with_retryable_busy_error(self) -> None:
        process = _FakeProcess()
        started = asyncio.Event()
        release = asyncio.Event()

        async def blocked_communicate(request: bytes) -> tuple[bytes, bytes]:
            process.request = request
            started.set()
            await release.wait()
            return process.stdout, process.stderr

        process.communicate = blocked_communicate  # type: ignore[method-assign]
        create_process = AsyncMock(return_value=process)

        with (
            patch.object(pdf, "_PDF_RENDER_SEMAPHORE", asyncio.Semaphore(1)),
            patch.object(asyncio, "create_subprocess_exec", create_process),
        ):
            first_render = asyncio.create_task(pdf.render_markdown_pdf_bytes("# First"))
            await started.wait()
            with self.assertRaisesRegex(PDFBusyError, pdf.PDF_RENDER_BUSY_MESSAGE):
                await pdf.render_markdown_pdf_bytes(
                    "# Second",
                    queue_timeout_seconds=0.001,
                )
            release.set()
            self.assertEqual(await first_render, b"%PDF-process")

        create_process.assert_awaited_once()


def _weasyprint_module() -> Any:
    return type("FakeWeasyPrint", (), {"HTML": _FakeHTML})


if __name__ == "__main__":
    unittest.main()
