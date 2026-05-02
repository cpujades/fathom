from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import cast

from fastapi import Request

from fathom.core.rate_limits import _get_rate_limit_rule, _get_rate_limit_subject
from fathom.services.supabase.helpers import is_unique_violation


def _request(
    *,
    path: str,
    method: str = "GET",
    client_host: str | None = "10.0.0.5",
    forwarded_for: str | None = None,
    authorization: str | None = None,
) -> Request:
    headers: dict[str, str] = {}
    if forwarded_for is not None:
        headers["x-forwarded-for"] = forwarded_for
    if authorization is not None:
        headers["authorization"] = authorization

    client = SimpleNamespace(host=client_host) if client_host is not None else None
    url = SimpleNamespace(path=path)
    return cast(Request, SimpleNamespace(headers=headers, client=client, method=method, url=url))


class UniqueViolationTests(unittest.TestCase):
    def test_detects_postgres_unique_violation(self) -> None:
        exc = cast(object, SimpleNamespace(code="23505"))

        self.assertTrue(is_unique_violation(exc))

    def test_ignores_other_errors(self) -> None:
        exc = cast(object, SimpleNamespace(code="42501"))

        self.assertFalse(is_unique_violation(exc))


class RateLimitSubjectTests(unittest.TestCase):
    def test_uses_ip_subject_without_bearer_token(self) -> None:
        request = _request(path="/briefings")

        subject = _get_rate_limit_subject(request, trust_proxy_headers=False)

        self.assertEqual(subject, "ip:10.0.0.5")

    def test_ignores_bearer_token_subject_before_auth_verification(self) -> None:
        request = _request(
            path="/briefings",
            authorization="Bearer header.eyJzdWIiOiAidXNlci0xMjMifQ.signature",
        )

        subject = _get_rate_limit_subject(request, trust_proxy_headers=False)

        self.assertEqual(subject, "ip:10.0.0.5")

    def test_fake_bearer_subjects_do_not_shard_ip_bucket(self) -> None:
        first_request = _request(
            path="/briefings",
            authorization="Bearer header.eyJzdWIiOiAiZmFrZS1hIn0.signature",
        )
        second_request = _request(
            path="/briefings",
            authorization="Bearer header.eyJzdWIiOiAiZmFrZS1iIn0.signature",
        )

        first_subject = _get_rate_limit_subject(first_request, trust_proxy_headers=False)
        second_subject = _get_rate_limit_subject(second_request, trust_proxy_headers=False)

        self.assertEqual(first_subject, "ip:10.0.0.5")
        self.assertEqual(second_subject, "ip:10.0.0.5")

    def test_falls_back_to_forwarded_ip_when_proxy_headers_are_trusted(self) -> None:
        request = _request(
            path="/briefings",
            client_host="10.0.0.5",
            forwarded_for="203.0.113.9, 10.0.0.5",
            authorization="Bearer not-a-jwt",
        )

        subject = _get_rate_limit_subject(request, trust_proxy_headers=True)

        self.assertEqual(subject, "ip:203.0.113.9")


class RateLimitRuleTests(unittest.TestCase):
    def test_exempts_meta_routes(self) -> None:
        request = _request(path="/meta/health")

        self.assertIsNone(_get_rate_limit_rule(request, 60))

    def test_exempts_polar_webhooks(self) -> None:
        request = _request(path="/webhooks/polar", method="POST")

        self.assertIsNone(_get_rate_limit_rule(request, 60))

    def test_exempts_briefing_session_events(self) -> None:
        request = _request(path="/briefing-sessions/123/events")

        self.assertIsNone(_get_rate_limit_rule(request, 60))

    def test_uses_strict_limit_for_briefing_creation(self) -> None:
        request = _request(path="/briefing-sessions", method="POST")

        rule = _get_rate_limit_rule(request, 60)

        self.assertIsNotNone(rule)
        assert rule is not None
        self.assertEqual(rule.scope, "briefing_create")
        self.assertEqual(rule.limit_per_minute, 12)

    def test_uses_billing_write_scope_for_non_get_billing_routes(self) -> None:
        request = _request(path="/billing/checkout", method="POST")

        rule = _get_rate_limit_rule(request, 60)

        self.assertIsNotNone(rule)
        assert rule is not None
        self.assertEqual(rule.scope, "billing_write")
        self.assertEqual(rule.limit_per_minute, 20)

    def test_uses_relaxed_read_scope_for_get_requests(self) -> None:
        request = _request(path="/briefings", method="GET")

        rule = _get_rate_limit_rule(request, 60)

        self.assertIsNotNone(rule)
        assert rule is not None
        self.assertEqual(rule.scope, "read")
        self.assertEqual(rule.limit_per_minute, 240)
