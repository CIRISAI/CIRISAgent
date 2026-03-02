package ai.ciris.mobile.shared.platform

actual object PlatformLogger {
    actual fun d(tag: String, message: String) {
        if (LogConfig.minLevel.priority <= LogLevel.DEBUG.priority) {
            println("[DEBUG][$tag] $message")
        }
    }

    actual fun i(tag: String, message: String) {
        if (LogConfig.minLevel.priority <= LogLevel.INFO.priority) {
            println("[INFO][$tag] $message")
        }
    }

    actual fun w(tag: String, message: String) {
        if (LogConfig.minLevel.priority <= LogLevel.WARN.priority) {
            println("[WARN][$tag] $message")
        }
    }

    actual fun e(tag: String, message: String) {
        if (LogConfig.minLevel.priority <= LogLevel.ERROR.priority) {
            System.err.println("[ERROR][$tag] $message")
        }
    }

    actual fun e(tag: String, message: String, throwable: Throwable) {
        if (LogConfig.minLevel.priority <= LogLevel.ERROR.priority) {
            System.err.println("[ERROR][$tag] $message")
            throwable.printStackTrace()
        }
    }
}
