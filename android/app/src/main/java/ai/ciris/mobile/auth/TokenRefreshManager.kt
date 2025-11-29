package ai.ciris.mobile.auth

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Manages Google ID token refresh for ciris.ai LLM proxy authentication.
 *
 * Google ID tokens expire in ~1 hour. This manager:
 * 1. Periodically refreshes tokens (every 45 minutes)
 * 2. Monitors for 401 signals from Python LLM service
 * 3. Updates .env file with fresh tokens
 */
class TokenRefreshManager(
    private val context: Context,
    private val googleSignInHelper: GoogleSignInHelper,
    private val onTokenRefreshed: ((String) -> Unit)? = null
) {
    companion object {
        private const val TAG = "TokenRefreshManager"

        // Refresh interval: 45 minutes (before 1-hour expiry)
        private const val REFRESH_INTERVAL_MS = 45L * 60L * 1000L

        // Signal file check interval: 10 seconds
        private const val SIGNAL_CHECK_INTERVAL_MS = 10L * 1000L

        // Signal file name (written by Python LLM service on 401)
        private const val TOKEN_REFRESH_SIGNAL_FILE = ".token_refresh_needed"
    }

    private val handler = Handler(Looper.getMainLooper())
    private var isRunning = false
    private var cirisHome: File? = null
    private var lastSignalTimestamp: Long = 0

    // Runnable for periodic token refresh
    private val periodicRefreshRunnable = object : Runnable {
        override fun run() {
            if (isRunning) {
                Log.i(TAG, "Periodic token refresh triggered")
                refreshToken()
                handler.postDelayed(this, REFRESH_INTERVAL_MS)
            }
        }
    }

    // Runnable for signal file monitoring
    private val signalMonitorRunnable = object : Runnable {
        override fun run() {
            if (isRunning) {
                checkForRefreshSignal()
                handler.postDelayed(this, SIGNAL_CHECK_INTERVAL_MS)
            }
        }
    }

    /**
     * Start the token refresh manager.
     * @param cirisHomePath Path to CIRIS_HOME directory (for signal file monitoring)
     * @param refreshImmediately If true, refresh token immediately on startup (for ciris.ai providers)
     */
    fun start(cirisHomePath: String?, refreshImmediately: Boolean = true) {
        if (isRunning) {
            Log.w(TAG, "TokenRefreshManager already running")
            return
        }

        isRunning = true
        cirisHome = cirisHomePath?.let { File(it) }

        Log.i(TAG, "Starting TokenRefreshManager")
        Log.i(TAG, "  - CIRIS_HOME: $cirisHomePath")
        Log.i(TAG, "  - Refresh interval: ${REFRESH_INTERVAL_MS / 1000 / 60} minutes")
        Log.i(TAG, "  - Signal check interval: ${SIGNAL_CHECK_INTERVAL_MS / 1000} seconds")
        Log.i(TAG, "  - Refresh immediately: $refreshImmediately")

        // For ciris.ai providers, refresh token immediately on startup
        // The stored token may be hours/days old and already expired
        if (refreshImmediately) {
            Log.i(TAG, "Performing immediate token refresh on startup")
            refreshToken()
        }

        // Start periodic refresh (first refresh in 45 minutes)
        handler.postDelayed(periodicRefreshRunnable, REFRESH_INTERVAL_MS)

        // Start signal file monitoring (check every 10 seconds)
        if (cirisHome != null) {
            handler.postDelayed(signalMonitorRunnable, SIGNAL_CHECK_INTERVAL_MS)
        }
    }

    /**
     * Stop the token refresh manager.
     */
    fun stop() {
        Log.i(TAG, "Stopping TokenRefreshManager")
        isRunning = false
        handler.removeCallbacks(periodicRefreshRunnable)
        handler.removeCallbacks(signalMonitorRunnable)
    }

    /**
     * Manually trigger a token refresh.
     */
    fun refreshToken() {
        Log.i(TAG, "Refreshing Google ID token via silentSignIn...")

        googleSignInHelper.silentSignIn { result ->
            when (result) {
                is GoogleSignInHelper.SignInResult.Success -> {
                    val newIdToken = result.account.idToken
                    if (newIdToken != null) {
                        Log.i(TAG, "Token refresh successful - new token obtained")
                        handleNewToken(newIdToken)
                    } else {
                        Log.w(TAG, "Token refresh returned null ID token")
                    }
                }
                is GoogleSignInHelper.SignInResult.Error -> {
                    Log.e(TAG, "Token refresh failed: ${result.statusCode} - ${result.message}")
                }
            }
        }
    }

    /**
     * Check for refresh signal file from Python LLM service.
     */
    private fun checkForRefreshSignal() {
        val signalFile = cirisHome?.let { File(it, TOKEN_REFRESH_SIGNAL_FILE) } ?: return

        if (signalFile.exists()) {
            try {
                val signalContent = signalFile.readText().trim()
                val signalTimestamp = signalContent.toDoubleOrNull()?.toLong() ?: 0

                // Only process if this is a new signal
                if (signalTimestamp > lastSignalTimestamp) {
                    Log.i(TAG, "401 refresh signal detected (timestamp: $signalTimestamp)")
                    lastSignalTimestamp = signalTimestamp

                    // Delete the signal file
                    signalFile.delete()

                    // Trigger token refresh
                    refreshToken()
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error reading signal file: ${e.message}")
            }
        }
    }

    /**
     * Handle a newly obtained token.
     */
    private fun handleNewToken(idToken: String) {
        Log.i(TAG, "Processing new ID token (length: ${idToken.length})")

        // Update the .env file with new token
        CoroutineScope(Dispatchers.IO).launch {
            updateEnvFile(idToken)

            withContext(Dispatchers.Main) {
                // Notify callback
                onTokenRefreshed?.invoke(idToken)
            }
        }
    }

    /**
     * Update the .env file with a new API key (ID token).
     * Also updates CIRIS_BILLING_GOOGLE_ID_TOKEN if present (for CIRIS proxy billing).
     */
    private fun updateEnvFile(newIdToken: String) {
        val envFile = cirisHome?.let { File(it, ".env") } ?: run {
            Log.w(TAG, "Cannot update .env - CIRIS_HOME not set")
            return
        }

        if (!envFile.exists()) {
            Log.w(TAG, ".env file not found at: ${envFile.absolutePath}")
            return
        }

        try {
            var content = envFile.readText()

            // Replace the OPENAI_API_KEY value
            // Match both quoted and unquoted formats
            val openaiPatterns = listOf(
                Regex("""OPENAI_API_KEY="[^"]*""""),
                Regex("""OPENAI_API_KEY='[^']*'"""),
                Regex("""OPENAI_API_KEY=[^\n]*""")
            )

            var updated = false
            for (pattern in openaiPatterns) {
                if (pattern.containsMatchIn(content)) {
                    content = pattern.replace(content, """OPENAI_API_KEY="$newIdToken"""")
                    updated = true
                    break
                }
            }

            // Also update CIRIS_BILLING_GOOGLE_ID_TOKEN if present (same token used for billing JWT auth)
            val billingPatterns = listOf(
                Regex("""CIRIS_BILLING_GOOGLE_ID_TOKEN="[^"]*""""),
                Regex("""CIRIS_BILLING_GOOGLE_ID_TOKEN='[^']*'"""),
                Regex("""CIRIS_BILLING_GOOGLE_ID_TOKEN=[^\n]*""")
            )

            for (pattern in billingPatterns) {
                if (pattern.containsMatchIn(content)) {
                    content = pattern.replace(content, """CIRIS_BILLING_GOOGLE_ID_TOKEN="$newIdToken"""")
                    Log.i(TAG, "Also updated CIRIS_BILLING_GOOGLE_ID_TOKEN")
                    break
                }
            }

            if (updated) {
                envFile.writeText(content)
                Log.i(TAG, ".env file updated with new ID token")

                // Also trigger Python to reload the config
                triggerPythonConfigReload()
            } else {
                Log.w(TAG, "OPENAI_API_KEY not found in .env file")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to update .env file: ${e.message}")
        }
    }

    /**
     * Signal Python runtime to reload configuration.
     * Writes a reload signal file that Python can watch.
     */
    private fun triggerPythonConfigReload() {
        val reloadFile = cirisHome?.let { File(it, ".config_reload") } ?: return

        try {
            reloadFile.writeText(System.currentTimeMillis().toString())
            Log.i(TAG, "Config reload signal written")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to write config reload signal: ${e.message}")
        }
    }
}
