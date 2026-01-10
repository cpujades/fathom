from __future__ import annotations

from typing import cast

from markdown import markdown

from app.core.errors import ExternalServiceError


class PDFError(ExternalServiceError):
    pass


def markdown_to_pdf_bytes(markdown_text: str) -> bytes:
    try:
        from weasyprint import HTML
    except Exception as exc:
        raise PDFError(
            "WeasyPrint is required for PDF export. Install it and ensure system dependencies are available."
        ) from exc

    html_body = markdown(markdown_text, extensions=["extra", "sane_lists"])
    html = f"""
    <html>
      <head>
        <meta charset=\"utf-8\" />
        <style>
          body {{
            font-family: "Helvetica Neue", Arial, sans-serif;
            line-height: 1.5;
            color: #111;
            padding: 40px;
          }}
          h1, h2, h3 {{
            margin-top: 1.4em;
            color: #0f172a;
          }}
          h1 {{ font-size: 28px; }}
          h2 {{ font-size: 22px; }}
          h3 {{ font-size: 18px; }}
          p, li {{ font-size: 14px; }}
          ul {{ margin-left: 18px; }}
          code {{ background: #f1f5f9; padding: 2px 4px; }}
        </style>
      </head>
      <body>
        {html_body}
      </body>
    </html>
    """

    # WeasyPrint returns PDF bytes, but its type stubs may expose `Any`.
    return cast(bytes, HTML(string=html).write_pdf())
