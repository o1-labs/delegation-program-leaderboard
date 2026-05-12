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
