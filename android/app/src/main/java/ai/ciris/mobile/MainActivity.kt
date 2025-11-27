package ai.ciris.mobile

import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.OutputStream
import java.io.PrintStream
import java.net.HttpURLConnection
import java.net.URL

/**
 * MainActivity for CIRIS Android.
 *
 * Launches the full CIRIS runtime on-device and displays the web UI
 * in a WebView. Shows a live console during startup.
 *
 * Architecture:
 * - Python runtime: On-device (Chaquopy)
 * - CIRIS Runtime: Full 22 services
 * - FastAPI server: localhost:8080
 * - Web UI: Bundled assets in WebView
 * - LLM: Remote endpoint only
 * - Database: On-device SQLite
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var consoleContainer: LinearLayout
    private lateinit var consoleScroll: ScrollView
    private lateinit var consoleOutput: TextView
    private lateinit var statusIndicator: TextView
    private var serverStarted = false
    private val consoleBuffer = StringBuilder()

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

        // Setup console views
        consoleContainer = findViewById(R.id.consoleContainer)
        consoleScroll = findViewById(R.id.consoleScroll)
        consoleOutput = findViewById(R.id.consoleOutput)
        statusIndicator = findViewById(R.id.statusIndicator)

        // Setup WebView (hidden initially)
        setupWebView()

        // Redirect Python stdout/stderr to console
        setupPythonOutputRedirect()

        // Initialize Python runtime
        appendToConsole("Initializing Python runtime...")
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
            appendToConsole("✓ Python runtime initialized")
            Log.i(TAG, "Python runtime initialized")
        } else {
            appendToConsole("✓ Python runtime already running")
        }

        // Start Python server in background
        startPythonServer()
    }

    private fun setupPythonOutputRedirect() {
        // Chaquopy redirects Python stdout/stderr to Android logcat with tags
        // "python.stdout" and "python.stderr". We capture these via a LogcatReader.
        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Clear logcat buffer first
                Runtime.getRuntime().exec("logcat -c")
                delay(100)

                // Start reading logcat for Python output
                val process = Runtime.getRuntime().exec("logcat -v raw python.stdout:I python.stderr:W *:S")
                val reader = process.inputStream.bufferedReader()

                while (true) {
                    val line = reader.readLine() ?: break
                    if (line.isNotBlank()) {
                        withContext(Dispatchers.Main) {
                            appendToConsole(line)
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Logcat reader error: ${e.message}")
            }
        }
    }

    private fun appendToConsole(text: String) {
        consoleBuffer.append(text).append("\n")

        // Limit buffer size to last 500 lines
        val lines = consoleBuffer.lines()
        if (lines.size > 500) {
            consoleBuffer.clear()
            consoleBuffer.append(lines.takeLast(500).joinToString("\n"))
        }

        consoleOutput.text = consoleBuffer.toString()

        // Auto-scroll to bottom
        consoleScroll.post {
            consoleScroll.fullScroll(View.FOCUS_DOWN)
        }
    }

    private fun updateStatus(status: String, color: String) {
        val colorInt = when (color) {
            "green" -> 0xFF00FF88.toInt()
            "red" -> 0xFFFF4444.toInt()
            else -> 0xFFFFCC00.toInt()  // yellow
        }
        statusIndicator.text = "● $status"
        statusIndicator.setTextColor(colorInt)
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

        Log.i(TAG, "WebView configured")
    }

    private fun startPythonServer() {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                withContext(Dispatchers.Main) {
                    appendToConsole("Starting CIRIS runtime...")
                    updateStatus("Starting", "yellow")
                }

                Log.i(TAG, "Starting Python server...")

                val python = Python.getInstance()
                val mobileMain = python.getModule("mobile_main")

                // Start server in background thread
                launch(Dispatchers.IO) {
                    try {
                        mobileMain.callAttr("main")
                    } catch (e: Exception) {
                        Log.e(TAG, "Server error: ${e.message}", e)
                        withContext(Dispatchers.Main) {
                            appendToConsole("❌ Server error: ${e.message}")
                            updateStatus("Error", "red")
                        }
                    }
                }

                // Poll health endpoint until server is ready
                val maxAttempts = 120  // Up to 2 minutes for full runtime init
                var attempts = 0
                var isHealthy = false

                withContext(Dispatchers.Main) {
                    appendToConsole("Waiting for API server...")
                }

                while (attempts < maxAttempts && !isHealthy) {
                    delay(1000)
                    attempts++
                    isHealthy = checkServerHealth()

                    if (attempts % 5 == 0) {
                        withContext(Dispatchers.Main) {
                            appendToConsole("Health check: ${if (isHealthy) "✓ Ready" else "waiting..."} ($attempts s)")
                        }
                    }

                    Log.i(TAG, "Health check attempt $attempts: ${if (isHealthy) "OK" else "waiting..."}")
                }

                withContext(Dispatchers.Main) {
                    if (isHealthy) {
                        serverStarted = true
                        appendToConsole("✓ CIRIS runtime ready!")
                        appendToConsole("Loading web interface...")
                        updateStatus("Ready", "green")

                        // Short delay to let user see the success message
                        delay(500)

                        // Transition to WebView
                        showWebView()
                    } else {
                        appendToConsole("❌ Server failed to start after ${maxAttempts}s")
                        updateStatus("Failed", "red")
                    }
                }

            } catch (e: Exception) {
                Log.e(TAG, "Failed to start server: ${e.message}", e)
                withContext(Dispatchers.Main) {
                    appendToConsole("❌ Failed to start CIRIS: ${e.message}")
                    updateStatus("Error", "red")
                }
            }
        }
    }

    private fun showWebView() {
        // Hide console, show WebView
        consoleContainer.visibility = View.GONE
        webView.visibility = View.VISIBLE
        loadUI()
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
