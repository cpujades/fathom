from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from markdown import markdown

from fathom.core.errors import ExternalServiceError


class PDFError(ExternalServiceError):
    pass


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
        content: "Fathom";
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
    <h1>Fathom Summary</h1>
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


def markdown_to_pdf_bytes(markdown_text: str, title: str = "Summary") -> bytes:
    """Convert markdown to a professionally styled PDF with headers and footers."""
    try:
        from weasyprint import HTML
    except Exception as exc:
        raise PDFError(
            "WeasyPrint is required for PDF export. Install it and ensure system dependencies are available."
        ) from exc

    # Convert markdown to HTML
    html_body = markdown(markdown_text, extensions=["extra", "sane_lists", "codehilite"])

    # Generate current date
    current_date = datetime.now(UTC).strftime("%B %d, %Y")

    # Render template
    html = PDF_TEMPLATE.format(
        title=title,
        date=current_date,
        content=html_body,
    )

    # WeasyPrint returns PDF bytes, but its type stubs may expose `Any`.
    return cast(bytes, HTML(string=html).write_pdf())
