package ai.ciris.mobile.shared.diagnostics

actual fun platformLog(tag: String, message: String) {
    println("$tag: $message")
}
