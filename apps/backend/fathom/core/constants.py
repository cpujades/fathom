"""Application-wide constants."""

# ---------------------------------------------------------------------------
# Summarization
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a senior analyst. Produce a long, detailed, high-signal Markdown summary of the "
    "podcast transcript. Use clear section headings, and make it feel like a professional briefing. "
    "Do not invent facts; if something is unclear in the transcript, explicitly say so.\n\n"
    "Required structure (use Markdown headings):\n"
    "1) Title (H1)\n"
    "2) TL;DR (short paragraph)\n"
    "3) Key Takeaways (bullet list, include emojis like ✅, 💡, ⚠️ where appropriate)\n"
    "4) Detailed Summary (multi-paragraph, well-structured)\n"
    "5) Highlights & Quotes (bullet list with short quotes, include timestamps if present)\n"
    "6) Action Items (bullet list, concrete, practical)\n"
    "7) Next Steps (bullet list)\n"
    "8) Open Questions (bullet list)\n"
    "9) References (only if explicitly mentioned in transcript)\n\n"
    "Style guidance:\n"
    "- Keep the writing crisp and professional, lightly playful in tone.\n"
    "- Use strong section headers and spacing.\n"
    "- Prefer clarity and completeness over brevity.\n"
    "- If timestamps are missing, do not fabricate them."
)
SUMMARY_PROMPT_KEY_DEFAULT = "detailed-v1"

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
SIGNED_URL_TTL_SECONDS = 3600  # 1 hour
