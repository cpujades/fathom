from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from fathom.schemas.briefing_contract import (
    BriefingContract,
    EvidencePoint,
    iter_evidence_points,
)
from fathom.schemas.transcripts import TranscriptSegment, resolve_transcript_citation

_TOKEN = re.compile(r"[a-z0-9]{3,}", re.IGNORECASE)
_QUOTED_TEXT = re.compile(r'["“]([^"”]{4,})["”]')
_WHITESPACE = re.compile(r"\s+")
_STOP_WORDS = {
    "and",
    "are",
    "but",
    "for",
    "from",
    "has",
    "have",
    "how",
    "into",
    "not",
    "that",
    "the",
    "their",
    "then",
    "this",
    "was",
    "what",
    "when",
    "where",
    "which",
    "will",
    "with",
}


@dataclass(frozen=True, slots=True)
class BriefingQualityReport:
    point_count: int
    resolved_citation_count: int
    evidence_supported_point_count: int
    quote_count: int
    grounded_quote_count: int
    forbidden_term_hits: tuple[str, ...]
    minimum_evidence_overlap_rate: float
    failure_reasons: tuple[str, ...]

    @property
    def citation_resolution_rate(self) -> float:
        return _ratio(self.resolved_citation_count, self.point_count)

    @property
    def evidence_overlap_rate(self) -> float:
        return _ratio(self.evidence_supported_point_count, self.point_count)

    @property
    def quote_grounding_rate(self) -> float:
        return _ratio(self.grounded_quote_count, self.quote_count)

    @property
    def passed(self) -> bool:
        return not self.failure_reasons

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result.update(
            {
                "citation_resolution_rate": self.citation_resolution_rate,
                "evidence_overlap_rate": self.evidence_overlap_rate,
                "quote_grounding_rate": self.quote_grounding_rate,
                "passed": self.passed,
            }
        )
        return result


def evaluate_briefing_quality(
    contract: BriefingContract,
    segments: tuple[TranscriptSegment, ...],
    *,
    forbidden_output_terms: tuple[str, ...] = (),
    minimum_evidence_overlap_rate: float = 0.75,
) -> BriefingQualityReport:
    if not 0 <= minimum_evidence_overlap_rate <= 1:
        raise ValueError("minimum_evidence_overlap_rate must be between zero and one.")

    points = tuple(iter_evidence_points(contract))
    resolved_citation_count = 0
    evidence_supported_point_count = 0
    quote_count = 0
    grounded_quote_count = 0

    for point in points:
        citation = _resolve_point(point, segments)
        if citation is None:
            continue
        resolved_citation_count += 1
        if _has_evidence_overlap(point.text, citation):
            evidence_supported_point_count += 1
        point_quotes = _QUOTED_TEXT.findall(point.text)
        quote_count += len(point_quotes)
        grounded_quote_count += sum(_normalize_text(quote) in _normalize_text(citation) for quote in point_quotes)

    contract_text = _contract_text(contract).casefold()
    forbidden_term_hits = tuple(
        term for term in forbidden_output_terms if term.strip() and term.casefold() in contract_text
    )
    failure_reasons = _failure_reasons(
        point_count=len(points),
        resolved_citation_count=resolved_citation_count,
        evidence_supported_point_count=evidence_supported_point_count,
        quote_count=quote_count,
        grounded_quote_count=grounded_quote_count,
        forbidden_term_hits=forbidden_term_hits,
        minimum_evidence_overlap_rate=minimum_evidence_overlap_rate,
    )
    return BriefingQualityReport(
        point_count=len(points),
        resolved_citation_count=resolved_citation_count,
        evidence_supported_point_count=evidence_supported_point_count,
        quote_count=quote_count,
        grounded_quote_count=grounded_quote_count,
        forbidden_term_hits=forbidden_term_hits,
        minimum_evidence_overlap_rate=minimum_evidence_overlap_rate,
        failure_reasons=failure_reasons,
    )


def _resolve_point(
    point: EvidencePoint,
    segments: tuple[TranscriptSegment, ...],
) -> str | None:
    try:
        citation = resolve_transcript_citation(segments, point.segment_indexes)
    except ValueError:
        return None
    return citation.evidence_text


def _has_evidence_overlap(point_text: str, evidence_text: str) -> bool:
    point_tokens = _significant_tokens(point_text)
    if not point_tokens:
        return False
    return bool(point_tokens & _significant_tokens(evidence_text))


def _significant_tokens(value: str) -> set[str]:
    return {token for token in (match.casefold() for match in _TOKEN.findall(value)) if token not in _STOP_WORDS}


def _normalize_text(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip().casefold()


def _contract_text(contract: BriefingContract) -> str:
    values = [contract.title]
    for point in iter_evidence_points(contract):
        values.append(point.text)
        label = getattr(point, "label", None)
        if isinstance(label, str):
            values.append(label)
    values.extend(section.heading for section in contract.detailed_briefing)
    return "\n".join(values)


def _failure_reasons(
    *,
    point_count: int,
    resolved_citation_count: int,
    evidence_supported_point_count: int,
    quote_count: int,
    grounded_quote_count: int,
    forbidden_term_hits: tuple[str, ...],
    minimum_evidence_overlap_rate: float,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if resolved_citation_count != point_count:
        reasons.append("One or more briefing points have invalid evidence ranges.")
    if _ratio(evidence_supported_point_count, point_count) < minimum_evidence_overlap_rate:
        reasons.append("Too few briefing points share meaningful terms with their cited evidence.")
    if grounded_quote_count != quote_count:
        reasons.append("One or more quoted passages are not verbatim in their cited evidence.")
    if forbidden_term_hits:
        reasons.append("The briefing contains a forbidden prompt-injection canary.")
    return tuple(reasons)


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return numerator / denominator
