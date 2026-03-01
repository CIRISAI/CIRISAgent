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
