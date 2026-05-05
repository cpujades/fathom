"""Application-wide constants."""

# ---------------------------------------------------------------------------
# Summarization
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a senior analyst. Produce a detailed, high-signal Markdown briefing of the "
    "podcast transcript. Use clear section headings, concise paragraphs, and an editorial briefing style. "
    "Do not invent facts; if something is unclear in the transcript, explicitly say so.\n\n"
    "Required structure (use Markdown headings):\n"
    "1) Title (H1, use the specific episode or topic name, never a generic title like 'Briefing' or 'Summary')\n"
    "2) Brief in 30 seconds (one short paragraph with the core point and why it matters)\n"
    "3) Key Takeaways (5-8 bullets, each formatted as '- **Lead-in:** one useful sentence'; do not use emojis)\n"
    "4) Detailed Briefing (multi-paragraph, well-structured; use H3 subheadings for major ideas)\n"
    "5) Highlights & Quotes (bullet list with short, skimmable quotes or moments; include timestamps if present)\n"
    "6) Action Items (bullet list, each formatted as '- **Action:** concrete practical detail')\n"
    "7) Next Steps (bullet list, each formatted as '- **Step:** concrete practical detail')\n"
    "8) Open Questions (bullet list of concise questions worth thinking about)\n"
    "9) References (only if explicitly mentioned in transcript)\n\n"
    "Style guidance:\n"
    "- Keep the writing crisp, specific, and professional.\n"
    "- Use strong section headers and enough spacing for readable Markdown.\n"
    "- Avoid emoji, decorative symbols, hype, and generic filler.\n"
    "- Keep bullets concise; split dense ideas instead of writing long multi-clause bullets.\n"
    "- Prefer clarity and completeness over brevity.\n"
    "- If timestamps are missing, do not fabricate them."
)
SUMMARY_PROMPT_KEY_DEFAULT = "briefing-v2"

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
SIGNED_URL_TTL_SECONDS = 3600  # 1 hour

# ---------------------------------------------------------------------------
# Transcription (Groq)
# ---------------------------------------------------------------------------
GROQ_MODEL = "whisper-large-v3-turbo"
GROQ_SIGNED_URL_TTL_SECONDS = 60

# ---------------------------------------------------------------------------
# Buckets
# ---------------------------------------------------------------------------
SUPABASE_PDF_BUCKET = "fathom"
SUPABASE_GROQ_BUCKET = "fathom_groq"
