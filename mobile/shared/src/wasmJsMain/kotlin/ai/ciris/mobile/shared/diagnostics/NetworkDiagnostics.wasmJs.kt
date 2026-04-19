package ai.ciris.mobile.shared.diagnostics

import ai.ciris.mobile.shared.platform.platformLog

actual fun platformLog(tag: String, message: String) {
    console.log("[$tag] $message")
}
