from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fathom.evaluation.briefing_quality import (
    BriefingQualityReport,
    evaluate_briefing_quality,
)
from fathom.schemas.briefing_contract import BriefingContract
from fathom.schemas.transcripts import TranscriptSegment
from fathom.services.provider_resilience import ProviderOperationError
from fathom.services.summarizer import summarize_transcript_with_evidence

DEFAULT_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "briefing_quality_cases.json"
HARD_MAX_CASES = 3
HARD_MAX_SOURCE_CHARS = 120_000
HARD_MAX_OUTPUT_TOKENS_PER_CASE = 4_000
HARD_MAX_DEADLINE_SECONDS = 600.0

StructuredSummarizer = Callable[..., Awaitable[BriefingContract]]


class ProviderEvalConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProviderEvalLimits:
    max_cases: int = 1
    max_source_chars: int = 60_000
    max_output_tokens_per_case: int = 2_500
    deadline_seconds_per_case: float = 180.0

    def __post_init__(self) -> None:
        _bounded_positive("max_cases", self.max_cases, HARD_MAX_CASES)
        _bounded_positive(
            "max_source_chars",
            self.max_source_chars,
            HARD_MAX_SOURCE_CHARS,
        )
        _bounded_positive(
            "max_output_tokens_per_case",
            self.max_output_tokens_per_case,
            HARD_MAX_OUTPUT_TOKENS_PER_CASE,
        )
        if not 0 < self.deadline_seconds_per_case <= HARD_MAX_DEADLINE_SECONDS:
            raise ProviderEvalConfigurationError(
                f"deadline_seconds_per_case must be greater than zero and no more than {HARD_MAX_DEADLINE_SECONDS:g}."
            )


@dataclass(frozen=True, slots=True)
class ProviderEvalCase:
    name: str
    segments: tuple[TranscriptSegment, ...]
    forbidden_output_terms: tuple[str, ...]
    minimum_evidence_overlap_rate: float

    @property
    def source_chars(self) -> int:
        return sum(len(segment.text) for segment in self.segments)


@dataclass(frozen=True, slots=True)
class ProviderEvalResult:
    case_name: str
    report: BriefingQualityReport

    def to_dict(self) -> dict[str, object]:
        return {
            "case_name": self.case_name,
            "report": self.report.to_dict(),
        }


def load_provider_eval_cases(path: Path = DEFAULT_FIXTURE_PATH) -> tuple[ProviderEvalCase, ...]:
    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw_cases, list):
        raise ProviderEvalConfigurationError("Provider evaluation fixture must contain a list.")

    cases: list[ProviderEvalCase] = []
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            raise ProviderEvalConfigurationError("Every provider evaluation case must be an object.")
        cases.append(_parse_case(raw_case))
    if not cases:
        raise ProviderEvalConfigurationError("Provider evaluation fixture has no cases.")
    return tuple(cases)


async def run_provider_evaluation(
    cases: Sequence[ProviderEvalCase],
    *,
    api_key: str,
    limits: ProviderEvalLimits,
    summarizer: StructuredSummarizer = summarize_transcript_with_evidence,
) -> tuple[ProviderEvalResult, ...]:
    if not api_key:
        raise ProviderEvalConfigurationError("OPENROUTER_API_KEY is required.")

    selected_cases = tuple(cases[: limits.max_cases])
    if not selected_cases:
        raise ProviderEvalConfigurationError("No provider evaluation cases were selected.")
    total_source_chars = sum(case.source_chars for case in selected_cases)
    if total_source_chars > limits.max_source_chars:
        raise ProviderEvalConfigurationError(
            f"Selected cases contain {total_source_chars} source characters; "
            f"the configured limit is {limits.max_source_chars}."
        )

    results: list[ProviderEvalResult] = []
    for case in selected_cases:
        contract = await summarizer(
            case.segments,
            api_key,
            deadline_seconds=limits.deadline_seconds_per_case,
            max_attempts=1,
            max_output_tokens=limits.max_output_tokens_per_case,
        )
        report = evaluate_briefing_quality(
            contract,
            case.segments,
            forbidden_output_terms=case.forbidden_output_terms,
            minimum_evidence_overlap_rate=case.minimum_evidence_overlap_rate,
        )
        results.append(ProviderEvalResult(case_name=case.name, report=report))
    return tuple(results)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _argument_parser()
    args = parser.parse_args(argv)
    if not args.confirm_paid:
        parser.error("provider evaluation is paid; pass --confirm-paid to continue")

    try:
        limits = ProviderEvalLimits(
            max_cases=args.max_cases,
            max_source_chars=args.max_source_chars,
            max_output_tokens_per_case=args.max_output_tokens,
            deadline_seconds_per_case=args.deadline_seconds,
        )
        cases = load_provider_eval_cases(args.fixture)
        results = asyncio.run(
            run_provider_evaluation(
                cases,
                api_key=os.environ.get("OPENROUTER_API_KEY", ""),
                limits=limits,
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
        ProviderEvalConfigurationError,
        ProviderOperationError,
    ) as exc:
        parser.error(str(exc))

    payload = {
        "limits": {
            "max_cases": limits.max_cases,
            "max_source_chars": limits.max_source_chars,
            "max_output_tokens_per_case": limits.max_output_tokens_per_case,
            "provider_attempts_per_case": 1,
        },
        "results": [result.to_dict() for result in results],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if all(result.report.passed for result in results) else 1


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a bounded, paid OpenRouter briefing-quality evaluation.",
    )
    parser.add_argument(
        "--confirm-paid",
        action="store_true",
        help="Acknowledge that this command makes paid provider requests.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE_PATH,
    )
    parser.add_argument("--max-cases", type=int, default=1)
    parser.add_argument("--max-source-chars", type=int, default=60_000)
    parser.add_argument("--max-output-tokens", type=int, default=2_500)
    parser.add_argument("--deadline-seconds", type=float, default=180.0)
    return parser


def _parse_case(raw_case: dict[str, Any]) -> ProviderEvalCase:
    name = raw_case.get("name")
    raw_segments = raw_case.get("segments")
    forbidden_output_terms = raw_case.get("forbidden_output_terms")
    minimum_overlap = raw_case.get("minimum_evidence_overlap_rate")
    if not isinstance(name, str) or not name.strip():
        raise ProviderEvalConfigurationError("Provider evaluation case name is required.")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise ProviderEvalConfigurationError(f"Provider evaluation case {name!r} has no segments.")
    if not isinstance(forbidden_output_terms, list) or not all(
        isinstance(term, str) for term in forbidden_output_terms
    ):
        raise ProviderEvalConfigurationError(f"Provider evaluation case {name!r} has invalid forbidden terms.")
    if not isinstance(minimum_overlap, (int, float)):
        raise ProviderEvalConfigurationError(f"Provider evaluation case {name!r} has no overlap threshold.")

    try:
        segments = tuple(
            TranscriptSegment(
                segment_index=segment["segment_index"],
                start_seconds=segment["start_seconds"],
                end_seconds=segment["end_seconds"],
                text=segment["text"],
            )
            for segment in raw_segments
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ProviderEvalConfigurationError(f"Provider evaluation case {name!r} has invalid segments.") from exc
    if not 0 <= float(minimum_overlap) <= 1:
        raise ProviderEvalConfigurationError(f"Provider evaluation case {name!r} has an invalid overlap threshold.")
    return ProviderEvalCase(
        name=name,
        segments=segments,
        forbidden_output_terms=tuple(forbidden_output_terms),
        minimum_evidence_overlap_rate=float(minimum_overlap),
    )


def _bounded_positive(name: str, value: int, hard_maximum: int) -> None:
    if not 0 < value <= hard_maximum:
        raise ProviderEvalConfigurationError(f"{name} must be greater than zero and no more than {hard_maximum}.")


if __name__ == "__main__":
    raise SystemExit(main())
