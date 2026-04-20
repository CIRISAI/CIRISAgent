package ai.ciris.mobile.shared.platform

/**
 * Centralized file-based logger for KMP.
 *
 * All KMP logs (from PlatformLogger) are written to a persistent log file
 * that can be pulled from the device for debugging. This solves the iOS problem
 * where println() output is ephemeral and not captured by the QA runner.
 *
 * Auto-initializes on first log call using platform-specific getKMPLogDir().
 *
 * The log file is at: {logDir}/kmp_app.log
 * Format: [2026-03-06 12:34:56.789] I/Tag: message
 * Max size: 2MB, rotated to kmp_app.log.1
 */
object KMPFileLogger {
    private var logDir: String? = null
    private var initialized = false
    private var initFailed = false

    private const val MAX_FILE_SIZE = 2 * 1024 * 1024L
    private const val LOG_FILENAME = "kmp_app.log"
    private const val LOG_FILENAME_PREV = "kmp_app.log.1"

    fun init(logDir: String) {
        this.logDir = logDir
        ensureDirectoryExists(logDir)
        // Test write to verify file I/O works
        val testPath = "$logDir/$LOG_FILENAME"
        appendToFile(testPath, "=== KMP File Logger initialized, logDir=$logDir ===\n")
        this.initialized = true
        this.initFailed = false
    }

    private fun ensureInitialized() {
        if (initialized || initFailed) return
        try {
            init(getKMPLogDir())
        } catch (e: Exception) {
            initFailed = true
        }
    }

    fun log(level: String, tag: String, message: String) {
        if (!initialized) ensureInitialized()
        val dir = logDir ?: return

        val timestamp = getCurrentTimestamp()
        val levelChar = when (level) {
            "DEBUG" -> "D"
            "INFO" -> "I"
            "WARN" -> "W"
            "ERROR" -> "E"
            else -> "?"
        }
        val line = "[$timestamp] $levelChar/$tag: $message\n"
        val filePath = "$dir/$LOG_FILENAME"

        try {
            appendToFile(filePath, line)
            if (shouldCheckRotation()) {
                val size = getFileSize(filePath)
                if (size > MAX_FILE_SIZE) {
                    rotateLog(dir)
                }
            }
        } catch (_: Exception) {
            // Logging must never crash the app
        }
    }

    private var writeCount = 0L

    private fun shouldCheckRotation(): Boolean {
        writeCount++
        return writeCount % 100 == 0L
    }

    private fun rotateLog(dir: String) {
        val current = "$dir/$LOG_FILENAME"
        val previous = "$dir/$LOG_FILENAME_PREV"
        try {
            deleteFile(previous)
            renameFile(current, previous)
        } catch (_: Exception) {
            // Best effort
        }
    }
}

// Platform-specific file operations — minimal expect/actual surface.
// JVM (Android/Desktop): java.io.File
// iOS: platform.posix (fopen/fwrite/fclose) — same as kotlinx-io
expect fun appendToFile(path: String, text: String)
expect fun getFileSize(path: String): Long
expect fun deleteFile(path: String)
expect fun renameFile(from: String, to: String)
expect fun ensureDirectoryExists(path: String)
expect fun getCurrentTimestamp(): String
expect fun getKMPLogDir(): String
