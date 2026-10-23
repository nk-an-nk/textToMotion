#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${ANDROID_HOME:?ANDROID_HOME must be set by devcontainer.json}"
export ANDROID_SDK_ROOT="$ANDROID_HOME"
export PATH="$ANDROID_HOME/cmdline-tools/19.0/bin:$ANDROID_HOME/platform-tools:$PATH"

if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
  echo 'Run this setup inside the Linux x86_64 Codespace.' >&2
  exit 1
fi

if [[ ! -x "$ANDROID_HOME/cmdline-tools/19.0/bin/sdkmanager" ]]; then
  download_dir="$(mktemp -d)"
  trap 'rm -rf "$download_dir"' EXIT
  curl --fail --location --retry 3 \
    'https://dl.google.com/android/repository/commandlinetools-linux-13114758_latest.zip' \
    --output "$download_dir/tools.zip"
  # Checksum published in Google's repository2-1.xml for cmdline-tools;19.0.
  echo "5fdcc763663eefb86a5b8879697aa6088b041e70  $download_dir/tools.zip" | sha1sum --check -
  unzip -q "$download_dir/tools.zip" -d "$download_dir"
  mkdir -p "$ANDROID_HOME/cmdline-tools"
  mv "$download_dir/cmdline-tools" "$ANDROID_HOME/cmdline-tools/19.0"
fi

# yes exits with SIGPIPE when sdkmanager finishes; check sdkmanager's status.
set +o pipefail
yes | sdkmanager --sdk_root="$ANDROID_HOME" --licenses
license_status=${PIPESTATUS[1]}
set -o pipefail
if [[ "$license_status" -ne 0 ]]; then
  exit "$license_status"
fi
sdkmanager --sdk_root="$ANDROID_HOME" \
  'platform-tools' 'platforms;android-28' 'platforms;android-35' 'build-tools;34.0.0'

bash "$project_root/scripts/download-nuwa-sdk.sh"
bash "$project_root/scripts/check-environment.sh"

# Application development dependencies (mock mode requires no external API key).
bash "$project_root/kebbi-conversation/scripts/setup.sh"
