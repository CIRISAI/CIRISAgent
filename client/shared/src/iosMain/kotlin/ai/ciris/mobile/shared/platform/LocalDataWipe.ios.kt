package ai.ciris.mobile.shared.platform

import platform.Foundation.NSFileManager
import platform.Foundation.NSHomeDirectory

/**
 * iOS wipe: the CIRIS state directory under the app sandbox.
 *
 * Sandboxed, so this can only ever reach this app's own container.
 */
actual fun wipeLocalData(): Boolean {
    val path = (
        platform.posix.getenv("CIRIS_HOME")?.let { kotlinx.cinterop.toKString(it) }
            ?: "${NSHomeDirectory()}/Documents/ciris"
        )
    val fm = NSFileManager.defaultManager
    if (!fm.fileExistsAtPath(path)) return true
    runCatching { fm.removeItemAtPath(path, null) }
    return !fm.fileExistsAtPath(path)
}
