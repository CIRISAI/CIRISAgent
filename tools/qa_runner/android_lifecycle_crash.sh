#!/usr/bin/env bash
# Android lifecycle crash scenarios, on an emulator (android-lifecycle-crash.yml).
#
#   tools/qa_runner/android_lifecycle_crash.sh <debug.apk> <out_dir>
#
# SCENARIO 1: killed in the background, never revived there.
# The app is started, sent to the background, and its process is killed the way
# the low-memory killer does it. A START_STICKY service is then restarted BY THE
# SYSTEM, in the background, where Android 12+ refuses startForeground():
# ForegroundServiceStartNotAllowedException, a crash, and a re-scheduled restart
# (every release 2.6.0..2.19.0). The scenario fails on either signal:
#   - ActivityManager scheduling a restart of the crashed service (the mechanism,
#     seen at once, whatever the restart backoff), or
#   - a FATAL EXCEPTION for the package in the crash buffer (the symptom).
# https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start
#
# A scenario passes only on a positive observation that it ran: the service was
# seen running before the kill, and the process was seen dead after it.
set -u
APK="$1"
OUT="$2"
PKG=ai.ciris.mobile.debug
SVC=ai.ciris.mobile.PythonRuntimeService
mkdir -p "$OUT"
say() { printf '[lifecycle] %s\n' "$*"; }
fail() { say "FAIL: $*"; adb logcat -d > "$OUT/logcat.txt" 2>&1; adb logcat -b crash -d > "$OUT/crash.txt" 2>&1; exit 1; }

adb install -r "$APK" >/dev/null || fail "install failed"
adb shell pm grant "$PKG" android.permission.POST_NOTIFICATIONS 2>/dev/null || true
adb logcat -c; adb logcat -b crash -c

say "launch"
adb shell am start -W -n "$PKG/ai.ciris.mobile.MainActivity" >/dev/null || fail "launch failed"
running=0
for _ in $(seq 1 90); do
  if adb shell dumpsys activity services "$PKG" | grep -q "$SVC"; then running=1; break; fi
  sleep 2
done
[ "$running" = 1 ] || fail "the runtime service never started (no positive observation; scenario did not run)"
say "service running; letting the runtime come up"
sleep 30

say "background the app (HOME)"
adb shell input keyevent KEYCODE_HOME
sleep 5
pid=$(adb shell pidof "$PKG" | tr -d '\r')
[ -n "$pid" ] || fail "no process to kill (scenario did not run)"
say "kill pid $pid as the low-memory killer would"
adb shell run-as "$PKG" kill -9 "$pid" || adb shell kill -9 "$pid" || fail "could not kill the process"
sleep 3
[ -z "$(adb shell pidof "$PKG" | tr -d '\r')" ] || say "note: a process is back already (pid $(adb shell pidof "$PKG"))"

say "observe 120 s for a background restart or a crash"
for _ in $(seq 1 60); do
  if adb logcat -d -s ActivityManager:W ActivityManager:I 2>/dev/null | grep -q "restart of crashed service $PKG/$SVC"; then
    fail "the system scheduled a background restart of $SVC (START_STICKY): $(adb logcat -d -s ActivityManager:W ActivityManager:I | grep "restart of crashed service $PKG/$SVC" | tail -1)"
  fi
  if adb logcat -b crash -d 2>/dev/null | grep -q "Process: $PKG"; then
    fail "the app crashed in the background: $(adb logcat -b crash -d | grep -m1 -E 'Exception|Error')"
  fi
  sleep 2
done
adb logcat -d > "$OUT/logcat.txt" 2>&1
say "PASS: killed in the background, no restart scheduled, no crash in 120 s"
