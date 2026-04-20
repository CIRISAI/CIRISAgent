package ai.ciris.mobile.shared.auth

/**
 * First-run detection for CIRIS mobile apps
 *
 * Determines whether the app needs to show the setup wizard on first launch.
 * This is based on checking for the existence of the CIRIS_HOME/.env file,
 * which is created during the setup process.
 *
 * Source logic from:
 * - android/app/src/main/java/ai/ciris/mobile/MainActivity.kt (lines 1859-1885) - checkSetupStatus
 * - android/app/src/main/java/ai/ciris/mobile/MainActivity.kt (lines 2842-2854) - .env file check
 * - android/app/src/main/java/ai/ciris/mobile/MainActivity.kt (lines 1720-1731, 1775-1786) - First-run handling
 *
 * Key concepts:
 * - First run: No .env file exists → show setup wizard
 * - Returning user: .env file exists → skip to authentication/main app
 * - Setup completion: Creates .env file with configuration
 */
expect class FirstRunDetector {

    /**
     * Check if this is the first run and setup is required
     *
     * Two-phase detection:
     * 1. Check local filesystem for CIRIS_HOME/.env
     * 2. Optionally verify with backend API /v1/setup/status
     *
     * Source: MainActivity.kt lines 1859-1885, 2842-2854
     *
     * @param cirisHomePath Path to CIRIS_HOME directory
     * @return true if setup wizard should be shown, false if setup is complete
     */
    suspend fun isFirstRunNeeded(cirisHomePath: String): Boolean

    /**
     * Check if setup is required by querying the backend API
     *
     * This provides the authoritative answer from the backend, but requires
     * the Python server to be running. Falls back to filesystem check if unavailable.
     *
     * Source: MainActivity.kt lines 1859-1885 (checkSetupStatus)
     *
     * @param serverUrl The API server URL (e.g., "http://127.0.0.1:8000")
     * @return true if setup is required according to backend, false if complete
     */
    suspend fun checkSetupStatusFromApi(serverUrl: String): Boolean

    /**
     * Check if .env file exists in CIRIS_HOME
     *
     * This is the primary indicator of first-run vs returning user.
     * The .env file is created by the setup wizard and contains configuration.
     *
     * Source: MainActivity.kt lines 2843-2854
     *
     * @param cirisHomePath Path to CIRIS_HOME directory
     * @return true if .env file exists, false otherwise
     */
    suspend fun envFileExists(cirisHomePath: String): Boolean

    /**
     * Get the path to the .env file
     *
     * @param cirisHomePath Path to CIRIS_HOME directory
     * @return Full path to .env file
     */
    fun getEnvFilePath(cirisHomePath: String): String
}

/**
 * Factory function to create platform-specific FirstRunDetector instance
 *
 * Usage:
 * ```kotlin
 * val detector = createFirstRunDetector()
 * val needsSetup = detector.isFirstRunNeeded("/path/to/ciris_home")
 * ```
 */
expect fun createFirstRunDetector(): FirstRunDetector

/**
 * Result of first-run detection
 */
data class FirstRunStatus(
    /**
     * Whether setup wizard should be shown
     */
    val setupRequired: Boolean,

    /**
     * Whether check was performed via API (true) or filesystem only (false)
     */
    val checkedViaApi: Boolean,

    /**
     * Whether .env file exists locally
     */
    val envFileExists: Boolean,

    /**
     * Optional error message if detection failed
     */
    val error: String? = null
)
