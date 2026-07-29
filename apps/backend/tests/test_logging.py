from __future__ import annotations

import json
import logging
import unittest

from fathom.core.logging import JsonFormatter, normalize_correlation_id


class CorrelationIdTests(unittest.TestCase):
    def test_preserves_bounded_log_safe_identifier(self) -> None:
        self.assertEqual(normalize_correlation_id("edge-01:request.abc_123"), "edge-01:request.abc_123")

    def test_replaces_unbounded_or_unsafe_identifier(self) -> None:
        for value in ("contains spaces", "x" * 65, "line\nbreak", ""):
            with self.subTest(value=value):
                generated = normalize_correlation_id(value)
                self.assertEqual(len(generated), 32)
                self.assertTrue(generated.isalnum())


class StructuredLogPrivacyTests(unittest.TestCase):
    def test_redacts_sensitive_fields_and_nested_payloads(self) -> None:
        record = logging.LogRecord(
            "fathom.test",
            logging.INFO,
            __file__,
            1,
            "test.event",
            (),
            None,
        )
        record.request_id = "request-1"
        record.job_id = "job-1"
        record.user_id = "user-1"
        record.source_url = "https://example.test/private?token=secret"
        record.metadata = {
            "provider": "fake",
            "email": "person@example.test",
            "access_token": "secret",
        }

        payload = json.loads(JsonFormatter().format(record))

        self.assertEqual(payload["request_id"], "request-1")
        self.assertEqual(payload["job_id"], "job-1")
        self.assertEqual(payload["user_id"], "[redacted]")
        self.assertEqual(payload["source_url"], "[redacted]")
        self.assertEqual(payload["metadata"]["provider"], "fake")
        self.assertEqual(payload["metadata"]["email"], "[redacted]")
        self.assertEqual(payload["metadata"]["access_token"], "[redacted]")


if __name__ == "__main__":
    unittest.main()
