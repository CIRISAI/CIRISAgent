# Compose Multiplatform Web Migration Guide

## Overview

This document outlines what the agent team needs to do to compile the KMP shared UI to WebAssembly (Wasm), enabling the Compose UI to run directly in browsers and be served by the Python API adapter.

## Current State

### KMP Structure
```
mobile/
├── shared/                    # Compose Multiplatform shared code
│   └── src/
│       ├── commonMain/        # ✅ Shared UI code (SetupScreen.kt, etc.)
│       ├── androidMain/       # 12 actual implementations
│       └── iosMain/           # 12 actual implementations + StoreKit
├── androidApp/                # Android app shell
├── iosApp/                    # iOS app shell
└── generated-api/             # OpenAPI-generated API client
```

### API Adapter Static File Serving
The Python API adapter already supports serving static GUI files:

```python
# ciris_engine/logic/adapters/api/app.py:155-183
def _mount_gui_assets(app: FastAPI) -> None:
    gui_static_dir = package_root / "gui_static"

    if gui_static_dir.exists() and any(gui_static_dir.iterdir()):
        app.mount("/", StaticFiles(directory=str(gui_static_dir), html=True), name="gui")
```

Currently serves: `ciris_engine/gui_static/` (Next.js static export)

## Required `actual` Implementations for Web

### Full List (12 files)

From `androidMain/` and `iosMain/` - all need web equivalents:

| File | Purpose | Web Implementation |
|------|---------|-------------------|
| `Platform.wasmJs.kt` | Platform detection | Return `Platform.WEB` |
| `Logger.wasmJs.kt` | Logging | `console.log/warn/error()` |
| `PlatformLog.wasmJs.kt` | Diagnostic logging | `console` API |
| `SecureStorage.wasmJs.kt` | Token/key storage | `localStorage` (⚠️ not secure) |
| `DebugLogBuffer.wasmJs.kt` | Crash report log buffer | In-memory buffer, `Date.now()` |
| `PythonRuntime.wasmJs.kt` | Python runtime control | **No-op stub** (backend handles) |
| `AppRestarter.wasmJs.kt` | App restart | `window.location.reload()` |
| `EnvFileUpdater.wasmJs.kt` | Env file updates | **No-op stub** (no filesystem) |
| `NetworkDiagnostics.wasmJs.kt` | Network diagnostics | Fetch API checks |
| `PlatformHttp.wasmJs.kt` | HTTP client config | Ktor JS engine defaults |
| `AuthManager.wasmJs.kt` | **Authentication** | OAuth redirects or email/password |
| `FirstRunDetector.wasmJs.kt` | First run detection | `localStorage` flag |

### iOS-Only (Stub or Skip)

| File | Purpose | Web Strategy |
|------|---------|--------------|
| `StoreKit.ios.kt` | In-app purchases | **No-op stub** (no IAP on web, or future Stripe) |
| `ServerManagerPlatform.ios.kt` | Local server management | **No-op stub** |

## AuthManager Complexity

`AuthManager` is the most complex `actual` implementation. It handles:

- Username/password login
- Google OAuth (Android) / Apple Sign-In (iOS)
- Token storage and refresh
- Session persistence

### Web Strategy Options

**Option A: Email/Password Only (Simplest)**
```kotlin
// wasmJsMain/.../AuthManager.wasmJs.kt
actual class AuthManager {
    actual suspend fun login(username: String, password: String, serverUrl: String): Result<AuthResponse> {
        // Direct API call via Ktor
    }

    actual suspend fun loginWithGoogle(idToken: String, serverUrl: String): Result<AuthResponse> {
        return Result.failure(UnsupportedOperationException("Use email login on web"))
    }
}
```

**Option B: OAuth Redirect Flow (More work)**
- Implement popup/redirect OAuth flow
- Handle callback URL parsing
- Store tokens in `localStorage`

**Recommendation for parity**: Start with Option A (email/password only).

## Build Configuration Changes

### 1. Update Plugin Versions (`mobile/build.gradle.kts`)

```kotlin
plugins {
    kotlin("multiplatform").version("2.0.0")  // Was 1.9.22
    id("org.jetbrains.compose").version("1.9.0")  // Was 1.6.0
}
```

### 2. Add Wasm Target (`shared/build.gradle.kts`)

```kotlin
kotlin {
    // Existing targets
    androidTarget { ... }
    listOf(iosX64(), iosArm64(), iosSimulatorArm64()).forEach { ... }

    // NEW: Wasm target
    @OptIn(ExperimentalWasmDsl::class)
    wasmJs {
        browser {
            commonWebpackConfig {
                outputFileName = "ciris-gui.js"
            }
        }
        binaries.executable()
    }

    sourceSets {
        val commonMain by getting { ... }

        // NEW: Web source set
        val wasmJsMain by getting {
            dependencies {
                implementation("io.ktor:ktor-client-js:2.3.7")
            }
        }
    }
}
```

### 3. Update Platform Enum

```kotlin
// commonMain/.../Platform.kt
enum class Platform {
    ANDROID,
    IOS,
    WEB  // NEW
}

fun getOAuthProviderName(): String = when (getPlatform()) {
    Platform.IOS -> "Apple"
    Platform.ANDROID -> "Google"
    Platform.WEB -> "Email"  // No OAuth on web initially
}
```

## Source Set Structure

Create:
```
shared/src/wasmJsMain/
└── kotlin/
    └── ai/ciris/mobile/shared/
        ├── auth/
        │   ├── AuthManager.wasmJs.kt
        │   └── FirstRunDetector.wasmJs.kt
        ├── diagnostics/
        │   └── PlatformLog.wasmJs.kt
        ├── platform/
        │   ├── AppRestarter.wasmJs.kt
        │   ├── DebugLogBuffer.wasmJs.kt
        │   ├── EnvFileUpdater.wasmJs.kt
        │   ├── Logger.wasmJs.kt
        │   ├── NetworkDiagnostics.wasmJs.kt
        │   ├── Platform.wasmJs.kt
        │   ├── PlatformHttp.wasmJs.kt
        │   ├── PythonRuntime.wasmJs.kt
        │   └── SecureStorage.wasmJs.kt
        └── Main.wasmJs.kt  # Entry point
```

## Build & Deploy

```bash
# Build Wasm distribution
cd mobile
./gradlew :shared:wasmJsBrowserDistribution

# Output location
ls shared/build/dist/wasmJs/productionExecutable/
# → ciris-gui.js, ciris-gui.wasm, index.html

# Deploy to API adapter
cp -r shared/build/dist/wasmJs/productionExecutable/* \
      ../ciris_engine/gui_static/
```

## Effort Estimate (Realistic)

| Task | Effort |
|------|--------|
| Update plugin versions | 1-2 hours |
| Add wasmJs target to build.gradle.kts | 1-2 hours |
| Create wasmJsMain source set structure | 1 hour |
| Implement platform actuals (9 simple) | 6-8 hours |
| Implement AuthManager (complex) | 4-8 hours |
| Implement FirstRunDetector | 1 hour |
| Update Platform enum | 30 min |
| Create Main.wasmJs.kt entry point | 1-2 hours |
| Test in browser | 4-8 hours |
| Debug and fix issues | 4-8 hours |
| Integrate with API adapter | 2 hours |
| **Total** | **3-5 days** |

## Browser Compatibility

All major browsers now support WasmGC:
- Chrome 119+ ✅
- Firefox 120+ ✅
- Safari 18+ ✅ (Dec 2024)
- Edge 119+ ✅

Compose Multiplatform 1.9.0 includes Kotlin/JS fallback for older browsers.

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Beta status | Compose for Web is Beta; expected stable Q4 2025 |
| Bundle size | Wasm is larger initially; lazy loading can help |
| localStorage not secure | Document this; tokens are not encrypted |
| OAuth complexity | Start with email/password only |

## References

- [Compose Multiplatform 1.9.0 Release](https://blog.jetbrains.com/kotlin/2025/09/compose-multiplatform-1-9-0-compose-for-web-beta/)
- [Kotlin/Wasm Getting Started](https://kotlinlang.org/docs/wasm-get-started.html)
- [Official Wasm Template](https://github.com/Kotlin/kotlin-wasm-compose-template)
- [KMP Roadmap Aug 2025](https://blog.jetbrains.com/kotlin/2025/08/kmp-roadmap-aug-2025/)
