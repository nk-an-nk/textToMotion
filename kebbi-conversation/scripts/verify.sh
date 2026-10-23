#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${KEBBI_PYTHON:-$root/backend/.venv/bin/python}"
"$python_bin" -m pytest -q "$root/backend/tests" -c "$root/backend/pytest.ini"
work="$(mktemp -d)"
server_pid=''
cleanup() { if [[ -n "$server_pid" ]]; then kill "$server_pid" 2>/dev/null || true; wait "$server_pid" 2>/dev/null || true; fi; rm -rf "$work"; }
trap cleanup EXIT
# Let the OS allocate a port, then hand the bound socket to Uvicorn (no port-selection race).
LLM_PROVIDER=mock BACKEND_TOKEN='' LOG_CONTENT=false PYTHONPATH="$root/backend"   "$python_bin" -u - "$work/port" > "$work/backend.log" 2>&1 <<'PYTHON' &
import socket, sys
import uvicorn
sock=socket.socket(); sock.bind(('127.0.0.1',0))
with open(sys.argv[1],'w') as f: f.write(str(sock.getsockname()[1]))
uvicorn.Server(uvicorn.Config('app.main:app',access_log=False,log_level='warning')).run(sockets=[sock])
PYTHON
server_pid=$!
for attempt in {1..50}; do
  if [[ -s "$work/port" ]] && curl --fail --silent "http://127.0.0.1:$(cat "$work/port")/health" > /dev/null; then break; fi
  if ! kill -0 "$server_pid" 2>/dev/null; then cat "$work/backend.log"; exit 1; fi
  sleep 0.2
done
export KEBBI_TEST_BACKEND="http://127.0.0.1:$(cat "$work/port")"
curl --fail --silent "$KEBBI_TEST_BACKEND/health"
cd "$root/android-app"
if ! ./gradlew :core:test :app:assembleMockDebug --rerun-tasks --console=plain; then cat "$work/backend.log"; exit 1; fi
# The real flavor is optional; explicitly enable when the vendor AAR has been supplied.
if [[ "${KEBBI_VERIFY_REAL:-false}" == true ]]; then ./gradlew :app:assembleRealDebug --console=plain; fi
