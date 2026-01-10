import re

SUMMARY_ID_RE = re.compile(r"^[0-9a-f]{32}$")

SYSTEM_PROMPT = (
    "You are a precise analyst. Produce a structured Markdown summary of the podcast transcript. "
    "Keep it concise and actionable. Use headings for: Summary, Key Points, Action Items. "
    "If you are unsure about a detail, say so rather than guessing."
)
