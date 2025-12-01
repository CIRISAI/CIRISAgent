package ai.ciris.mobile.auth

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.util.Log
import com.google.android.gms.auth.api.signin.GoogleSignIn
import com.google.android.gms.auth.api.signin.GoogleSignInAccount
import com.google.android.gms.auth.api.signin.GoogleSignInClient
import com.google.android.gms.auth.api.signin.GoogleSignInOptions
import com.google.android.gms.common.api.ApiException
import com.google.android.gms.tasks.Task

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
     * Silent sign-in attempt (no UI).
     * Use this to restore sign-in state on app launch.
     */
    fun silentSignIn(onResult: (SignInResult) -> Unit) {
        googleSignInClient.silentSignIn()
            .addOnSuccessListener { account ->
                Log.i(TAG, "Silent sign-in successful: ${account.email}")
                onResult(SignInResult.Success(account))
            }
            .addOnFailureListener { e ->
                Log.w(TAG, "Silent sign-in failed: ${e.message}")
                onResult(SignInResult.Error(-1, e.message))
            }
    }

    sealed class SignInResult {
        data class Success(val account: GoogleSignInAccount) : SignInResult()
        data class Error(val statusCode: Int, val message: String?) : SignInResult()
    }
}
