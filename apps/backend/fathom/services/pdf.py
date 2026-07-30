from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime
from html import escape
from typing import NoReturn, cast

from markdown import markdown

from fathom.core.errors import ExternalServiceError

logger = logging.getLogger(__name__)


class PDFError(ExternalServiceError):
    pass


MAX_PDF_MARKDOWN_BYTES = 1 * 1024 * 1024
MAX_PDF_TITLE_BYTES = 4 * 1024
MAX_PDF_OUTPUT_BYTES = 10 * 1024 * 1024
PDF_RENDER_DEADLINE_SECONDS = 30.0

PDF_INPUT_TOO_LARGE_MESSAGE = "Briefing content is too large to export as PDF."
PDF_OUTPUT_TOO_LARGE_MESSAGE = "Generated PDF is too large to export."
PDF_RENDER_FAILED_MESSAGE = "PDF export could not be generated."
PDF_RENDER_TIMEOUT_MESSAGE = "PDF export took too long to generate."
_PDF_WORKER_MODULE = "fathom.services.pdf_worker"
_PDF_WORKER_ERROR_PREFIX = b"FATHOM_PDF_ERROR:"
_PDF_WORKER_ENV_KEYS = (
    "DYLD_FALLBACK_LIBRARY_PATH",
    "DYLD_LIBRARY_PATH",
    "FONTCONFIG_FILE",
    "FONTCONFIG_PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "LD_LIBRARY_PATH",
    "PATH",
    "PYTHONPATH",
    "VIRTUAL_ENV",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
)
_STABLE_PDF_ERRORS = {
    PDF_INPUT_TOO_LARGE_MESSAGE,
    PDF_OUTPUT_TOO_LARGE_MESSAGE,
    PDF_RENDER_FAILED_MESSAGE,
}

PDF_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>{title}</title>
  <style>
    @page {{
      size: A4;
      margin: 2.5cm 2cm 2cm 2cm;
      @top-right {{
        content: "Talven";
        font-size: 9pt;
        color: #64748b;
        font-family: "Inter", -apple-system, sans-serif;
      }}
      @bottom-center {{
        content: "Page " counter(page) " of " counter(pages);
        font-size: 9pt;
        color: #64748b;
        font-family: "Inter", -apple-system, sans-serif;
      }}
      @bottom-right {{
        content: "{date}";
        font-size: 9pt;
        color: #64748b;
        font-family: "Inter", -apple-system, sans-serif;
      }}
    }}

    * {{
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }}

    body {{
      font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 11pt;
      line-height: 1.6;
      color: #1e293b;
      background: white;
    }}

    /* Header */
    .pdf-header {{
      margin-bottom: 2em;
      padding-bottom: 1em;
      border-bottom: 2px solid #e2e8f0;
    }}

    .pdf-header h1 {{
      font-size: 24pt;
      font-weight: 700;
      color: #0f172a;
      margin-bottom: 0.5em;
      letter-spacing: -0.02em;
    }}

    .pdf-metadata {{
      display: flex;
      gap: 1em;
      font-size: 9pt;
      color: #64748b;
    }}

    /* Typography */
    h1, h2, h3, h4, h5, h6 {{
      font-weight: 600;
      line-height: 1.3;
      margin-top: 1.5em;
      margin-bottom: 0.75em;
      color: #0f172a;
      letter-spacing: -0.01em;
    }}

    h1 {{ font-size: 20pt; border-bottom: 1px solid #e2e8f0; padding-bottom: 0.3em; }}
    h2 {{ font-size: 16pt; }}
    h3 {{ font-size: 14pt; }}
    h4 {{ font-size: 12pt; }}

    p {{
      margin-bottom: 1em;
      text-align: justify;
      hyphens: auto;
    }}

    /* Links */
    a {{
      color: #3b82f6;
      text-decoration: none;
      border-bottom: 1px solid #93c5fd;
    }}

    /* Lists */
    ul, ol {{
      margin: 1em 0 1em 1.5em;
    }}

    li {{
      margin-bottom: 0.5em;
    }}

    /* Code */
    code {{
      font-family: "Geist Mono", "Monaco", "Courier New", monospace;
      font-size: 0.9em;
      background: #f1f5f9;
      padding: 0.15em 0.4em;
      border-radius: 3px;
      color: #475569;
    }}

    pre {{
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 1em;
      margin: 1em 0;
      overflow: auto;
      page-break-inside: avoid;
    }}

    pre code {{
      background: none;
      padding: 0;
      font-size: 9pt;
      line-height: 1.5;
    }}

    /* Blockquotes */
    blockquote {{
      border-left: 4px solid #3b82f6;
      padding-left: 1em;
      margin: 1em 0;
      font-style: italic;
      color: #475569;
      background: #f8fafc;
      padding: 0.75em 1em;
      border-radius: 0 6px 6px 0;
      page-break-inside: avoid;
    }}

    /* Tables */
    table {{
      width: 100%;
      border-collapse: collapse;
      margin: 1.5em 0;
      font-size: 10pt;
      page-break-inside: avoid;
    }}

    thead {{
      background: #f1f5f9;
    }}

    th {{
      font-weight: 600;
      text-align: left;
      padding: 0.75em 1em;
      border-bottom: 2px solid #cbd5e1;
      color: #0f172a;
    }}

    td {{
      padding: 0.6em 1em;
      border-bottom: 1px solid #e2e8f0;
    }}

    tbody tr:nth-child(even) {{
      background: #f8fafc;
    }}

    /* Horizontal rule */
    hr {{
      border: none;
      border-top: 1px solid #e2e8f0;
      margin: 2em 0;
    }}

    /* Images */
    img {{
      max-width: 100%;
      height: auto;
      display: block;
      margin: 1.5em auto;
      border-radius: 6px;
    }}

    /* Page breaks */
    h1, h2, h3 {{
      page-break-after: avoid;
    }}

    p, blockquote, pre {{
      orphans: 3;
      widows: 3;
    }}
  </style>
</head>
<body>
  <div class="pdf-header">
    <h1>Talven Briefing</h1>
    <div class="pdf-metadata">
      <span>Generated: {date}</span>
    </div>
  </div>
  <div class="pdf-content">
    {content}
  </div>
</body>
</html>
"""


async def render_markdown_pdf_bytes(
    markdown_text: str,
    title: str = "Talven Briefing",
    *,
    deadline_seconds: float = PDF_RENDER_DEADLINE_SECONDS,
) -> bytes:
    """Render a PDF in a disposable subprocess with a hard deadline."""
    _validate_input_size(markdown_text, title)
    request = json.dumps(
        {"markdown": markdown_text, "title": title},
        ensure_ascii=False,
    ).encode("utf-8")
    process: asyncio.subprocess.Process | None = None
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            _PDF_WORKER_MODULE,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=_pdf_worker_environment(),
        )
        async with asyncio.timeout(deadline_seconds):
            rendered, stderr = await process.communicate(request)
    except TimeoutError as exc:
        await _terminate_process(process)
        raise PDFError(PDF_RENDER_TIMEOUT_MESSAGE) from exc
    except asyncio.CancelledError:
        await asyncio.shield(_terminate_process(process))
        raise
    except Exception as exc:
        logger.exception(
            "pdf.render.process_failed",
            extra={"error_type": type(exc).__name__},
        )
        raise PDFError(PDF_RENDER_FAILED_MESSAGE) from exc

    if process.returncode != 0:
        logger.error(
            "pdf.render.worker_failed",
            extra={"return_code": process.returncode},
        )
        raise PDFError(_parse_worker_error(stderr))
    if not rendered.startswith(b"%PDF") or len(rendered) > MAX_PDF_OUTPUT_BYTES:
        raise PDFError(PDF_RENDER_FAILED_MESSAGE)
    return rendered


def markdown_to_pdf_bytes(markdown_text: str, title: str = "Talven Briefing") -> bytes:
    """Convert untrusted briefing Markdown to a bounded, self-contained PDF."""
    _validate_input_size(markdown_text, title)
    try:
        from weasyprint import HTML
    except Exception as exc:
        raise PDFError(PDF_RENDER_FAILED_MESSAGE) from exc

    # Escaping angle brackets disables raw HTML while preserving Markdown syntax.
    html_body = markdown(
        escape(markdown_text),
        extensions=["extra", "sane_lists", "codehilite"],
    )

    current_date = datetime.now(UTC).strftime("%B %d, %Y")
    html = PDF_TEMPLATE.format(
        title=escape(title, quote=True),
        date=current_date,
        content=html_body,
    )

    try:
        # No base URL is supplied, and the custom fetcher denies every URL scheme.
        rendered = cast(
            bytes,
            HTML(string=html, url_fetcher=_deny_resource_fetch).write_pdf(),
        )
    except PDFError:
        raise
    except Exception as exc:
        raise PDFError(PDF_RENDER_FAILED_MESSAGE) from exc

    if not isinstance(rendered, bytes):
        raise PDFError(PDF_RENDER_FAILED_MESSAGE)
    if len(rendered) > MAX_PDF_OUTPUT_BYTES:
        raise PDFError(PDF_OUTPUT_TOO_LARGE_MESSAGE)
    return rendered


def _validate_input_size(markdown_text: str, title: str) -> None:
    if len(markdown_text.encode("utf-8")) > MAX_PDF_MARKDOWN_BYTES or len(title.encode("utf-8")) > MAX_PDF_TITLE_BYTES:
        raise PDFError(PDF_INPUT_TOO_LARGE_MESSAGE)


def _deny_resource_fetch(
    _url: str,
    *_args: object,
    **_kwargs: object,
) -> NoReturn:
    raise PDFError("External and local resources are not permitted in PDF exports.")


def _pdf_worker_environment() -> dict[str, str]:
    return {key: os.environ[key] for key in _PDF_WORKER_ENV_KEYS if key in os.environ}


async def _terminate_process(process: asyncio.subprocess.Process | None) -> None:
    if process is None:
        return
    if process.returncode is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
    await process.wait()


def _parse_worker_error(stderr: bytes) -> str:
    for line in reversed(stderr.splitlines()):
        if not line.startswith(_PDF_WORKER_ERROR_PREFIX):
            continue
        try:
            payload = json.loads(line.removeprefix(_PDF_WORKER_ERROR_PREFIX))
        except (json.JSONDecodeError, UnicodeDecodeError):
            break
        message = payload.get("message") if isinstance(payload, dict) else None
        if isinstance(message, str) and message in _STABLE_PDF_ERRORS:
            return message
        break
    return PDF_RENDER_FAILED_MESSAGE
