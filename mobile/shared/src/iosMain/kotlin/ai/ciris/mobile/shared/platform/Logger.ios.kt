package ai.ciris.mobile.shared.platform

/**
 * iOS implementation of PlatformLogger using println for console output.
 * Logs are also stored in the debug buffer for UI display.
 * Respects LogConfig.minLevel for filtering.
 *
 * Note: NSLog with varargs crashes in Kotlin/Native, so we use println instead.
 * println output still appears in Xcode console and system logs.
 */
actual object PlatformLogger {
    actual fun d(tag: String, message: String) {
        if (LogConfig.minLevel.priority <= LogLevel.DEBUG.priority) {
            println("D/$tag: $message")
            DebugLogBuffer.add("DEBUG", tag, message)
            KMPFileLogger.log("DEBUG", tag, message)
        }
    }

    actual fun i(tag: String, message: String) {
        if (LogConfig.minLevel.priority <= LogLevel.INFO.priority) {
            println("I/$tag: $message")
            DebugLogBuffer.add("INFO", tag, message)
            KMPFileLogger.log("INFO", tag, message)
        }
    }

    actual fun w(tag: String, message: String) {
        if (LogConfig.minLevel.priority <= LogLevel.WARN.priority) {
            println("W/$tag: $message")
            DebugLogBuffer.add("WARN", tag, message)
            KMPFileLogger.log("WARN", tag, message)
        }
    }

    actual fun e(tag: String, message: String) {
        if (LogConfig.minLevel.priority <= LogLevel.ERROR.priority) {
            println("E/$tag: $message")
            DebugLogBuffer.add("ERROR", tag, message)
            KMPFileLogger.log("ERROR", tag, message)
        }
    }

    actual fun e(tag: String, message: String, throwable: Throwable) {
        if (LogConfig.minLevel.priority <= LogLevel.ERROR.priority) {
            val stackTrace = throwable.stackTraceToString().take(500)
            println("E/$tag: $message\n$stackTrace")
            DebugLogBuffer.add("ERROR", tag, "$message\n$stackTrace")
            KMPFileLogger.log("ERROR", tag, "$message\n$stackTrace")
        }
    }
}
