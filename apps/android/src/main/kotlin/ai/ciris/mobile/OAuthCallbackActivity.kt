package ai.ciris.mobile

import android.content.Intent
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity

/**
 * Handles OAuth callback deep links (ciris://oauth)
 * Based on original android/app/.../OAuthCallbackActivity.kt
 */
class OAuthCallbackActivity : ComponentActivity() {

    companion object {
        private const val TAG = "OAuthCallback"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        handleIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    private fun handleIntent(intent: Intent?) {
        val uri = intent?.data
        if (uri != null) {
            Log.i(TAG, "OAuth callback received: $uri")

            // Extract auth code or token from URI
            val code = uri.getQueryParameter("code")
            val error = uri.getQueryParameter("error")

            if (error != null) {
                Log.e(TAG, "OAuth error: $error")
            } else if (code != null) {
                Log.i(TAG, "OAuth code received")
                // TODO: Exchange code for token via API
            }

            // Return to MainActivity
            val mainIntent = Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
                putExtra("oauth_code", code)
                putExtra("oauth_error", error)
            }
            startActivity(mainIntent)
        }

        finish()
    }
}
