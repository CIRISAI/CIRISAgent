package ai.ciris.mobile.shared.platform

/**
 * iOS implementation of PlatformLogger using println (NSLog could be used for better output).
 */
actual object PlatformLogger {
    actual fun d(tag: String, message: String) {
        println("D/$tag: $message")
    }

    actual fun i(tag: String, message: String) {
        println("I/$tag: $message")
    }

    actual fun w(tag: String, message: String) {
        println("W/$tag: $message")
    }

    actual fun e(tag: String, message: String) {
        println("E/$tag: $message")
    }

    actual fun e(tag: String, message: String, throwable: Throwable) {
        println("E/$tag: $message\n${throwable.stackTraceToString()}")
    }
}
