from __future__ import annotations

import unittest

from fathom.core.errors import ExternalServiceError
from fathom.services.supabase.helpers import first_row, response_record, response_records


class SupabaseResponseHelpersTests(unittest.TestCase):
    def test_response_record_copies_a_string_keyed_mapping(self) -> None:
        source = {"id": "record-1", "count": 2}

        result = response_record(source, error_message="invalid")

        self.assertEqual(result, source)
        self.assertIsNot(result, source)

    def test_response_record_rejects_non_string_keys(self) -> None:
        with self.assertRaisesRegex(ExternalServiceError, "invalid"):
            response_record({1: "value"}, error_message="invalid")

    def test_response_records_accepts_none_as_an_empty_result(self) -> None:
        self.assertEqual(response_records(None, error_message="invalid"), [])

    def test_response_records_validates_every_row(self) -> None:
        with self.assertRaisesRegex(ExternalServiceError, "invalid"):
            response_records([{"id": "record-1"}, "not-a-record"], error_message="invalid")

    def test_first_row_uses_the_same_record_validation(self) -> None:
        with self.assertRaisesRegex(ExternalServiceError, "invalid"):
            first_row([{1: "value"}], error_message="invalid")


if __name__ == "__main__":
    unittest.main()
