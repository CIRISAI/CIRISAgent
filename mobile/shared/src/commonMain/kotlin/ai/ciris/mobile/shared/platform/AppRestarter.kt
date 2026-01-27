package ai.ciris.mobile.shared.platform

/**
 * Platform-specific utility to restart the app.
 *
 * Used when we need to fully restart the app process, such as after
 * deleting the .env file to re-run the setup wizard.
 *
 * On Android, this kills the current process and relaunches the app.
 */
expect object AppRestarter {
    /**
     * Restart the app completely.
     *
     * This will:
     * 1. Schedule a restart intent
     * 2. Kill the current process
     *
     * The app will start fresh, including any embedded Python runtime.
     */
    fun restartApp()
}
