from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    segment_index: int
    start_seconds: float
    end_seconds: float
    text: str

    def __post_init__(self) -> None:
        if self.segment_index < 0:
            raise ValueError("segment_index cannot be negative")
        if not math.isfinite(self.start_seconds) or self.start_seconds < 0:
            raise ValueError("start_seconds must be finite and non-negative")
        if not math.isfinite(self.end_seconds) or self.end_seconds < self.start_seconds:
            raise ValueError("end_seconds must be finite and not precede start_seconds")
        if not self.text.strip():
            raise ValueError("segment text cannot be empty")


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    text: str
    segments: tuple[TranscriptSegment, ...]

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("transcript text cannot be empty")


@dataclass(frozen=True, slots=True)
class TranscriptCitation:
    segment_indexes: tuple[int, ...]
    start_seconds: float
    end_seconds: float
    evidence_text: str


class CitationResolutionError(ValueError):
    pass


def resolve_transcript_citation(
    segments: tuple[TranscriptSegment, ...],
    segment_indexes: tuple[int, ...],
) -> TranscriptCitation:
    if not segment_indexes:
        raise CitationResolutionError("A citation must reference at least one segment.")
    if tuple(sorted(set(segment_indexes))) != segment_indexes:
        raise CitationResolutionError("Citation segment indexes must be unique and ordered.")

    expected_indexes = tuple(range(segment_indexes[0], segment_indexes[-1] + 1))
    if segment_indexes != expected_indexes:
        raise CitationResolutionError("A citation must reference a contiguous segment range.")

    segments_by_index = {segment.segment_index: segment for segment in segments}
    try:
        cited_segments = tuple(segments_by_index[index] for index in segment_indexes)
    except KeyError as exc:
        raise CitationResolutionError(f"Unknown transcript segment index: {exc.args[0]}.") from exc

    return TranscriptCitation(
        segment_indexes=segment_indexes,
        start_seconds=cited_segments[0].start_seconds,
        end_seconds=cited_segments[-1].end_seconds,
        evidence_text=" ".join(segment.text.strip() for segment in cited_segments),
    )
