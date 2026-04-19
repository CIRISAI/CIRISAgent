package ai.ciris.mobile.shared.auth

import kotlinx.browser.localStorage

actual class FirstRunDetector {
    actual fun isFirstRun(): Boolean {
        return localStorage.getItem("ciris_configured") != "true"
    }

    actual fun markConfigured() {
        localStorage.setItem("ciris_configured", "true")
    }

    actual fun reset() {
        localStorage.removeItem("ciris_configured")
    }
}

actual fun createFirstRunDetector(): FirstRunDetector = FirstRunDetector()
