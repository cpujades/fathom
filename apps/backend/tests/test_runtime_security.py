from __future__ import annotations

import unittest

from pydantic import ValidationError
from starlette.responses import Response

from fathom.core.config import Settings
from fathom.core.middleware import apply_security_headers


def _settings_values(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "OPENROUTER_API_KEY": "test-openrouter",
        "GROQ_API_KEY": "test-groq",
        "SUPABASE_URL": "https://project.supabase.co",
        "SUPABASE_PUBLISHABLE_KEY": "test-publishable",
        "SUPABASE_SECRET_KEY": "test-secret",
    }
    values.update(overrides)
    return values


class RuntimeSecuritySettingsTests(unittest.TestCase):
    def test_local_runtime_keeps_explicit_development_defaults(self) -> None:
        settings = Settings.model_validate(_settings_values())

        self.assertEqual(settings.app_env, "local")
        self.assertEqual(settings.rate_limit, 0)
        self.assertEqual(settings.cors_allow_origins, [])
        self.assertFalse(settings.is_strict_runtime)

    def test_rejects_unknown_environment_name(self) -> None:
        with self.assertRaises(ValidationError):
            Settings.model_validate(_settings_values(APP_ENV="prodution"))

    def test_hosted_runtime_requires_rate_limit(self) -> None:
        with self.assertRaisesRegex(ValidationError, "RATE_LIMIT must be greater than zero"):
            Settings.model_validate(
                _settings_values(
                    APP_ENV="production",
                    CORS_ALLOW_ORIGINS="https://app.talven.ai",
                )
            )

    def test_hosted_runtime_requires_cors_origin(self) -> None:
        with self.assertRaisesRegex(ValidationError, "CORS_ALLOW_ORIGINS is required"):
            Settings.model_validate(
                _settings_values(
                    APP_ENV="staging",
                    RATE_LIMIT=60,
                )
            )

    def test_rejects_wildcard_or_path_cors_origins(self) -> None:
        for origin in ("*", "https://*.talven.ai", "https://app.talven.ai/path"):
            with self.subTest(origin=origin), self.assertRaises(ValidationError):
                Settings.model_validate(_settings_values(CORS_ALLOW_ORIGINS=origin))

    def test_hosted_runtime_requires_https_non_loopback_origin(self) -> None:
        for origin in ("http://app.talven.ai", "https://localhost", "https://127.0.0.1"):
            with self.subTest(origin=origin), self.assertRaises(ValidationError):
                Settings.model_validate(
                    _settings_values(
                        APP_ENV="production",
                        RATE_LIMIT=60,
                        CORS_ALLOW_ORIGINS=origin,
                    )
                )

    def test_hosted_runtime_accepts_exact_https_origins(self) -> None:
        settings = Settings.model_validate(
            _settings_values(
                APP_ENV="production",
                RATE_LIMIT=60,
                CORS_ALLOW_ORIGINS=("https://app.talven.ai/, https://admin.talven.ai"),
            )
        )

        self.assertEqual(
            settings.cors_allow_origins,
            ["https://app.talven.ai", "https://admin.talven.ai"],
        )
        self.assertTrue(settings.is_strict_runtime)

    def test_proxy_headers_require_an_explicit_network_allowlist(self) -> None:
        with self.assertRaisesRegex(ValidationError, "enabled or disabled together"):
            Settings.model_validate(_settings_values(TRUST_PROXY_HEADERS=True))

        with self.assertRaisesRegex(ValidationError, "enabled or disabled together"):
            Settings.model_validate(_settings_values(TRUSTED_PROXY_NETWORKS="10.0.0.0/8"))

    def test_proxy_networks_are_validated_and_normalized(self) -> None:
        with self.assertRaisesRegex(ValidationError, "IP addresses or CIDR"):
            Settings.model_validate(
                _settings_values(
                    TRUST_PROXY_HEADERS=True,
                    TRUSTED_PROXY_NETWORKS="not-a-network",
                )
            )

        settings = Settings.model_validate(
            _settings_values(
                TRUST_PROXY_HEADERS=True,
                TRUSTED_PROXY_NETWORKS="10.0.0.4, 2001:db8::/32",
            )
        )
        self.assertEqual(
            settings.trusted_proxy_networks,
            ["10.0.0.4/32", "2001:db8::/32"],
        )


class SecurityHeaderTests(unittest.TestCase):
    def test_api_responses_receive_baseline_headers(self) -> None:
        response = Response()

        apply_security_headers(
            response,
            path="/briefings",
            strict_transport_security=False,
        )

        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(response.headers["referrer-policy"], "no-referrer")
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        self.assertIn("camera=()", response.headers["permissions-policy"])
        self.assertNotIn("strict-transport-security", response.headers)

    def test_hosted_responses_receive_hsts_and_strict_api_csp(self) -> None:
        response = Response()

        apply_security_headers(
            response,
            path="/docs",
            strict_transport_security=True,
        )

        self.assertEqual(
            response.headers["strict-transport-security"],
            "max-age=31536000; includeSubDomains",
        )
        self.assertEqual(
            response.headers["content-security-policy"],
            "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        )

    def test_local_docs_csp_allows_only_documentation_assets(self) -> None:
        response = Response()

        apply_security_headers(
            response,
            path="/docs",
            strict_transport_security=False,
        )

        policy = response.headers["content-security-policy"]
        self.assertIn("https://cdn.jsdelivr.net", policy)
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertNotIn("*", policy)


if __name__ == "__main__":
    unittest.main()
