"""Application-wide constants."""

# ---------------------------------------------------------------------------
# Summarization
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a precise analyst. Produce a structured Markdown summary of the podcast transcript. "
    "Keep it concise and actionable. Use headings for: Summary, Key Points, Action Items. "
    "If you are unsure about a detail, say so rather than guessing."
)
SUMMARY_PROMPT_KEY_DEFAULT = "default"

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
SIGNED_URL_TTL_SECONDS = 3600  # 1 hour
