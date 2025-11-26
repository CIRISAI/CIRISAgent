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
 * Login screen with Google Sign-In.
 *
 * After successful sign-in, the Google user ID is used for
 * CIRIS LLM proxy authentication at llm.ciris.ai
 */
class LoginActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "LoginActivity"
    }

    private lateinit var googleSignInHelper: GoogleSignInHelper
    private lateinit var signInButton: Button
    private lateinit var progressBar: ProgressBar
    private lateinit var statusText: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_login)

        googleSignInHelper = GoogleSignInHelper(this)

        // Bind views
        signInButton = findViewById(R.id.sign_in_button)
        progressBar = findViewById(R.id.progress_bar)
        statusText = findViewById(R.id.status_text)

        signInButton.setOnClickListener {
            startSignIn()
        }

        // Try silent sign-in on launch
        attemptSilentSignIn()
    }

    private fun attemptSilentSignIn() {
        // Check if already signed in
        if (googleSignInHelper.isSignedIn()) {
            Log.i(TAG, "Already signed in, proceeding to main")
            proceedToMain()
            return
        }

        // Try silent sign-in
        showProgress(true, "Checking sign-in status...")
        googleSignInHelper.silentSignIn { result ->
            runOnUiThread {
                when (result) {
                    is GoogleSignInHelper.SignInResult.Success -> {
                        Log.i(TAG, "Silent sign-in successful")
                        proceedToMain()
                    }
                    is GoogleSignInHelper.SignInResult.Error -> {
                        Log.i(TAG, "Silent sign-in failed, showing sign-in button")
                        showProgress(false)
                    }
                }
            }
        }
    }

    private fun startSignIn() {
        showProgress(true, "Signing in with Google...")
        val signInIntent = googleSignInHelper.getSignInIntent()
        startActivityForResult(signInIntent, GoogleSignInHelper.RC_SIGN_IN)
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)

        if (requestCode == GoogleSignInHelper.RC_SIGN_IN) {
            val result = googleSignInHelper.handleSignInResult(data)
            when (result) {
                is GoogleSignInHelper.SignInResult.Success -> {
                    Log.i(TAG, "Sign-in successful: ${result.account.email}")
                    Toast.makeText(this, "Welcome, ${result.account.displayName}!", Toast.LENGTH_SHORT).show()
                    proceedToMain()
                }
                is GoogleSignInHelper.SignInResult.Error -> {
                    Log.e(TAG, "Sign-in error: ${result.statusCode}")
                    showProgress(false)
                    showError("Sign-in failed: ${result.message ?: "Unknown error"}")
                }
            }
        }
    }

    private fun proceedToMain() {
        val intent = Intent(this, MainActivity::class.java).apply {
            // Pass the Google user ID to MainActivity
            putExtra("google_user_id", googleSignInHelper.getGoogleUserId())
            putExtra("user_email", googleSignInHelper.getUserEmail())
            putExtra("user_name", googleSignInHelper.getUserDisplayName())
        }
        startActivity(intent)
        finish()
    }

    private fun showProgress(show: Boolean, message: String = "") {
        progressBar.visibility = if (show) View.VISIBLE else View.GONE
        signInButton.visibility = if (show) View.GONE else View.VISIBLE
        statusText.text = message
        statusText.visibility = if (message.isNotEmpty()) View.VISIBLE else View.GONE
    }

    private fun showError(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
        statusText.text = message
        statusText.visibility = View.VISIBLE
    }
}
