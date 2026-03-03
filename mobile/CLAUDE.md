# CIRIS Cross-Platform Client (Kotlin Multiplatform)

**NOTE: "mobile" is a misnomer.** This is a **cross-platform client** targeting:
- **Android** (phone, tablet)
- **iOS** (iPhone, iPad)
- **Windows** (x64)
- **macOS** (x64, arm64)
- **Linux** (x64, arm64, arm32)

## Architecture

The `shared/` module contains **95% of the code** and runs on ALL platforms:

```
shared/
├── commonMain/     # Cross-platform code (ALL platforms)
│   ├── api/        # Ktor HTTP client
│   ├── models/     # Data models
│   ├── viewmodels/ # Business logic (StartupViewModel, ChatViewModel, etc.)
│   ├── ui/         # Compose Multiplatform UI
│   └── platform/   # expect declarations (interfaces)
├── androidMain/    # Android actual implementations
├── iosMain/        # iOS actual implementations
└── desktopMain/    # Desktop actual implementations (Windows, macOS, Linux)
```

## Platform-Specific Code

Each platform has `actual` implementations for `expect` declarations:

| Feature | Android | iOS | Desktop |
|---------|---------|-----|---------|
| Python Runtime | Chaquopy | PythonKit | Subprocess |
| Secure Storage | EncryptedSharedPrefs | Keychain | keyring |
| Logging | Logcat | os_log | println |
| App Restart | ProcessPhoenix | exit(0) | System.exit |

## Console Output Parsing

The Python backend outputs status messages to stdout that drive UI animations:

```
[CIRISVerify] FFI init starting         → Verify step 1/8
[CIRISVerify] TPM: device nodes detected → Verify step 2/8
[CIRISVerify] LicenseEngine: init...     → Verify step 3/8
[CIRISVerify] Ed25519 signer init...     → Verify step 4/8
[CIRISVerify] DNS cross-check            → Verify step 5/8
[CIRISVerify] HTTPS query complete       → Verify step 6/8
[CIRISVerify] Binary check               → Verify step 7/8
[CIRISVerify] Unified attestation...     → Verify step 8/8

[SERVICE 1/22] STARTED                   → Service step 1/22
[SERVICE 2/22] STARTED                   → Service step 2/22
...
```

**Cross-platform parsing:**
- Android: Parse `python.stdout` via logcat
- iOS: Redirect stdout to callback
- Desktop: Read subprocess stdout

## Key ViewModels

- `StartupViewModel` - Manages startup sequence (verify, prep, services)
- `ChatViewModel` - Chat interaction with CIRIS
- `SettingsViewModel` - LLM configuration (CIRIS Proxy vs BYOK)
- `TrustViewModel` - Device attestation status

## Testing

```bash
# Shared unit tests (all platforms)
./gradlew :shared:allTests

# Android instrumented tests
./gradlew :androidApp:connectedAndroidTest

# Desktop tests
./gradlew :shared:desktopTest
```

## Build Targets

```bash
# Android APK
./gradlew :androidApp:assembleDebug

# iOS Framework
./gradlew :shared:assembleDebugXCFramework

# Desktop JAR (Windows/macOS/Linux)
./gradlew :desktopApp:packageDistributionForCurrentOS
```
