package ai.ciris.mobile.shared.platform

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update

/**
 * Debug log entry for UI display
 */
data class DebugLogEntry(
    val id: Long,
    val timestamp: Long,
    val level: String,  // DEBUG, INFO, WARN, ERROR
    val tag: String,
    val message: String
) {
    // Unicode symbols — render on all platforms including WASM/Skia
    val symbol: String get() = when (level) {
        "DEBUG" -> "\u25CB"  // ○
        "INFO" -> "\u2139"   // ℹ
        "WARN" -> "\u26A0"   // ⚠
        "ERROR" -> "\u2716"  // ✖
        else -> "\u22EF"     // ⋯
    }

    val formattedTime: String get() {
        val hours = ((timestamp / 3600000) % 24).toInt()
        val minutes = ((timestamp / 60000) % 60).toInt()
        val seconds = ((timestamp / 1000) % 60).toInt()
        val displayHours = if (hours == 0) 12 else if (hours > 12) hours - 12 else hours
        return "$displayHours:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}"
    }
}

/**
 * Thread-safe buffer that stores recent debug logs for UI display.
 * Best-in-class logging that surfaces to the UI for easy troubleshooting.
 */
object DebugLogBuffer {
    private const val MAX_ENTRIES = 200

    private val _entries = MutableStateFlow<List<DebugLogEntry>>(emptyList())
    val entries: StateFlow<List<DebugLogEntry>> = _entries.asStateFlow()

    // Count of errors since last clear - shown as badge
    private val _errorCount = MutableStateFlow(0)
    val errorCount: StateFlow<Int> = _errorCount.asStateFlow()

    // Latest error message for quick display
    private val _latestError = MutableStateFlow<String?>(null)
    val latestError: StateFlow<String?> = _latestError.asStateFlow()

    /**
     * Add a log entry to the buffer.
     *
     * Called from any thread: the desktop node's stdout reader logs from
     * `Dispatchers.IO` while view models log from their own scopes. Every
     * mutation here is therefore a compare-and-set, not a read-modify-write —
     * `x.value = x.value + 1` loses updates under exactly the concurrency that
     * a failing startup produces, which is when this buffer has to be right.
     *
     * The id is derived INSIDE the update block rather than from a counter.
     * `update` re-runs its lambda when it loses a race, so a `counter++` beside
     * it would burn ids on retries and hand out duplicates; the tail of the
     * list is the one source that is already consistent with the winning CAS.
     */
    fun add(level: String, tag: String, message: String) {
        val timestamp = currentTimeMillis()

        _entries.update { current ->
            val entry = DebugLogEntry(
                id = (current.lastOrNull()?.id ?: -1L) + 1L,
                timestamp = timestamp,
                level = level,
                tag = tag,
                message = message
            )
            (current + entry).takeLast(MAX_ENTRIES)
        }

        if (level == "ERROR" || level == "WARN") {
            _errorCount.update { it + 1 }
            if (level == "ERROR") {
                // Last writer wins, which is the definition of "latest".
                _latestError.value = "[$tag] $message"
            }
        }
    }

    /**
     * Clear all log entries
     */
    fun clear() {
        _entries.value = emptyList()
        _errorCount.value = 0
        _latestError.value = null
    }

    /**
     * Clear just the error count (after user has seen errors)
     */
    fun clearErrorCount() {
        _errorCount.value = 0
    }

    /**
     * Dismiss the latest error
     */
    fun dismissLatestError() {
        _latestError.value = null
    }

    /**
     * Get filtered entries
     */
    fun getFiltered(level: String? = null, tag: String? = null): List<DebugLogEntry> {
        return _entries.value.filter { entry ->
            (level == null || entry.level == level) &&
            (tag == null || entry.tag.contains(tag, ignoreCase = true))
        }
    }

    /**
     * Get only error entries
     */
    fun getErrors(): List<DebugLogEntry> = getFiltered(level = "ERROR")

    /**
     * Get only warn and error entries
     */
    fun getWarningsAndErrors(): List<DebugLogEntry> {
        return _entries.value.filter { it.level == "WARN" || it.level == "ERROR" }
    }
}

/**
 * Platform-specific current time in milliseconds
 */
expect fun currentTimeMillis(): Long
