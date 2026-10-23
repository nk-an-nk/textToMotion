#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${ANDROID_HOME:?ANDROID_HOME is not set}"
python --version
node --version
npm --version
git --version
java -version
javac -version
gradle --version
"$ANDROID_HOME/cmdline-tools/19.0/bin/sdkmanager" --version
"$ANDROID_HOME/platform-tools/adb" version
for package_file in \
  platforms/android-28/android.jar \
  platforms/android-35/android.jar \
  build-tools/34.0.0/aapt2; do
  if [[ ! -f "$ANDROID_HOME/$package_file" ]]; then
    echo "Missing Android SDK component: $package_file" >&2
    exit 1
  fi
done
sdk_file="$project_root/sdk/nuwa/NuwaSDK-2023-10-11_v2.1.0.08_513b45c_release.aar"
echo "be9ccb81744cae7b31ea4506687e5bd33be38c9a431f0e0d1a245960a1918f72  $sdk_file" | sha256sum --check -
unzip -tq "$sdk_file"
echo 'NUWA SDK development environment is ready.'
