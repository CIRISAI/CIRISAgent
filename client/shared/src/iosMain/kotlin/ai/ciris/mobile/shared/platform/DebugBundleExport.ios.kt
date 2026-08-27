package ai.ciris.mobile.shared.platform

import platform.Foundation.NSDocumentDirectory
import platform.Foundation.NSSearchPathForDirectoriesInDomains
import platform.Foundation.NSString
import platform.Foundation.NSUTF8StringEncoding
import platform.Foundation.NSUserDomainMask
import platform.Foundation.writeToFile
import platform.UIKit.UIPasteboard

/** iOS: Documents, so the file is visible in Files.app when sharing is enabled. */
actual fun saveDebugBundle(fileName: String, content: String): String? = runCatching {
    val dirs = NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, true)
    val dir = dirs.firstOrNull() as? String ?: return null
    val path = "$dir/$fileName"
    val ok = (content as NSString).writeToFile(path, true, NSUTF8StringEncoding, null)
    if (ok) path else null
}.getOrNull()

actual fun copyToClipboard(text: String): Boolean = runCatching {
    UIPasteboard.generalPasteboard.string = text
    true
}.getOrDefault(false)
