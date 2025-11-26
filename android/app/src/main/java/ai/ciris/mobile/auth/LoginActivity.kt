package ai.ciris.mobile.auth

import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.view.View
import android.widget.Button
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import ai.ciris.mobile.MainActivity
import ai.ciris.mobile.R

/**
 * Login screen with Google Sign-In and API Key options.
 *
 * Both options proceed to the setup wizard:
 * - Google Sign-In: Uses CIRIS LLM Proxy with Google auth
 * - API Key: User provides their own OpenAI-compatible endpoint
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

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_login)

        googleSignInHelper = GoogleSignInHelper(this)

        // Bind views
        signInButton = findViewById(R.id.sign_in_button)
        apiKeyButton = findViewById(R.id.api_key_button)
        progressBar = findViewById(R.id.progress_bar)
        statusText = findViewById(R.id.status_text)

        signInButton.setOnClickListener {
            startGoogleSignIn()
        }

        apiKeyButton.setOnClickListener {
            proceedWithApiKey()
        }

        // Try silent sign-in on launch (only for returning Google users)
        attemptSilentSignIn()
    }

    private fun attemptSilentSignIn() {
        // Check if already signed in with Google
        if (googleSignInHelper.isSignedIn()) {
            Log.i(TAG, "Already signed in with Google, proceeding to main")
            proceedToMain(AUTH_METHOD_GOOGLE)
            return
        }

        // Try silent sign-in for Google
        showProgress(true, "Checking sign-in status...")
        googleSignInHelper.silentSignIn { result ->
            runOnUiThread {
                when (result) {
                    is GoogleSignInHelper.SignInResult.Success -> {
                        Log.i(TAG, "Silent sign-in successful")
                        proceedToMain(AUTH_METHOD_GOOGLE)
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
        // Skip Google auth, proceed directly with API key mode
        Log.i(TAG, "User chose API key mode")
        proceedToMain(AUTH_METHOD_API_KEY)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)

        if (requestCode == GoogleSignInHelper.RC_SIGN_IN) {
            val result = googleSignInHelper.handleSignInResult(data)
            when (result) {
                is GoogleSignInHelper.SignInResult.Success -> {
                    Log.i(TAG, "Sign-in successful: ${result.account.email}")
                    Toast.makeText(this, "Welcome, ${result.account.displayName}!", Toast.LENGTH_SHORT).show()
                    proceedToMain(AUTH_METHOD_GOOGLE)
                }
                is GoogleSignInHelper.SignInResult.Error -> {
                    Log.e(TAG, "Sign-in error: ${result.statusCode}")
                    showProgress(false)
                    showError("Sign-in failed: ${result.message ?: "Unknown error"}")
                }
            }
        }
    }

    private fun proceedToMain(authMethod: String) {
        val intent = Intent(this, MainActivity::class.java).apply {
            putExtra("auth_method", authMethod)

            if (authMethod == AUTH_METHOD_GOOGLE) {
                // Pass Google user info
                putExtra("google_user_id", googleSignInHelper.getGoogleUserId())
                putExtra("user_email", googleSignInHelper.getUserEmail())
                putExtra("user_name", googleSignInHelper.getUserDisplayName())
            }

            // Both methods should show setup wizard on first run
            putExtra("show_setup", true)
        }
        startActivity(intent)
        finish()
    }

    private fun showProgress(show: Boolean, message: String = "") {
        progressBar.visibility = if (show) View.VISIBLE else View.GONE
        signInButton.visibility = if (show) View.GONE else View.VISIBLE
        apiKeyButton.visibility = if (show) View.GONE else View.VISIBLE
        statusText.text = message
        statusText.visibility = if (message.isNotEmpty()) View.VISIBLE else View.GONE
    }

    private fun showError(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
        statusText.text = message
        statusText.visibility = View.VISIBLE
    }
}
