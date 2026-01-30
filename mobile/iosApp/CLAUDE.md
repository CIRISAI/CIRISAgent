# iOS KMP App - Claude Development Notes

## Overview

This is the Kotlin Multiplatform (KMP) iOS app for CIRIS. It uses Compose Multiplatform for UI and embeds a Python runtime to run the CIRIS backend.

## Architecture

```
mobile/iosApp/
├── iosApp/                    # Swift/ObjC code
│   ├── ContentView.swift      # SwiftUI shell that hosts Compose + Apple Sign-In bridge
│   ├── AppleSignInHelper.swift # Sign in with Apple implementation
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

Two components can cause this:
1. **Toga**: Using `ciris_ios` module directly instead of `ciris_ios.kmp_main`. The latter bypasses Toga's signal handling.
2. **Uvicorn**: The API adapter has a fix that calls `_serve()` directly on iOS to bypass uvicorn's signal handling wrapper. This is in `ciris_engine/logic/adapters/api/adapter.py`.

The uvicorn fix was added because Python runs on a background thread in KMP (the Compose UI owns the main thread), but the threading module incorrectly identifies this as the main thread.

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
| CIRIS Source | From BeeWare build | Overlaid from main repo |

## Important: Source Overlay

The `prepare_python_bundle.sh` script overlays the latest `ciris_engine/` and `ciris_adapters/` from the main CIRISAgent repo over the BeeWare build. This ensures any fixes in the main repo (like the uvicorn signal handler fix) are included without requiring a full BeeWare rebuild.

If you make changes to the CIRIS engine:
1. Changes in `/Users/macmini/CIRISAgent/ciris_engine/` will be included on next bundle preparation
2. Run `./scripts/prepare_python_bundle.sh` to update the Resources/
3. Regenerate Resources.zip: `cd Resources && zip -q -r ../Resources.zip . && cd ..`
4. Rebuild the app

## Authentication

### Sign in with Apple

The app uses Sign in with Apple for iOS authentication:

1. **AppleSignInHelper.swift** - Handles ASAuthorizationController flow
2. **ContentView.swift** - Bridges Apple credentials to Kotlin via `AppleSignInResultBridge`
3. **Main.ios.kt** - Kotlin bridge that converts to `NativeSignInResult`
4. **CIRISApp.kt** - Exchanges Apple ID token for CIRIS access token via `/v1/auth/native/apple`

Token refresh is provider-aware - the `TokenManager` tracks whether the user signed in with Apple or Google and calls the correct endpoint on refresh.

### Token Flow

```
Apple Sign-In → identityToken (JWT) → /v1/auth/native/apple → CIRIS access token → Keychain
```

The CIRIS access token is stored in iOS Keychain via `SecureStorage.ios.kt`.

## Status

- [x] Python runtime initialization
- [x] Resource extraction from zip
- [x] Native module frameworks
- [x] Startup checks (6/6 pass)
- [x] Service initialization completes (22/22 services)
- [x] Full runtime startup (CIRIS engine)
- [x] API server running (setup wizard accessible)
- [x] Sign in with Apple integration
- [x] Apple ID token → CIRIS token exchange
- [x] Secure token storage (Keychain)
- [x] Provider-aware token refresh
- [x] Compose UI integration with API
- [x] Navigation to Interact screen after auth
- [ ] Full agent interaction flow
- [ ] Billing/LLM integration (requires backend token configuration)
