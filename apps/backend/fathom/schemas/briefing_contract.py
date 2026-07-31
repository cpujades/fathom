from __future__ import annotations

from collections.abc import Iterator

from pydantic import BaseModel, ConfigDict, Field

from fathom.schemas.transcripts import TranscriptSegment, resolve_transcript_citation


class BriefingContractError(ValueError):
    pass


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidencePoint(_ContractModel):
    text: str = Field(min_length=1, max_length=2_000)
    segment_indexes: tuple[int, ...] = Field(min_length=1, max_length=20)


class EvidenceBullet(EvidencePoint):
    label: str = Field(min_length=1, max_length=120)


class DetailedSection(_ContractModel):
    heading: str = Field(min_length=1, max_length=160)
    paragraphs: tuple[EvidencePoint, ...] = Field(min_length=1, max_length=6)


class BriefingContract(_ContractModel):
    title: str = Field(min_length=1, max_length=180)
    brief: EvidencePoint
    key_takeaways: tuple[EvidenceBullet, ...] = Field(min_length=4, max_length=8)
    detailed_briefing: tuple[DetailedSection, ...] = Field(min_length=1, max_length=5)
    highlights_and_quotes: tuple[EvidencePoint, ...] = Field(max_length=6)
    action_items: tuple[EvidenceBullet, ...] = Field(max_length=5)
    next_steps: tuple[EvidenceBullet, ...] = Field(max_length=5)
    open_questions: tuple[EvidencePoint, ...] = Field(max_length=4)
    references: tuple[EvidencePoint, ...] = Field(max_length=12)


def iter_evidence_points(contract: BriefingContract) -> Iterator[EvidencePoint]:
    yield contract.brief
    yield from contract.key_takeaways
    for section in contract.detailed_briefing:
        yield from section.paragraphs
    yield from contract.highlights_and_quotes
    yield from contract.action_items
    yield from contract.next_steps
    yield from contract.open_questions
    yield from contract.references


def validate_briefing_evidence(
    contract: BriefingContract,
    segments: tuple[TranscriptSegment, ...],
) -> None:
    if not segments:
        raise BriefingContractError("Timestamped transcript segments are required.")

    for point in iter_evidence_points(contract):
        try:
            resolve_transcript_citation(segments, point.segment_indexes)
        except ValueError as exc:
            raise BriefingContractError(f"Invalid evidence for briefing point: {point.text[:80]!r}.") from exc
