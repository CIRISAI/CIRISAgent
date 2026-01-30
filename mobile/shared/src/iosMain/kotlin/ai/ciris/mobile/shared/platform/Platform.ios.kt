package ai.ciris.mobile.shared.platform

/**
 * iOS implementation of platform detection.
 */
actual fun getPlatform(): Platform = Platform.IOS

/**
 * iOS implementation of platform logging.
 */
actual fun platformLog(tag: String, message: String) {
    println("[$tag] $message")
}
