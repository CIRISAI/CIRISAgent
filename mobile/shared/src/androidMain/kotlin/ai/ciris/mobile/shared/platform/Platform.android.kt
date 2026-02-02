package ai.ciris.mobile.shared.platform

import android.util.Log

/**
 * Android implementation of platform detection.
 */
actual fun getPlatform(): Platform = Platform.ANDROID

/**
 * Android implementation of platform logging.
 */
actual fun platformLog(tag: String, message: String) {
    Log.d(tag, message)
}
