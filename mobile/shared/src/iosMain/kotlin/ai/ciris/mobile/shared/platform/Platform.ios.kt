package ai.ciris.mobile.shared.platform

import platform.Foundation.NSBundle
import platform.Foundation.NSURL
import platform.Foundation.NSProcessInfo
import platform.UIKit.UIApplication
import platform.UIKit.UIDevice
import platform.darwin.dispatch_async
import platform.darwin.dispatch_get_main_queue

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

/**
 * iOS implementation: open URL in Safari via UIApplication.
 * Must dispatch to main queue — UIKit calls require main thread.
 * Uses the modern open(_:options:completionHandler:) API.
 */
actual fun openUrlInBrowser(url: String) {
    val nsUrl = NSURL.URLWithString(url) ?: return
    dispatch_async(dispatch_get_main_queue()) {
        UIApplication.sharedApplication.openURL(nsUrl, emptyMap<Any?, Any>(), null)
    }
}
