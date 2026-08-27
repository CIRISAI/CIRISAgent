package ai.ciris.mobile.shared.platform

import android.content.ClipData
import android.content.ClipboardManager
import android.content.ContentValues
import android.content.Context
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import java.io.File

/**
 * Android debug-bundle export — into the shared Downloads collection.
 *
 * NOT `getExternalFilesDir()`. That resolves under
 * `Android/data/<package>/files`, which scoped storage hides from ordinary file
 * managers and the system document picker on Android 11+. The UI would report
 * an absolute path as a successful "Download" that the user then cannot reach
 * without adb — the same "it said it worked" failure this whole change exists to
 * remove, one layer out.
 *
 * MediaStore rather than a share intent: this runs from screens where the app is
 * least healthy (a login that cannot exchange a token, a startup that never
 * completes), and a share sheet needs a live Activity. Writing a file needs only
 * a Context, and on Android 10+ MediaStore Downloads requires no runtime
 * permission.
 */
private var appContext: Context? = null

fun initDebugBundleExport(context: Context) {
    appContext = context.applicationContext
}

actual fun saveDebugBundle(fileName: String, content: String): String? {
    val ctx = appContext ?: return null
    return runCatching {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val values = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)
                put(MediaStore.MediaColumns.MIME_TYPE, "text/plain")
                put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
            }
            val uri = ctx.contentResolver.insert(
                MediaStore.Downloads.EXTERNAL_CONTENT_URI,
                values,
            ) ?: return@runCatching null
            ctx.contentResolver.openOutputStream(uri)?.use { it.write(content.toByteArray()) }
                ?: return@runCatching null
            // A name the user can search for, not a URI they cannot act on.
            "Downloads/$fileName"
        } else {
            // Pre-Q (API 24-28): the app-specific external dir, NOT public
            // Downloads.
            //
            // Public Downloads needs WRITE_EXTERNAL_STORAGE on these versions —
            // which this app does not declare, and which would have to be
            // requested at runtime from an Activity that the screens using this
            // (a login that cannot exchange a token, a startup that never
            // completes) may not have. The write would simply throw and the
            // Download button would silently do nothing.
            //
            // The app-specific dir needs no permission, and on API 24-28 it is
            // genuinely browsable — scoped storage only hides it from Android 11
            // onward, which is exactly why the Q+ branch above exists.
            val dir = ctx.getExternalFilesDir(null) ?: ctx.filesDir
            val out = File(dir, fileName)
            out.writeText(content)
            out.absolutePath
        }
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
