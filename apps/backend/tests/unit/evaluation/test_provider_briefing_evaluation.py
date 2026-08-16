from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr
from unittest.mock import AsyncMock

from fathom.evaluation.provider_eval import (
    HARD_MAX_CASES,
    ProviderEvalConfigurationError,
    ProviderEvalLimits,
    load_provider_eval_cases,
    main,
    run_provider_evaluation,
)
from fathom.schemas.briefing_contract import BriefingContract


class ProviderBriefingEvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_runner_uses_one_attempt_and_bounded_output_per_case(self) -> None:
        cases = load_provider_eval_cases()
        contract = BriefingContract.model_validate(
            {
                "title": "Bounded provider evaluation",
                "brief": {
                    "text": "Validate the core workflow before expanding.",
                    "segment_indexes": [1],
                },
                "key_takeaways": [
                    {
                        "label": "Workflow",
                        "text": "Validate the core workflow.",
                        "segment_indexes": [1],
                    },
                    {
                        "label": "Accuracy",
                        "text": "Measure factual accuracy.",
                        "segment_indexes": [2],
                    },
                    {
                        "label": "Pilot",
                        "text": "Run a small private pilot.",
                        "segment_indexes": [3],
                    },
                    {
                        "label": "Recovery",
                        "text": "Track failed jobs.",
                        "segment_indexes": [5],
                    },
                ],
                "detailed_briefing": [
                    {
                        "heading": "Quality",
                        "paragraphs": [
                            {
                                "text": "Readers should receive accurate citations.",
                                "segment_indexes": [2],
                            }
                        ],
                    }
                ],
                "highlights_and_quotes": [],
                "action_items": [],
                "next_steps": [],
                "open_questions": [],
                "references": [],
            }
        )
        summarizer = AsyncMock(return_value=contract)
        limits = ProviderEvalLimits(
            max_cases=1,
            max_source_chars=10_000,
            max_output_tokens_per_case=1_234,
            deadline_seconds_per_case=45,
        )

        results = await run_provider_evaluation(
            cases,
            api_key="test-key",
            limits=limits,
            summarizer=summarizer,
        )

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].report.passed)
        summarizer.assert_awaited_once_with(
            cases[0].segments,
            "test-key",
            timeout_seconds=45,
            max_attempts=1,
            max_output_tokens=1_234,
        )

    async def test_runner_rejects_total_source_over_cap_before_provider_call(
        self,
    ) -> None:
        cases = load_provider_eval_cases()
        summarizer = AsyncMock()

        with self.assertRaisesRegex(
            ProviderEvalConfigurationError,
            "source characters",
        ):
            await run_provider_evaluation(
                cases,
                api_key="test-key",
                limits=ProviderEvalLimits(
                    max_cases=1,
                    max_source_chars=1,
                ),
                summarizer=summarizer,
            )

        summarizer.assert_not_awaited()

    def test_hard_limits_reject_unbounded_or_invalid_configuration(self) -> None:
        with self.assertRaises(ProviderEvalConfigurationError):
            ProviderEvalLimits(max_cases=HARD_MAX_CASES + 1)
        with self.assertRaises(ProviderEvalConfigurationError):
            ProviderEvalLimits(max_output_tokens_per_case=0)
        with self.assertRaises(ProviderEvalConfigurationError):
            ProviderEvalLimits(deadline_seconds_per_case=601)

    def test_cli_requires_explicit_paid_confirmation_before_loading_cases(
        self,
    ) -> None:
        stderr = io.StringIO()

        with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            main([])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("--confirm-paid", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
