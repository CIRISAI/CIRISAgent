package ai.ciris.mobile.auth

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.util.Base64
import android.util.Log
import com.google.android.gms.auth.api.signin.GoogleSignIn
import com.google.android.gms.auth.api.signin.GoogleSignInAccount
import com.google.android.gms.auth.api.signin.GoogleSignInClient
import com.google.android.gms.auth.api.signin.GoogleSignInOptions
import com.google.android.gms.common.api.ApiException
import com.google.android.gms.tasks.Task
import org.json.JSONObject

/**
 * Helper for Google Sign-In authentication.
 *
 * The Google user ID is used for CIRIS LLM proxy authentication:
 * Authorization: Bearer google:{user_id}
 */
class GoogleSignInHelper(private val context: Context) {

    companion object {
        private const val TAG = "GoogleSignInHelper"
        const val RC_SIGN_IN = 9001

        // Web client ID from Google Cloud Console (CIRIS Mobile)
        private const val WEB_CLIENT_ID = "265882853697-l421ndojcs5nm7lkln53jj29kf7kck91.apps.googleusercontent.com"

        // Minimum token validity in seconds - if token expires sooner, force refresh
        // Set to 5 minutes to ensure token is valid for the entire session
        private const val MIN_TOKEN_VALIDITY_SECONDS = 300L
    }

    private val googleSignInClient: GoogleSignInClient

    init {
        val gso = GoogleSignInOptions.Builder(GoogleSignInOptions.DEFAULT_SIGN_IN)
            .requestIdToken(WEB_CLIENT_ID)
            .requestEmail()
            .requestProfile()
            .build()

        googleSignInClient = GoogleSignIn.getClient(context, gso)
    }

    /**
     * Get the currently signed-in account, if any.
     */
    fun getLastSignedInAccount(): GoogleSignInAccount? {
        return GoogleSignIn.getLastSignedInAccount(context)
    }

    /**
     * Check if user is signed in.
     */
    fun isSignedIn(): Boolean {
        return getLastSignedInAccount() != null
    }

    /**
     * Get the Google user ID for CIRIS proxy authentication.
     * Returns null if not signed in.
     */
    fun getGoogleUserId(): String? {
        return getLastSignedInAccount()?.id
    }

    /**
     * Get the Google ID token for native token exchange.
     * This token can be sent to the server to verify the user's identity.
     * Returns null if not signed in.
     */
    fun getIdToken(): String? {
        return getLastSignedInAccount()?.idToken
    }

    /**
     * Get the user's email address.
     */
    fun getUserEmail(): String? {
        return getLastSignedInAccount()?.email
    }

    /**
     * Get the user's display name.
     */
    fun getUserDisplayName(): String? {
        return getLastSignedInAccount()?.displayName
    }

    /**
     * Get the user's profile photo URL.
     */
    fun getUserPhotoUrl(): String? {
        return getLastSignedInAccount()?.photoUrl?.toString()
    }

    /**
     * Get the sign-in intent to start the Google Sign-In flow.
     * Call this from your activity and start it with startActivityForResult().
     */
    fun getSignInIntent(): Intent {
        return googleSignInClient.signInIntent
    }

    /**
     * Handle the result from the sign-in intent.
     * Call this from onActivityResult().
     *
     * @return SignInResult with success status and account/error info
     */
    fun handleSignInResult(data: Intent?): SignInResult {
        val task: Task<GoogleSignInAccount> = GoogleSignIn.getSignedInAccountFromIntent(data)
        return try {
            val account = task.getResult(ApiException::class.java)
            Log.i(TAG, "Sign-in successful: ${account.email}")
            SignInResult.Success(account)
        } catch (e: ApiException) {
            Log.e(TAG, "Sign-in failed: ${e.statusCode} - ${e.message}")
            SignInResult.Error(e.statusCode, e.message)
        }
    }

    /**
     * Sign out the current user.
     */
    fun signOut(onComplete: () -> Unit = {}) {
        googleSignInClient.signOut().addOnCompleteListener {
            Log.i(TAG, "Sign-out complete")
            onComplete()
        }
    }

    /**
     * Revoke access (disconnect the app from the user's Google account).
     */
    fun revokeAccess(onComplete: () -> Unit = {}) {
        googleSignInClient.revokeAccess().addOnCompleteListener {
            Log.i(TAG, "Access revoked")
            onComplete()
        }
    }

    /**
     * Log token diagnostics without exposing the actual token.
     * Safe for release builds - logs only metadata useful for debugging.
     */
    fun logTokenDiagnostics(source: String, idToken: String?) {
        if (idToken == null) {
            Log.w(TAG, "[TokenDiag:$source] Token is NULL")
            return
        }

        val expiry = getTokenExpiry(idToken)
        val nowSeconds = System.currentTimeMillis() / 1000
        val remainingSeconds = expiry?.let { it - nowSeconds }
        val isExpired = remainingSeconds != null && remainingSeconds <= 0

        // Generate a short hash of the token for correlation (first 8 chars of SHA-256)
        val tokenHash = try {
            val digest = java.security.MessageDigest.getInstance("SHA-256")
            val hash = digest.digest(idToken.toByteArray())
            hash.take(4).joinToString("") { "%02x".format(it) }
        } catch (e: Exception) { "????????" }

        Log.i(TAG, "[TokenDiag:$source] length=${idToken.length}, hash=$tokenHash, " +
                "expiry=${expiry ?: "unknown"}, remaining=${remainingSeconds ?: "unknown"}s, " +
                "expired=$isExpired")
    }

    /**
     * Get the expiry time (in seconds since epoch) from a JWT token.
     * Returns null if parsing fails.
     */
    fun getTokenExpiry(idToken: String): Long? {
        return try {
            // JWT has 3 parts: header.payload.signature
            val parts = idToken.split(".")
            if (parts.size != 3) {
                Log.w(TAG, "Invalid JWT format: expected 3 parts, got ${parts.size}")
                return null
            }

            // Decode the payload (second part)
            val payload = String(Base64.decode(parts[1], Base64.URL_SAFE or Base64.NO_WRAP))
            val json = JSONObject(payload)
            val exp = json.optLong("exp", 0L)

            if (exp > 0) {
                Log.d(TAG, "Token expiry: $exp (${(exp - System.currentTimeMillis() / 1000)}s remaining)")
                exp
            } else {
                Log.w(TAG, "No 'exp' claim in JWT payload")
                null
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse JWT: ${e.message}")
            null
        }
    }

    /**
     * Check if a token has sufficient validity remaining.
     * Returns true if token expires in more than MIN_TOKEN_VALIDITY_SECONDS.
     */
    private fun isTokenValid(idToken: String?): Boolean {
        if (idToken == null) return false

        val expiry = getTokenExpiry(idToken) ?: return false
        val nowSeconds = System.currentTimeMillis() / 1000
        val remainingSeconds = expiry - nowSeconds

        Log.d(TAG, "Token validity check: ${remainingSeconds}s remaining, need ${MIN_TOKEN_VALIDITY_SECONDS}s")
        return remainingSeconds > MIN_TOKEN_VALIDITY_SECONDS
    }

    /**
     * Silent sign-in attempt (no UI).
     * Use this to restore sign-in state on app launch.
     *
     * If the cached token is close to expiry (< 5 minutes), this will
     * clear the cached auth and force a fresh sign-in to get a new token.
     */
    fun silentSignIn(onResult: (SignInResult) -> Unit) {
        // First, check if cached token is still valid
        val cachedAccount = getLastSignedInAccount()
        val cachedToken = cachedAccount?.idToken

        if (cachedToken != null && isTokenValid(cachedToken)) {
            Log.i(TAG, "Cached token still valid, using it")
            onResult(SignInResult.Success(cachedAccount))
            return
        }

        if (cachedToken != null) {
            Log.i(TAG, "Cached token expired or close to expiry, forcing fresh sign-in")
            // Clear the cached account to force Google to fetch a fresh token
            googleSignInClient.signOut().addOnCompleteListener {
                Log.d(TAG, "Cleared cached auth, now performing silent sign-in")
                performSilentSignIn(onResult)
            }
        } else {
            Log.i(TAG, "No cached token, performing silent sign-in")
            performSilentSignIn(onResult)
        }
    }

    /**
     * Internal method to perform the actual silent sign-in.
     */
    private fun performSilentSignIn(onResult: (SignInResult) -> Unit) {
        googleSignInClient.silentSignIn()
            .addOnSuccessListener { account ->
                val token = account.idToken
                if (token != null) {
                    val expiry = getTokenExpiry(token)
                    val remaining = expiry?.let { it - System.currentTimeMillis() / 1000 }
                    Log.i(TAG, "Silent sign-in successful: ${account.email}, token valid for ${remaining}s")
                } else {
                    Log.i(TAG, "Silent sign-in successful: ${account.email} (no ID token)")
                }
                onResult(SignInResult.Success(account))
            }
            .addOnFailureListener { e ->
                // Extract error code for better diagnostics
                val errorCode = if (e is ApiException) e.statusCode else -1
                val errorDescription = when (errorCode) {
                    4 -> "SIGN_IN_REQUIRED - User needs to interactively sign in"
                    7 -> "NETWORK_ERROR - Network unavailable"
                    8 -> "INTERNAL_ERROR - Internal error in Google Play services"
                    12500 -> "SIGN_IN_CANCELLED - Sign in was cancelled"
                    12501 -> "SIGN_IN_CURRENTLY_IN_PROGRESS - Sign in already in progress"
                    12502 -> "SIGN_IN_FAILED - Sign in failed"
                    else -> "Unknown error"
                }
                Log.w(TAG, "Silent sign-in failed: code=$errorCode ($errorDescription), message=${e.message}")
                onResult(SignInResult.Error(errorCode, "$errorCode: ${e.message}"))
            }
    }

    sealed class SignInResult {
        data class Success(val account: GoogleSignInAccount) : SignInResult()
        data class Error(val statusCode: Int, val message: String?) : SignInResult()
    }
}
