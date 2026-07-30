from __future__ import annotations

import re
from urllib.parse import quote

from fathom.schemas.briefing_contract import (
    BriefingContract,
    DetailedSection,
    EvidenceBullet,
    EvidencePoint,
    validate_briefing_evidence,
)
from fathom.schemas.transcripts import TranscriptSegment, resolve_transcript_citation

_WHITESPACE = re.compile(r"\s+")
_MARKDOWN_INLINE = re.compile(r"([\\`*_\[\]<>])")


def render_briefing(
    contract: BriefingContract,
    segments: tuple[TranscriptSegment, ...],
    *,
    source_video_id: str | None = None,
) -> str:
    validate_briefing_evidence(contract, segments)

    blocks = [
        f"# {_safe_inline(contract.title)}",
        f"## Brief in 30 seconds\n{_render_point(contract.brief, segments, source_video_id)}",
        f"## Key Takeaways\n{_render_bullets(contract.key_takeaways, segments, source_video_id)}",
        f"## Detailed Briefing\n{_render_detailed_sections(contract.detailed_briefing, segments, source_video_id)}",
    ]
    _append_point_section(
        blocks,
        "Highlights & Quotes",
        contract.highlights_and_quotes,
        segments,
        source_video_id,
    )
    _append_bullet_section(blocks, "Action Items", contract.action_items, segments, source_video_id)
    _append_bullet_section(blocks, "Next Steps", contract.next_steps, segments, source_video_id)
    _append_point_section(blocks, "Open Questions", contract.open_questions, segments, source_video_id)
    _append_point_section(blocks, "References", contract.references, segments, source_video_id)
    return "\n\n".join(blocks).strip() + "\n"


def _append_point_section(
    blocks: list[str],
    heading: str,
    points: tuple[EvidencePoint, ...],
    segments: tuple[TranscriptSegment, ...],
    source_video_id: str | None,
) -> None:
    if points:
        blocks.append(f"## {heading}\n{_render_points(points, segments, source_video_id)}")


def _append_bullet_section(
    blocks: list[str],
    heading: str,
    points: tuple[EvidenceBullet, ...],
    segments: tuple[TranscriptSegment, ...],
    source_video_id: str | None,
) -> None:
    if points:
        blocks.append(f"## {heading}\n{_render_bullets(points, segments, source_video_id)}")


def _render_detailed_sections(
    sections: tuple[DetailedSection, ...],
    segments: tuple[TranscriptSegment, ...],
    source_video_id: str | None,
) -> str:
    return "\n\n".join(
        f"### {_safe_inline(section.heading)}\n\n"
        + "\n\n".join(_render_point(point, segments, source_video_id) for point in section.paragraphs)
        for section in sections
    )


def _render_points(
    points: tuple[EvidencePoint, ...],
    segments: tuple[TranscriptSegment, ...],
    source_video_id: str | None,
) -> str:
    return "\n".join(f"- {_render_point(point, segments, source_video_id)}" for point in points)


def _render_bullets(
    points: tuple[EvidenceBullet, ...],
    segments: tuple[TranscriptSegment, ...],
    source_video_id: str | None,
) -> str:
    return "\n".join(
        f"- **{_safe_inline(point.label)}:** {_render_point(point, segments, source_video_id)}" for point in points
    )


def _render_point(
    point: EvidencePoint,
    segments: tuple[TranscriptSegment, ...],
    source_video_id: str | None,
) -> str:
    citation = resolve_transcript_citation(segments, point.segment_indexes)
    timestamp = _format_timestamp_range(
        citation.start_seconds,
        citation.end_seconds,
    )
    citation_label = f"[{timestamp}]"
    if source_video_id:
        start_seconds = max(int(citation.start_seconds), 0)
        video_id = quote(source_video_id, safe="")
        citation_label = f"[{timestamp}](https://www.youtube.com/watch?v={video_id}&t={start_seconds}s)"
    return f"{_safe_inline(point.text)} {citation_label}"


def _format_timestamp_range(start_seconds: float, end_seconds: float) -> str:
    return f"{_format_timestamp(start_seconds)}–{_format_timestamp(end_seconds)}"


def _format_timestamp(seconds: float) -> str:
    total_seconds = max(int(seconds), 0)
    hours, remainder = divmod(total_seconds, 3_600)
    minutes, seconds_remainder = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds_remainder:02d}"
    return f"{minutes:02d}:{seconds_remainder:02d}"


def _safe_inline(value: str) -> str:
    normalized = _WHITESPACE.sub(" ", value).strip()
    return _MARKDOWN_INLINE.sub(r"\\\1", normalized)
