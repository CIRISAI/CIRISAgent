package ai.ciris.mobile.shared.auth

import kotlinx.browser.localStorage

/**
 * wasmJs implementation of FirstRunDetector using browser localStorage
 *
 * Detects first-run status by checking for CIRIS configuration in localStorage.
 * Note: Browser fetch API is not fully supported in Kotlin/WASM, so we rely
 * on localStorage markers only for first-run detection.
 */
actual class FirstRunDetector {

    private val ENV_FILE_KEY = "ciris_env_file_exists"
    private val CONFIGURED_KEY = "ciris_configured"

    /**
     * Check if this is the first run and setup is required
     *
     * For browser environment, we check localStorage for the env file marker.
     * If envFileExists returns false, setup is needed.
     *
     * @param cirisHomePath Path to CIRIS_HOME directory (not used in browser)
     * @return true if setup wizard should be shown, false if setup is complete
     */
    actual suspend fun isFirstRunNeeded(cirisHomePath: String): Boolean {
        // In browser, we rely on localStorage marker for .env file
        return !envFileExists(cirisHomePath)
    }

    /**
     * Check if setup is required by querying the backend API
     *
     * For WASM, browser fetch API is not fully supported, so we fall back
     * to localStorage-based detection.
     *
     * @param serverUrl The API server URL (not used in WASM)
     * @return true if setup is required based on localStorage markers
     */
    actual suspend fun checkSetupStatusFromApi(serverUrl: String): Boolean {
        // WASM doesn't have full fetch API support, use localStorage check
        return !envFileExists("")
    }

    /**
     * Check if .env file exists in CIRIS_HOME
     *
     * For browser, we use a localStorage marker to track whether the env file exists.
     * This marker is set when setup completes.
     *
     * @param cirisHomePath Path to CIRIS_HOME directory (not used in browser)
     * @return true if .env file exists, false otherwise
     */
    actual suspend fun envFileExists(cirisHomePath: String): Boolean {
        // Check if env file marker is set in localStorage
        val exists = localStorage.getItem(ENV_FILE_KEY) == "true"

        // Also check legacy configured marker
        val configured = localStorage.getItem(CONFIGURED_KEY) == "true"

        return exists || configured
    }

    /**
     * Get the path to the .env file
     *
     * For browser, returns a virtual path since we use localStorage.
     *
     * @param cirisHomePath Path to CIRIS_HOME directory
     * @return Full path to .env file
     */
    actual fun getEnvFilePath(cirisHomePath: String): String {
        return "$cirisHomePath/.env"
    }

    /**
     * Mark that .env file has been created (helper for setup completion)
     * This is not part of the expect interface but useful for browser implementation.
     */
    fun markEnvFileCreated() {
        localStorage.setItem(ENV_FILE_KEY, "true")
        localStorage.setItem(CONFIGURED_KEY, "true")
    }

    /**
     * Reset first-run detection (helper for testing)
     * This is not part of the expect interface but useful for browser implementation.
     */
    fun reset() {
        localStorage.removeItem(ENV_FILE_KEY)
        localStorage.removeItem(CONFIGURED_KEY)
    }
}

/**
 * Factory function to create wasmJs-specific FirstRunDetector instance
 */
actual fun createFirstRunDetector(): FirstRunDetector = FirstRunDetector()
