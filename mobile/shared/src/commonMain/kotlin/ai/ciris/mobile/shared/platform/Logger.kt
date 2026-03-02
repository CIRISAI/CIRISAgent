package ai.ciris.mobile.shared.platform

/**
 * Log level configuration for KMP logging.
 */
enum class LogLevel(val priority: Int) {
    DEBUG(0),
    INFO(1),
    WARN(2),
    ERROR(3),
    NONE(4)
}

/**
 * Global log level configuration.
 * Default is INFO for release builds (suppresses DEBUG).
 */
object LogConfig {
    var minLevel: LogLevel = LogLevel.INFO
}

/**
 * Platform-specific logger for KMP.
 * On Android, uses android.util.Log for logcat output.
 * On other platforms, uses println.
 */
expect object PlatformLogger {
    fun d(tag: String, message: String)
    fun i(tag: String, message: String)
    fun w(tag: String, message: String)
    fun e(tag: String, message: String)
    fun e(tag: String, message: String, throwable: Throwable)
}
