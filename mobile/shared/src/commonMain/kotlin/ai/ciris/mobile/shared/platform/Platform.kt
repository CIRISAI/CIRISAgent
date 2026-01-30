package ai.ciris.mobile.shared.platform

/**
 * Platform detection for Kotlin Multiplatform.
 * Used to show platform-appropriate UI text and behavior.
 */
enum class Platform {
    ANDROID,
    IOS
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
 * Get the platform-appropriate OAuth provider name.
 */
fun getOAuthProviderName(): String = when (getPlatform()) {
    Platform.IOS -> "Apple"
    Platform.ANDROID -> "Google"
}

/**
 * Get the platform-appropriate OAuth provider identifier.
 */
fun getOAuthProviderId(): String = when (getPlatform()) {
    Platform.IOS -> "apple"
    Platform.ANDROID -> "google"
}
