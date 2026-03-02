package ai.ciris.mobile.shared.platform

import android.util.Log

/**
 * Android implementation of PlatformLogger using android.util.Log for logcat output.
 * Logs are also stored in the debug buffer for UI display.
 * Respects LogConfig.minLevel for filtering.
 */
actual object PlatformLogger {
    actual fun d(tag: String, message: String) {
        if (LogConfig.minLevel.priority <= LogLevel.DEBUG.priority) {
            Log.d(tag, message)
            DebugLogBuffer.add("DEBUG", tag, message)
        }
    }

    actual fun i(tag: String, message: String) {
        if (LogConfig.minLevel.priority <= LogLevel.INFO.priority) {
            Log.i(tag, message)
            DebugLogBuffer.add("INFO", tag, message)
        }
    }

    actual fun w(tag: String, message: String) {
        if (LogConfig.minLevel.priority <= LogLevel.WARN.priority) {
            Log.w(tag, message)
            DebugLogBuffer.add("WARN", tag, message)
        }
    }

    actual fun e(tag: String, message: String) {
        if (LogConfig.minLevel.priority <= LogLevel.ERROR.priority) {
            Log.e(tag, message)
            DebugLogBuffer.add("ERROR", tag, message)
        }
    }

    actual fun e(tag: String, message: String, throwable: Throwable) {
        if (LogConfig.minLevel.priority <= LogLevel.ERROR.priority) {
            Log.e(tag, message, throwable)
            val stackTrace = throwable.stackTraceToString().take(500)
            DebugLogBuffer.add("ERROR", tag, "$message\n$stackTrace")
        }
    }
}
