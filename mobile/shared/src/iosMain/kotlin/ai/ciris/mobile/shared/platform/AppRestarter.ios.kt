package ai.ciris.mobile.shared.platform

import kotlinx.cinterop.ExperimentalForeignApi
import platform.Foundation.NSLog
import platform.posix.exit

/**
 * iOS implementation of AppRestarter.
 *
 * iOS doesn't allow apps to restart themselves the way Android does.
 * However, we can terminate the app, and iOS will allow the user to relaunch it.
 *
 * NOTE: Calling exit() may cause App Store rejection in release builds.
 * Apple prefers apps to handle errors gracefully rather than terminating.
 * This is primarily useful for debug/development scenarios.
 */
actual object AppRestarter {

    @OptIn(ExperimentalForeignApi::class)
    actual fun restartApp() {
        NSLog("[AppRestarter.ios] restartApp called - terminating app")
        NSLog("[AppRestarter.ios] User should tap the app icon to restart fresh")

        // Terminate the app - iOS will allow the user to relaunch
        // This ensures Python runtime starts fresh on next launch
        exit(0)
    }
}
