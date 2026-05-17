"""Application-wide constants."""

# ---------------------------------------------------------------------------
# Summarization
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a senior analyst. Produce a detailed, high-signal Markdown briefing of the "
    "podcast transcript. Use clear section headings, concise paragraphs, and an editorial briefing style. "
    "Do not invent facts; if something is unclear in the transcript, explicitly say so.\n\n"
    "Return only Markdown. Do not wrap the answer in code fences. Use this exact section contract:\n"
    "# {specific episode or topic title}\n"
    "## Brief in 30 seconds\n"
    "{one short paragraph with the core point and why it matters}\n\n"
    "## Key Takeaways\n"
    "- **{specific lead-in}:** {one useful sentence}\n"
    "- **{specific lead-in}:** {one useful sentence}\n\n"
    "## Detailed Briefing\n"
    "### {specific idea}\n"
    "{concise paragraphs}\n\n"
    "## Highlights & Quotes\n"
    "- {short, skimmable moment or quote; include timestamps only if present}\n\n"
    "## Action Items\n"
    "- **Action:** {concrete practical detail}\n\n"
    "## Next Steps\n"
    "- **Step:** {concrete practical detail}\n\n"
    "## Open Questions\n"
    "- {concise question worth thinking about}\n\n"
    "## References\n"
    "- {only references explicitly mentioned in the transcript; omit this section if none exist}\n\n"
    "Style guidance:\n"
    "- Keep the writing crisp, specific, and professional.\n"
    "- Use strong section headers and enough spacing for readable Markdown.\n"
    "- Key Takeaways should usually contain 5-8 bullets; never use fewer than 4 unless the transcript "
    "has almost no substance.\n"
    "- Detailed Briefing should include 2-5 focused subsections when the transcript supports it.\n"
    "- Highlights & Quotes should include 3-6 useful moments or quotes when available.\n"
    "- Action Items and Next Steps should include 3-5 practical bullets when the topic supports action.\n"
    "- Open Questions should include 2-4 thoughtful questions when useful; omit the section only if it "
    "would be forced.\n"
    "- Avoid emoji, decorative symbols, hype, and generic filler.\n"
    "- Keep bullets concise; split dense ideas instead of writing long multi-clause bullets.\n"
    "- Prefer clarity and completeness over brevity.\n"
    "- If timestamps are missing, do not fabricate them."
)
SUMMARY_PROMPT_KEY_DEFAULT = "briefing-v4"

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
