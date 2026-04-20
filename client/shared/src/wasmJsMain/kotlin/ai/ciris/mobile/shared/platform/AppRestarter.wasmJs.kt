package ai.ciris.mobile.shared.platform

import kotlinx.browser.window

actual object AppRestarter {
    actual fun restartApp() {
        window.location.reload()
    }
}
