package ai.ciris.mobile.shared.platform

import kotlinx.datetime.Clock
import kotlinx.datetime.TimeZone
import kotlinx.datetime.toLocalDateTime

/**
 * WASM/JS file operations - stub implementation that logs to console.
 * File I/O is not available in browser environment.
 */
actual fun appendToFile(path: String, text: String) {
    // Log to console instead of file in browser
    println(text.trimEnd())
}

actual fun getFileSize(path: String): Long = 0L

actual fun deleteFile(path: String) {
    // No-op in browser
}

actual fun renameFile(from: String, to: String) {
    // No-op in browser
}

actual fun ensureDirectoryExists(path: String) {
    // No-op in browser
}

actual fun getCurrentTimestamp(): String {
    // Use kotlinx.datetime for cross-platform compatibility
    val now = Clock.System.now()
    val local = now.toLocalDateTime(TimeZone.currentSystemDefault())
    val year = local.year
    val month = local.monthNumber.toString().padStart(2, '0')
    val day = local.dayOfMonth.toString().padStart(2, '0')
    val hours = local.hour.toString().padStart(2, '0')
    val minutes = local.minute.toString().padStart(2, '0')
    val seconds = local.second.toString().padStart(2, '0')
    val millis = (local.nanosecond / 1_000_000).toString().padStart(3, '0')

    return "$year-$month-$day $hours:$minutes:$seconds.$millis"
}

actual fun getKMPLogDir(): String = "/logs"
