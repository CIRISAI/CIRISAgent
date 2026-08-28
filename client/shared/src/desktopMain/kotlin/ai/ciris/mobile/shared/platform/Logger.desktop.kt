package ai.ciris.mobile.shared.platform

/**
 * Desktop logger.
 *
 * Feeds DebugLogBuffer as well as stdout and the file log. It previously did
 * not, and Android/iOS did — so the in-app diagnostics bundle rendered an empty
 * "Recent log buffer" on desktop for the entire process lifetime, not merely
 * after a restart. The download/copy affordance was therefore useless on the
 * platform where a stuck install is hardest to inspect.
 */
actual object PlatformLogger {
    actual fun d(tag: String, message: String) {
        if (LogConfig.minLevel.priority <= LogLevel.DEBUG.priority) {
            println("[DEBUG][$tag] $message")
            DebugLogBuffer.add("DEBUG", tag, message)
            KMPFileLogger.log("DEBUG", tag, message)
        }
    }

    actual fun i(tag: String, message: String) {
        if (LogConfig.minLevel.priority <= LogLevel.INFO.priority) {
            println("[INFO][$tag] $message")
            DebugLogBuffer.add("INFO", tag, message)
            KMPFileLogger.log("INFO", tag, message)
        }
    }

    actual fun w(tag: String, message: String) {
        if (LogConfig.minLevel.priority <= LogLevel.WARN.priority) {
            println("[WARN][$tag] $message")
            DebugLogBuffer.add("WARN", tag, message)
            KMPFileLogger.log("WARN", tag, message)
        }
    }

    actual fun e(tag: String, message: String) {
        if (LogConfig.minLevel.priority <= LogLevel.ERROR.priority) {
            System.err.println("[ERROR][$tag] $message")
            DebugLogBuffer.add("ERROR", tag, message)
            KMPFileLogger.log("ERROR", tag, message)
        }
    }

    actual fun e(tag: String, message: String, throwable: Throwable) {
        if (LogConfig.minLevel.priority <= LogLevel.ERROR.priority) {
            System.err.println("[ERROR][$tag] $message")
            throwable.printStackTrace()
            val stackTrace = throwable.stackTraceToString().take(500)
            DebugLogBuffer.add("ERROR", tag, "$message\n$stackTrace")
            KMPFileLogger.log("ERROR", tag, "$message\n$stackTrace")
        }
    }
}
