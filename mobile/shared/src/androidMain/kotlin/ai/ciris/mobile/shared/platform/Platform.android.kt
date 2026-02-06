package ai.ciris.mobile.shared.platform

import android.os.Build
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

/**
 * Android implementation of device debug info.
 * Returns CPU architecture, Android version, device model, etc.
 */
actual fun getDeviceDebugInfo(): String {
    val cpuAbi = Build.SUPPORTED_ABIS.firstOrNull() ?: "unknown"
    val allAbis = Build.SUPPORTED_ABIS.joinToString(", ")
    val is32Bit = cpuAbi == "armeabi-v7a" || cpuAbi == "x86"

    return buildString {
        appendLine("Platform: Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})")
        appendLine("Device: ${Build.MANUFACTURER} ${Build.MODEL}")
        appendLine("CPU: $cpuAbi${if (is32Bit) " (32-bit)" else " (64-bit)"}")
        appendLine("All ABIs: $allAbis")
    }.trim()
}
