package ai.ciris.mobile.shared.diagnostics

import android.util.Log

actual fun platformLog(tag: String, message: String) {
    Log.i(tag, message)
}
