package ai.ciris.mobile.shared.platform

/**
 * iOS implementation of PlatformLogger using println for console output.
 * Logs are also stored in the debug buffer for UI display.
 *
 * Note: NSLog with varargs crashes in Kotlin/Native, so we use println instead.
 * println output still appears in Xcode console and system logs.
 */
actual object PlatformLogger {
    actual fun d(tag: String, message: String) {
        println("D/$tag: $message")
        DebugLogBuffer.add("DEBUG", tag, message)
    }

    actual fun i(tag: String, message: String) {
        println("I/$tag: $message")
        DebugLogBuffer.add("INFO", tag, message)
    }

    actual fun w(tag: String, message: String) {
        println("⚠️ W/$tag: $message")
        DebugLogBuffer.add("WARN", tag, message)
    }

    actual fun e(tag: String, message: String) {
        println("❌ E/$tag: $message")
        DebugLogBuffer.add("ERROR", tag, message)
    }

    actual fun e(tag: String, message: String, throwable: Throwable) {
        val stackTrace = throwable.stackTraceToString().take(500)
        println("❌ E/$tag: $message\n$stackTrace")
        DebugLogBuffer.add("ERROR", tag, "$message\n$stackTrace")
    }
}
