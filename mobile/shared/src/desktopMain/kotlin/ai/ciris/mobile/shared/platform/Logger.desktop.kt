package ai.ciris.mobile.shared.platform

actual object PlatformLogger {
    actual fun d(tag: String, message: String) {
        println("[DEBUG][$tag] $message")
    }

    actual fun i(tag: String, message: String) {
        println("[INFO][$tag] $message")
    }

    actual fun w(tag: String, message: String) {
        println("[WARN][$tag] $message")
    }

    actual fun e(tag: String, message: String) {
        System.err.println("[ERROR][$tag] $message")
    }

    actual fun e(tag: String, message: String, throwable: Throwable) {
        System.err.println("[ERROR][$tag] $message")
        throwable.printStackTrace()
    }
}
