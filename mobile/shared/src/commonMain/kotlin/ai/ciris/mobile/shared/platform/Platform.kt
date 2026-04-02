package ai.ciris.mobile.shared.platform

/**
 * Platform detection for Kotlin Multiplatform.
 * Used to show platform-appropriate UI text and behavior.
 */
enum class Platform {
    ANDROID,
    IOS,
    DESKTOP
}

/**
 * Get the current platform.
 */
expect fun getPlatform(): Platform

/**
 * Platform-specific logging.
 */
expect fun platformLog(tag: String, message: String)

/**
 * Check if running on iOS.
 */
fun isIOS(): Boolean = getPlatform() == Platform.IOS

/**
 * Check if running on Android.
 */
fun isAndroid(): Boolean = getPlatform() == Platform.ANDROID

/**
 * Check if running on Desktop.
 */
fun isDesktop(): Boolean = getPlatform() == Platform.DESKTOP

/**
 * Get the platform-appropriate OAuth provider name.
 */
fun getOAuthProviderName(): String = when (getPlatform()) {
    Platform.IOS -> "Apple"
    Platform.ANDROID -> "Google"
    Platform.DESKTOP -> "Desktop"
}

/**
 * Get the platform-appropriate OAuth provider identifier.
 */
fun getOAuthProviderId(): String = when (getPlatform()) {
    Platform.IOS -> "apple"
    Platform.ANDROID -> "google"
    Platform.DESKTOP -> "desktop"
}

/**
 * Get device debug information for error reporting.
 * Includes platform, OS version, CPU architecture, and app version.
 */
expect fun getDeviceDebugInfo(): String

/**
 * Open a URL in the platform's default browser.
 * On iOS calls UIApplication.shared.open, on Android uses Intent.ACTION_VIEW.
 */
expect fun openUrlInBrowser(url: String)

/**
 * Get the app version string (e.g., "2.3.1").
 * On Android reads from BuildConfig, on iOS from Bundle.main, on Desktop from constant.
 */
expect fun getAppVersion(): String

/**
 * Get the app build number/version code (e.g., "77").
 * On Android reads versionCode, on iOS reads CFBundleVersion, on Desktop returns "0".
 */
expect fun getAppBuildNumber(): String

/**
 * Start the test automation HTTP server if CIRIS_TEST_MODE is enabled.
 * On desktop: no-op (server is started from Main.kt).
 * On iOS: starts POSIX socket server on port 8091.
 * On Android: starts Ktor CIO server on port 8091.
 */
expect fun startTestAutomationServer()
