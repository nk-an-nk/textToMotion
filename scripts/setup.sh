#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ is required"'
if [ ! -e .venv ]; then
  python -m venv .venv
elif [ ! -x .venv/bin/python ]; then
  printf '%s\n' 'Inspect the existing invalid .venv before continuing.' >&2
  exit 1
fi
.venv/bin/python -m pip --disable-pip-version-check install --no-cache-dir -r requirements-app.lock
.venv/bin/python -m pip --disable-pip-version-check install --no-cache-dir --no-deps -e .
npm ci --cache "${MOTION_LAB_NPM_CACHE:-/tmp/motion-lab-npm-cache}"
.venv/bin/python -m pip check
printf '%s\n' 'Application dependencies ready. Model weights and environments are separate; see docs/gpu_setup.md.'
