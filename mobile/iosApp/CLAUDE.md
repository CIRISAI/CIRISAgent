# iOS KMP App - Claude Development Notes

## Overview

This is the Kotlin Multiplatform (KMP) iOS app for CIRIS. It uses Compose Multiplatform for UI and embeds a Python runtime to run the CIRIS backend.

## Architecture

```
mobile/iosApp/
├── iosApp/                    # Swift/ObjC code
│   ├── ContentView.swift      # SwiftUI shell that hosts Compose
│   ├── PythonBridge.swift     # Swift Python manager (extraction, init)
│   ├── PythonInit.h/m         # ObjC Python C API bridge
│   └── Info.plist             # App configuration
├── scripts/
│   ├── prepare_python_bundle.sh    # Copy resources from BeeWare build
│   └── embed_native_frameworks.sh  # Copy/sign Python C extensions
├── Frameworks/                # Python.xcframework + native extensions
├── Resources/                 # Extracted Python stdlib, app, packages
├── Resources.zip              # Compressed bundle (built from Resources/)
└── project.yml                # xcodegen configuration
```

## Build Process

### Prerequisites

1. BeeWare build of iOS Python runtime:
   ```bash
   cd /Users/macmini/CIRISAgent/ios
   briefcase build iOS
   ```

2. KMP shared framework:
   ```bash
   cd /Users/macmini/CIRISAgent/mobile
   ./gradlew :shared:linkDebugFrameworkIosSimulatorArm64
   ```

### Building the iOS App

```bash
cd mobile/iosApp

# 1. Prepare Python bundle from BeeWare build
./scripts/prepare_python_bundle.sh

# 2. Create Resources.zip (avoids code signing 5000+ files)
rm -f Resources.zip && cd Resources && zip -q -r ../Resources.zip . && cd ..

# 3. Regenerate Xcode project
xcodegen generate

# 4. Build
xcodebuild -project iosApp.xcodeproj -scheme iosApp -sdk iphonesimulator \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' build
```

### Running on Simulator

```bash
# Boot simulator (use ID from `xcrun simctl list devices`)
xcrun simctl boot B5DF0392-A42D-4C86-BE28-CAA456D00665

# Install
xcrun simctl install booted \
  ~/Library/Developer/Xcode/DerivedData/iosApp-*/Build/Products/Debug-iphonesimulator/iosApp.app

# Launch
xcrun simctl launch booted ai.ciris.mobile

# View logs
xcrun simctl spawn booted log show --last 30s --predicate 'process == "iosApp"'
```

## Key Components

### PythonBridge.swift

Manages Python runtime lifecycle:
- Extracts `Resources.zip` to Documents/PythonResources on first launch
- Initializes Python via `PythonInit` (ObjC bridge)
- Starts CIRIS runtime in background thread
- Provides health check endpoint monitoring

### PythonInit.m

ObjC bridge to Python C API:
- `PyPreConfig_InitIsolatedConfig` - Configure isolated Python
- `Py_InitializeFromConfig` - Initialize with custom paths
- `runpy._run_module_as_main` - Run entry point module

### kmp_main.py

KMP-specific entry point that bypasses Toga (which requires main thread):
```python
# ciris_ios/kmp_main.py
from ciris_ios.ios_main import run_startup_checks, setup_ios_environment, start_mobile_runtime

if run_startup_checks():
    setup_ios_environment()
    asyncio.run(start_mobile_runtime())
```

### Resources.zip Structure

```
Resources.zip
├── python/           # Python stdlib (43MB)
│   └── lib/python3.10/
├── app/              # CIRIS source (10MB)
│   ├── ciris_engine/
│   ├── ciris_ios/
│   └── ciris_sdk/
└── app_packages/     # Third-party packages (28MB)
```

**Important**: Web GUI (ios_gui_static, gui_static) is excluded - it's not needed for mobile.

## Native Module Frameworks

Python C extensions are compiled as individual `.framework` files by BeeWare. These are copied to `Frameworks/` and embedded in the app bundle by `embed_native_frameworks.sh`.

76 frameworks including: `_struct`, `_json`, `_ssl`, `_hashlib`, `_sqlite3`, etc.

## Troubleshooting

### "Python stdlib not found"

The zip extraction may have failed or extracted to wrong path. Check:
```bash
xcrun simctl spawn booted log show --last 30s --predicate 'process == "iosApp"' | grep PythonBridge
```

### "Module not found" errors

C extension frameworks missing. Ensure:
1. `./scripts/prepare_python_bundle.sh` ran successfully
2. `Frameworks/` contains `*.framework` files
3. Rebuild with `xcodegen generate && xcodebuild ...`

### "signal only works in main thread"

Using `ciris_ios` module directly instead of `ciris_ios.kmp_main`. The latter bypasses Toga's signal handling.

### Service initialization failures

Check CIRIS runtime logs:
```bash
xcrun simctl spawn booted log show --last 1m --predicate 'process == "iosApp"' | grep SERVICE
```

Incident log location: `Documents/ciris/logs/incidents_latest.log`

## Differences from BeeWare Build

| Aspect | BeeWare | KMP |
|--------|---------|-----|
| UI Framework | Toga (Python) | Compose (Kotlin) |
| Python Entry | ciris_ios module | ciris_ios.kmp_main |
| Resources | Loose files | Resources.zip |
| Native Extensions | Auto-embedded | embed_native_frameworks.sh |

## Status

- [x] Python runtime initialization
- [x] Resource extraction from zip
- [x] Native module frameworks
- [x] Startup checks (6/6 pass)
- [x] Service initialization starts
- [ ] Full runtime startup (CIRIS engine issue)
- [ ] Compose UI integration
