package ai.ciris.mobile.shared.platform

/**
 * iOS implementation of AppRestarter.
 *
 * iOS doesn't allow apps to restart themselves in the same way as Android.
 * This is a stub implementation that logs the request.
 */
actual object AppRestarter {

    actual fun restartApp() {
        // iOS doesn't allow apps to programmatically restart themselves
        // The user would need to manually close and reopen the app
        println("[AppRestarter.ios] restartApp called - iOS cannot programmatically restart apps")
        println("[AppRestarter.ios] Please close and reopen the app to complete the reset")
    }
}
