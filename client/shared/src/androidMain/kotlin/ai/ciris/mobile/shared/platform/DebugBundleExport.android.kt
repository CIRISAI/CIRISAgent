package ai.ciris.mobile.shared.platform

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import java.io.File

/**
 * Android debug-bundle export.
 *
 * Writes into the app's external files dir rather than shared Downloads: it
 * needs no runtime permission on any supported API level, survives the app
 * being stuck pre-login (which is exactly when this is used), and is reachable
 * over USB/adb and by most file managers. A share sheet was the alternative and
 * was rejected — it requires an Activity, and the login screen this must work on
 * is precisely where the app is least healthy.
 */
private var appContext: Context? = null

fun initDebugBundleExport(context: Context) {
    appContext = context.applicationContext
}

actual fun saveDebugBundle(fileName: String, content: String): String? {
    val ctx = appContext ?: return null
    return runCatching {
        val dir = ctx.getExternalFilesDir(null) ?: ctx.filesDir
        val out = File(dir, fileName)
        out.writeText(content)
        out.absolutePath
    }.getOrNull()
}

actual fun copyToClipboard(text: String): Boolean {
    val ctx = appContext ?: return false
    return runCatching {
        val cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        cm.setPrimaryClip(ClipData.newPlainText("CIRIS debug bundle", text))
        true
    }.getOrDefault(false)
}
