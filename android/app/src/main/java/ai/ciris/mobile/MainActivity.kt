package ai.ciris.mobile

import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.view.Menu
import android.view.MenuItem
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL

/**
 * MainActivity for CIRIS Android.
 *
 * Launches the Python FastAPI server on-device and displays the web UI
 * in a WebView. All LLM calls are routed to a remote OpenAI-compatible endpoint.
 *
 * Architecture:
 * - Python runtime: On-device (Chaquopy)
 * - FastAPI server: localhost:8000
 * - Web UI: Bundled assets in WebView
 * - LLM: Remote endpoint only
 * - Database: On-device SQLite
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private var serverStarted = false

    // User info passed from LoginActivity
    private var authMethod: String? = null
    private var googleUserId: String? = null
    private var userEmail: String? = null
    private var userName: String? = null
    private var showSetup: Boolean = false

    companion object {
        private const val TAG = "CIRISMobile"
        private const val SERVER_URL = "http://127.0.0.1:8080"  // Match GUI SDK default
        private const val UI_PATH = "/index.html"

        // Static reference to current Google user ID for LLM proxy calls
        var currentGoogleUserId: String? = null
            private set
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        // Get user info from LoginActivity
        authMethod = intent.getStringExtra("auth_method") ?: "api_key"
        googleUserId = intent.getStringExtra("google_user_id")
        userEmail = intent.getStringExtra("user_email")
        userName = intent.getStringExtra("user_name")
        showSetup = intent.getBooleanExtra("show_setup", true)

        // Store globally for LLM proxy access
        currentGoogleUserId = googleUserId

        Log.i(TAG, "Auth method: $authMethod, User: $userName ($userEmail), Setup: $showSetup")

        // Initialize Python runtime
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
            Log.i(TAG, "Python runtime initialized")
        }

        // Setup WebView for bundled UI
        setupWebView()

        // Start Python server in background
        startPythonServer()
    }

    private fun setupWebView() {
        webView = findViewById(R.id.webView)

        webView.apply {
            settings.apply {
                javaScriptEnabled = true
                domStorageEnabled = true
                databaseEnabled = true
                allowFileAccess = true
                allowContentAccess = true
            }

            webViewClient = object : WebViewClient() {
                override fun onReceivedError(
                    view: WebView?,
                    errorCode: Int,
                    description: String?,
                    failingUrl: String?
                ) {
                    Log.e(TAG, "WebView error: $description at $failingUrl")
                    if (!serverStarted) {
                        // Server might not be ready yet, retry
                        retryLoadUI()
                    }
                }

                override fun shouldOverrideUrlLoading(
                    view: WebView?,
                    url: String?
                ): Boolean {
                    // Keep navigation within WebView
                    return false
                }

                override fun onPageFinished(view: WebView?, url: String?) {
                    super.onPageFinished(view, url)
                    // Inject auth data after the real page loads (not on data: URLs)
                    if (url?.startsWith("http") == true) {
                        Log.i(TAG, "Page loaded: $url - injecting auth data")
                        injectAuthData()
                    }
                }
            }

            webChromeClient = WebChromeClient()
        }

        // Show loading screen immediately
        showLoadingScreen()

        Log.i(TAG, "WebView configured")
    }

    private fun showLoadingScreen() {
        webView.loadData(
            """
            <!DOCTYPE html>
            <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {
                        display: flex;
                        flex-direction: column;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        color: white;
                    }
                    .logo {
                        font-size: 72px;
                        margin-bottom: 20px;
                    }
                    h1 {
                        font-size: 28px;
                        margin: 0 0 10px 0;
                        font-weight: 600;
                    }
                    p {
                        font-size: 16px;
                        opacity: 0.9;
                        margin: 0;
                    }
                    .spinner {
                        margin-top: 30px;
                        width: 40px;
                        height: 40px;
                        border: 3px solid rgba(255,255,255,0.3);
                        border-top-color: white;
                        border-radius: 50%;
                        animation: spin 1s linear infinite;
                    }
                    @keyframes spin {
                        to { transform: rotate(360deg); }
                    }
                </style>
            </head>
            <body>
                <div class="logo">C</div>
                <h1>CIRIS Agent</h1>
                <p>Initializing, please wait...</p>
                <div class="spinner"></div>
            </body>
            </html>
            """.trimIndent(),
            "text/html",
            "UTF-8"
        )
    }

    private fun startPythonServer() {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                Log.i(TAG, "Starting Python server...")

                val python = Python.getInstance()
                val mobileMain = python.getModule("mobile_main")

                // Start server in background thread
                launch(Dispatchers.IO) {
                    try {
                        mobileMain.callAttr("main")
                    } catch (e: Exception) {
                        Log.e(TAG, "Server error: ${e.message}", e)
                    }
                }

                // Poll health endpoint until server is ready
                val maxAttempts = 60  // Up to 60 seconds
                var attempts = 0
                var isHealthy = false

                while (attempts < maxAttempts && !isHealthy) {
                    delay(1000)
                    attempts++
                    isHealthy = checkServerHealth()
                    Log.i(TAG, "Health check attempt $attempts: ${if (isHealthy) "OK" else "waiting..."}")
                }

                withContext(Dispatchers.Main) {
                    if (isHealthy) {
                        serverStarted = true
                        loadUI()
                    } else {
                        showErrorScreen("Server failed to start after ${maxAttempts}s")
                    }
                }

            } catch (e: Exception) {
                Log.e(TAG, "Failed to start server: ${e.message}", e)
                withContext(Dispatchers.Main) {
                    showErrorScreen("Failed to start CIRIS server: ${e.message}")
                }
            }
        }
    }

    private fun checkServerHealth(): Boolean {
        return try {
            val url = URL("$SERVER_URL/v1/system/health")
            val connection = url.openConnection() as HttpURLConnection
            connection.connectTimeout = 2000
            connection.readTimeout = 2000
            connection.requestMethod = "GET"
            val responseCode = connection.responseCode
            connection.disconnect()
            responseCode == 200
        } catch (e: Exception) {
            false
        }
    }

    private fun showErrorScreen(message: String) {
        webView.loadData(
            """
            <!DOCTYPE html>
            <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {
                        display: flex;
                        flex-direction: column;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        padding: 20px;
                        box-sizing: border-box;
                        background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%);
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        color: white;
                        text-align: center;
                    }
                    h1 { font-size: 24px; margin: 0 0 15px 0; }
                    p { font-size: 14px; opacity: 0.9; margin: 0 0 20px 0; }
                    .hint { font-size: 12px; opacity: 0.7; }
                </style>
            </head>
            <body>
                <h1>Server Error</h1>
                <p>$message</p>
                <p class="hint">Check Settings to configure your LLM endpoint, or restart the app.</p>
            </body>
            </html>
            """.trimIndent(),
            "text/html",
            "UTF-8"
        )
    }

    private fun loadUI() {
        val url = "$SERVER_URL$UI_PATH"
        Log.i(TAG, "Loading UI from $url")
        // Auth data is injected in onPageFinished after page loads
        webView.loadUrl(url)
    }

    private fun injectAuthData() {
        // Inject auth data into localStorage for the web UI
        // The web app will check for this and use it for authentication
        val authJson = """
            {
                "provider": "${authMethod ?: "api_key"}",
                "googleUserId": "${googleUserId ?: ""}",
                "email": "${userEmail ?: ""}",
                "displayName": "${userName ?: ""}",
                "isNativeApp": true,
                "showSetup": $showSetup
            }
        """.trimIndent().replace("\n", "")

        val script = """
            (function() {
                localStorage.setItem('ciris_native_auth', '$authJson');
                localStorage.setItem('ciris_auth_method', '${authMethod ?: "api_key"}');
                localStorage.setItem('ciris_google_user_id', '${googleUserId ?: ""}');
                localStorage.setItem('ciris_user_email', '${userEmail ?: ""}');
                localStorage.setItem('ciris_user_name', '${userName ?: ""}');
                localStorage.setItem('ciris_show_setup', '${showSetup}');
                localStorage.setItem('isNativeApp', 'true');
                console.log('[Native] Auth data injected - method: ${authMethod ?: "api_key"}, showSetup: $showSetup');

                // Dispatch event to notify web app of native auth
                window.dispatchEvent(new CustomEvent('ciris_native_auth_ready', { detail: $authJson }));
            })();
        """.trimIndent()

        webView.evaluateJavascript(script) { result ->
            Log.i(TAG, "Auth injection result: $result")
        }
    }

    private fun retryLoadUI() {
        CoroutineScope(Dispatchers.Main).launch {
            delay(1000)
            if (serverStarted) {
                loadUI()
            }
        }
    }

    override fun onCreateOptionsMenu(menu: Menu?): Boolean {
        menuInflater.inflate(R.menu.main_menu, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_buy_credits -> {
                startActivity(Intent(this, PurchaseActivity::class.java))
                true
            }
            R.id.action_settings -> {
                startActivity(Intent(this, SettingsActivity::class.java))
                true
            }
            R.id.action_refresh -> {
                webView.reload()
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        // Note: Python server continues running
        // In production, implement proper shutdown
    }
}
