#!/usr/bin/env bash
# Optional Android UI verification entirely inside GitHub Codespaces.
set -euo pipefail
if [[ "${CODESPACES:-}" != true || "$(uname -s)" != Linux ]]; then
  echo "Run this script in GitHub Codespaces, not on your Mac." >&2
  exit 1
fi
sdk="${ANDROID_HOME:?ANDROID_HOME is required}"
root="$(cd "$(dirname "$0")/../.." && pwd)"
run=/tmp/kebbi-cloud-android
avd=kebbi_cloud_api28
mkdir -p "$run"
if [[ "${1:-}" == setup ]]; then
  sudo apt-get update -qq
  sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    xvfb x11vnc novnc websockify libpulse0 libnss3 libx11-6 libxcb1 \
    libxcomposite1 libxcursor1 libxi6 libxtst6 libxrandr2 libgl1 libxkbcommon-x11-0
  sdkmanager --install emulator 'system-images;android-28;default;x86_64'
  exit
fi
if [[ "${1:-}" != run ]]; then
  echo "Usage: bash kebbi-conversation/scripts/cloud-android.sh setup|run"
  exit 1
fi
[[ -x "$sdk/emulator/emulator" ]] || { echo "Run setup first." >&2; exit 1; }
[[ -f "$root/kebbi-conversation/android-app/app/build/outputs/apk/mock/debug/app-mock-debug.apk" ]] || {
  echo "Build :app:assembleMockDebug in kebbi-conversation/android-app first." >&2; exit 1;
}
if adb devices | grep -q '^emulator-'; then
  echo "An emulator is already running; reuse it or stop it first." >&2
  exit 1
fi
if [[ ! -d "$HOME/.android/avd/$avd.avd" ]]; then
  echo no | avdmanager create avd -n "$avd" -k 'system-images;android-28;default;x86_64' -d pixel_2
fi
python3 - "$HOME/.android/avd/$avd.avd/config.ini" <<'PYCONFIG'
import sys
from pathlib import Path
p = Path(sys.argv[1])
values = dict(line.split('=', 1) for line in p.read_text().splitlines() if '=' in line)
values.update({'hw.lcd.width': '480', 'hw.lcd.height': '800', 'hw.lcd.density': '160',
               'hw.keyboard': 'yes', 'disk.dataPartition.size': '1024M', 'showDeviceFrame': 'no'})
p.write_text(''.join(f'{k.strip()}={v.strip()}\n' for k, v in values.items()))
PYCONFIG
export DISPLAY=:99 ANDROID_I_WANT_MY_TCG=yes QT_X11_NO_MITSHM=1
pids=()
cleanup() { for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT
trap 'exit 130' INT TERM
Xvfb :99 -screen 0 1024x900x24 -nolisten tcp > "$run/xvfb.log" 2>&1 &
pids+=("$!")
sleep 2
x11vnc -display :99 -localhost -nopw -forever -shared -noxdamage -rfbport 5900 > "$run/vnc.log" 2>&1 &
pids+=("$!")
# Keep port 6080 PRIVATE in Codespaces; VNC is bound only to loopback.
websockify --web=/usr/share/novnc 127.0.0.1:6080 127.0.0.1:5900 > "$run/novnc.log" 2>&1 &
pids+=("$!")
"$sdk/emulator/emulator" -avd "$avd" -accel off -gpu swiftshader \
  -memory 1024 -cores 2 -no-snapshot -no-audio -no-boot-anim \
  -camera-back none -camera-front none -skin 480x800 -feature -Vulkan > "$run/emulator.log" 2>&1 &
emulator_pid=$!
pids+=("$emulator_pid")
echo "Android is booting. Open private port 6080 /vnc.html?resize=scale and click Connect."
booted=false
for ((i=0; i<90; i++)); do
  kill -0 "$emulator_pid" 2>/dev/null || { tail -30 "$run/emulator.log"; exit 1; }
  if [[ "$(timeout 5 adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r' || true)" == 1 ]]; then
    booted=true
    break
  fi
  sleep 10
done
[[ "$booted" == true ]] || { echo "Boot timed out. Check $run/emulator.log"; exit 1; }
adb install -r "$root/kebbi-conversation/android-app/app/build/outputs/apk/mock/debug/app-mock-debug.apk"
adb shell am start -n jp.ojimalab.kebbi.conversation.mock/jp.ojimalab.kebbi.MainActivity
echo "Mock app started. Keep this terminal running. Ctrl+C stops the emulator and viewer."
wait "$emulator_pid"
