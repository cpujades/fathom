from __future__ import annotations

import json
import sys
from typing import Any

from fathom.services.pdf import (
    _PDF_WORKER_ERROR_PREFIX,
    PDF_RENDER_FAILED_MESSAGE,
    PDFError,
    markdown_to_pdf_bytes,
)


def main() -> int:
    try:
        request = json.loads(sys.stdin.buffer.read())
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
