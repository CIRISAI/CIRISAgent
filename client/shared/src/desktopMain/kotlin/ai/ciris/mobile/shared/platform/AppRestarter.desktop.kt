package ai.ciris.mobile.shared.platform

import kotlin.system.exitProcess

actual object AppRestarter {
    actual fun restartApp() {
        // On desktop, we can't easily restart the app.
        // The user should manually restart.
        println("[AppRestarter] Please restart the application manually.")
        exitProcess(0)
    }
}
