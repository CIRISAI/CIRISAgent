package ai.ciris.mobile.shared.platform

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
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

/** Stored application context for URL opening. */
private var urlOpenerContext: Context? = null

/** Call from Application.onCreate() or MainActivity.onCreate(). */
fun initUrlOpener(context: Context) {
    urlOpenerContext = context.applicationContext
}

/**
 * Android implementation: open URL via Intent.ACTION_VIEW.
 */
actual fun openUrlInBrowser(url: String) {
    val ctx = urlOpenerContext
    if (ctx == null) {
        Log.e("Platform", "openUrlInBrowser: context not initialized, call initUrlOpener() first")
        return
    }
    try {
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        ctx.startActivity(intent)
    } catch (e: Exception) {
        Log.e("Platform", "Failed to open URL: $url", e)
    }
}

/** Cached version info to avoid repeated PackageManager lookups. */
private var cachedVersionName: String? = null
private var cachedVersionCode: String? = null

/**
 * Android implementation: get version name from PackageManager.
 * Falls back to "unknown" if context not initialized.
 */
actual fun getAppVersion(): String {
    cachedVersionName?.let { return it }

    val ctx = urlOpenerContext ?: return ANDROID_VERSION_FALLBACK
    return try {
        val packageInfo = ctx.packageManager.getPackageInfo(ctx.packageName, 0)
        packageInfo.versionName.also { cachedVersionName = it } ?: ANDROID_VERSION_FALLBACK
    } catch (e: PackageManager.NameNotFoundException) {
        Log.e("Platform", "Failed to get version name", e)
        ANDROID_VERSION_FALLBACK
    }
}

/**
 * Android implementation: get version code from PackageManager.
 */
actual fun getAppBuildNumber(): String {
    cachedVersionCode?.let { return it }

    val ctx = urlOpenerContext ?: return "0"
    return try {
        val packageInfo = ctx.packageManager.getPackageInfo(ctx.packageName, 0)
        @Suppress("DEPRECATION")
        val code = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            packageInfo.longVersionCode.toString()
        } else {
            packageInfo.versionCode.toString()
        }
        code.also { cachedVersionCode = it }
    } catch (e: PackageManager.NameNotFoundException) {
        Log.e("Platform", "Failed to get version code", e)
        "0"
    }
}

/**
 * Fallback version if context not initialized.
 * Keep in sync with mobile/androidApp/build.gradle versionName.
 */
private const val ANDROID_VERSION_FALLBACK = "2.3.1"
