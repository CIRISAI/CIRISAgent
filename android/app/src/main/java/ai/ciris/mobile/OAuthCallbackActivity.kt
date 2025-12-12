package ai.ciris.mobile

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.util.Log
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL

/**
 * OAuthCallbackActivity handles deep link OAuth callbacks from external browsers.
 *
 * This activity is registered to handle the ciris:// URI scheme, enabling OAuth2
 * authentication flows with any provider (Home Assistant, Discord, Google, Microsoft,
 * Reddit, etc.) when using Chrome Custom Tabs or the system browser.
 *
 * Deep Link Format:
 *   ciris://oauth/callback?code=xxx&state=yyy
 *   ciris://oauth/ha?code=xxx&state=yyy        (provider-specific)
 *   ciris://oauth/discord?code=xxx&state=yyy
 *
 * The activity extracts OAuth parameters and forwards them to the local Python
 * server running on the device, which processes the OAuth callback and updates
 * the adapter configuration session.
 *
 * Flow:
 * 1. System browser redirects to ciris://oauth/callback?code=xxx&state=yyy
 * 2. Android launches this activity via intent filter
 * 3. Activity extracts code/state/error parameters
 * 4. Forwards to http://127.0.0.1:8080/v1/adapters/oauth/callback
 * 5. Returns user to the app (MainActivity with AdaptersFragment)
 */
class OAuthCallbackActivity : AppCompatActivity() {

    companion object {
        private const val TAG = "OAuthCallback"
        private const val LOCAL_SERVER_PORT = 8080
        // Path matches the router prefix "/system" + endpoint "/adapters/oauth/callback"
        private const val LOCAL_CALLBACK_PATH = "/v1/system/adapters/oauth/callback"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Log.i(TAG, "[OAUTH_DEEPLINK] OAuthCallbackActivity created")
        handleIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        Log.i(TAG, "[OAUTH_DEEPLINK] OAuthCallbackActivity received new intent")
        handleIntent(intent)
    }

    private fun handleIntent(intent: Intent?) {
        val uri = intent?.data
        if (uri == null) {
            Log.e(TAG, "[OAUTH_DEEPLINK] No URI in intent")
            showErrorAndFinish("OAuth callback failed: No data received")
            return
        }

        Log.i(TAG, "[OAUTH_DEEPLINK] Received OAuth callback: $uri")
        Log.i(TAG, "[OAUTH_DEEPLINK] Scheme: ${uri.scheme}, Host: ${uri.host}, Path: ${uri.path}")
        Log.i(TAG, "[OAUTH_DEEPLINK] Query: ${uri.query}")

        // Extract OAuth parameters
        val code = uri.getQueryParameter("code")
        val state = uri.getQueryParameter("state")
        val error = uri.getQueryParameter("error")
        val errorDescription = uri.getQueryParameter("error_description")

        // Extract provider from path if available (e.g., /ha, /discord, /callback)
        val path = uri.path ?: "/callback"
        val provider = when {
            path.contains("/ha") -> "home_assistant"
            path.contains("/discord") -> "discord"
            path.contains("/google") -> "google"
            path.contains("/microsoft") -> "microsoft"
            path.contains("/reddit") -> "reddit"
            else -> extractProviderFromState(state)
        }

        Log.i(TAG, "[OAUTH_DEEPLINK] Parsed: code=${code?.take(10)}..., state=$state, error=$error, provider=$provider")

        if (error != null) {
            Log.e(TAG, "[OAUTH_DEEPLINK] OAuth error from provider: $error - $errorDescription")
            showErrorAndFinish("OAuth failed: $error - ${errorDescription ?: "Unknown error"}")
            return
        }

        if (code == null) {
            Log.e(TAG, "[OAUTH_DEEPLINK] No authorization code in callback")
            showErrorAndFinish("OAuth callback missing authorization code")
            return
        }

        // Forward to local Python server
        forwardToLocalServer(code, state, provider)
    }

    /**
     * Extract provider hint from state parameter if encoded there.
     * State format can be: "random_state" or "provider:random_state"
     */
    private fun extractProviderFromState(state: String?): String? {
        if (state == null) return null
        val parts = state.split(":", limit = 2)
        return if (parts.size == 2 && parts[0].length < 20) {
            // Looks like "provider:actual_state"
            parts[0]
        } else {
            null
        }
    }

    /**
     * Forward the OAuth callback to the local Python server.
     * The server handles token exchange and session updates.
     */
    private fun forwardToLocalServer(code: String, state: String?, provider: String?) {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Build callback URL for local server
                val callbackUrl = buildString {
                    append("http://127.0.0.1:$LOCAL_SERVER_PORT$LOCAL_CALLBACK_PATH")
                    append("?code=")
                    append(java.net.URLEncoder.encode(code, "UTF-8"))
                    if (state != null) {
                        append("&state=")
                        append(java.net.URLEncoder.encode(state, "UTF-8"))
                    }
                    if (provider != null) {
                        append("&provider=")
                        append(java.net.URLEncoder.encode(provider, "UTF-8"))
                    }
                    // Mark this as a deep link callback
                    append("&source=deeplink")
                }

                Log.i(TAG, "[OAUTH_DEEPLINK] Forwarding to local server: $callbackUrl")

                val url = URL(callbackUrl)
                val connection = url.openConnection() as HttpURLConnection
                connection.requestMethod = "GET"
                connection.connectTimeout = 5000
                connection.readTimeout = 5000

                val responseCode = connection.responseCode
                val responseMessage = if (responseCode in 200..299) {
                    connection.inputStream.bufferedReader().readText()
                } else {
                    connection.errorStream?.bufferedReader()?.readText() ?: "Unknown error"
                }

                Log.i(TAG, "[OAUTH_DEEPLINK] Server response: $responseCode - ${responseMessage.take(200)}")

                withContext(Dispatchers.Main) {
                    if (responseCode in 200..299) {
                        Log.i(TAG, "[OAUTH_DEEPLINK] OAuth callback forwarded successfully")
                        Toast.makeText(
                            this@OAuthCallbackActivity,
                            "Authentication successful!",
                            Toast.LENGTH_SHORT
                        ).show()
                        returnToApp(success = true)
                    } else {
                        Log.e(TAG, "[OAUTH_DEEPLINK] Server error: $responseCode")
                        showErrorAndFinish("Server error: $responseMessage")
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "[OAUTH_DEEPLINK] Failed to forward callback: ${e.message}", e)
                withContext(Dispatchers.Main) {
                    showErrorAndFinish("Failed to process OAuth: ${e.message}")
                }
            }
        }
    }

    /**
     * Return to the main app after OAuth processing.
     */
    private fun returnToApp(success: Boolean) {
        Log.i(TAG, "[OAUTH_DEEPLINK] Returning to app, success=$success")

        // Launch MainActivity which will show AdaptersFragment
        val intent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP
            putExtra("oauth_success", success)
            putExtra("show_adapters", true)
        }
        startActivity(intent)
        finish()
    }

    private fun showErrorAndFinish(message: String) {
        Log.e(TAG, "[OAUTH_DEEPLINK] $message")
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
        returnToApp(success = false)
    }
}
