package ai.ciris.mobile.auth

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import ai.ciris.mobile.MainActivity
import ai.ciris.mobile.R

/**
 * Login screen with Google Sign-In and Local Login options.
 *
 * Both options proceed to the setup wizard:
 * - Google Sign-In: Required for CIRIS hosted LLM services, also supports BYOK
 * - Local Login: Offline mode with user-provided API key (BYOK only)
 */
class LoginActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "LoginActivity"

        // Auth method constants
        const val AUTH_METHOD_GOOGLE = "google"
        const val AUTH_METHOD_API_KEY = "api_key"
    }

    private lateinit var googleSignInHelper: GoogleSignInHelper
    private lateinit var signInButton: Button
    private lateinit var apiKeyButton: Button
    private lateinit var progressBar: ProgressBar
    private lateinit var statusText: TextView
    private lateinit var marketingCheckbox: CheckBox
    private lateinit var privacyLink: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        // Enable edge-to-edge display for Android 15+ (SDK 35)
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_login)

        // Handle window insets for edge-to-edge display
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(android.R.id.content)) { view, windowInsets ->
            val insets = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(insets.left, insets.top, insets.right, insets.bottom)
            WindowInsetsCompat.CONSUMED
        }

        googleSignInHelper = GoogleSignInHelper(this)

        // Bind views
        signInButton = findViewById(R.id.sign_in_button)
        apiKeyButton = findViewById(R.id.api_key_button)
        progressBar = findViewById(R.id.progress_bar)
        statusText = findViewById(R.id.status_text)
        marketingCheckbox = findViewById(R.id.marketing_checkbox)
        privacyLink = findViewById(R.id.privacy_link)

        signInButton.setOnClickListener {
            startGoogleSignIn()
        }

        apiKeyButton.setOnClickListener {
            proceedWithApiKey()
        }

        privacyLink.setOnClickListener {
            openPrivacyPolicy()
        }

        // Only attempt silent sign-in if user previously chose Google auth
        val prefs = getSharedPreferences("ciris_auth", MODE_PRIVATE)
        val savedAuthMethod = prefs.getString("auth_method", null)

        when (savedAuthMethod) {
            AUTH_METHOD_GOOGLE -> {
                // Returning Google user - try silent sign-in
                Log.i(TAG, "Returning Google user - attempting silent sign-in")
                attemptSilentSignIn()
            }
            AUTH_METHOD_API_KEY -> {
                // Returning API key user - go straight to main
                Log.i(TAG, "Returning API key user - proceeding to main")
                proceedToMain(AUTH_METHOD_API_KEY)
            }
            else -> {
                // First-time user - show login options
                Log.i(TAG, "First-time user - showing login options")
                showProgress(false)
            }
        }
    }

    private fun openPrivacyPolicy() {
        // Open privacy policy in browser or in-app WebView
        val privacyUrl = "file:///android_asset/public/privacy-policy.html"
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(privacyUrl))
        try {
            startActivity(intent)
        } catch (e: Exception) {
            // Fallback: show toast with external URL
            Log.e(TAG, "Failed to open privacy policy: ${e.message}")
            Toast.makeText(this, "Privacy policy available at ciris.ai/privacy", Toast.LENGTH_LONG).show()
        }
    }

    private fun attemptSilentSignIn() {
        // ALWAYS call silentSignIn() to get a fresh token
        // DO NOT use getLastSignedInAccount() directly - it returns cached tokens that may be expired
        // The silentSignIn() function checks token validity and refreshes if needed
        showProgress(true, "Checking sign-in status...")
        googleSignInHelper.silentSignIn { result ->
            runOnUiThread {
                when (result) {
                    is GoogleSignInHelper.SignInResult.Success -> {
                        Log.i(TAG, "Silent sign-in successful")
                        googleSignInHelper.logTokenDiagnostics("SilentSignIn", result.account.idToken)
                        // Pass the fresh account from silent sign-in result
                        proceedToMain(AUTH_METHOD_GOOGLE, result.account)
                    }
                    is GoogleSignInHelper.SignInResult.Error -> {
                        Log.i(TAG, "Silent sign-in failed, showing options")
                        showProgress(false)
                    }
                }
            }
        }
    }

    private fun startGoogleSignIn() {
        showProgress(true, "Signing in with Google...")
        val signInIntent = googleSignInHelper.getSignInIntent()
        startActivityForResult(signInIntent, GoogleSignInHelper.RC_SIGN_IN)
    }

    private fun proceedWithApiKey() {
        // Skip Google auth, proceed directly with local login mode
        Log.i(TAG, "User chose local login mode")
        proceedToMain(AUTH_METHOD_API_KEY)
    }

    // Store the fresh token from interactive sign-in to avoid cache issues
    private var freshSignInToken: String? = null

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)

        if (requestCode == GoogleSignInHelper.RC_SIGN_IN) {
            val result = googleSignInHelper.handleSignInResult(data)
            when (result) {
                is GoogleSignInHelper.SignInResult.Success -> {
                    Log.i(TAG, "Sign-in successful: ${result.account.email}")

                    // CRITICAL: Store the fresh token from the sign-in result directly
                    // Do NOT use getLastSignedInAccount() which may return a stale cached token
                    freshSignInToken = result.account.idToken
                    Log.i(TAG, "[TokenFlow] Fresh token obtained from sign-in result")
                    googleSignInHelper.logTokenDiagnostics("InteractiveSignIn", freshSignInToken)

                    // Also log what getLastSignedInAccount() would return for comparison
                    val cachedToken = googleSignInHelper.getIdToken()
                    Log.i(TAG, "[TokenFlow] Cached token from getLastSignedInAccount():")
                    googleSignInHelper.logTokenDiagnostics("CachedAccount", cachedToken)

                    if (freshSignInToken != cachedToken) {
                        Log.w(TAG, "[TokenFlow] WARNING: Fresh token differs from cached token!")
                    }

                    Toast.makeText(this, "Welcome, ${result.account.displayName}!", Toast.LENGTH_SHORT).show()
                    proceedToMain(AUTH_METHOD_GOOGLE, result.account)
                }
                is GoogleSignInHelper.SignInResult.Error -> {
                    Log.e(TAG, "Sign-in error: ${result.statusCode}")
                    showProgress(false)
                    showError("Sign-in failed: ${result.message ?: "Unknown error"}")
                }
            }
        }
    }

    /**
     * Proceed to main activity with API key auth (no Google account).
     */
    private fun proceedToMain(authMethod: String) {
        proceedToMain(authMethod, null)
    }

    /**
     * Proceed to main activity, optionally with a fresh Google account from sign-in.
     *
     * IMPORTANT: When account is provided, use token directly from it to avoid cache issues.
     * Do NOT call getLastSignedInAccount() which may return stale cached data.
     */
    private fun proceedToMain(authMethod: String, freshAccount: com.google.android.gms.auth.api.signin.GoogleSignInAccount?) {
        Log.i(TAG, "[Auth Flow] proceedToMain called with authMethod: $authMethod, freshAccount: ${freshAccount != null}")

        // Save the user's auth method choice for future launches
        val prefs = getSharedPreferences("ciris_auth", MODE_PRIVATE)
        prefs.edit().putString("auth_method", authMethod).apply()
        Log.i(TAG, "[Auth Flow] Saved auth_method preference: $authMethod")

        val intent = Intent(this, MainActivity::class.java).apply {
            putExtra("auth_method", authMethod)

            if (authMethod == AUTH_METHOD_GOOGLE) {
                // CRITICAL: Use freshAccount if available, otherwise fall back to cached
                // This fixes the bug where stale cached tokens were used after interactive sign-in
                val account = freshAccount ?: googleSignInHelper.getLastSignedInAccount()

                if (freshAccount != null) {
                    Log.i(TAG, "[Auth Flow] Using FRESH account from sign-in result")
                } else {
                    Log.i(TAG, "[Auth Flow] Using CACHED account from getLastSignedInAccount()")
                }

                val googleUserId = account?.id
                val googleIdToken = account?.idToken
                val userEmail = account?.email
                val userName = account?.displayName
                val userPhotoUrl = account?.photoUrl?.toString()
                val marketingOptIn = marketingCheckbox.isChecked

                Log.i(TAG, "[Auth Flow] Google auth data:")
                Log.i(TAG, "[Auth Flow]   google_user_id: ${googleUserId ?: "(null)"}")
                googleSignInHelper.logTokenDiagnostics("ProceedToMain", googleIdToken)
                Log.i(TAG, "[Auth Flow]   user_email: ${userEmail ?: "(null)"}")
                Log.i(TAG, "[Auth Flow]   user_name: ${userName ?: "(null)"}")
                Log.i(TAG, "[Auth Flow]   user_photo_url: ${userPhotoUrl ?: "(null)"}")
                Log.i(TAG, "[Auth Flow]   marketing_opt_in: $marketingOptIn")

                putExtra("google_user_id", googleUserId)
                putExtra("google_id_token", googleIdToken)
                putExtra("user_email", userEmail)
                putExtra("user_name", userName)
                putExtra("user_photo_url", userPhotoUrl)
                putExtra("marketing_opt_in", marketingOptIn)
            }

            // Both methods should show setup wizard on first run
            putExtra("show_setup", true)
        }
        Log.i(TAG, "[Auth Flow] Starting MainActivity with intent extras")
        startActivity(intent)
        finish()
    }

    private fun showProgress(show: Boolean, message: String = "") {
        progressBar.visibility = if (show) View.VISIBLE else View.GONE
        signInButton.visibility = if (show) View.GONE else View.VISIBLE
        apiKeyButton.visibility = if (show) View.GONE else View.VISIBLE
        marketingCheckbox.visibility = if (show) View.GONE else View.VISIBLE
        privacyLink.visibility = if (show) View.GONE else View.VISIBLE
        statusText.text = message
        statusText.visibility = if (message.isNotEmpty()) View.VISIBLE else View.GONE
    }

    private fun showError(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
        statusText.text = message
        statusText.visibility = View.VISIBLE
    }
}
