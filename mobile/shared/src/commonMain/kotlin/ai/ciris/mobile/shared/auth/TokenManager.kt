package ai.ciris.mobile.shared.auth

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import kotlin.io.encoding.Base64
import kotlin.io.encoding.ExperimentalEncodingApi

/**
 * Token Manager for handling Google ID token refresh.
 *
 * Google ID tokens expire in ~1 hour. This manager:
 * 1. Checks token expiry on startup
 * 2. Triggers silent sign-in when token is stale (< 5 minutes remaining)
 * 3. Periodically refreshes tokens (every 45 minutes)
 * 4. Handles 401 errors by triggering token refresh
 *
 * Ported from android/app/.../auth/TokenRefreshManager.kt
 */
class TokenManager(
    private val scope: CoroutineScope = CoroutineScope(Dispatchers.Default + SupervisorJob())
) {
    companion object {
        private const val TAG = "TokenManager"

        // Minimum token validity in seconds - if token expires sooner, force refresh
        private const val MIN_TOKEN_VALIDITY_SECONDS = 300L // 5 minutes

        // Refresh interval: 45 minutes (before 1-hour expiry)
        private const val REFRESH_INTERVAL_MS = 45L * 60L * 1000L
    }

    private fun log(level: String, method: String, message: String) {
        println("[$TAG][$level][$method] $message")
    }

    private fun logDebug(method: String, message: String) = log("DEBUG", method, message)
    private fun logInfo(method: String, message: String) = log("INFO", method, message)
    private fun logWarn(method: String, message: String) = log("WARN", method, message)
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    // Current token state
    private val _currentToken = MutableStateFlow<String?>(null)
    val currentToken: StateFlow<String?> = _currentToken.asStateFlow()

    private val _tokenState = MutableStateFlow(TokenState.UNKNOWN)
    val tokenState: StateFlow<TokenState> = _tokenState.asStateFlow()

    private val _needsInteractiveLogin = MutableStateFlow(false)
    val needsInteractiveLogin: StateFlow<Boolean> = _needsInteractiveLogin.asStateFlow()

    // Callback for silent sign-in
    private var silentSignInCallback: (suspend () -> SilentSignInResult)? = null

    // Callback for when token is refreshed
    private var onTokenRefreshed: ((String) -> Unit)? = null

    // Periodic refresh job
    private var refreshJob: Job? = null

    /**
     * Set the callback for performing silent sign-in.
     * This should be provided by the platform-specific code.
     */
    fun setSilentSignInCallback(callback: suspend () -> SilentSignInResult) {
        silentSignInCallback = callback
    }

    /**
     * Set the callback for when a token is successfully refreshed.
     */
    fun setOnTokenRefreshed(callback: (String) -> Unit) {
        onTokenRefreshed = callback
    }

    /**
     * Check and refresh token if needed.
     * Call this on app startup.
     *
     * @param storedToken The token from secure storage
     * @return true if token is valid (or was refreshed), false if interactive login needed
     */
    suspend fun checkAndRefreshToken(storedToken: String?): Boolean {
        val method = "checkAndRefreshToken"

        if (storedToken == null) {
            logInfo(method, "No stored token - interactive login required")
            _tokenState.value = TokenState.MISSING
            _needsInteractiveLogin.value = true
            return false
        }

        // Check token validity
        val expiry = getTokenExpiry(storedToken)
        val nowSeconds = currentTimeSeconds()
        val remainingSeconds = expiry?.let { it - nowSeconds }

        logInfo(method, "Token check: expiry=$expiry, remaining=${remainingSeconds}s, " +
                "minValid=${MIN_TOKEN_VALIDITY_SECONDS}s")

        if (remainingSeconds == null) {
            logWarn(method, "Could not parse token expiry - treating as expired")
            return attemptSilentRefresh()
        }

        if (remainingSeconds <= 0) {
            logInfo(method, "Token is EXPIRED - attempting silent refresh")
            _tokenState.value = TokenState.EXPIRED
            return attemptSilentRefresh()
        }

        if (remainingSeconds < MIN_TOKEN_VALIDITY_SECONDS) {
            logInfo(method, "Token expires soon (${remainingSeconds}s) - proactive refresh")
            _tokenState.value = TokenState.EXPIRING_SOON
            return attemptSilentRefresh()
        }

        // Token is valid
        logInfo(method, "Token is VALID - ${remainingSeconds}s remaining")
        _tokenState.value = TokenState.VALID
        _currentToken.value = storedToken
        _needsInteractiveLogin.value = false

        // Start periodic refresh
        startPeriodicRefresh()

        return true
    }

    /**
     * Attempt silent sign-in to refresh the token.
     */
    private suspend fun attemptSilentRefresh(): Boolean {
        val method = "attemptSilentRefresh"
        val callback = silentSignInCallback

        if (callback == null) {
            logWarn(method, "No silent sign-in callback set - interactive login required")
            _needsInteractiveLogin.value = true
            return false
        }

        logInfo(method, "Attempting silent sign-in...")
        _tokenState.value = TokenState.REFRESHING

        return try {
            when (val result = callback()) {
                is SilentSignInResult.Success -> {
                    logInfo(method, "Silent sign-in successful!")
                    handleNewToken(result.idToken)
                    true
                }
                is SilentSignInResult.NeedsInteractiveLogin -> {
                    logInfo(method, "Silent sign-in requires interactive login (code: ${result.errorCode})")
                    _tokenState.value = TokenState.NEEDS_INTERACTIVE
                    _needsInteractiveLogin.value = true
                    false
                }
                is SilentSignInResult.Error -> {
                    logError(method, "Silent sign-in failed: ${result.message}")
                    _tokenState.value = TokenState.ERROR
                    _needsInteractiveLogin.value = true
                    false
                }
            }
        } catch (e: Exception) {
            logError(method, "Silent sign-in exception: ${e::class.simpleName}: ${e.message}")
            _tokenState.value = TokenState.ERROR
            _needsInteractiveLogin.value = true
            false
        }
    }

    /**
     * Handle a newly obtained token (from silent or interactive sign-in).
     */
    fun handleNewToken(idToken: String) {
        val method = "handleNewToken"
        logInfo(method, "Processing new token (length: ${idToken.length})")

        _currentToken.value = idToken
        _tokenState.value = TokenState.VALID
        _needsInteractiveLogin.value = false

        // Log token diagnostics
        val expiry = getTokenExpiry(idToken)
        val remaining = expiry?.let { it - currentTimeSeconds() }
        logInfo(method, "New token expiry: $expiry (${remaining}s remaining)")

        // Notify callback
        onTokenRefreshed?.invoke(idToken)

        // Start/restart periodic refresh
        startPeriodicRefresh()
    }

    /**
     * Handle a 401 error from an API call.
     * Triggers token refresh.
     */
    fun on401Error() {
        val method = "on401Error"
        logWarn(method, "401 error received - triggering token refresh")
        _tokenState.value = TokenState.EXPIRED

        scope.launch {
            attemptSilentRefresh()
        }
    }

    /**
     * Start periodic token refresh.
     */
    private fun startPeriodicRefresh() {
        val method = "startPeriodicRefresh"

        refreshJob?.cancel()
        refreshJob = scope.launch {
            logInfo(method, "Starting periodic refresh (interval: ${REFRESH_INTERVAL_MS / 1000 / 60} minutes)")

            while (isActive) {
                delay(REFRESH_INTERVAL_MS)
                logInfo(method, "Periodic refresh triggered")
                attemptSilentRefresh()
            }
        }
    }

    /**
     * Stop periodic refresh.
     */
    fun stopPeriodicRefresh() {
        logInfo("stopPeriodicRefresh", "Stopping periodic refresh")
        refreshJob?.cancel()
        refreshJob = null
    }

    /**
     * Clear the interactive login flag after user completes login.
     */
    fun clearInteractiveLoginNeeded() {
        _needsInteractiveLogin.value = false
    }

    /**
     * Get the expiry time (in seconds since epoch) from a JWT token.
     * Returns null if parsing fails.
     */
    @OptIn(ExperimentalEncodingApi::class)
    fun getTokenExpiry(idToken: String): Long? {
        val method = "getTokenExpiry"
        return try {
            // JWT has 3 parts: header.payload.signature
            val parts = idToken.split(".")
            if (parts.size != 3) {
                logWarn(method, "Invalid JWT format: expected 3 parts, got ${parts.size}")
                return null
            }

            // Decode the payload (second part) - use URL-safe base64
            val payloadBase64 = parts[1]
                .replace('-', '+')
                .replace('_', '/')

            // Add padding if needed
            val paddedPayload = when (payloadBase64.length % 4) {
                2 -> "$payloadBase64=="
                3 -> "$payloadBase64="
                else -> payloadBase64
            }

            val payloadBytes = Base64.decode(paddedPayload)
            val payload = payloadBytes.decodeToString()

            val json = Json { ignoreUnknownKeys = true }
            val jsonObj = json.parseToJsonElement(payload).jsonObject
            val exp = jsonObj["exp"]?.jsonPrimitive?.long

            if (exp != null && exp > 0) {
                logDebug(method, "Token expiry: $exp (${exp - currentTimeSeconds()}s remaining)")
                exp
            } else {
                logWarn(method, "No 'exp' claim in JWT payload")
                null
            }
        } catch (e: Exception) {
            logError(method, "Failed to parse JWT: ${e::class.simpleName}: ${e.message}")
            null
        }
    }

    /**
     * Check if a token is valid (has sufficient time remaining).
     */
    fun isTokenValid(idToken: String?): Boolean {
        if (idToken == null) return false

        val expiry = getTokenExpiry(idToken) ?: return false
        val remainingSeconds = expiry - currentTimeSeconds()

        logDebug("isTokenValid", "Token validity: ${remainingSeconds}s remaining, need ${MIN_TOKEN_VALIDITY_SECONDS}s")
        return remainingSeconds > MIN_TOKEN_VALIDITY_SECONDS
    }

    private fun currentTimeSeconds(): Long = System.currentTimeMillis() / 1000

    /**
     * Clean up resources.
     */
    fun cleanup() {
        logInfo("cleanup", "Cleaning up TokenManager")
        stopPeriodicRefresh()
        scope.cancel()
    }
}

/**
 * Token validity state.
 */
enum class TokenState {
    UNKNOWN,
    VALID,
    EXPIRING_SOON,
    EXPIRED,
    REFRESHING,
    NEEDS_INTERACTIVE,
    MISSING,
    ERROR
}

/**
 * Result of silent sign-in attempt.
 */
sealed class SilentSignInResult {
    data class Success(val idToken: String, val email: String? = null) : SilentSignInResult()
    data class NeedsInteractiveLogin(val errorCode: Int) : SilentSignInResult()
    data class Error(val message: String, val errorCode: Int = -1) : SilentSignInResult()
}
