#!/usr/bin/env bash
# Run graphql/ tests. Invoked locally and by the graphql-image CI workflow.
# The tests start a PostgreSQL container with testcontainers, so Docker
# must be available.
set -euo pipefail

cd "$(dirname "$0")"

VENV="${GRAPHQL_VENV:-.venv}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3.12 || command -v python3)}"

if [ ! -d "$VENV" ]; then
  "$PYTHON_BIN" -m venv "$VENV"
fi

# shellcheck source=/dev/null
source "$VENV/bin/activate"

python3 -m pip install --quiet --upgrade pip
python3 -m pip install --quiet -r requirements-dev.txt

python3 -m pytest tests/ -v
