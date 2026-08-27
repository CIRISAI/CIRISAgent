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

/**
 * Desktop implementation: read version from JAR manifest or fallback to constant.
 * The version is set in desktopApp/build.gradle.kts compose.desktop.application.version
 */
actual fun getAppVersion(): String {
    // Try to read from JAR manifest (set by Compose Desktop build)
    return try {
        val pkg = Platform::class.java.`package`
        pkg?.implementationVersion ?: DESKTOP_VERSION_FALLBACK
    } catch (e: Exception) {
        DESKTOP_VERSION_FALLBACK
    }
}

/**
 * Desktop implementation: build number (not applicable, return "0").
 */
actual fun getAppBuildNumber(): String = "0"

actual fun startTestAutomationServer() {
    // Desktop: no-op here — server is started from desktopApp/Main.kt
}

/**
 * The desktop version.
 *
 * Named "fallback" for history: `getAppVersion()` prefers the JAR manifest's
 * `Implementation-Version`, but the Compose uber-jar task builds its manifest
 * itself and carries only Main-Class, so this constant is in practice the ONLY
 * value desktop ever reports.
 *
 * It used to say "keep in sync with androidApp versionName" — an instruction to
 * a human that nobody ran. It sat at 2.3.2 while builds shipped 2.9.x, so the
 * diagnostics bundle confidently named the wrong build, which is the one field
 * a bundle exists to get right.
 *
 * `tools/dev/bump_version.py` now rewrites it, so it moves with every release
 * and the sync is no longer anyone's job to remember.
 */
private const val DESKTOP_VERSION_FALLBACK = "2.9.41"
