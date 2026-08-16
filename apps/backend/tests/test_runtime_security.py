from __future__ import annotations

import os
import unittest
from unittest.mock import patch

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
        "APP_ENV": "local",
        "RATE_LIMIT": 0,
        "CORS_ALLOW_ORIGINS": "",
    }
    values.update(overrides)
    return values


def _strict_settings_values(**overrides: object) -> dict[str, object]:
    values = _settings_values(
        APP_ENV="production",
        RATE_LIMIT=60,
        CORS_ALLOW_ORIGINS="https://app.talven.ai",
        SUPABASE_DB_HOST="db.project.supabase.co",
        SUPABASE_DB_PASSWORD="test-database-password",
        POLAR_SERVER="production",
        POLAR_SUCCESS_URL="https://app.talven.ai/billing/success",
        POLAR_CHECKOUT_RETURN_URL="https://app.talven.ai/billing",
        POLAR_PORTAL_RETURN_URL="https://app.talven.ai/billing",
    )
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
            _strict_settings_values(
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

    def test_explore_operator_ids_are_validated_and_deduplicated(self) -> None:
        operator_id = "11111111-1111-1111-1111-111111111111"
        settings = Settings.model_validate(_settings_values(EXPLORE_OPERATOR_USER_IDS=f"{operator_id}, {operator_id}"))

        self.assertEqual(settings.explore_operator_user_ids, [operator_id])
        with self.assertRaisesRegex(ValidationError, "must be UUIDs"):
            Settings.model_validate(_settings_values(EXPLORE_OPERATOR_USER_IDS="not-a-user-id"))

    def test_comma_separated_lists_load_from_real_environment_sources(self) -> None:
        environment = {
            key: str(value)
            for key, value in _strict_settings_values(
                CORS_ALLOW_ORIGINS="https://app.talven.ai, https://admin.talven.ai",
                TRUST_PROXY_HEADERS=True,
                TRUSTED_PROXY_NETWORKS="10.0.0.4, 2001:db8::/32",
            ).items()
        }
        with patch.dict(os.environ, environment, clear=True):
            settings = Settings(_env_file=None)

        self.assertEqual(settings.cors_allow_origins, ["https://app.talven.ai", "https://admin.talven.ai"])
        self.assertEqual(settings.trusted_proxy_networks, ["10.0.0.4/32", "2001:db8::/32"])

    def test_hosted_runtime_rejects_insecure_service_urls_and_database_hosts(self) -> None:
        invalid_values = (
            {"SUPABASE_URL": "http://project.supabase.co"},
            {"SUPABASE_URL": "https://localhost"},
            {"SUPABASE_DB_HOST": "127.0.0.1"},
            {"POLAR_SUCCESS_URL": "http://app.talven.ai/billing"},
        )
        for overrides in invalid_values:
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                Settings.model_validate(_strict_settings_values(**overrides))

    def test_hosted_runtime_requires_direct_database_password(self) -> None:
        with self.assertRaisesRegex(ValidationError, "SUPABASE_DB_PASSWORD is required"):
            Settings.model_validate(_strict_settings_values(SUPABASE_DB_PASSWORD=""))

    def test_database_port_is_bounded(self) -> None:
        for port in (0, 65_536):
            with self.subTest(port=port), self.assertRaises(ValidationError):
                Settings.model_validate(_settings_values(SUPABASE_DB_PORT=port))

    def test_production_runtime_rejects_polar_sandbox(self) -> None:
        with self.assertRaisesRegex(ValidationError, "POLAR_SERVER must be production"):
            Settings.model_validate(_strict_settings_values(POLAR_SERVER="sandbox"))


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
