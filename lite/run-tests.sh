#!/usr/bin/env bash
# Run lite/ unit tests. Invoked locally and by the lite-image CI workflow.
set -euo pipefail

cd "$(dirname "$0")"

VENV="${LITE_VENV:-.venv}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3.11 || command -v python3.12 || command -v python3)}"

if [ ! -d "$VENV" ]; then
  "$PYTHON_BIN" -m venv "$VENV"
fi

# shellcheck source=/dev/null
source "$VENV/bin/activate"

python3 -m pip install --quiet --upgrade pip
python3 -m pip install --quiet -r api/requirements-dev.txt

python3 -m pytest tests/ -v

# JS tests for the client-side CSV helpers. ubuntu-latest GitHub runners
# ship Node 20+ pre-installed, which provides the stable node:test runner.
# Skip locally if node is missing rather than failing the whole script.
if command -v node >/dev/null 2>&1; then
  node --test tests/test_csv.js
else
  echo "WARN: node not found; skipping JS unit tests for csv.js."
fi
