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
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import ai.ciris.mobile.auth.GoogleSignInHelper
import ai.ciris.mobile.auth.TokenRefreshManager
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
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
    private var googleIdToken: String? = null
    private var userEmail: String? = null
    private var userName: String? = null
    private var showSetup: Boolean = false
    private var cirisAccessToken: String? = null

    // Track auth injection to prevent duplicate events
    private var authInjected = false
    private var lastInjectedUrl: String? = null

    // UI Preference
    private var useNativeUi = true

    // Token refresh manager for ciris.ai proxy authentication
    private var googleSignInHelper: GoogleSignInHelper? = null
    private var tokenRefreshManager: TokenRefreshManager? = null
    private var cirisHomePath: String? = null

    companion object {
        private const val TAG = "CIRISMobile"
        private const val PREFS_UI = "ciris_ui_prefs"
        private const val KEY_USE_NATIVE = "use_native_interact"
        private const val SERVER_URL = "http://localhost:8080"  // Match GUI SDK default (must use localhost, not 127.0.0.1, for Same-Origin Policy)
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
        googleIdToken = intent.getStringExtra("google_id_token")
        userEmail = intent.getStringExtra("user_email")
        userName = intent.getStringExtra("user_name")
        showSetup = intent.getBooleanExtra("show_setup", true)

        // Store globally for LLM proxy access
        currentGoogleUserId = googleUserId

        // Comprehensive logging of received auth data
        Log.i(TAG, "[Auth Received] ========================================")
        Log.i(TAG, "[Auth Received] auth_method: $authMethod")
        Log.i(TAG, "[Auth Received] google_user_id: ${googleUserId ?: "(null/empty)"}")
        Log.i(TAG, "[Auth Received] google_id_token: ${googleIdToken?.let { "${it.take(20)}... (${it.length} chars)" } ?: "(null)"}")
        Log.i(TAG, "[Auth Received] user_email: ${userEmail ?: "(null)"}")
        Log.i(TAG, "[Auth Received] user_name: ${userName ?: "(null)"}")
        Log.i(TAG, "[Auth Received] show_setup: $showSetup")
        Log.i(TAG, "[Auth Received] ========================================")

        // Initialize CIRIS_HOME path (same logic as mobile_main.py)
        initializeCirisHomePath()

        // Initialize token refresh manager for Google auth with ciris.ai
        if (authMethod == "google") {
            initializeTokenRefreshManager()
        }

        // Load UI preference
        val prefs = getSharedPreferences(PREFS_UI, MODE_PRIVATE)
        useNativeUi = prefs.getBoolean(KEY_USE_NATIVE, true)

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

    private fun injectPythonConfig() {
        try {
            val masterKey = MasterKey.Builder(this)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build()

            val prefs = EncryptedSharedPreferences.create(
                this,
                SettingsActivity.PREFS_NAME,
                masterKey,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
            )

            val apiBase = prefs.getString(SettingsActivity.KEY_API_BASE, null)
            val apiKey = prefs.getString(SettingsActivity.KEY_API_KEY, null)

            if (!apiBase.isNullOrEmpty()) {
                System.setProperty("OPENAI_API_BASE", apiBase)
                Log.i(TAG, "Injected OPENAI_API_BASE from secure settings")
            }

            if (!apiKey.isNullOrEmpty()) {
                System.setProperty("OPENAI_API_KEY", apiKey)
                Log.i(TAG, "Injected OPENAI_API_KEY from secure settings")
            }

        } catch (e: Exception) {
            Log.e(TAG, "Failed to read secure settings: ${e.message}")
        }
    }

    private fun setupWebView() {
        webView = findViewById(R.id.webView)

        webView.apply {
            settings.apply {
                javaScriptEnabled = true
                domStorageEnabled = true
                databaseEnabled = true
                allowFileAccess = false
                allowContentAccess = false
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
                    // Check for native UI interception
                    if (useNativeUi && url != null && (url.contains("/runtime") || url.contains("runtime/index.html"))) {
                        Log.i(TAG, "Intercepting runtime URL for native UI: $url")
                        launchInteractActivity()
                        return true
                    }

                    // Only allow localhost/127.0.0.1
                    if (url != null && (url.startsWith("http://localhost") || url.startsWith("http://127.0.0.1"))) {
                        return false
                    }

                    // Open external links in system browser
                    if (url != null) {
                        try {
                            val intent = Intent(Intent.ACTION_VIEW, android.net.Uri.parse(url))
                            startActivity(intent)
                        } catch (e: Exception) {
                            Log.e(TAG, "Failed to open external URL: $url")
                        }
                    }
                    return true
                }

                override fun onPageFinished(view: WebView?, url: String?) {
                    super.onPageFinished(view, url)
                    // Inject auth data after the real page loads (not on data: URLs)
                    if (url?.startsWith("http") == true) {
                        // Normalize URL by removing trailing slash for comparison
                        val normalizedUrl = url.trimEnd('/')
                        val normalizedLast = lastInjectedUrl?.trimEnd('/') ?: ""

                        // Only inject if this is a genuinely new page (not just trailing slash diff)
                        if (normalizedUrl != normalizedLast) {
                            Log.i(TAG, "Page loaded: $url - injecting auth data (first time for this path)")
                            lastInjectedUrl = normalizedUrl
                            // Always dispatch event on new pages - web side handles deduplication
                            injectAuthData(dispatchEvent = true)
                        } else {
                            Log.d(TAG, "Page loaded: $url - skipping duplicate injection (same path as $lastInjectedUrl)")
                        }
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
        // Start token refresh manager now that server is ready
        startTokenRefreshManager()

        // If we have a Google ID token, exchange it for a CIRIS API token
        if (googleIdToken != null && authMethod == "google") {
            CoroutineScope(Dispatchers.IO).launch {
                val exchanged = exchangeGoogleIdToken()
                withContext(Dispatchers.Main) {
                    if (exchanged) {
                        Log.i(TAG, "Successfully exchanged Google ID token for CIRIS token")
                    } else {
                        Log.w(TAG, "Token exchange failed, proceeding without CIRIS token")
                    }
                    // Hide console, show WebView
                    consoleContainer.visibility = View.GONE
                    webView.visibility = View.VISIBLE
                    loadUI()
                }
            }
        } else {
            // Hide console, show WebView (no token exchange needed for API key auth)
            consoleContainer.visibility = View.GONE
            webView.visibility = View.VISIBLE
            loadUI()
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

    /**
     * Check setup status from backend API.
     * Returns true if setup is required, false if setup is complete.
     * This is the authoritative source - not the intent extra.
     */
    private fun checkSetupStatus(): Boolean {
        return try {
            val url = URL("$SERVER_URL/v1/setup/status")
            val connection = url.openConnection() as HttpURLConnection
            connection.connectTimeout = 2000
            connection.readTimeout = 2000
            connection.requestMethod = "GET"
            val responseCode = connection.responseCode

            if (responseCode == 200) {
                val response = connection.inputStream.bufferedReader().use { it.readText() }
                connection.disconnect()
                // Parse JSON response: {"setup_required": true/false, ...}
                val gson = com.google.gson.Gson()
                val status = gson.fromJson(response, SetupStatusResponse::class.java)
                Log.i(TAG, "[SetupStatus] Backend says setup_required=${status.setup_required}")
                status.setup_required
            } else {
                Log.w(TAG, "[SetupStatus] Failed to get status (HTTP $responseCode), defaulting to intent value: $showSetup")
                connection.disconnect()
                showSetup  // Fall back to intent value if API fails
            }
        } catch (e: Exception) {
            Log.e(TAG, "[SetupStatus] Exception checking status: ${e.message}, defaulting to intent value: $showSetup")
            showSetup  // Fall back to intent value if API fails
        }
    }

    // Response model for setup status
    data class SetupStatusResponse(
        val setup_required: Boolean,
        val config_exists: Boolean?,
        val is_first_run: Boolean?
    )

    /**
     * Exchange Google ID token for CIRIS API access token.
     * This allows the web UI to make authenticated API calls.
     */
    private fun exchangeGoogleIdToken(): Boolean {
        val idToken = googleIdToken
        if (idToken == null) {
            Log.w(TAG, "[TokenExchange] No Google ID token available")
            return false
        }

        Log.i(TAG, "[TokenExchange] Starting token exchange - token length: ${idToken.length}, prefix: ${idToken.take(20)}...")

        return try {
            val url = URL("$SERVER_URL/v1/auth/native/google")
            Log.i(TAG, "[TokenExchange] Connecting to: $url")
            val connection = url.openConnection() as HttpURLConnection
            connection.connectTimeout = 15000
            connection.readTimeout = 15000
            connection.requestMethod = "POST"
            connection.setRequestProperty("Content-Type", "application/json")
            connection.doOutput = true

            // Send the request
            val requestBody = """{"id_token": "$idToken", "provider": "google"}"""
            Log.i(TAG, "[TokenExchange] Sending request - body length: ${requestBody.length}")
            connection.outputStream.bufferedWriter().use { it.write(requestBody) }

            val responseCode = connection.responseCode
            Log.i(TAG, "[TokenExchange] Response code: $responseCode")

            if (responseCode == 200) {
                // Parse response to get access token
                val response = connection.inputStream.bufferedReader().use { it.readText() }
                Log.i(TAG, "[TokenExchange] Response body: ${response.take(200)}...")
                val gson = com.google.gson.Gson()
                val tokenResponse = gson.fromJson(response, NativeTokenResponse::class.java)
                cirisAccessToken = tokenResponse.access_token
                Log.i(TAG, "[TokenExchange] SUCCESS - Got CIRIS access token for user: ${tokenResponse.user_id}, role: ${tokenResponse.role}")
                connection.disconnect()
                true
            } else {
                val error = connection.errorStream?.bufferedReader()?.use { it.readText() } ?: "Unknown error"
                Log.e(TAG, "[TokenExchange] FAILED ($responseCode): $error")
                connection.disconnect()
                false
            }
        } catch (e: Exception) {
            Log.e(TAG, "[TokenExchange] Exception: ${e.javaClass.simpleName}: ${e.message}", e)
            false
        }
    }

    // Response model for native token exchange
    data class NativeTokenResponse(
        val access_token: String,
        val token_type: String,
        val expires_in: Int,
        val user_id: String,
        val role: String,
        val email: String?,
        val name: String?
    )

    private fun loadUI() {
        val url = "$SERVER_URL$UI_PATH"
        Log.i(TAG, "Loading UI from $url")
        // Auth data is injected in onPageFinished after page loads
        webView.loadUrl(url)
    }

    private fun injectAuthData(dispatchEvent: Boolean = true) {
        // Query backend for authoritative setup status, then inject
        CoroutineScope(Dispatchers.IO).launch {
            // Get current setup status from backend (source of truth)
            val setupRequired = checkSetupStatus()
            showSetup = setupRequired  // Update our cached value

            withContext(Dispatchers.Main) {
                doInjectAuthData(setupRequired, dispatchEvent)
            }
        }
    }

    private fun doInjectAuthData(setupRequired: Boolean, dispatchEvent: Boolean) {
        // Inject auth data into localStorage for the web UI
        // The web app will check for this and use it for authentication
        val hasToken = cirisAccessToken != null

        // Comprehensive logging of what we're about to inject
        Log.i(TAG, "[Inject] ========================================")
        Log.i(TAG, "[Inject] doInjectAuthData called (dispatchEvent=$dispatchEvent)")
        Log.i(TAG, "[Inject] Values to inject:")
        Log.i(TAG, "[Inject]   authMethod: ${authMethod ?: "(null)"}")
        Log.i(TAG, "[Inject]   googleUserId: ${googleUserId ?: "(null/empty)"}")
        Log.i(TAG, "[Inject]   userEmail: ${userEmail ?: "(null)"}")
        Log.i(TAG, "[Inject]   userName: ${userName ?: "(null)"}")
        Log.i(TAG, "[Inject]   showSetup: $setupRequired (from backend)")
        Log.i(TAG, "[Inject]   hasToken: $hasToken")
        Log.i(TAG, "[Inject]   cirisAccessToken: ${if (cirisAccessToken != null) "${cirisAccessToken!!.take(20)}..." else "(null)"}")
        Log.i(TAG, "[Inject] ========================================")

        val authJson = """
            {
                "provider": "${authMethod ?: "api_key"}",
                "googleUserId": "${googleUserId ?: ""}",
                "email": "${userEmail ?: ""}",
                "displayName": "${userName ?: ""}",
                "isNativeApp": true,
                "showSetup": $setupRequired,
                "hasAccessToken": $hasToken
            }
        """.trimIndent().replace("\n", "")

        val tokenScript = if (cirisAccessToken != null) {
            """
                // Set the CIRIS access token for API authentication
                localStorage.setItem('ciris_access_token', '${cirisAccessToken}');
                localStorage.setItem('access_token', '${cirisAccessToken}');
            """
        } else {
            ""
        }

        // Only dispatch event once to prevent redirect loops
        val eventScript = if (dispatchEvent) {
            """
                // Dispatch event to notify web app of native auth (only on first injection)
                console.log('[Native] Dispatching ciris_native_auth_ready event');
                window.dispatchEvent(new CustomEvent('ciris_native_auth_ready', { detail: $authJson }));
            """
        } else {
            "console.log('[Native] Skipping event dispatch (already dispatched)');"
        }

        val script = """
            (function() {
                localStorage.setItem('ciris_native_auth', '$authJson');
                localStorage.setItem('ciris_auth_method', '${authMethod ?: "api_key"}');
                localStorage.setItem('ciris_google_user_id', '${googleUserId ?: ""}');
                localStorage.setItem('ciris_google_id_token', '${googleIdToken ?: ""}');
                localStorage.setItem('ciris_user_email', '${userEmail ?: ""}');
                localStorage.setItem('ciris_user_name', '${userName ?: ""}');

                // Backend is source of truth for show_setup - set it directly
                var backendShowSetup = ${setupRequired};
                localStorage.setItem('ciris_show_setup', backendShowSetup ? 'true' : 'false');
                console.log('[Native] Backend says setup_required=' + backendShowSetup + ' - set ciris_show_setup accordingly');

                localStorage.setItem('isNativeApp', 'true');
                $tokenScript
                console.log('[Native] Auth data injected - method: ${authMethod ?: "api_key"}, showSetup: ' + localStorage.getItem('ciris_show_setup') + ', hasToken: $hasToken');

                $eventScript
            })();
        """.trimIndent()

        webView.evaluateJavascript(script) { result ->
            Log.i(TAG, "Auth injection result: $result (dispatchEvent=$dispatchEvent)")
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
        // Set initial state of the toggle
        menu?.findItem(R.id.action_toggle_native)?.isChecked = useNativeUi
        return true
    }

    private fun launchInteractActivity() {
        val intent = Intent(this, InteractActivity::class.java)
        cirisAccessToken?.let { token ->
            intent.putExtra("access_token", token)
        }
        startActivity(intent)
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_toggle_native -> {
                useNativeUi = !useNativeUi
                item.isChecked = useNativeUi

                // Save preference
                getSharedPreferences(PREFS_UI, MODE_PRIVATE)
                    .edit()
                    .putBoolean(KEY_USE_NATIVE, useNativeUi)
                    .apply()

                // If we are currently on the runtime page and just disabled native,
                // or if we enabled it, reload might be useful, but simply toggling ensures
                // next navigation is correct.
                true
            }
            R.id.action_buy_credits -> {
                startActivity(Intent(this, PurchaseActivity::class.java))
                true
            }
            R.id.action_interact -> {
                launchInteractActivity()
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

    /**
     * Initialize CIRIS_HOME path (same logic as mobile_main.py).
     * Path: {ANDROID_DATA}/data/ai.ciris.mobile/files/ciris
     */
    private fun initializeCirisHomePath() {
        try {
            // Use the app's files directory which is always writable
            val filesDir = applicationContext.filesDir
            val cirisDir = File(filesDir, "ciris")
            if (!cirisDir.exists()) {
                cirisDir.mkdirs()
            }
            cirisHomePath = cirisDir.absolutePath
            Log.i(TAG, "CIRIS_HOME path: $cirisHomePath")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to initialize CIRIS_HOME path: ${e.message}")
        }
    }

    /**
     * Initialize the token refresh manager for Google auth.
     * Only called when using Google authentication.
     */
    private fun initializeTokenRefreshManager() {
        Log.i(TAG, "Initializing token refresh manager for Google auth")

        googleSignInHelper = GoogleSignInHelper(this)

        tokenRefreshManager = TokenRefreshManager(
            context = this,
            googleSignInHelper = googleSignInHelper!!,
            onTokenRefreshed = { newToken ->
                Log.i(TAG, "Token refreshed, new token length: ${newToken.length}")
                // Update the stored ID token
                googleIdToken = newToken
            }
        )
    }

    /**
     * Start the token refresh manager (called after server is ready).
     */
    private fun startTokenRefreshManager() {
        if (authMethod == "google" && tokenRefreshManager != null && cirisHomePath != null) {
            Log.i(TAG, "Starting token refresh manager")
            tokenRefreshManager?.start(cirisHomePath)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        // Stop token refresh manager
        tokenRefreshManager?.stop()
        // Note: Python server continues running
        // In production, implement proper shutdown
    }
}
