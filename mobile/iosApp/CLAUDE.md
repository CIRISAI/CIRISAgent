# iOS KMP App - Claude Development Notes

## Overview

This is the Kotlin Multiplatform (KMP) iOS app for CIRIS. It uses Compose Multiplatform for UI and embeds a Python runtime to run the CIRIS backend.

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
| `Documents/ciris/logs/kmp_runtime.log` | Main KMP/Python runtime log |
| `Documents/ciris/logs/kmp_errors.log` | Errors only |
| `Documents/ciris/logs/incidents_*.log` | CIRIS incident logs |
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

# Get recent runtime log
xcrun devicectl device copy from --device $DEVICE_ID \
  --domain-type appDataContainer --domain-identifier $BUNDLE_ID \
  --source Documents/ciris/logs/kmp_runtime.log \
  --destination /tmp/ios_logs/runtime.log && tail -100 /tmp/ios_logs/runtime.log

# Check for Python errors
xcrun devicectl device copy from --device $DEVICE_ID \
  --domain-type appDataContainer --domain-identifier $BUNDLE_ID \
  --source Documents/python_error.log \
  --destination /tmp/ios_logs/python_error.log 2>/dev/null && cat /tmp/ios_logs/python_error.log

# Check crash reports
mkdir -p /tmp/ios_crashes
idevicecrashreport -k -u $DEVICE_ID /tmp/ios_crashes
find /tmp/ios_crashes -name "*.ips" -o -name "*.crash" 2>/dev/null
```

### System Log (Limited)

iOS restricts syslog access. This may not show app logs:

```bash
# Try to get syslog (may be empty)
idevicesyslog -u $DEVICE_ID 2>&1 | grep -i "iosApp\|ciris" | head -50
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
│   ├── PythonBridge.swift     # Swift Python manager
│   ├── PythonInit.h/m         # ObjC Python C API bridge
│   └── Info.plist             # App configuration
├── scripts/
│   ├── prepare_python_bundle.sh    # Copy resources from BeeWare build
│   └── embed_native_frameworks.sh  # Copy/sign Python C extensions
├── Frameworks/                # Python.xcframework + native extensions
├── Resources/                 # Python stdlib, app, packages
├── Resources.zip              # Compressed bundle
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

### For Physical Device

Build via Xcode (requires signing):

1. Open `iosApp.xcodeproj` in Xcode
2. Select your device as target
3. Cmd+R to build and run

Or via command line (if provisioning is set up):

```bash
xcodebuild -project iosApp.xcodeproj -scheme iosApp \
  -sdk iphoneos -configuration Debug \
  -destination 'generic/platform=iOS' \
  DEVELOPMENT_TEAM=T7HP5J7U87 \
  -allowProvisioningUpdates \
  -quiet build
```

### Updating Python Bundle

After changes to Python code:

```bash
# 1. Copy updated files to Resources
cp /path/to/updated/*.py Resources/app/ciris_ios/

# 2. Recreate zip
rm -f Resources.zip && cd Resources && zip -q -r ../Resources.zip . && cd ..

# 3. Bump version in Info.plist
# Edit CFBundleVersion

# 4. Regenerate project and build
xcodegen generate
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

### Log Phases

| Phase | Description |
|-------|-------------|
| EARLY_INIT | Before any imports |
| COMPAT_SHIMS | Loading crypto compatibility |
| ENVIRONMENT | Setting up iOS paths |
| STARTUP_CHECKS | Validating Python modules |
| RUNTIME_INIT | Creating CIRISRuntime |
| SERVICE_INIT | Initializing 22 services |
| SERVER | API server running |
| SHUTDOWN | Graceful shutdown |

### In-App Log Viewer

Tap "View Logs" button on startup screen to see logs on-device without needing Xcode connection.

## Troubleshooting

### "No module named X" on startup

Native Python module missing. Check:
1. Module exists in `Frameworks/*.framework`
2. `embed_native_frameworks.sh` ran during build
3. Correct architecture (device vs simulator)

### Server not responding after resume

Check for event loop binding errors in logs:
```bash
grep "different event loop" /tmp/ios_logs/incidents.log
```

### App stuck on "Starting server..."

Pull logs to check what phase failed:
```bash
# Check runtime status
xcrun devicectl device copy from --device $DEVICE_ID \
  --domain-type appDataContainer --domain-identifier ai.ciris.mobile \
  --source Documents/ciris/runtime_status.json \
  --destination /tmp/status.json && cat /tmp/status.json
```

## Status

- [x] Python runtime initialization
- [x] Resource extraction from zip
- [x] Native module frameworks
- [x] Startup checks (6/6 pass)
- [x] Service initialization (22/22 services)
- [x] API server running
- [x] Sign in with Apple integration
- [x] Restart signal mechanism (watchdog thread)
- [ ] Event loop binding fix for restart
- [ ] Full agent interaction after resume
