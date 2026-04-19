# KMP 2.x Migration Guide

**Migration Path**: Kotlin 1.9.22 → 2.0.21 | Compose 1.6.0 → 1.7.1 | AGP 8.1.0 → 8.5.2

This guide documents the migration process, lessons learned, and gotchas discovered during the CIRISHome WASM deployment.

---

## Quick Start

```bash
# 1. Validate migration readiness
./scripts/validate-kmp2-migration.sh --verbose

# 2. Auto-fix safe issues
./scripts/validate-kmp2-migration.sh --fix

# 3. Run migration (creates backups)
./scripts/migrate-to-kmp2.sh

# 4. Verify builds
./gradlew :shared:compileKotlinWasmJs
./gradlew :androidApp:assembleDebug
```

---

## Compatibility Matrix

| Component | Current | Target | Notes |
|-----------|---------|--------|-------|
| **Kotlin** | 1.9.22 | 2.0.21 | New compose compiler architecture |
| **Compose Multiplatform** | 1.6.0 | 1.7.1 | WASM Beta support |
| **Android Gradle Plugin** | 8.1.0 | 8.5.2 | Required for Kotlin 2.x |
| **Gradle** | 8.2 | 8.7+ | Required for AGP 8.5+ |
| **Chaquopy** | 17.0.0 | 17.0.0 | Already compatible! |
| **arm32 (armeabi-v7a)** | ✅ | ✅ | Maintained via Chaquopy |

---

## What Changes

### Build Configuration

```kotlin
// OLD (Kotlin 1.9.x)
plugins {
    kotlin("multiplatform").version("1.9.22")
    id("org.jetbrains.compose").version("1.6.0")
}

// NEW (Kotlin 2.x)
plugins {
    kotlin("multiplatform").version("2.0.21")
    kotlin("plugin.compose").version("2.0.21")  // NEW - required!
    id("org.jetbrains.compose").version("1.7.1")
}
```

### Compiler Options Syntax

```kotlin
// OLD
kotlinOptions {
    jvmTarget = "17"
}

// NEW
compilerOptions {
    jvmTarget.set(JvmTarget.JVM_17)
}
```

### Compose Compiler Extension

```kotlin
// OLD - REMOVE THIS
composeOptions {
    kotlinCompilerExtensionVersion = "1.5.8"
}

// NEW - Managed by kotlin("plugin.compose")
// No explicit version needed
```

---

## New Target: wasmJs

The migration adds a new compilation target for web browsers via WebAssembly.

### Source Set Structure

```
shared/src/
├── commonMain/          # 95%+ of code (unchanged)
├── androidMain/         # Android-specific
├── iosMain/             # iOS-specific
├── desktopMain/         # Desktop (JVM)
└── wasmJsMain/          # NEW - Web/WASM specific
    └── kotlin/
        └── ai/ciris/mobile/shared/
            ├── platform/
            │   ├── Platform.wasmJs.kt
            │   ├── SecureStorage.wasmJs.kt
            │   ├── PythonRuntime.wasmJs.kt
            │   └── ...
            ├── auth/
            └── ui/components/
```

### Platform Enum

```kotlin
enum class Platform {
    ANDROID,
    IOS,
    DESKTOP,
    WEB      // NEW
}
```

---

## Critical Gotchas

### 1. Dispatchers.IO Not Available in WASM

```kotlin
// ❌ BREAKS in wasmJs
withContext(Dispatchers.IO) { ... }

// ✅ WORKS everywhere
withContext(Dispatchers.Default) { ... }
```

**Fix**: The migration script automatically replaces `Dispatchers.IO` with `Dispatchers.Default`.

### 2. Missing `override` Causes Silent ClassCastException

This is the **#1 cause of mysterious WASM crashes**.

```kotlin
// ❌ COMPILES but CRASHES at runtime in WASM
actual class PythonRuntime : PythonRuntimeProtocol {
    actual fun initialize(): Result<Unit> = ...  // Missing override!
}

// ✅ WORKS
actual class PythonRuntime : PythonRuntimeProtocol {
    actual override fun initialize(): Result<Unit> = ...  // Has override!
}
```

**Why**: Kotlin/WASM strictly enforces interface contracts at runtime. Missing `override` compiles but throws `ClassCastException` when casting to the interface type.

**Symptom**: Cryptic `[object WebAssembly.Exception]` with no stack trace.

### 3. Platform.WEB in when() Expressions

```kotlin
// ❌ NON-EXHAUSTIVE in Kotlin 2.x with WEB target
when (getPlatform()) {
    Platform.ANDROID -> ...
    Platform.IOS -> ...
    Platform.DESKTOP -> ...
    // Missing Platform.WEB!
}

// ✅ EXHAUSTIVE
when (getPlatform()) {
    Platform.ANDROID -> ...
    Platform.IOS -> ...
    Platform.DESKTOP -> ...
    Platform.WEB -> ...  // Or use 'else ->'
}
```

### 4. Reflection Limitations

```kotlin
// ⚠️ WORKS but increases binary size
val name = MyClass::class.qualifiedName

// ⚠️ LIMITED - reflection is minimal in WASM
val members = MyClass::class.members  // May not work
```

**Best Practice**: Use sealed classes instead of reflection for type discrimination.

### 5. Okio Not Supported

```kotlin
// ❌ NOT AVAILABLE in wasmJs
import okio.FileSystem
import okio.Path

// ✅ ALTERNATIVE - use Ktor or browser APIs
import io.ktor.client.*
import kotlinx.browser.localStorage
```

### 6. Font/Emoji Rendering

WASM uses Skia to render on canvas - it doesn't use browser fonts!

```kotlin
// ❌ Emojis render as "tofu" boxes
Text("🛡️")

// ✅ Use Material Icons instead
Icon(Icons.Default.Shield, contentDescription = "Shield")

// ✅ Or bundle fonts via composeResources
// shared/src/commonMain/composeResources/font/NotoEmoji-Regular.ttf
```

### 7. Canvas Loading Timing

WASM takes 2-3+ seconds to initialize. Don't hide loading screens too early!

```javascript
// ❌ BAD - checks once after 1 second
setTimeout(() => hideLoading(), 1000);

// ✅ GOOD - polls until canvas is ready
const poll = setInterval(() => {
    const canvas = document.querySelector('canvas');
    if (canvas && canvas.width > 300) {
        hideLoading();
        clearInterval(poll);
    }
}, 200);
```

---

## Performance Optimizations

### Binaryen (Automatic in Kotlin 2.0+)

Production builds automatically use Binaryen optimization:
- **20% faster** runtime performance
- **24% smaller** compressed .wasm size

### Custom Binaryen Flags

```kotlin
// build.gradle.kts - for aggressive optimization
tasks.withType<org.jetbrains.kotlin.gradle.targets.js.binaryen.BinaryenExec> {
    binaryenArgs = mutableListOf(
        "--enable-gc",
        "--enable-reference-types",
        "--enable-exception-handling",
        "--enable-bulk-memory",
        "--inline-functions-with-loops",
        "--traps-never-happen",
        "--fast-math",
        "-O3", "-Oz"
    )
}
```

### Incremental Compilation

```properties
# gradle.properties - 2x faster dev builds
kotlin.incremental.wasm=true
```

---

## Browser Compatibility

| Browser | Minimum Version | Notes |
|---------|-----------------|-------|
| Chrome/Chromium | 119+ | Full support |
| Firefox | 120+ | Full support |
| Safari | 18.2+ | WasmGC added Dec 2024 |
| Edge | 119+ | Chromium-based |

### Compatibility Mode (Compose 1.9.0+)

```kotlin
// New webMain source set - single actual for both JS and WASM
// Modern browsers → WASM (fast)
// Older browsers → JS fallback (slower but works)
```

---

## Testing After Migration

### 1. WASM Compilation

```bash
./gradlew :shared:compileKotlinWasmJs
```

### 2. WASM Dev Server

```bash
./gradlew :webApp:wasmJsBrowserDevelopmentRun
# Open http://localhost:8080
```

### 3. Android Build (including arm32)

```bash
./gradlew :androidApp:assembleDebug

# Test on arm32 device (SM-J700T)
adb -s 330016f5b40463cd install -r androidApp/build/outputs/apk/debug/androidApp-debug.apk
```

### 4. Desktop Build

```bash
./gradlew :desktopApp:run
```

---

## Debugging WASM Issues

### Enable Source Maps

```kotlin
// build.gradle.kts
wasmJs {
    browser {
        commonWebpackConfig {
            devtool = "source-map"
        }
    }
}
```

### Browser DevTools

1. Open DevTools (F12)
2. Go to Sources tab
3. Find Kotlin sources under `webpack://`
4. Set breakpoints in .kt files

### Exception Debugging (Kotlin 2.2.20+)

```kotlin
// Improved exception messages in newer Kotlin
// Exceptions thrown from Kotlin can be caught as JS errors
// WebAssembly.JSTag support for better error propagation
```

---

## Rollback Procedure

If migration fails:

```bash
# Restore backup files
find . -name "*.bak" -exec sh -c 'mv "$1" "${1%.bak}"' _ {} \;

# Or use git
git checkout -- .
```

---

## Reference Projects

| Project | URL | What to Learn |
|---------|-----|---------------|
| KotlinConf App | [github.com/JetBrains/kotlinconf-app](https://github.com/JetBrains/kotlinconf-app) | Full 4-platform architecture |
| Compose Multiplatform | [github.com/JetBrains/compose-multiplatform](https://github.com/JetBrains/compose-multiplatform) | Official examples |
| WASM Template | [github.com/Kotlin/kotlin-wasm-compose-template](https://github.com/Kotlin/kotlin-wasm-compose-template) | Minimal WASM setup |
| kmp-awesome | [github.com/terrakok/kmp-awesome](https://github.com/terrakok/kmp-awesome) | Library ecosystem |

---

## Sources

- [Kotlin/Wasm Documentation](https://kotlinlang.org/docs/wasm-overview.html)
- [Compose Multiplatform 1.7.1 Release](https://blog.jetbrains.com/kotlin/2025/09/compose-multiplatform-1-9-0-compose-for-web-beta/)
- [Kotlin 2.0 Migration Guide](https://kotlinlang.org/docs/compose-compiler-migration-guide.html)
- [Chaquopy Changelog](https://chaquo.com/chaquopy/doc/current/changelog.html)
- [Binaryen GC Optimization](https://github.com/WebAssembly/binaryen/wiki/GC-Optimization-Guidebook)

---

## Changelog

- **2025-04-19**: Initial migration guide created from CIRISHome lessons learned
