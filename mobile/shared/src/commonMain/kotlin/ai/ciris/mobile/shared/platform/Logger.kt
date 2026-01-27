package ai.ciris.mobile.shared.platform

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
