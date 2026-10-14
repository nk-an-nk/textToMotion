#!/usr/bin/env bash
# Prepare a disposable GPU Linux Pod; no resource creation, deposits, or model downloads.
set -euo pipefail
cd "$(dirname "$0")/.."
if ! command -v nvidia-smi >/dev/null 2>&1; then
  printf '%s\n' 'NVIDIA driver/GPU is missing. Run this inside the allocated RunPod GPU Pod.' >&2
  exit 1
fi
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
python -c 'import sys; assert sys.version_info >= (3,11), "Use a RunPod Python 3.11+ template"'
if [ "${1:-}" = '--check' ]; then
  python -c 'import sys; assert sys.version_info >= (3,12), "Frozen application dependencies require Python 3.12+"'
  node --version
  command -v ffmpeg
  printf '%s\n' 'Basic tools detected. Use probe_webgl.cjs to verify actual hardware rendering.'
  exit 0
fi
if [ "$(id -u)" -ne 0 ]; then
  printf '%s\n' 'Run the installation inside a disposable RunPod root container.' >&2
  exit 1
fi
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3.12-venv ffmpeg fonts-noto-cjk curl ca-certificates xz-utils libvulkan1 mesa-vulkan-drivers
mkdir -p .motion-lab/tools/python/bin
runpod_app_python="$(command -v python3.12)"
ln -sf "$runpod_app_python" .motion-lab/tools/python/bin/python
if ! command -v node >/dev/null 2>&1 || ! node -e 'if(Number(process.versions.node.split(".")[0])<20)process.exit(1)'; then
  mkdir -p .motion-lab/tools/node-download
  (
    cd .motion-lab/tools/node-download
    curl --fail --location --show-error --output node-v22.16.0-linux-x64.tar.xz https://nodejs.org/dist/v22.16.0/node-v22.16.0-linux-x64.tar.xz
    curl --fail --location --show-error --output SHASUMS256.txt https://nodejs.org/dist/v22.16.0/SHASUMS256.txt
    awk '$2 == "node-v22.16.0-linux-x64.tar.xz" {print}' SHASUMS256.txt > expected.sha256
    test -s expected.sha256
    sha256sum --check expected.sha256
    if [ ! -d ../node-v22.16.0-linux-x64 ]; then tar -xJf node-v22.16.0-linux-x64.tar.xz -C ..; fi
  )
fi
mkdir -p .motion-lab
cat > .motion-lab/runpod-env.sh <<'ENV'
# Source from the repository root in each new terminal.
if [ -d "$PWD/.motion-lab/tools/python/bin" ]; then
  export PATH="$PWD/.motion-lab/tools/python/bin:$PATH"
fi
if [ -d "$PWD/.motion-lab/tools/node-v22.16.0-linux-x64/bin" ]; then
  export PATH="$PWD/.motion-lab/tools/node-v22.16.0-linux-x64/bin:$PATH"
fi
ENV
source .motion-lab/runpod-env.sh
bash scripts/setup.sh
npx playwright install --with-deps chromium
printf '%s\n' 'In each new terminal: source .motion-lab/runpod-env.sh'
printf '%s\n' 'Next: node scripts/probe_webgl.cjs --renderer gpu --output .motion-lab/runpod-webgl.json'
printf '%s\n' 'If the GPU probe fails, inspect driver graphics/Vulkan access before generating a full video.'
