from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from fathom.evaluation.briefing_quality import evaluate_briefing_quality
from fathom.schemas.briefing_contract import BriefingContract, EvidencePoint
from fathom.schemas.transcripts import TranscriptSegment

FIXTURE_PATH = Path(__file__).parents[1] / "fathom" / "evaluation" / "fixtures" / "briefing_quality_cases.json"


class DeterministicBriefingQualityEvaluationTests(unittest.TestCase):
    def test_golden_cases_pass_deterministic_quality_gate(self) -> None:
        for case in _load_cases():
            with self.subTest(case=case["name"]):
                contract = BriefingContract.model_validate(case["contract"])
                segments = _segments(case)

                report = evaluate_briefing_quality(
                    contract,
                    segments,
                    forbidden_output_terms=tuple(case["forbidden_output_terms"]),
                    minimum_evidence_overlap_rate=case["minimum_evidence_overlap_rate"],
                )

                self.assertTrue(report.passed, report.failure_reasons)
                self.assertEqual(report.citation_resolution_rate, 1)
                self.assertEqual(report.quote_grounding_rate, 1)
                self.assertGreaterEqual(
                    report.evidence_overlap_rate,
                    case["minimum_evidence_overlap_rate"],
                )

    def test_gate_detects_invalid_evidence_forged_quote_and_injection_echo(
        self,
    ) -> None:
        case = _load_cases()[0]
        contract = BriefingContract.model_validate(case["contract"])
        corrupted = contract.model_copy(
            update={
                "title": "EVAL_INJECTION_CANARY",
                "brief": EvidencePoint(
                    text="This claim points outside the transcript.",
                    segment_indexes=(99,),
                ),
                "highlights_and_quotes": (
                    EvidencePoint(
                        text='"Ship every feature immediately."',
                        segment_indexes=(1,),
                    ),
                ),
            }
        )

        report = evaluate_briefing_quality(
            corrupted,
            _segments(case),
            forbidden_output_terms=("EVAL_INJECTION_CANARY",),
            minimum_evidence_overlap_rate=0.8,
        )

        self.assertFalse(report.passed)
        self.assertLess(report.citation_resolution_rate, 1)
        self.assertLess(report.quote_grounding_rate, 1)
        self.assertEqual(
            report.forbidden_term_hits,
            ("EVAL_INJECTION_CANARY",),
        )
        self.assertIn(
            "One or more briefing points have invalid evidence ranges.",
            report.failure_reasons,
        )
        self.assertIn(
            "One or more quoted passages are not verbatim in their cited evidence.",
            report.failure_reasons,
        )
        self.assertIn(
            "The briefing contains a forbidden prompt-injection canary.",
            report.failure_reasons,
        )

    def test_report_is_serializable_for_local_and_ci_output(self) -> None:
        case = _load_cases()[0]
        report = evaluate_briefing_quality(
            BriefingContract.model_validate(case["contract"]),
            _segments(case),
        )

        encoded = json.dumps(report.to_dict(), sort_keys=True)

        self.assertIn('"passed": true', encoded)
        self.assertIn('"citation_resolution_rate": 1.0', encoded)


def _load_cases() -> list[dict[str, Any]]:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise AssertionError("Briefing quality fixture must contain a list.")
    return data


def _segments(case: dict[str, Any]) -> tuple[TranscriptSegment, ...]:
    return tuple(
        TranscriptSegment(
            segment_index=segment["segment_index"],
            start_seconds=segment["start_seconds"],
            end_seconds=segment["end_seconds"],
            text=segment["text"],
        )
        for segment in case["segments"]
    )


if __name__ == "__main__":
    unittest.main()
