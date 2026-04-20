@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package ai.ciris.mobile.shared.platform

import kotlinx.cinterop.ExperimentalForeignApi
import platform.Foundation.NSFileManager
import platform.Foundation.NSHomeDirectory
import platform.Foundation.NSLog
import platform.Foundation.NSString
import platform.Foundation.NSUTF8StringEncoding
import platform.Foundation.writeToFile

/**
 * iOS implementation of AppRestarter.
 *
 * Instead of exit(0) (which looks like a crash), writes a .restart_signal
 * file that the Python watchdog thread detects. The watchdog stops the
 * event loop and kmp_main.py's restart loop brings up a fresh runtime.
 *
 * The caller (CIRISApp) navigates to Screen.Startup, and StartupViewModel
 * polls until the new runtime is healthy — seamless restart like Android.
 */
actual object AppRestarter {

    actual fun restartApp() {
        NSLog("[AppRestarter.ios] restartApp — writing .restart_signal for Python watchdog")

        val homeDir = NSHomeDirectory()
        val cirisDir = "$homeDir/Documents/ciris"
        val signalPath = "$cirisDir/.restart_signal"

        // Ensure directory exists
        NSFileManager.defaultManager.createDirectoryAtPath(
            cirisDir, withIntermediateDirectories = true, attributes = null, error = null
        )

        // Write signal file
        @Suppress("CAST_NEVER_SUCCEEDS")
        val content = "restart" as NSString
        val written = content.writeToFile(signalPath, atomically = true, encoding = NSUTF8StringEncoding, error = null)

        if (written) {
            NSLog("[AppRestarter.ios] .restart_signal written — checking if Python runtime is alive")
        } else {
            NSLog("[AppRestarter.ios] WARNING: Failed to write .restart_signal")
        }

        // Check if Python server is alive by looking for .server_ready file
        // If missing, the runtime crashed and watchdog can't read the restart signal
        val serverReadyPath = "$cirisDir/.server_ready"
        val serverAlive = NSFileManager.defaultManager.fileExistsAtPath(serverReadyPath)
        if (!serverAlive) {
            NSLog("[AppRestarter.ios] Python server not ready — falling back to exit(0)")
            platform.posix.exit(0)
        } else {
            NSLog("[AppRestarter.ios] Python server ready file exists — watchdog will handle restart")
        }
    }
}
