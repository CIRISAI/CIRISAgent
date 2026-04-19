package ai.ciris.mobile.shared.platform

import kotlinx.browser.window

actual fun getPlatform(): Platform = Platform.WEB

actual fun platformLog(tag: String, message: String) {
    println("[$tag] $message")
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
