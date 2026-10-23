#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sdk_dir="$project_root/sdk/nuwa"
sdk_file='NuwaSDK-2023-10-11_v2.1.0.08_513b45c_release.aar'
sdk_sha256='be9ccb81744cae7b31ea4506687e5bd33be38c9a431f0e0d1a245960a1918f72'

verify() {
  if command -v sha256sum >/dev/null 2>&1; then
    echo "$sdk_sha256  $1" | sha256sum --check -
  else
    echo "$sdk_sha256  $1" | shasum -a 256 --check -
  fi
}

mkdir -p "$sdk_dir"
if [[ ! -f "$sdk_dir/$sdk_file" ]]; then
  download_file="$(mktemp "$sdk_dir/.download.XXXXXX")"
  trap 'rm -f "$download_file"' EXIT
  curl --fail --location --retry 3 \
    "https://bj.bcebos.com/v1/nuwarobotics-files/sdk/$sdk_file" \
    --output "$download_file"
  verify "$download_file"
  unzip -tq "$download_file"
  mv "$download_file" "$sdk_dir/$sdk_file"
fi
verify "$sdk_dir/$sdk_file"
echo "NUWA SDK ready: $sdk_dir/$sdk_file"
