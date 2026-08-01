from __future__ import annotations

import json
import sys
from typing import Any

from fathom.services.pdf import (
    _PDF_WORKER_ERROR_PREFIX,
    MAX_PDF_MARKDOWN_BYTES,
    MAX_PDF_TITLE_BYTES,
    PDF_RENDER_FAILED_MESSAGE,
    PDFError,
    markdown_to_pdf_bytes,
)

MAX_PDF_WORKER_REQUEST_BYTES = MAX_PDF_MARKDOWN_BYTES + MAX_PDF_TITLE_BYTES + 4096


def main() -> int:
    try:
        raw_request = sys.stdin.buffer.read(MAX_PDF_WORKER_REQUEST_BYTES + 1)
        if len(raw_request) > MAX_PDF_WORKER_REQUEST_BYTES:
            raise PDFError(PDF_RENDER_FAILED_MESSAGE)
        request = json.loads(raw_request)
        if not isinstance(request, dict):
            raise PDFError(PDF_RENDER_FAILED_MESSAGE)
        markdown = request.get("markdown")
        title = request.get("title")
        if not isinstance(markdown, str) or not isinstance(title, str):
            raise PDFError(PDF_RENDER_FAILED_MESSAGE)
        rendered = markdown_to_pdf_bytes(markdown, title)
    except PDFError as exc:
        _write_error(exc.detail)
        return 2
    except Exception:
        _write_error(PDF_RENDER_FAILED_MESSAGE)
        return 2

    sys.stdout.buffer.write(rendered)
    return 0


def _write_error(message: str) -> None:
    payload: dict[str, Any] = {"message": message}
    sys.stderr.buffer.write(_PDF_WORKER_ERROR_PREFIX + json.dumps(payload).encode("utf-8") + b"\n")


if __name__ == "__main__":
    raise SystemExit(main())
