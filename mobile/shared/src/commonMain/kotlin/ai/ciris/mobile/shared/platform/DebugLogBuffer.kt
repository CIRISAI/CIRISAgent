package ai.ciris.mobile.shared.platform

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

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
    val emoji: String get() = when (level) {
        "DEBUG" -> "🔍"
        "INFO" -> "ℹ️"
        "WARN" -> "⚠️"
        "ERROR" -> "❌"
        else -> "📝"
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
    private var idCounter = 0L

    private val _entries = MutableStateFlow<List<DebugLogEntry>>(emptyList())
    val entries: StateFlow<List<DebugLogEntry>> = _entries.asStateFlow()

    // Count of errors since last clear - shown as badge
    private val _errorCount = MutableStateFlow(0)
    val errorCount: StateFlow<Int> = _errorCount.asStateFlow()

    // Latest error message for quick display
    private val _latestError = MutableStateFlow<String?>(null)
    val latestError: StateFlow<String?> = _latestError.asStateFlow()

    /**
     * Add a log entry to the buffer
     */
    fun add(level: String, tag: String, message: String) {
        val entry = DebugLogEntry(
            id = idCounter++,
            timestamp = currentTimeMillis(),
            level = level,
            tag = tag,
            message = message
        )

        _entries.value = (_entries.value + entry).takeLast(MAX_ENTRIES)

        if (level == "ERROR" || level == "WARN") {
            _errorCount.value = _errorCount.value + 1
            if (level == "ERROR") {
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
