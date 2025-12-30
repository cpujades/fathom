#!/usr/bin/env bash
set -euo pipefail

echo "ty (informational):"

if ! command -v ty >/dev/null 2>&1; then
  echo "  ty is not installed. Skipping."
  exit 0
fi

# Run type checking, but never fail the commit/CI (informational only).
#
# Note: pre-commit typically hides output for successful hooks. We pair this with
# `verbose: true` in `.pre-commit-config.yaml` so you can see ty diagnostics even
# though the hook always exits 0.
output="$(ty check app 2>&1)" || true
if [[ -n "${output}" ]]; then
  echo "${output}"
fi
