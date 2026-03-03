# CIRIS Cross-Platform Client - Kotlin Multiplatform

**Cross-platform CIRIS client for Android, iOS, Windows, macOS, and Linux** using Kotlin Multiplatform + Compose Multiplatform.

> **Note:** The directory is named "mobile" for historical reasons, but this is a **cross-platform** codebase targeting all major platforms.

## Quick Start

### Prerequisites
- JDK 17
- Android SDK 34+
- Python 3.10 (for Chaquopy)
- Xcode 15+ (for iOS)

### Build Android
```bash
cd mobile
./gradlew :androidApp:assembleDebug
adb install androidApp/build/outputs/apk/debug/androidApp-debug.apk
```

### Build iOS
```bash
cd mobile
./gradlew :shared:assembleDebugXCFramework
cd iosApp
xcodebuild -workspace iosApp.xcworkspace -scheme iosApp
```

### Run Tests
```bash
./gradlew :shared:test                # Shared unit tests
./gradlew :androidApp:connectedTest   # Android instrumented tests
```

## Architecture

```
shared/
├── commonMain/     # 95% of code - shared Android + iOS
│   ├── api/        # Ktor API client
│   ├── models/     # Data models
│   ├── viewmodels/ # Business logic
│   └── ui/         # Compose Multiplatform UI
├── androidMain/    # Android-specific (5%)
└── iosMain/        # iOS-specific (5%)
```

## Features

- ✅ Chat interface (native performance)
- ✅ Real-time status monitoring
- ⏳ Settings management
- ⏳ Purchase flow (Google Play + App Store)
- ⏳ Setup wizard
- ⏳ Runtime monitoring (22 services)

## Documentation

See [MIGRATION_PLAN.md](./MIGRATION_PLAN.md) for full migration guide.

## License

AGPL 3.0 (same as main CIRIS project)
