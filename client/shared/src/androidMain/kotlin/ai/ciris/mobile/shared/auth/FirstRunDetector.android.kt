package ai.ciris.mobile.shared.auth

import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * Android implementation of FirstRunDetector
 *
 * Uses the Android file system API to check for the existence of CIRIS_HOME/.env file.
 * Also provides API-based verification through the backend /v1/setup/status endpoint.
 *
 * Source logic extracted from:
 * - android/app/src/main/java/ai/ciris/mobile/MainActivity.kt (lines 1859-1885) - API check
 * - android/app/src/main/java/ai/ciris/mobile/MainActivity.kt (lines 2842-2854) - File check
 * - android/app/src/main/java/ai/ciris/mobile/MainActivity.kt (lines 1702, 1769) - Setup status integration
 */
actual class FirstRunDetector {

    companion object {
        private const val TAG = "FirstRunDetector"
        private const val ENV_FILE_NAME = ".env"
    }

    /**
     * Check if this is the first run and setup is required
     *
     * Strategy:
     * 1. First check if .env file exists locally (fast, offline)
     * 2. If file exists, setup is NOT required
     * 3. If file doesn't exist, setup IS required
     *
     * Source: MainActivity.kt lines 2843-2854
     */
    actual suspend fun isFirstRunNeeded(cirisHomePath: String): Boolean = withContext(Dispatchers.IO) {
        try {
            val envExists = envFileExists(cirisHomePath)
            val setupRequired = !envExists

            Log.i(TAG, "First-run check: .env exists=$envExists, setup required=$setupRequired")
            setupRequired
        } catch (e: Exception) {
            Log.e(TAG, "Error checking first-run status: ${e.message}", e)
            // If we can't check, assume setup is needed to be safe
            true
        }
    }

    /**
     * Check if setup is required by querying the backend API
     *
     * This is the authoritative source from the backend, but requires the
     * Python server to be running.
     *
     * Source: MainActivity.kt lines 1859-1885
     *
     * Response format (wrapped in SuccessResponse):
     * ```json
     * {
     *   "data": {
     *     "setup_required": true/false,
     *     ...
     *   },
     *   "metadata": {...}
     * }
     * ```
     */
    actual suspend fun checkSetupStatusFromApi(serverUrl: String): Boolean = withContext(Dispatchers.IO) {
        try {
            val url = URL("$serverUrl/v1/setup/status")
            val connection = url.openConnection() as HttpURLConnection
            connection.connectTimeout = 2000
            connection.readTimeout = 2000
            connection.requestMethod = "GET"

            val responseCode = connection.responseCode

            if (responseCode == 200) {
                val response = connection.inputStream.bufferedReader().use { it.readText() }
                connection.disconnect()

                // Parse JSON response: {"data": {"setup_required": true/false, ...}, "metadata": {...}}
                val jsonResponse = org.json.JSONObject(response)
                val data = jsonResponse.getJSONObject("data")
                val setupRequired = data.getBoolean("setup_required")

                Log.i(TAG, "Backend says setup_required=$setupRequired")
                setupRequired
            } else {
                Log.w(TAG, "Failed to get setup status from API (HTTP $responseCode)")
                connection.disconnect()
                // Fall back to filesystem check
                Log.i(TAG, "Falling back to filesystem check")
                true // Assume setup needed if API unavailable
            }
        } catch (e: Exception) {
            Log.e(TAG, "Exception checking setup status from API: ${e.message}")
            // Fall back to filesystem check
            true // Assume setup needed if API fails
        }
    }

    /**
     * Check if .env file exists in CIRIS_HOME
     *
     * The .env file is created during setup and contains configuration like:
     * - OPENAI_API_KEY
     * - OPENAI_API_BASE
     * - AGENT_NAME
     * - etc.
     *
     * Source: MainActivity.kt lines 2843-2854
     */
    actual suspend fun envFileExists(cirisHomePath: String): Boolean = withContext(Dispatchers.IO) {
        try {
            val envFile = File(cirisHomePath, ENV_FILE_NAME)
            val exists = envFile.exists()

            Log.d(TAG, "Checking .env file at: ${envFile.absolutePath}")
            Log.d(TAG, ".env file exists: $exists")

            exists
        } catch (e: Exception) {
            Log.e(TAG, "Error checking .env file: ${e.message}", e)
            false
        }
    }

    /**
     * Get the path to the .env file
     */
    actual fun getEnvFilePath(cirisHomePath: String): String {
        return File(cirisHomePath, ENV_FILE_NAME).absolutePath
    }
}

/**
 * Factory function to create FirstRunDetector instance
 */
actual fun createFirstRunDetector(): FirstRunDetector = FirstRunDetector()

/**
 * Helper function to perform comprehensive first-run detection
 *
 * This combines both filesystem and API checks to provide a complete picture.
 *
 * @param cirisHomePath Path to CIRIS_HOME directory
 * @param serverUrl API server URL (optional, for API verification)
 * @return FirstRunStatus with detailed detection results
 */
suspend fun detectFirstRunStatus(
    cirisHomePath: String,
    serverUrl: String? = null
): FirstRunStatus {
    val detector = createFirstRunDetector()

    // Always check filesystem first (fast, offline)
    val envExists = detector.envFileExists(cirisHomePath)

    // If .env exists, setup is complete (no need to check API)
    if (envExists) {
        Log.i("FirstRunDetector", "Setup complete - .env file exists")
        return FirstRunStatus(
            setupRequired = false,
            checkedViaApi = false,
            envFileExists = true
        )
    }

    // If .env doesn't exist and we have a server URL, verify with API
    if (serverUrl != null) {
        try {
            val setupRequired = detector.checkSetupStatusFromApi(serverUrl)
            Log.i("FirstRunDetector", "Setup status from API: required=$setupRequired")
            return FirstRunStatus(
                setupRequired = setupRequired,
                checkedViaApi = true,
                envFileExists = false
            )
        } catch (e: Exception) {
            Log.w("FirstRunDetector", "API check failed, falling back to filesystem check")
            return FirstRunStatus(
                setupRequired = true, // No .env file = setup needed
                checkedViaApi = false,
                envFileExists = false,
                error = "API check failed: ${e.message}"
            )
        }
    }

    // No .env file and no API check = setup needed
    Log.i("FirstRunDetector", "Setup required - no .env file found")
    return FirstRunStatus(
        setupRequired = true,
        checkedViaApi = false,
        envFileExists = false
    )
}
