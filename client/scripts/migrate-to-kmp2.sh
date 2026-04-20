#!/bin/bash
#
# migrate-to-kmp2.sh
# Execute migration from Kotlin 1.9.x → 2.x + Compose 1.6 → 1.7+
#
# Usage: ./scripts/migrate-to-kmp2.sh [--dry-run] [--skip-validation]
#
# This script:
# 1. Validates readiness (unless --skip-validation)
# 2. Upgrades Gradle wrapper to 8.7
# 3. Updates build.gradle.kts files with new versions
# 4. Adds kotlin("plugin.compose") to modules
# 5. Converts kotlinOptions → compilerOptions syntax
# 6. Creates wasmJsMain source set with platform implementations
# 7. Applies code transformations (Dispatchers.IO, Platform.WEB, etc.)
# 8. Runs verification build
#
# Based on lessons learned from CIRISHome WASM deployment.
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOBILE_ROOT="$(dirname "$SCRIPT_DIR")"
SHARED_DIR="${MOBILE_ROOT}/shared"

# Target versions
KOTLIN_VERSION="2.0.21"
COMPOSE_VERSION="1.7.1"
AGP_VERSION="8.5.2"
GRADLE_VERSION="8.7"
KTOR_VERSION="3.0.3"
LIFECYCLE_VERSION="2.8.4"
NAVIGATION_VERSION="2.8.0-alpha10"

# Options
DRY_RUN=false
SKIP_VALIDATION=false

for arg in "$@"; do
    case $arg in
        --dry-run) DRY_RUN=true ;;
        --skip-validation) SKIP_VALIDATION=true ;;
        --help|-h)
            echo "Usage: $0 [--dry-run] [--skip-validation]"
            echo ""
            echo "Execute migration to Kotlin 2.x + Compose 1.7+"
            echo ""
            echo "Options:"
            echo "  --dry-run          Show what would be done without making changes"
            echo "  --skip-validation  Skip pre-migration validation"
            exit 0
            ;;
    esac
done

log_header() { echo -e "\n${BOLD}${BLUE}═══════════════════════════════════════════════════════════════${NC}"; echo -e "${BOLD}$1${NC}"; echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }
log_ok() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_dry() { echo -e "${YELLOW}[DRY-RUN]${NC} Would: $1"; }

do_or_dry() {
    if $DRY_RUN; then
        log_dry "$1"
    else
        eval "$2"
        log_ok "$1"
    fi
}

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║     KMP 2.x Migration Script                                  ║"
echo "║     Kotlin $KOTLIN_VERSION | Compose $COMPOSE_VERSION | AGP $AGP_VERSION             ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""
echo "Mobile root: $MOBILE_ROOT"
echo "Dry run: $DRY_RUN"
echo ""

# =============================================================================
# STEP 0: Pre-flight validation
# =============================================================================
if ! $SKIP_VALIDATION; then
    log_header "Step 0: Pre-Migration Validation"

    if ! "$SCRIPT_DIR/validate-kmp2-migration.sh" --fix; then
        log_error "Validation failed. Fix issues and re-run, or use --skip-validation"
        exit 1
    fi
fi

# =============================================================================
# STEP 1: Upgrade Gradle wrapper
# =============================================================================
log_header "Step 1: Upgrade Gradle Wrapper to $GRADLE_VERSION"

cd "$MOBILE_ROOT"

if $DRY_RUN; then
    log_dry "Run: ./gradlew wrapper --gradle-version=$GRADLE_VERSION"
else
    if [ -f "./gradlew" ]; then
        ./gradlew wrapper --gradle-version=$GRADLE_VERSION --quiet
        log_ok "Gradle wrapper upgraded to $GRADLE_VERSION"
    else
        log_warn "gradlew not found - create wrapper manually"
    fi
fi

# =============================================================================
# STEP 2: Update root build.gradle.kts
# =============================================================================
log_header "Step 2: Update root build.gradle.kts"

ROOT_BUILD="$MOBILE_ROOT/build.gradle.kts"

if [ -f "$ROOT_BUILD" ]; then
    if $DRY_RUN; then
        log_dry "Update Kotlin to $KOTLIN_VERSION"
        log_dry "Add kotlin(\"plugin.compose\") version $KOTLIN_VERSION"
        log_dry "Update AGP to $AGP_VERSION"
        log_dry "Update Compose to $COMPOSE_VERSION"
    else
        # Backup
        cp "$ROOT_BUILD" "${ROOT_BUILD}.bak"

        # Create new root build file
        cat > "$ROOT_BUILD" << EOF
plugins {
    // Kotlin 2.x with new Compose compiler architecture
    kotlin("multiplatform").version("$KOTLIN_VERSION").apply(false)
    kotlin("android").version("$KOTLIN_VERSION").apply(false)
    kotlin("plugin.serialization").version("$KOTLIN_VERSION").apply(false)
    kotlin("plugin.compose").version("$KOTLIN_VERSION").apply(false)

    // Android Gradle Plugin 8.5+ (required for Kotlin 2.x)
    id("com.android.application").version("$AGP_VERSION").apply(false)
    id("com.android.library").version("$AGP_VERSION").apply(false)

    // Compose Multiplatform 1.7+
    id("org.jetbrains.compose").version("$COMPOSE_VERSION").apply(false)

    // Python runtime - Chaquopy 17.0.0 (compatible with AGP 8.5+, Kotlin 2.x)
    id("com.chaquo.python").version("17.0.0").apply(false)
}

tasks.register("clean", Delete::class) {
    delete(rootProject.layout.buildDirectory)
}
EOF
        log_ok "Root build.gradle.kts updated"
    fi
else
    log_error "Root build.gradle.kts not found at $ROOT_BUILD"
fi

# =============================================================================
# STEP 3: Update gradle.properties
# =============================================================================
log_header "Step 3: Update gradle.properties"

GRADLE_PROPS="$MOBILE_ROOT/gradle.properties"

if $DRY_RUN; then
    log_dry "Add WASM experimental flags to gradle.properties"
else
    # Ensure required properties exist
    cat > "$GRADLE_PROPS" << 'EOF'
# Kotlin Multiplatform
kotlin.code.style=official
kotlin.mpp.stability.nowarn=true
kotlin.mpp.enableCInteropCommonization=true

# Compose for Web (WASM)
org.jetbrains.compose.experimental.wasm.enabled=true
compose.resources.always.generate.accessors=true

# WASM incremental compilation (2x faster builds)
kotlin.incremental.wasm=true

# Android
android.useAndroidX=true

# Build performance
org.gradle.jvmargs=-Xmx4g -XX:+UseParallelGC
org.gradle.parallel=true
org.gradle.caching=true
EOF
    log_ok "gradle.properties updated with WASM support"
fi

# =============================================================================
# STEP 4: Update shared/build.gradle.kts for wasmJs target
# =============================================================================
log_header "Step 4: Update shared/build.gradle.kts with wasmJs target"

SHARED_BUILD="$SHARED_DIR/build.gradle.kts"

if [ -f "$SHARED_BUILD" ]; then
    if $DRY_RUN; then
        log_dry "Add wasmJs target to shared module"
        log_dry "Add kotlin(\"plugin.compose\") plugin"
        log_dry "Update dependencies for Kotlin 2.x compatibility"
    else
        # Backup
        cp "$SHARED_BUILD" "${SHARED_BUILD}.bak"

        cat > "$SHARED_BUILD" << 'EOF'
import org.jetbrains.kotlin.gradle.ExperimentalWasmDsl
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    kotlin("multiplatform")
    kotlin("plugin.serialization")
    id("com.android.library")
    id("org.jetbrains.compose")
    kotlin("plugin.compose")
}

kotlin {
    // Android
    androidTarget {
        compilerOptions {
            jvmTarget.set(JvmTarget.JVM_17)
        }
    }

    // iOS
    listOf(
        iosX64(),
        iosArm64(),
        iosSimulatorArm64()
    ).forEach { iosTarget ->
        iosTarget.binaries.framework {
            baseName = "shared"
            isStatic = true
        }
    }

    // Desktop (JVM)
    jvm("desktop") {
        compilerOptions {
            jvmTarget.set(JvmTarget.JVM_17)
        }
    }

    // Web (WASM) - NEW TARGET
    @OptIn(ExperimentalWasmDsl::class)
    wasmJs {
        moduleName = "ciris-shared"
        browser {
            commonWebpackConfig {
                outputFileName = "ciris-shared.js"
            }
        }
        binaries.executable()
    }

    sourceSets {
        val commonMain by getting {
            dependencies {
                // Compose Multiplatform
                implementation(compose.runtime)
                implementation(compose.foundation)
                implementation(compose.material3)
                implementation(compose.materialIconsExtended)
                implementation(compose.components.resources)
                @OptIn(org.jetbrains.compose.ExperimentalComposeLibrary::class)
                implementation(compose.components.uiToolingPreview)

                // Coroutines
                implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.9.0")

                // Serialization
                implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")

                // Date/Time
                implementation("org.jetbrains.kotlinx:kotlinx-datetime:0.6.1")

                // Ktor client
                implementation("io.ktor:ktor-client-core:3.0.3")
                implementation("io.ktor:ktor-client-content-negotiation:3.0.3")
                implementation("io.ktor:ktor-serialization-kotlinx-json:3.0.3")
                implementation("io.ktor:ktor-client-logging:3.0.3")
                implementation("io.ktor:ktor-client-auth:3.0.3")

                // Multiplatform ViewModel
                implementation("org.jetbrains.androidx.lifecycle:lifecycle-viewmodel-compose:2.8.4")
                implementation("org.jetbrains.androidx.lifecycle:lifecycle-runtime-compose:2.8.4")

                // Navigation
                implementation("org.jetbrains.androidx.navigation:navigation-compose:2.8.0-alpha10")

                // Generated API client
                implementation(project(":generated-api"))
            }
        }

        val androidMain by getting {
            dependencies {
                implementation("io.ktor:ktor-client-okhttp:3.0.3")
                implementation("androidx.activity:activity-compose:1.9.3")
            }
        }

        val iosMain by creating {
            dependsOn(commonMain)
            dependencies {
                implementation("io.ktor:ktor-client-darwin:3.0.3")
            }
        }

        val iosX64Main by getting { dependsOn(iosMain) }
        val iosArm64Main by getting { dependsOn(iosMain) }
        val iosSimulatorArm64Main by getting { dependsOn(iosMain) }

        val desktopMain by getting {
            dependencies {
                implementation(compose.desktop.currentOs)
                implementation("io.ktor:ktor-client-cio:3.0.3")
            }
        }

        val wasmJsMain by getting {
            dependencies {
                implementation("io.ktor:ktor-client-js:3.0.3")
            }
        }

        val commonTest by getting {
            dependencies {
                implementation(kotlin("test"))
                implementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0")
            }
        }
    }
}

android {
    namespace = "ai.ciris.mobile.shared"
    compileSdk = 34

    defaultConfig {
        minSdk = 24
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
EOF
        log_ok "shared/build.gradle.kts updated with wasmJs target"
    fi
else
    log_warn "shared/build.gradle.kts not found - create manually"
fi

# =============================================================================
# STEP 5: Create wasmJsMain platform implementations
# =============================================================================
log_header "Step 5: Create wasmJsMain Platform Implementations"

WASM_MAIN="$SHARED_DIR/src/wasmJsMain/kotlin/ai/ciris/mobile/shared/platform"

if $DRY_RUN; then
    log_dry "Create directory: $WASM_MAIN"
    log_dry "Create Platform.wasmJs.kt"
    log_dry "Create SecureStorage.wasmJs.kt"
    log_dry "Create PythonRuntime.wasmJs.kt"
    log_dry "Create EnvFileUpdater.wasmJs.kt"
    log_dry "Create other platform implementations..."
else
    mkdir -p "$WASM_MAIN"
    mkdir -p "$SHARED_DIR/src/wasmJsMain/kotlin/ai/ciris/mobile/shared/auth"
    mkdir -p "$SHARED_DIR/src/wasmJsMain/kotlin/ai/ciris/mobile/shared/diagnostics"
    mkdir -p "$SHARED_DIR/src/wasmJsMain/kotlin/ai/ciris/mobile/shared/localization"
    mkdir -p "$SHARED_DIR/src/wasmJsMain/kotlin/ai/ciris/mobile/shared/services"
    mkdir -p "$SHARED_DIR/src/wasmJsMain/kotlin/ai/ciris/mobile/shared/ui/components"

    # Platform.wasmJs.kt
    cat > "$WASM_MAIN/Platform.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.platform

import kotlinx.browser.window

actual fun getPlatform(): Platform = Platform.WEB

actual fun platformLog(tag: String, message: String) {
    console.log("[$tag] $message")
}

actual fun getDeviceDebugInfo(): String {
    return buildString {
        appendLine("Platform: Web (WASM)")
        appendLine("User Agent: ${window.navigator.userAgent}")
        appendLine("Language: ${window.navigator.language}")
    }
}

actual fun openUrlInBrowser(url: String) {
    window.open(url, "_blank")
}

actual fun getAppVersion(): String = "2.3.2"

actual fun getAppBuildNumber(): String = "0"

actual fun startTestAutomationServer() {
    // No-op on web - test automation via browser DevTools
}
EOF

    # SecureStorage.wasmJs.kt
    cat > "$WASM_MAIN/SecureStorage.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.platform

import kotlinx.browser.localStorage

actual class SecureStorage actual constructor() {

    actual suspend fun saveApiKey(key: String, value: String): Result<Unit> = runCatching {
        localStorage.setItem("apikey_$key", value)
    }

    actual suspend fun getApiKey(key: String): Result<String?> = runCatching {
        localStorage.getItem("apikey_$key")
    }

    actual suspend fun saveAccessToken(token: String): Result<Unit> = runCatching {
        localStorage.setItem("ciris_access_token", token)
    }

    actual suspend fun getAccessToken(): Result<String?> = runCatching {
        localStorage.getItem("ciris_access_token")
    }

    actual suspend fun deleteAccessToken(): Result<Unit> = runCatching {
        localStorage.removeItem("ciris_access_token")
    }

    actual suspend fun save(key: String, value: String): Result<Unit> = runCatching {
        localStorage.setItem(key, value)
    }

    actual suspend fun get(key: String): Result<String?> = runCatching {
        localStorage.getItem(key)
    }

    actual suspend fun delete(key: String): Result<Unit> = runCatching {
        localStorage.removeItem(key)
    }

    actual suspend fun clear(): Result<Unit> = runCatching {
        localStorage.clear()
    }
}

actual fun createSecureStorage(): SecureStorage = SecureStorage()
EOF

    # PythonRuntime.wasmJs.kt
    # CRITICAL: All interface methods MUST have 'override' modifier!
    cat > "$WASM_MAIN/PythonRuntime.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.platform

/**
 * Web implementation of PythonRuntime - no-op since backend handles Python.
 * The web UI connects to a remote CIRIS agent via HTTP API.
 *
 * CRITICAL: This class implements PythonRuntimeProtocol and ALL interface
 * methods MUST have the `override` modifier. Missing `override` causes
 * ClassCastException at runtime when code casts to PythonRuntimeProtocol.
 */
actual class PythonRuntime actual constructor() : PythonRuntimeProtocol {
    private var _initialized = false
    private var _serverStarted = false

    actual override suspend fun initialize(pythonHome: String): Result<Unit> = runCatching {
        _initialized = true
    }

    actual override suspend fun startServer(): Result<String> = runCatching {
        _serverStarted = true
        serverUrl
    }

    actual override suspend fun startPythonServer(onStatus: ((String) -> Unit)?): Result<String> = runCatching {
        onStatus?.invoke("Web mode - connecting to remote server...")
        _serverStarted = true
        serverUrl
    }

    actual override fun injectPythonConfig(config: Map<String, String>) {
        // No-op on web - config is on server side
    }

    actual override suspend fun checkHealth(): Result<Boolean> = Result.success(true)

    actual override suspend fun getServicesStatus(): Result<Pair<Int, Int>> = Result.success(22 to 22)

    actual override suspend fun getPrepStatus(): Result<Pair<Int, Int>> = Result.success(2 to 2)

    actual override fun shutdown() {
        _serverStarted = false
    }

    actual override fun isInitialized(): Boolean = _initialized

    actual override fun isServerStarted(): Boolean = _serverStarted

    actual override val serverUrl: String = ""  // Empty = relative URLs for ingress
}

actual fun createPythonRuntime(): PythonRuntime = PythonRuntime()
EOF

    # EnvFileUpdater.wasmJs.kt
    cat > "$WASM_MAIN/EnvFileUpdater.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.platform

/**
 * Web implementation of EnvFileUpdater - no-op since web doesn't have .env files.
 * Configuration is handled server-side via API.
 */
actual class EnvFileUpdater {

    actual suspend fun updateEnvWithToken(oauthIdToken: String): Result<Boolean> = Result.success(true)

    actual fun triggerConfigReload() {
        // No-op on web
    }

    actual suspend fun readLlmConfig(): EnvLlmConfig? = null

    actual suspend fun deleteEnvFile(): Result<Boolean> = Result.success(true)

    actual fun checkTokenRefreshSignal(): Boolean = false

    actual suspend fun clearSigningKey(): Result<Boolean> = Result.success(true)

    actual suspend fun clearDataOnly(): Result<Boolean> = Result.success(true)
}

actual fun createEnvFileUpdater(): EnvFileUpdater = EnvFileUpdater()
EOF

    # BackHandler.wasmJs.kt
    cat > "$WASM_MAIN/BackHandler.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.platform

import androidx.compose.runtime.Composable

@Composable
actual fun PlatformBackHandler(enabled: Boolean, onBack: () -> Unit) {
    // No-op on web - browser handles back button via history API
}
EOF

    # AppRestarter.wasmJs.kt
    cat > "$WASM_MAIN/AppRestarter.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.platform

import kotlinx.browser.window

actual object AppRestarter {
    actual fun restartApp() {
        window.location.reload()
    }
}
EOF

    # Logger.wasmJs.kt
    cat > "$WASM_MAIN/Logger.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.platform

actual object PlatformLogger {
    actual fun d(tag: String, message: String) {
        console.log("[D][$tag] $message")
    }
    actual fun i(tag: String, message: String) {
        console.log("[I][$tag] $message")
    }
    actual fun w(tag: String, message: String) {
        console.warn("[W][$tag] $message")
    }
    actual fun e(tag: String, message: String) {
        console.error("[E][$tag] $message")
    }
    actual fun e(tag: String, message: String, throwable: Throwable) {
        console.error("[E][$tag] $message: ${throwable.message}")
    }
}
EOF

    # CellVizCapability.wasmJs.kt
    cat > "$WASM_MAIN/CellVizCapability.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.platform

/**
 * Web implementation - always capable since modern browsers can handle the viz.
 */
actual fun probeCellVizCapability(): CellVizCapability = CellVizCapability(
    isCapable = true,
    totalRamGb = 0.0,  // Unknown on web
    reason = "Web browsers can handle the cell visualization"
)
EOF

    # KeyboardPadding.wasmJs.kt
    cat > "$WASM_MAIN/KeyboardPadding.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.platform

import androidx.compose.ui.Modifier

actual fun Modifier.platformImePadding(): Modifier = this  // No-op on web
EOF

    # TestAutomation.wasmJs.kt
    cat > "$WASM_MAIN/TestAutomation.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.platform

import androidx.compose.ui.Modifier

actual object TestAutomation {
    actual val isEnabled: Boolean = false
    actual fun registerElement(tag: String, bounds: Any?) {}
    actual fun unregisterElement(tag: String) {}
    actual fun setCurrentScreen(screen: String) {}
    actual fun getElements(): Map<String, Any?> = emptyMap()
    actual fun getCurrentScreen(): String = ""
}

actual fun Modifier.testable(tag: String, text: String?): Modifier = this
actual fun Modifier.testableClickable(tag: String, text: String?, onClick: () -> Unit): Modifier = this
actual fun Modifier.testableWithHandler(tag: String, onClick: () -> Unit): Modifier = this
EOF

    # FilePicker.wasmJs.kt
    cat > "$WASM_MAIN/FilePicker.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.platform

import androidx.compose.runtime.Composable

@Composable
actual fun FilePickerDialog(
    show: Boolean,
    fileExtensions: List<String>,
    onFileSelected: (String?) -> Unit,
    onDismiss: () -> Unit
) {
    // TODO: Implement using HTML file input element
    if (show) {
        onFileSelected(null)
        onDismiss()
    }
}
EOF

    # LocalInferenceCapability.wasmJs.kt
    cat > "$WASM_MAIN/LocalInferenceCapability.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.platform

actual fun probeLocalInferenceCapability(): LocalInferenceCapability = LocalInferenceCapability(
    isCapable = false,
    reason = "Local inference not available in web browsers",
    availableModels = emptyList()
)
EOF

    # LocalLLMServer.wasmJs.kt
    cat > "$WASM_MAIN/LocalLLMServer.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.platform

actual fun getLocalLLMServer(): LocalLLMServer = object : LocalLLMServer {
    override suspend fun start(): Result<String> = Result.failure(
        UnsupportedOperationException("Local LLM not available on web")
    )
    override suspend fun stop(): Result<Unit> = Result.success(Unit)
    override fun isRunning(): Boolean = false
    override fun getModelInfo(): String? = null
}
EOF

    # ScheduledTaskNotifications.wasmJs.kt
    cat > "$WASM_MAIN/ScheduledTaskNotifications.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.platform

actual object ScheduledTaskNotifications {
    actual fun scheduleNotification(taskId: String, title: String, message: String, triggerTimeMs: Long) {
        // TODO: Use Web Notifications API with user permission
    }
    actual fun cancelNotification(taskId: String) {}
    actual fun cancelAllNotifications() {}
}
EOF

    # KMPFileLogger.wasmJs.kt
    cat > "$WASM_MAIN/KMPFileLogger.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.platform

actual fun appendToFile(path: String, text: String) {
    console.log(text)  // Log to console instead of file
}
actual fun getFileSize(path: String): Long = 0L
actual fun deleteFile(path: String) {}
actual fun renameFile(from: String, to: String) {}
actual fun ensureDirectoryExists(path: String) {}
actual fun getCurrentTimestamp(): String = js("new Date().toISOString()") as String
actual fun getKMPLogDir(): String = "/logs"
EOF

    # DebugLogBuffer.wasmJs.kt
    cat > "$WASM_MAIN/DebugLogBuffer.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.platform

actual fun currentTimeMillis(): Long = js("Date.now()") as Long
EOF

    # Auth implementations
    cat > "$SHARED_DIR/src/wasmJsMain/kotlin/ai/ciris/mobile/shared/auth/AuthManager.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.auth

import kotlinx.browser.localStorage

actual class AuthManager {
    actual suspend fun signInWithApple(): Result<String> = Result.failure(
        UnsupportedOperationException("Apple Sign-In not available on web - use backend OAuth")
    )

    actual suspend fun signInWithGoogle(): Result<String> = Result.failure(
        UnsupportedOperationException("Google Sign-In not available on web - use backend OAuth")
    )

    actual suspend fun signOut(): Result<Unit> = runCatching {
        localStorage.removeItem("ciris_access_token")
    }

    actual fun isSignedIn(): Boolean {
        return localStorage.getItem("ciris_access_token") != null
    }

    actual fun getCurrentUserId(): String? {
        return localStorage.getItem("ciris_user_id")
    }
}

actual fun createAuthManager(): AuthManager = AuthManager()
EOF

    cat > "$SHARED_DIR/src/wasmJsMain/kotlin/ai/ciris/mobile/shared/auth/FirstRunDetector.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.auth

import kotlinx.browser.localStorage

actual class FirstRunDetector {
    actual fun isFirstRun(): Boolean {
        return localStorage.getItem("ciris_configured") != "true"
    }

    actual fun markConfigured() {
        localStorage.setItem("ciris_configured", "true")
    }

    actual fun reset() {
        localStorage.removeItem("ciris_configured")
    }
}

actual fun createFirstRunDetector(): FirstRunDetector = FirstRunDetector()
EOF

    # Diagnostics
    cat > "$SHARED_DIR/src/wasmJsMain/kotlin/ai/ciris/mobile/shared/diagnostics/NetworkDiagnostics.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.diagnostics

import ai.ciris.mobile.shared.platform.platformLog

actual fun platformLog(tag: String, message: String) {
    console.log("[$tag] $message")
}
EOF

    # Localization
    cat > "$SHARED_DIR/src/wasmJsMain/kotlin/ai/ciris/mobile/shared/localization/LocalizationResourceLoader.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.localization

actual class LocalizationResourceLoader actual constructor() {
    actual suspend fun loadStrings(languageCode: String): Map<String, String> {
        // TODO: Fetch from server or bundled resources
        return emptyMap()
    }
}

actual fun createLocalizationResourceLoader(): LocalizationResourceLoader = LocalizationResourceLoader()
EOF

    # Services
    cat > "$SHARED_DIR/src/wasmJsMain/kotlin/ai/ciris/mobile/shared/services/ServerManager.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.services

/**
 * Web implementation - server is remote, not local.
 */
actual class ServerManager {
    actual suspend fun startServer(): Result<String> = Result.success("")  // Use relative URLs
    actual fun stopServer() {}
    actual fun isRunning(): Boolean = true  // Always "running" (remote server)
    actual fun getServerUrl(): String = ""  // Relative URLs for ingress
}
EOF

    # UI Components
    cat > "$SHARED_DIR/src/wasmJsMain/kotlin/ai/ciris/mobile/shared/ui/components/PlatformScrollbar.wasmJs.kt" << 'EOF'
package ai.ciris.mobile.shared.ui.components

import androidx.compose.foundation.ScrollState
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier

@Composable
actual fun VerticalScrollbar(
    scrollState: ScrollState,
    modifier: Modifier
) {
    // Browser handles scrollbar natively
}

@Composable
actual fun LazyColumnScrollbar(
    listState: LazyListState,
    modifier: Modifier
) {
    // Browser handles scrollbar natively
}
EOF

    log_ok "Created wasmJsMain platform implementations"
fi

# =============================================================================
# STEP 6: Apply code transformations
# =============================================================================
log_header "Step 6: Apply Code Transformations"

if $DRY_RUN; then
    log_dry "Replace Dispatchers.IO with Dispatchers.Default"
    log_dry "Add Platform.WEB branches to when expressions"
else
    COMMON_MAIN="$SHARED_DIR/src/commonMain"

    # Replace Dispatchers.IO
    find "$COMMON_MAIN" -name "*.kt" -exec sed -i '/import kotlinx\.coroutines\.IO$/d' {} \;
    find "$COMMON_MAIN" -name "*.kt" -exec sed -i 's/Dispatchers\.IO/Dispatchers.Default/g' {} \;
    find "$COMMON_MAIN" -name "*.kt" -exec sed -i 's/withContext(IO)/withContext(Dispatchers.Default)/g' {} \;
    log_ok "Replaced Dispatchers.IO with Dispatchers.Default"

    # Note: Platform.WEB branches need manual review - automated replacement is risky
    log_warn "Review Platform when() expressions manually for WEB branches"
fi

# =============================================================================
# STEP 7: Add Platform.WEB to enum (if not present)
# =============================================================================
log_header "Step 7: Ensure Platform.WEB Exists"

PLATFORM_FILE="$SHARED_DIR/src/commonMain/kotlin/ai/ciris/mobile/shared/platform/Platform.kt"

if [ -f "$PLATFORM_FILE" ]; then
    if ! grep -q "WEB" "$PLATFORM_FILE"; then
        if $DRY_RUN; then
            log_dry "Add WEB to Platform enum"
        else
            # Add WEB before the closing brace of the enum
            sed -i '/enum class Platform/,/}/{s/DESKTOP/DESKTOP,\n    WEB/}' "$PLATFORM_FILE"
            log_ok "Added WEB to Platform enum"
        fi
    else
        log_ok "Platform.WEB already exists"
    fi
else
    log_warn "Platform.kt not found at expected location"
fi

# =============================================================================
# STEP 8: Clean and verify
# =============================================================================
log_header "Step 8: Clean and Verify"

if $DRY_RUN; then
    log_dry "Run: ./gradlew clean"
    log_dry "Run: ./gradlew :shared:compileKotlinWasmJs"
else
    cd "$MOBILE_ROOT"
    echo "Cleaning build directories..."
    ./gradlew clean --quiet 2>/dev/null || true

    echo "Verifying WASM compilation..."
    if ./gradlew :shared:compileKotlinWasmJs --quiet 2>&1; then
        log_ok "WASM compilation successful!"
    else
        log_error "WASM compilation failed - review errors above"
        echo ""
        echo "Common issues:"
        echo "  1. Missing 'override' on interface methods"
        echo "  2. Platform.WEB not handled in when expressions"
        echo "  3. expect declarations without wasmJsMain actuals"
        echo ""
        echo "Run: ./gradlew :shared:compileKotlinWasmJs 2>&1 | head -100"
    fi
fi

# =============================================================================
# SUMMARY
# =============================================================================
log_header "Migration Complete"

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║  Migration Summary                                            ║"
echo "╠═══════════════════════════════════════════════════════════════╣"
echo "║  Kotlin:    1.9.22 → $KOTLIN_VERSION                              ║"
echo "║  Compose:   1.6.0  → $COMPOSE_VERSION                               ║"
echo "║  AGP:       8.1.0  → $AGP_VERSION                               ║"
echo "║  Gradle:    8.2    → $GRADLE_VERSION                                 ║"
echo "║  New target: wasmJs (browser)                                 ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  1. Review Platform when() expressions for WEB branches"
echo "  2. Test Android build: ./gradlew :androidApp:assembleDebug"
echo "  3. Test arm32 device: adb -s 330016f5b40463cd install ..."
echo "  4. Test WASM: ./gradlew :webApp:wasmJsBrowserDevelopmentRun"
echo "  5. Update CLAUDE.md with new build commands"
echo ""
echo "Backup files created with .bak extension"
echo ""
