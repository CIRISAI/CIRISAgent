@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package ai.ciris.mobile.shared.platform

import kotlinx.cinterop.addressOf
import kotlinx.cinterop.alloc
import kotlinx.cinterop.memScoped
import kotlinx.cinterop.ptr
import kotlinx.cinterop.usePinned
import platform.Foundation.NSDate
import platform.Foundation.NSDateFormatter
import platform.Foundation.NSFileManager
import platform.Foundation.NSHomeDirectory
import platform.posix.fclose
import platform.posix.fflush
import platform.posix.fopen
import platform.posix.fwrite
import platform.posix.remove
import platform.posix.rename
import platform.posix.stat

/**
 * iOS file operations using POSIX for file I/O, Foundation for directory management.
 */

actual fun appendToFile(path: String, text: String) {
    val file = fopen(path, "a") ?: return
    val bytes = text.encodeToByteArray()
    bytes.usePinned { pinned ->
        fwrite(pinned.addressOf(0), 1u, bytes.size.toULong(), file)
    }
    fflush(file)
    fclose(file)
}

actual fun getFileSize(path: String): Long {
    memScoped {
        val st = alloc<stat>()
        return if (platform.posix.stat(path, st.ptr) == 0) st.st_size else 0L
    }
}

actual fun deleteFile(path: String) {
    remove(path)
}

actual fun renameFile(from: String, to: String) {
    rename(from, to)
}

actual fun ensureDirectoryExists(path: String) {
    val fm = NSFileManager.defaultManager
    if (!fm.fileExistsAtPath(path)) {
        fm.createDirectoryAtPath(
            path,
            withIntermediateDirectories = true,
            attributes = null,
            error = null
        )
    }
}

actual fun getCurrentTimestamp(): String {
    val formatter = NSDateFormatter()
    formatter.dateFormat = "yyyy-MM-dd HH:mm:ss.SSS"
    return formatter.stringFromDate(NSDate())
}

actual fun getKMPLogDir(): String {
    val homeDir = NSHomeDirectory()
    return "$homeDir/Documents/ciris/logs"
}
