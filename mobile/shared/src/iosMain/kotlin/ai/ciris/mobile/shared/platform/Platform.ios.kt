package ai.ciris.mobile.shared.platform

import platform.UIKit.UIDevice
import platform.Foundation.NSBundle
import platform.Foundation.NSProcessInfo

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

/**
 * iOS implementation of device debug info.
 * Returns iOS version, device model, CPU architecture, etc.
 */
actual fun getDeviceDebugInfo(): String {
    val device = UIDevice.currentDevice
    val processInfo = NSProcessInfo.processInfo
    val bundle = NSBundle.mainBundle

    // Get CPU architecture
    val cpuArch = when {
        processInfo.environment["SIMULATOR_DEVICE_NAME"] != null -> "Simulator"
        else -> {
            // On real devices, check the process info
            val archInfo = processInfo.operatingSystemVersionString
            if (archInfo.contains("arm64")) "arm64" else "unknown"
        }
    }

    val appVersion = bundle.objectForInfoDictionaryKey("CFBundleShortVersionString") as? String ?: "unknown"
    val buildNumber = bundle.objectForInfoDictionaryKey("CFBundleVersion") as? String ?: "unknown"

    return buildString {
        appendLine("Platform: iOS ${device.systemVersion}")
        appendLine("Device: ${device.model} (${device.name})")
        appendLine("CPU: $cpuArch")
        appendLine("App: CIRIS v$appVersion ($buildNumber)")
    }.trim()
}
