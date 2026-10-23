#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python3 -m venv "$root/backend/.venv"
"$root/backend/.venv/bin/python" -m pip install -r "$root/backend/requirements-dev.txt"
echo 'Backend ready. See kebbi-conversation/docs/setup.md for startup and Android builds.'
