# iOS KMP App - Claude Development Notes

## Overview

This is the Kotlin Multiplatform (KMP) iOS app for CIRIS. It uses Compose Multiplatform for UI and embeds a Python runtime to run the CIRIS backend.

## CIRISVerify (CRITICAL)

CIRISVerify is a Rust FFI library providing hardware-rooted license verification and Ed25519 signing. It is a **hard requirement for 2.0**.

### Architecture

```
Frameworks/CIRISVerify.xcframework/     # Dynamic framework (MUST be .dylib, NOT .a)
  ios-arm64/CIRISVerify.framework/      # Device (iphoneos)
  ios-arm64-simulator/CIRISVerify.framework/  # Simulator

Resources/app_packages/ciris_verify/    # Python bindings (extracted from Resources.zip)
  client.py                             # Main client - wraps FFI via ctypes
  types.py                              # Pydantic models (AttestationProof, etc.)
  __init__.py                           # Exports CIRISVerify class
  exceptions.py                         # BinaryNotFoundError, etc.
  libciris_verify_ffi.dylib             # Fallback dylib (used if framework path unavailable)

Resources/app/ciris_adapters/ciris_verify/  # CIRIS adapter (loads CIRISVerify as a service)
  adapter.py                            # CIRISVerifyAdapter - registers as TOOL service
  service.py                            # CIRISVerifyService - iOS-specific 8MB stack thread
  manifest.json                         # Adapter metadata
```

### Key Constraints

1. **XCFramework MUST contain dynamic libraries** (`.dylib`), NOT static archives (`.a`). The CIRISVerify build script produces both but the default XCFramework uses `.a`. Python's `ctypes.CDLL()` cannot resolve symbols from static archives via `dlsym`. Use `tools/update_ciris_verify.py --local` to rebuild correctly.

2. **8MB stack thread required on iOS.** The Rust/Tokio runtime inside CIRISVerify needs ~8MB of stack. iOS default thread stack is 512KB. The iOS `service.py` wraps `CIRISVerify()` construction in an 8MB stack thread. **Do NOT overwrite this file with the repo version** (`ciris_adapters/ciris_verify/service.py`) without re-applying the fix.

3. **Resources.zip extraction is version-gated.** `PythonBridge.swift:extractResourcesIfNeeded()` compares `"{CFBundleShortVersionString}-{CFBundleVersion}"` against a `.extraction_version` marker file. If the version matches, extraction is skipped. **To force re-extraction after updating Python code, bump `CFBundleVersion` in `Info.plist`** (e.g., 49→50). Deleting the app also works but is slower.

4. **Framework path discovery.** `PythonBridge.swift` sets `CIRIS_IOS_FRAMEWORK_PATH` env var pointing to the embedded framework in the app bundle. The Python `ciris_verify` client reads this to find the `.dylib`.

5. **Device vs Simulator native modules.** Pre-built frameworks in `Frameworks/` may be simulator-only. Device builds need `app_packages_native/*.so` files (from BeeWare build output). The `embed_native_frameworks.sh` script handles this: simulator copies from `Frameworks/`, device converts from `app_packages_native/`.

### Updating CIRISVerify

Use the update script (preferred):
```bash
# From local CIRISVerify build (rebuilds XCFramework as dynamic)
python -m tools.update_ciris_verify --local /path/to/CIRISVerify

# From GitHub release (Android + Python only, iOS requires --local)
python -m tools.update_ciris_verify 0.6.16
```

Manual update:
```bash
# 1. Rebuild XCFramework from .dylib (NOT .a)
#    See tools/update_ciris_verify.py build_ios_xcframework()

# 2. Sync Python bindings from Android
cp mobile/androidApp/src/main/python/ciris_verify/*.py \
   mobile/iosApp/Resources/app_packages/ciris_verify/

# 3. Copy device dylib
cp /path/to/CIRISVerify/target/aarch64-apple-ios/release/libciris_verify_ffi.dylib \
   mobile/iosApp/Resources/app_packages/ciris_verify/

# 4. Sync adapter (BUT preserve iOS service.py 8MB stack fix!)
cp ciris_adapters/ciris_verify/adapter.py mobile/iosApp/Resources/app/ciris_adapters/ciris_verify/
# DO NOT blindly copy service.py - it has an iOS-specific patch

# 5. Rebuild Resources.zip
cd mobile/iosApp && rm -f Resources.zip && cd Resources && zip -q -r ../Resources.zip . && cd ..

# 6. Delete app from device, rebuild, reinstall
```

### Verifying CIRISVerify Loaded

After deploying, check via the API (port forward with iproxy):
```bash
iproxy 18080 8080 -u $(idevice_id -l) &
# Authenticate (use native Apple auth)
curl -s http://127.0.0.1:18080/v1/system/adapters -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
# Look for ciris_verify in the adapter list
```

Or pull the incidents log - if CIRISVerify fails to load, there will be an ERROR entry:
```bash
xcrun devicectl device copy from --device $DEVICE_ID \
  --domain-type appDataContainer --domain-identifier ai.ciris.mobile \
  --source Documents/ciris/logs/incidents_20260220_021549.log \
  --destination /tmp/ios_logs/incidents.log
grep -i "verify\|adapter" /tmp/ios_logs/incidents.log
```

## Device Debugging (IMPORTANT)

### Connecting to Physical Device

The iPhone must be connected via USB and trusted. Check connection:

```bash
# List connected devices
idevice_id -l
# Example output: 00008110-0016395C1ED9401E

# Get device info
ideviceinfo -u <DEVICE_ID> | head -20
```

### Taking Screenshots of Device

Uses `pymobiledevice3` with a background `tunneld` daemon (requires one-time `sudo` setup for the TUN device). Once tunneld is running, screenshots work without sudo.

```bash
# One-time setup: start tunneld as background daemon (requires sudo)
sudo python3 -m pymobiledevice3 remote tunneld &
# Or make permanent via launchd (see below)

# Take screenshot (no sudo needed, connects to running tunneld)
python3 -m pymobiledevice3 developer dvt screenshot /tmp/ios_screenshot.png
```

**Permanent tunneld setup (survives reboots):**

Create `/Library/LaunchDaemons/com.pymobiledevice3.tunneld.plist` and load with:
```bash
sudo launchctl bootstrap system /Library/LaunchDaemons/com.pymobiledevice3.tunneld.plist
```

**Why this approach:** Other methods don't work on iOS 26:
- `idevicescreenshot` — broken (requires DeveloperDiskImage, removed in iOS 17+)
- `xcrun devicectl` — has no screenshot subcommand
- iPhone Mirroring — DRM-protected (`kCGWindowSharingState: 0`), invisible to all macOS screen capture APIs
- AVFoundation/CoreMediaIO — only sees Continuity Camera, not the device screen
- `screencapture` CLI — fails with "could not create image from display"

### Pulling Logs from Device

Use `xcrun devicectl` to access app files on physical devices:

```bash
DEVICE_ID="00008110-0016395C1ED9401E"  # Replace with actual device ID
BUNDLE_ID="ai.ciris.mobile"

# List all files in app container
xcrun devicectl device info files \
  --device $DEVICE_ID \
  --domain-type appDataContainer \
  --domain-identifier $BUNDLE_ID 2>&1 | head -50

# Find log files
xcrun devicectl device info files \
  --device $DEVICE_ID \
  --domain-type appDataContainer \
  --domain-identifier $BUNDLE_ID 2>&1 | grep -E "\.log|runtime_status|python_error"

# Pull a specific file
mkdir -p /tmp/ios_logs
xcrun devicectl device copy from \
  --device $DEVICE_ID \
  --domain-type appDataContainer \
  --domain-identifier $BUNDLE_ID \
  --source Documents/ciris/logs/kmp_runtime.log \
  --destination /tmp/ios_logs/kmp_runtime.log

# View pulled log
tail -100 /tmp/ios_logs/kmp_runtime.log
```

### Key Log Files

| File | Description |
|------|-------------|
| `Documents/ciris/runtime_status.json` | Current Python runtime phase and status |
| `Documents/ciris/startup_status.json` | Startup check results (Pydantic, FastAPI, etc.) |
| `Documents/ciris/logs/kmp_runtime.log` | Main KMP/Python runtime log (phases only) |
| `Documents/ciris/logs/kmp_errors.log` | Errors only |
| `Documents/ciris/logs/incidents_*.log` | CIRIS incident logs (WARNING/ERROR - check this first!) |
| `Documents/ciris/logs/ciris_agent_*.log` | Full agent log (large, may fail devicectl transfer) |
| `Documents/ciris/logs/latest.log` | Symlink to agent log (cannot pull via devicectl - use timestamped file) |
| `Documents/python_error.log` | Python import/startup errors |
| `Documents/ciris/.restart_signal` | Restart signal file (if pending) |
| `Documents/ciris/.server_ready` | Server ready indicator |

### Quick Debug Commands

```bash
# Check runtime status
xcrun devicectl device copy from --device $DEVICE_ID \
  --domain-type appDataContainer --domain-identifier $BUNDLE_ID \
  --source Documents/ciris/runtime_status.json \
  --destination /tmp/ios_logs/status.json && cat /tmp/ios_logs/status.json

# Check startup checks (Pydantic, FastAPI, Cryptography, CIRIS Engine)
xcrun devicectl device copy from --device $DEVICE_ID \
  --domain-type appDataContainer --domain-identifier $BUNDLE_ID \
  --source Documents/ciris/startup_status.json \
  --destination /tmp/ios_logs/startup.json && cat /tmp/ios_logs/startup.json

# Get recent runtime log
xcrun devicectl device copy from --device $DEVICE_ID \
  --domain-type appDataContainer --domain-identifier $BUNDLE_ID \
  --source Documents/ciris/logs/kmp_runtime.log \
  --destination /tmp/ios_logs/runtime.log && tail -100 /tmp/ios_logs/runtime.log

# Pull incidents log (find exact filename first)
xcrun devicectl device info files --device $DEVICE_ID \
  --domain-type appDataContainer --domain-identifier $BUNDLE_ID 2>&1 | grep incidents

# Port forward to hit API directly
iproxy 18080 8080 -u $DEVICE_ID &
curl -s http://127.0.0.1:18080/v1/system/health | python3 -m json.tool

# Check for Python errors
xcrun devicectl device copy from --device $DEVICE_ID \
  --domain-type appDataContainer --domain-identifier $BUNDLE_ID \
  --source Documents/python_error.log \
  --destination /tmp/ios_logs/python_error.log 2>/dev/null && cat /tmp/ios_logs/python_error.log
```

### Checking App Installation

```bash
# List installed apps
ideviceinstaller list --user 2>&1 | grep -i ciris
# Output: ai.ciris.mobile, "1.0", "CIRIS"
```

## Architecture

```
mobile/iosApp/
├── iosApp/                    # Swift/ObjC code
│   ├── ContentView.swift      # SwiftUI shell + debug log viewer
│   ├── AppleSignInHelper.swift # Sign in with Apple implementation
│   ├── PythonBridge.swift     # Swift Python manager (sets CIRIS_IOS_FRAMEWORK_PATH)
│   ├── PythonInit.h/m         # ObjC Python C API bridge
│   └── Info.plist             # App configuration
├── scripts/
│   ├── prepare_python_bundle.sh    # Copy resources from BeeWare build
│   └── embed_native_frameworks.sh  # Copy/sign Python C extensions
├── Frameworks/                # Python.xcframework + CIRISVerify.xcframework
├── Resources/                 # Python stdlib, app, packages
│   ├── app/                   # CIRIS engine + adapters
│   │   └── ciris_adapters/ciris_verify/  # iOS adapter (8MB stack fix)
│   └── app_packages/          # Python packages
│       └── ciris_verify/      # Python bindings + fallback dylib
├── app_packages_native/       # Device-compiled .so files (iphoneos arm64)
│   ├── pydantic_core/         # _pydantic_core.cpython-310-iphoneos.so
│   ├── cryptography/          # _openssl.abi3.so, _padding.abi3.so
│   ├── aiohttp/               # _helpers, _http_parser, _http_writer, _websocket
│   └── _cffi_backend.cpython-310-iphoneos.so
├── Resources.zip              # Compressed Python bundle (re-extract = delete app first)
└── project.yml                # xcodegen configuration
```

## Build Process

### For Simulator

```bash
cd mobile/iosApp

# 1. Build KMP shared framework for simulator
cd ../.. && ./gradlew :shared:linkDebugFrameworkIosSimulatorArm64 && cd mobile/iosApp

# 2. Regenerate Xcode project
xcodegen generate

# 3. Build for simulator
xcodebuild -project iosApp.xcodeproj -scheme iosApp \
  -sdk iphonesimulator \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' \
  -quiet build

# 4. Install and launch on simulator
APP_PATH=$(find ~/Library/Developer/Xcode/DerivedData/iosApp-* \
  -name "iosApp.app" -path "*Debug-iphonesimulator*" | head -1)
xcrun simctl install booted "$APP_PATH"
xcrun simctl launch booted ai.ciris.mobile
```

### For Physical Device — CLI Build & Deploy (Preferred)

CLI builds work with the developer account configured in Xcode (Team `MHX9MGJ62V`):

```bash
DEVICE_ID="00008110-0016395C1ED9401E"  # Replace with actual device ID
cd mobile/iosApp

# 1. Build for device
xcodebuild -project iosApp.xcodeproj -scheme iosApp \
  -sdk iphoneos -configuration Debug \
  -destination 'generic/platform=iOS' \
  -allowProvisioningUpdates \
  -quiet build

# 2. Find the built app
APP_PATH=$(find ~/Library/Developer/Xcode/DerivedData/iosApp-* \
  -name "iosApp.app" -path "*Debug-iphoneos*" -not -path "*/Index.noindex/*" | head -1)

# 3. Install to device
xcrun devicectl device install app --device $DEVICE_ID "$APP_PATH"

# 4. Launch
xcrun devicectl device process launch --device $DEVICE_ID ai.ciris.mobile

# 5. Port forward to hit API
iproxy 18080 8080 -u $DEVICE_ID &
curl -s http://127.0.0.1:18080/v1/system/health | python3 -m json.tool
```

Or build via Xcode UI: Open `iosApp.xcodeproj`, select device, Cmd+R.

### Updating Python Bundle & Deploying

After changes to Python code (engine, adapters, ciris_verify bindings):

```bash
cd mobile/iosApp

# 1. Sync updated files to Resources/
#    - Engine:   cp ../../ciris_engine/path/to/file.py Resources/app/ciris_engine/path/to/file.py
#    - Verify:   cp ~/CIRISVerify/bindings/python/ciris_verify/*.py Resources/app_packages/ciris_verify/
#    - Adapter:  cp file Resources/app/ciris_adapters/ciris_verify/ (BUT preserve service.py 8MB fix!)

# 2. Rebuild Resources.zip
rm -f Resources.zip && cd Resources && zip -q -r ../Resources.zip . && cd ..

# 3. Bump build number in Info.plist (triggers re-extraction on device)
#    Increment CFBundleVersion (e.g., 50 → 51)

# 4. Build, install, launch (see CLI commands above)
```

## Sleep/Wake Recovery

The app implements automatic recovery from iOS background suspension:

### How It Works

1. **Swift side** (`ContentView.swift`):
   - Detects `scenePhase` change to `.active`
   - Checks if server is healthy via HTTP
   - If dead, writes `.restart_signal` file
   - Waits for Python to restart

2. **Python side** (`kmp_main.py`):
   - Watchdog thread runs OUTSIDE asyncio (won't freeze)
   - Monitors `.restart_signal` file every second
   - When detected: stops event loop via `call_soon_threadsafe`
   - Main loop restarts runtime with new event loop

3. **Signal files**:
   - `.restart_signal` - Swift writes, Python reads and deletes
   - `.server_ready` - Python writes when server is up

### Known Issues

**Event Loop Binding Bug**: After restart, asyncio.Event objects from previous loop cause:
```
RuntimeError: ... is bound to a different event loop
```

This happens in ShutdownService. Fix: Reset global asyncio state between iterations.

## Logging System

Python logs go to `~/Documents/ciris/logs/`:

- `kmp_runtime.log` - All runtime logs with phases
- `kmp_errors.log` - Errors only
- `runtime_status.json` - Current phase/status for Swift to read
- `startup_status.json` - Startup check results for KMP UI
- `incidents_*.log` - WARNING/ERROR level (check this first!)
- `ciris_agent_*.log` - Full agent log (very large)

### Log Phases

| Phase | Description |
|-------|-------------|
| EARLY_INIT | Before any imports |
| COMPAT_SHIMS | Loading crypto compatibility |
| ENVIRONMENT | Setting up iOS paths |
| STARTUP_CHECKS | Validating Python modules (6 checks) |
| RUNTIME_INIT | Creating CIRISRuntime + loading adapters |
| SERVICE_INIT | Initializing 22 services |
| SERVER | API server running on 127.0.0.1:8080 |
| SHUTDOWN | Graceful shutdown |

### In-App Log Viewer

Tap "View Logs" button on startup screen to see logs on-device without needing Xcode connection.

## Troubleshooting

### "No module named X" on startup

Native Python module missing. Check:
1. Module exists in `Frameworks/*.framework`
2. `embed_native_frameworks.sh` ran during build
3. Correct architecture (device vs simulator)
4. For device: check `app_packages_native/` has the `.so` file

### CIRISVerify "symbol not found" or "dlsym" error

The XCFramework contains a static archive instead of a dynamic library. Rebuild with `tools/update_ciris_verify.py --local`.

### CIRISVerify stack overflow (EXC_BAD_ACCESS SIGBUS)

The iOS `service.py` is missing the 8MB stack thread fix. Check that `threading.stack_size(8 * 1024 * 1024)` is in `initialize()`.

### CIRISVerify adapter not found in /v1/system/adapters

The `ciris_verify` Python package is missing from `Resources/app_packages/`. This means Resources.zip wasn't re-extracted. Bump `CFBundleVersion` in `Info.plist` and redeploy (or delete the app and reinstall).

### pydantic_core framework not found (device only)

The `app_packages_native/pydantic_core/_pydantic_core.cpython-310-iphoneos.so` file is missing. Copy from BeeWare build output or from `ios/CirisiOS/build/ciris_ios/ios/xcode/CirisiOS/app_packages.iphoneos/`.

### Server not responding after resume

Check for event loop binding errors in logs:
```bash
grep "different event loop" /tmp/ios_logs/incidents.log
```

### App stuck on "Starting server..."

Pull logs to check what phase failed:
```bash
xcrun devicectl device copy from --device $DEVICE_ID \
  --domain-type appDataContainer --domain-identifier ai.ciris.mobile \
  --source Documents/ciris/runtime_status.json \
  --destination /tmp/status.json && cat /tmp/status.json
```

## Status

- [x] Python runtime initialization
- [x] Resource extraction from zip
- [x] Native module frameworks (device + simulator)
- [x] Startup checks (6/6 pass)
- [x] Service initialization (22/22 services, 41/41 total)
- [x] API server running (port 8080)
- [x] Sign in with Apple integration
- [x] Restart signal mechanism (watchdog thread)
- [x] CIRISVerify XCFramework (dynamic)
- [x] CIRISVerify Python bindings v0.8.13 (attestation, Ed25519, audit trail)
- [x] CIRISVerify adapter with 8MB stack thread fix
- [x] CLI build & deploy pipeline (xcodebuild → devicectl install → devicectl launch)
- [x] 15/15 services healthy on device (build 50, 2026-02-24)
- [ ] Secure Enclave ECIES hardware-wrapped Ed25519 (CIRISVerify 0.8.11+ Rust side done, iOS build feature gate issue)
- [ ] Event loop binding fix for restart
- [ ] Full agent interaction after resume
