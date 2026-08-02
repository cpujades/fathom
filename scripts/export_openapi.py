"""Export Talven's OpenAPI schema without starting an HTTP server."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Path to the committed OpenAPI JSON file.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed file differs instead of writing it.",
    )
    args = parser.parse_args()

    _configure_schema_environment()
    from fathom.api.app import app

    rendered = json.dumps(app.openapi(), indent=2) + "\n"
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            print(f"OpenAPI contract is stale: {args.output}")
            print("Run `pnpm generate:api-client` and commit the generated changes.")
            return 1
        print(f"OpenAPI contract is current: {args.output}")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"Exported OpenAPI contract to {args.output}")
    return 0


def _configure_schema_environment() -> None:
    """Provide inert values for settings required while importing the app."""

    os.environ.update(
        {
            "APP_ENV": "test",
            "CORS_ALLOW_ORIGINS": "",
            "TRUST_PROXY_HEADERS": "false",
            "TRUSTED_PROXY_NETWORKS": "",
        }
    )
    defaults = {
        "GROQ_API_KEY": "schema-export",
        "OPENROUTER_API_KEY": "schema-export",
        "SUPABASE_PUBLISHABLE_KEY": "schema-export",
        "SUPABASE_SECRET_KEY": "schema-export",
        "SUPABASE_URL": "http://127.0.0.1:54321",
    }
    for name, value in defaults.items():
        os.environ.setdefault(name, value)


if __name__ == "__main__":
    raise SystemExit(main())
