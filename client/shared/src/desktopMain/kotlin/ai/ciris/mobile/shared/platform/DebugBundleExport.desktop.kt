package ai.ciris.mobile.shared.platform

import java.awt.Toolkit
import java.awt.datatransfer.StringSelection
import java.io.File

/** Desktop: the user's home dir, which is always writable and always nameable. */
actual fun saveDebugBundle(fileName: String, content: String): String? = runCatching {
    val out = File(System.getProperty("user.home") ?: ".", fileName)
    out.writeText(content)
    out.absolutePath
}.getOrNull()

actual fun copyToClipboard(text: String): Boolean = runCatching {
    Toolkit.getDefaultToolkit().systemClipboard.setContents(StringSelection(text), null)
    true
}.getOrDefault(false)
