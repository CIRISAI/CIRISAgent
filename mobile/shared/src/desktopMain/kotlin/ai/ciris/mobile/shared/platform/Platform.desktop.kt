package ai.ciris.mobile.shared.platform

import java.awt.Desktop
import java.net.URI

actual fun getPlatform(): Platform = Platform.DESKTOP

actual fun platformLog(tag: String, message: String) {
    println("[$tag] $message")
}

actual fun getDeviceDebugInfo(): String {
    return buildString {
        appendLine("Platform: Desktop JVM")
        appendLine("Java Version: ${System.getProperty("java.version")}")
        appendLine("OS: ${System.getProperty("os.name")} ${System.getProperty("os.version")}")
        appendLine("Arch: ${System.getProperty("os.arch")}")
        appendLine("User: ${System.getProperty("user.name")}")
        appendLine("Home: ${System.getProperty("user.home")}")
    }
}

actual fun openUrlInBrowser(url: String) {
    try {
        if (Desktop.isDesktopSupported()) {
            Desktop.getDesktop().browse(URI(url))
        }
    } catch (e: Exception) {
        println("Failed to open URL: $url - ${e.message}")
    }
}
