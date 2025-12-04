package ai.ciris.mobile

import android.animation.ArgbEvaluator
import android.animation.ValueAnimator
import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.util.TypedValue
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.activity.result.ActivityResult
import androidx.activity.result.ActivityResultLauncher
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.enableEdgeToEdge
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import ai.ciris.mobile.auth.GoogleSignInHelper
import ai.ciris.mobile.auth.TokenRefreshManager
import ai.ciris.mobile.billing.BillingApiClient
import ai.ciris.mobile.integrity.PlayIntegrityManager
import ai.ciris.mobile.integrity.IntegrityResult
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import com.google.android.gms.auth.api.signin.GoogleSignIn
import com.google.android.gms.auth.api.signin.GoogleSignInAccount
import com.google.android.gms.common.api.ApiException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.coroutines.suspendCoroutine
import kotlin.coroutines.resume
import android.graphics.Bitmap
import android.graphics.drawable.BitmapDrawable
import android.graphics.drawable.Drawable
import coil.ImageLoader
import coil.request.ImageRequest
import coil.request.SuccessResult
import coil.transform.CircleCropTransformation
import org.json.JSONObject
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
    private lateinit var fragmentContainer: FrameLayout
    private lateinit var consoleContainer: LinearLayout
    private lateinit var consoleScroll: ScrollView
    private lateinit var consoleOutput: TextView
    private lateinit var statusIndicator: TextView
    private var serverStarted = false
    private val consoleBuffer = StringBuilder()

    // Splash screen views
    private lateinit var splashContainer: LinearLayout
    private lateinit var lightsRow1: LinearLayout
    private lateinit var lightsRow2: LinearLayout
    private lateinit var splashStatus: TextView
    private lateinit var currentServiceName: TextView
    private lateinit var showLogsButton: TextView
    private lateinit var backToSplashButton: TextView

    // Prep phase views (6 lights for pydantic/native lib setup)
    private lateinit var prepLightsContainer: LinearLayout
    private lateinit var prepLightsRow: LinearLayout
    private lateinit var prepLabel: TextView
    private lateinit var servicesLabel: TextView
    private val prepLights = mutableListOf<View>()
    private val litPrepSteps = mutableSetOf<Int>()
    private val totalPrepSteps = 6

    // Service lights (22 total - 2 rows of 11)
    private val serviceLights = mutableListOf<View>()
    private val litServices = mutableSetOf<Int>()
    private var hasError = false
    private val totalServices = 22

    // Colors for lights
    private val colorOff = 0xFF2a2a3e.toInt()      // Dark gray (off)
    private val colorOn = 0xFF00d4ff.toInt()       // Cyan (on)
    private val colorError = 0xFFff4444.toInt()    // Red (error)

    // User info passed from LoginActivity
    private var authMethod: String? = null
    private var googleUserId: String? = null
    private var googleIdToken: String? = null
    private var userEmail: String? = null
    private var userName: String? = null
    private var userPhotoUrl: String? = null
    private var showSetup: Boolean = false
    private var cirisAccessToken: String? = null
    private var userRole: String = "OBSERVER"  // Default role, updated after token exchange

    // Track auth injection to prevent duplicate events
    private var authInjected = false
    private var lastInjectedUrl: String? = null

    // UI Preference
    private var useNativeUi = true

    // Custom toolbar views
    private lateinit var toolbar: androidx.appcompat.widget.Toolbar
    private lateinit var toolbarSignet: ImageView
    private lateinit var creditsContainer: View
    private lateinit var creditsCountText: TextView

    // Token refresh manager for ciris.ai proxy authentication
    private var googleSignInHelper: GoogleSignInHelper? = null
    private var tokenRefreshManager: TokenRefreshManager? = null
    private var cirisHomePath: String? = null

    // Play Integrity manager for device/app attestation
    private var integrityManager: PlayIntegrityManager? = null
    private var integrityVerified: Boolean = false

    // Activity result launcher for Google Sign-In from WebView
    private lateinit var googleSignInLauncher: ActivityResultLauncher<Intent>
    private var pendingGoogleSignInCallback: String? = null

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
        // Enable edge-to-edge display for Android 15+ (SDK 35)
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)

        // Register Google Sign-In activity result launcher BEFORE setContentView
        googleSignInLauncher = registerForActivityResult(
            ActivityResultContracts.StartActivityForResult()
        ) { result ->
            handleGoogleSignInResult(result)
        }

        setContentView(R.layout.activity_main)

        // Handle window insets for edge-to-edge display
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(android.R.id.content)) { view, windowInsets ->
            val insets = windowInsets.getInsets(WindowInsetsCompat.Type.systemBars())
            view.setPadding(insets.left, insets.top, insets.right, insets.bottom)
            WindowInsetsCompat.CONSUMED
        }

        // Set up custom toolbar (include tag makes the Toolbar have the include's ID)
        toolbar = findViewById(R.id.toolbarInclude) as androidx.appcompat.widget.Toolbar
        setSupportActionBar(toolbar)
        supportActionBar?.setDisplayShowTitleEnabled(false)

        // Set up toolbar click listeners (views are children of the toolbar)
        toolbarSignet = toolbar.findViewById(R.id.toolbarSignet)
        creditsContainer = toolbar.findViewById(R.id.creditsContainer)
        creditsCountText = toolbar.findViewById(R.id.creditsCount)

        toolbarSignet.setOnClickListener {
            showInteractFragment()
        }

        creditsContainer.setOnClickListener {
            startActivity(Intent(this, PurchaseActivity::class.java))
        }

        // Get user info from LoginActivity
        authMethod = intent.getStringExtra("auth_method") ?: "api_key"
        googleUserId = intent.getStringExtra("google_user_id")
        googleIdToken = intent.getStringExtra("google_id_token")
        userEmail = intent.getStringExtra("user_email")
        userName = intent.getStringExtra("user_name")
        userPhotoUrl = intent.getStringExtra("user_photo_url")
        showSetup = intent.getBooleanExtra("show_setup", true)

        // Store globally for LLM proxy access
        currentGoogleUserId = googleUserId

        // Save Google user info to BillingApiClient for billing API calls
        if (!googleUserId.isNullOrEmpty()) {
            val billingApiClient = BillingApiClient(this)
            billingApiClient.setGoogleUserId(googleUserId!!)
            userEmail?.let { billingApiClient.setGoogleEmail(it) }
            userName?.let { billingApiClient.setGoogleDisplayName(it) }
            googleIdToken?.let { billingApiClient.setGoogleIdToken(it) }
            Log.i(TAG, "Saved Google user info to BillingApiClient: id=$googleUserId, hasIdToken=${googleIdToken != null}")
        }

        // Comprehensive logging of received auth data
        Log.i(TAG, "[Auth Received] ========================================")
        Log.i(TAG, "[Auth Received] auth_method: $authMethod")
        Log.i(TAG, "[Auth Received] google_user_id: ${googleUserId ?: "(null/empty)"}")
        Log.i(TAG, "[Auth Received] google_id_token: ${googleIdToken?.let { "${it.take(20)}... (${it.length} chars)" } ?: "(null)"}")
        Log.i(TAG, "[Auth Received] user_email: ${userEmail ?: "(null)"}")
        Log.i(TAG, "[Auth Received] user_name: ${userName ?: "(null)"}")
        Log.i(TAG, "[Auth Received] user_photo_url: ${userPhotoUrl ?: "(null)"}")
        Log.i(TAG, "[Auth Received] show_setup: $showSetup")
        Log.i(TAG, "[Auth Received] ========================================")

        // Initialize CIRIS_HOME path (same logic as mobile_main.py)
        initializeCirisHomePath()

        // Initialize Play Integrity manager for device attestation
        integrityManager = PlayIntegrityManager(this)

        // Initialize token refresh manager for Google auth with ciris.ai
        if (authMethod == "google") {
            initializeTokenRefreshManager()
        }

        // Load UI preference
        val prefs = getSharedPreferences(PREFS_UI, MODE_PRIVATE)
        useNativeUi = prefs.getBoolean(KEY_USE_NATIVE, true)

        // Setup fragment container for native Kotlin pages
        fragmentContainer = findViewById(R.id.fragmentContainer)

        // Setup splash screen views
        splashContainer = findViewById(R.id.splashContainer)
        lightsRow1 = findViewById(R.id.lightsRow1)
        lightsRow2 = findViewById(R.id.lightsRow2)
        splashStatus = findViewById(R.id.splashStatus)
        currentServiceName = findViewById(R.id.currentServiceName)
        showLogsButton = findViewById(R.id.showLogsButton)
        backToSplashButton = findViewById(R.id.backToSplashButton)

        // Setup prep phase views
        prepLightsContainer = findViewById(R.id.prepLightsContainer)
        prepLightsRow = findViewById(R.id.prepLightsRow)
        prepLabel = findViewById(R.id.prepLabel)
        servicesLabel = findViewById(R.id.servicesLabel)

        // Setup console views
        consoleContainer = findViewById(R.id.consoleContainer)
        consoleScroll = findViewById(R.id.consoleScroll)
        consoleOutput = findViewById(R.id.consoleOutput)
        statusIndicator = findViewById(R.id.statusIndicator)

        // Create prep lights (6 for pydantic/native lib setup)
        createPrepLights()

        // Create service lights (22 total - 2 rows of 11)
        createServiceLights()

        // Setup button click handlers
        showLogsButton.setOnClickListener { showConsoleView() }
        backToSplashButton.setOnClickListener { showSplashView() }

        // Setup WebView (hidden initially)
        setupWebView()

        // Redirect Python stdout/stderr to console
        setupPythonOutputRedirect()

        // Initialize Python and start server in background to avoid ANR
        appendToConsole("Initializing...")
        initializePythonAndStartServer()
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

                // Regex to match prep phase lines: [1/6], [2/6], etc.
                val prepPattern = Regex("""\[(\d+)/6\]""")
                // Regex to match service startup lines: [SERVICE X/22] ServiceName STARTED
                val servicePattern = Regex("""\[SERVICE (\d+)/(\d+)\] (\w+) STARTED""")
                // Regex to detect errors
                val errorPattern = Regex("""ERROR|FAILED|Exception|Traceback""", RegexOption.IGNORE_CASE)

                while (true) {
                    val line = reader.readLine() ?: break
                    if (line.isNotBlank()) {
                        withContext(Dispatchers.Main) {
                            appendToConsole(line)

                            // Check for prep phase steps (pydantic/native lib setup)
                            val prepMatch = prepPattern.find(line)
                            if (prepMatch != null) {
                                val stepNum = prepMatch.groupValues[1].toIntOrNull() ?: 0
                                onPrepStepCompleted(stepNum, line)
                            }

                            // Check for service startup
                            val serviceMatch = servicePattern.find(line)
                            if (serviceMatch != null) {
                                val serviceNum = serviceMatch.groupValues[1].toIntOrNull() ?: 0
                                val serviceName = serviceMatch.groupValues[3]
                                onServiceStarted(serviceNum, serviceName)
                            }

                            // Check for errors
                            if (errorPattern.containsMatchIn(line)) {
                                onErrorDetected(line)
                            }
                        }
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Logcat reader error: ${e.message}")
            }
        }
    }

    /**
     * Create the 6 prep phase indicator lights.
     * Tracks pydantic/native library setup progress.
     */
    private fun createPrepLights() {
        prepLights.clear()

        // Convert 12dp to pixels for prep light size (smaller than service lights)
        val lightSizeDp = 12
        val lightMarginDp = 3
        val lightSizePx = TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_DIP, lightSizeDp.toFloat(), resources.displayMetrics
        ).toInt()
        val lightMarginPx = TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_DIP, lightMarginDp.toFloat(), resources.displayMetrics
        ).toInt()

        // Create 6 prep lights
        for (i in 1..totalPrepSteps) {
            val light = View(this).apply {
                layoutParams = LinearLayout.LayoutParams(lightSizePx, lightSizePx).apply {
                    setMargins(lightMarginPx, lightMarginPx, lightMarginPx, lightMarginPx)
                }
                setBackgroundColor(colorOff)
            }

            prepLights.add(light)
            prepLightsRow.addView(light)
        }

        Log.i(TAG, "Created ${prepLights.size} prep indicator lights")
    }

    /**
     * Called when a prep step completes (pydantic/native lib setup).
     */
    private fun onPrepStepCompleted(stepNum: Int, description: String) {
        if (stepNum < 1 || stepNum > totalPrepSteps) return

        // Track this step as lit
        litPrepSteps.add(stepNum)

        // Light up the indicator with animation
        val lightIndex = stepNum - 1
        if (lightIndex < prepLights.size) {
            val light = prepLights[lightIndex]
            animateLightOn(light)
        }

        // Update prep label to show progress
        prepLabel.text = "Preparing Environment... $stepNum/$totalPrepSteps"
        prepLabel.setTextColor(0xFF00d4ff.toInt())  // Cyan when active

        // Update status text with current step
        splashStatus.text = "Setting up Python runtime..."
        currentServiceName.text = description.take(50)  // Truncate long descriptions

        // When all prep steps complete, show the services section
        if (litPrepSteps.size >= totalPrepSteps) {
            prepLabel.text = "Environment Ready"
            prepLabel.setTextColor(0xFF00ff88.toInt())  // Green when complete
            servicesLabel.visibility = View.VISIBLE
        }

        Log.i(TAG, "Prep step $stepNum/$totalPrepSteps completed: ${description.take(50)}")
    }

    /**
     * Create the 22 service indicator lights (2 rows of 11).
     * Looks like old computer startup LEDs.
     */
    private fun createServiceLights() {
        serviceLights.clear()

        // Convert 16dp to pixels for light size
        val lightSizeDp = 16
        val lightMarginDp = 4
        val lightSizePx = TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_DIP, lightSizeDp.toFloat(), resources.displayMetrics
        ).toInt()
        val lightMarginPx = TypedValue.applyDimension(
            TypedValue.COMPLEX_UNIT_DIP, lightMarginDp.toFloat(), resources.displayMetrics
        ).toInt()

        // Create 22 lights
        for (i in 1..totalServices) {
            val light = View(this).apply {
                layoutParams = LinearLayout.LayoutParams(lightSizePx, lightSizePx).apply {
                    setMargins(lightMarginPx, lightMarginPx, lightMarginPx, lightMarginPx)
                }
                setBackgroundColor(colorOff)
            }

            serviceLights.add(light)

            // Add to appropriate row (1-11 in row 1, 12-22 in row 2)
            if (i <= 11) {
                lightsRow1.addView(light)
            } else {
                lightsRow2.addView(light)
            }
        }

        Log.i(TAG, "Created ${serviceLights.size} service indicator lights")
    }

    /**
     * Called when a service starts. Lights up the corresponding indicator.
     */
    private fun onServiceStarted(serviceNum: Int, serviceName: String) {
        if (serviceNum < 1 || serviceNum > totalServices) return

        // Track this service as lit
        litServices.add(serviceNum)

        // Light up the indicator with animation
        val lightIndex = serviceNum - 1
        if (lightIndex < serviceLights.size) {
            val light = serviceLights[lightIndex]
            animateLightOn(light)
        }

        // Update status text
        splashStatus.text = "Starting services... ${litServices.size}/$totalServices"
        currentServiceName.text = serviceName

        Log.i(TAG, "Service $serviceNum/$totalServices started: $serviceName")
    }

    /**
     * Animate a light turning on with a glow effect.
     */
    private fun animateLightOn(light: View) {
        val animator = ValueAnimator.ofObject(ArgbEvaluator(), colorOff, colorOn)
        animator.duration = 200
        animator.addUpdateListener { animation ->
            light.setBackgroundColor(animation.animatedValue as Int)
        }
        animator.start()
    }

    /**
     * Called when an error is detected in the logs.
     * Shows error state and makes log view accessible.
     */
    private fun onErrorDetected(errorLine: String) {
        if (hasError) return  // Already in error state
        hasError = true

        Log.e(TAG, "Error detected: $errorLine")

        // Update splash status to show error
        splashStatus.text = "Error detected"
        splashStatus.setTextColor(colorError)

        // Show the "Show Logs" button
        showLogsButton.visibility = View.VISIBLE

        // Update status indicator
        updateStatus("Error", "red")
    }

    /**
     * Show the console/log view.
     */
    private fun showConsoleView() {
        splashContainer.visibility = View.GONE
        consoleContainer.visibility = View.VISIBLE
    }

    /**
     * Show the splash screen view.
     */
    private fun showSplashView() {
        consoleContainer.visibility = View.GONE
        splashContainer.visibility = View.VISIBLE
    }

    /**
     * Initialize Python runtime and start server in background.
     * This prevents ANR (Application Not Responding) during startup.
     */
    private fun initializePythonAndStartServer() {
        CoroutineScope(Dispatchers.Default).launch {
            try {
                withContext(Dispatchers.Main) {
                    appendToConsole("Initializing Python runtime...")
                    updateStatus("Starting", "yellow")
                }

                // PRE-FLIGHT TOKEN REFRESH: Get fresh Google ID token BEFORE starting Python
                // This ensures Python's billing service has a valid token when it reads .env
                if (authMethod == "google") {
                    withContext(Dispatchers.Main) {
                        appendToConsole("Refreshing authentication token...")
                    }

                    val freshToken = refreshGoogleTokenBeforeStartup()
                    if (freshToken != null) {
                        // Write fresh token to .env BEFORE Python starts
                        val written = writeTokenToEnvFile(freshToken)
                        withContext(Dispatchers.Main) {
                            if (written) {
                                appendToConsole("✓ Authentication token refreshed")
                            } else {
                                appendToConsole("⚠ Could not save token - billing may fail")
                            }
                        }
                    } else {
                        withContext(Dispatchers.Main) {
                            appendToConsole("⚠ Token refresh failed - using existing token")
                        }
                        // Still try to write the existing token if we have one
                        googleIdToken?.let { writeTokenToEnvFile(it) }
                    }
                }

                // Python.start() can take several seconds - do it off main thread
                // Note: AndroidPlatform requires a Context, but doesn't need to be on main thread
                if (!Python.isStarted()) {
                    Python.start(AndroidPlatform(this@MainActivity))
                    withContext(Dispatchers.Main) {
                        appendToConsole("✓ Python runtime initialized")
                    }
                    Log.i(TAG, "Python runtime initialized")
                } else {
                    withContext(Dispatchers.Main) {
                        appendToConsole("✓ Python runtime already running")
                    }
                }

                // Now start the server
                startPythonServer()
            } catch (e: Exception) {
                Log.e(TAG, "Failed to initialize Python: ${e.message}", e)
                withContext(Dispatchers.Main) {
                    appendToConsole("❌ Failed to initialize Python: ${e.message}")
                    updateStatus("Error", "red")
                }
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
                    // Intercept ciris:// URL scheme for native functionality
                    if (url != null && url.startsWith("ciris://")) {
                        Log.i(TAG, "Intercepting CIRIS URL scheme: $url")
                        handleCirisUrlScheme(url)
                        return true
                    }

                    // Check for native UI interception
                    // NOT API endpoints like /v1/system/runtime/reasoning-stream
                    if (useNativeUi && url != null) {
                        // Exclude API endpoints
                        val isApiEndpoint = url.contains("/v1/") || url.contains("/api/")

                        // Check for interact page -> InteractActivity (chat UI)
                        val isInteractPage = url.endsWith("/interact") ||
                                            url.endsWith("/interact/") ||
                                            url.contains("/interact/index.html") ||
                                            url.contains("/interact?")
                        if (isInteractPage && !isApiEndpoint) {
                            Log.i(TAG, "Intercepting interact page for native chat UI: $url")
                            launchInteractActivity()
                            return true
                        }

                        // Check for runtime page -> RuntimeActivity (SSE stream viewer)
                        val isRuntimePage = url.endsWith("/runtime") ||
                                           url.endsWith("/runtime/") ||
                                           url.contains("/runtime/index.html") ||
                                           url.contains("/runtime?")
                        if (isRuntimePage && !isApiEndpoint) {
                            Log.i(TAG, "Intercepting runtime page for native stream viewer: $url")
                            launchRuntimeActivity()
                            return true
                        }
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

                override fun onPageStarted(view: WebView?, url: String?, favicon: android.graphics.Bitmap?) {
                    super.onPageStarted(view, url, favicon)
                    // CRITICAL: Clear stale tokens BEFORE the page loads and React initializes
                    // This prevents the SDK from using old tokens from previous sessions
                    if (url?.startsWith("http") == true && cirisAccessToken != null) {
                        val clearStaleTokenScript = """
                            (function() {
                                var existing = localStorage.getItem('ciris_auth_token');
                                if (existing) {
                                    console.log('[Native onPageStarted] Clearing stale ciris_auth_token BEFORE page loads');
                                    localStorage.removeItem('ciris_auth_token');
                                }
                                // Also set the fresh token immediately
                                var authTokenJson = JSON.stringify({
                                    access_token: '${cirisAccessToken}',
                                    token_type: 'Bearer',
                                    expires_in: 2592000,
                                    user_id: 'native_user',
                                    role: 'SYSTEM_ADMIN',
                                    created_at: Date.now()
                                });
                                localStorage.setItem('ciris_auth_token', authTokenJson);
                                localStorage.setItem('ciris_access_token', '${cirisAccessToken}');
                                console.log('[Native onPageStarted] Injected fresh token BEFORE page loads');
                            })();
                        """.trimIndent()
                        view?.evaluateJavascript(clearStaleTokenScript, null)
                        Log.i(TAG, "[onPageStarted] Cleared stale token and injected fresh one for: $url")
                    }
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

            // Add JavaScript interface for native Google Sign-In
            addJavascriptInterface(WebAppInterface(), "CIRISNative")
        }

        Log.i(TAG, "WebView configured with CIRISNative JavaScript interface")
    }

    /**
     * JavaScript interface for WebView to call native Android methods.
     * Called from JavaScript via: window.CIRISNative.signIn()
     */
    inner class WebAppInterface {
        /**
         * Trigger native Google Sign-In flow.
         * JavaScript should call this and then wait for the callback.
         * @param callbackId A unique ID to track this sign-in request
         */
        @JavascriptInterface
        fun signIn(callbackId: String) {
            Log.i(TAG, "[WebAppInterface] signIn() called from JavaScript with callbackId: $callbackId")
            pendingGoogleSignInCallback = callbackId

            // Must run on main thread
            runOnUiThread {
                try {
                    // Initialize GoogleSignInHelper if not already done
                    if (googleSignInHelper == null) {
                        googleSignInHelper = GoogleSignInHelper(this@MainActivity)
                    }

                    // Get the sign-in intent and launch
                    val signInIntent = googleSignInHelper!!.getSignInIntent()
                    googleSignInLauncher.launch(signInIntent)
                    Log.i(TAG, "[WebAppInterface] Launched Google Sign-In activity")
                } catch (e: Exception) {
                    Log.e(TAG, "[WebAppInterface] Failed to launch sign-in: ${e.message}", e)
                    sendGoogleSignInError(callbackId, e.message ?: "Failed to launch sign-in")
                }
            }
        }

        /**
         * Check if native Google Sign-In is available.
         * @return true if available
         */
        @JavascriptInterface
        fun isGoogleSignInAvailable(): Boolean {
            return true
        }

        /**
         * Get the current Google user if already signed in.
         * @return JSON string with user info or null
         */
        @JavascriptInterface
        fun getCurrentUser(): String? {
            val account = GoogleSignIn.getLastSignedInAccount(this@MainActivity)
            return if (account != null) {
                try {
                    val json = JSONObject()
                    json.put("id", account.id)
                    json.put("email", account.email)
                    json.put("name", account.displayName)
                    json.put("photoUrl", account.photoUrl?.toString())
                    json.put("idToken", account.idToken)
                    json.toString()
                } catch (e: Exception) {
                    Log.e(TAG, "[WebAppInterface] Error getting current user: ${e.message}")
                    null
                }
            } else {
                null
            }
        }

        /**
         * Refresh the CIRIS access token by re-exchanging the Google ID token.
         * Call this after setup completes to get a token with updated role.
         */
        @JavascriptInterface
        fun refreshToken() {
            Log.i(TAG, "[WebAppInterface] refreshToken() called from JavaScript")

            if (googleIdToken == null || authMethod != "google") {
                Log.w(TAG, "[WebAppInterface] Cannot refresh - no Google ID token or not Google auth")
                return
            }

            CoroutineScope(Dispatchers.IO).launch {
                val exchanged = exchangeGoogleIdToken()
                withContext(Dispatchers.Main) {
                    if (exchanged) {
                        Log.i(TAG, "[WebAppInterface] Token refreshed successfully")
                        // Re-inject auth data with fresh token
                        injectAuthData(true)
                    } else {
                        Log.w(TAG, "[WebAppInterface] Token refresh failed")
                    }
                }
            }
        }
    }

    /**
     * Handle the result from Google Sign-In activity.
     */
    private fun handleGoogleSignInResult(result: ActivityResult) {
        val callbackId = pendingGoogleSignInCallback
        pendingGoogleSignInCallback = null

        Log.i(TAG, "[GoogleSignIn] handleGoogleSignInResult - resultCode: ${result.resultCode}, callbackId: $callbackId")

        if (callbackId == null) {
            Log.e(TAG, "[GoogleSignIn] No callback ID found for sign-in result")
            return
        }

        try {
            val task = GoogleSignIn.getSignedInAccountFromIntent(result.data)
            val account = task.getResult(ApiException::class.java)

            if (account != null) {
                Log.i(TAG, "[GoogleSignIn] Sign-in successful: ${account.email}, hasIdToken: ${account.idToken != null}")

                // Update stored values
                googleUserId = account.id
                googleIdToken = account.idToken
                userEmail = account.email
                userName = account.displayName
                userPhotoUrl = account.photoUrl?.toString()
                currentGoogleUserId = account.id

                // Also save to BillingApiClient for billing API calls
                val billingApiClient = BillingApiClient(this)
                account.id?.let { billingApiClient.setGoogleUserId(it) }
                account.email?.let { billingApiClient.setGoogleEmail(it) }
                account.displayName?.let { billingApiClient.setGoogleDisplayName(it) }
                account.idToken?.let { billingApiClient.setGoogleIdToken(it) }
                Log.i(TAG, "[GoogleSignIn] Saved user info to BillingApiClient: id=${account.id}, email=${account.email}, name=${account.displayName}, hasIdToken=${account.idToken != null}")

                // Build JSON response for JavaScript
                val json = JSONObject()
                json.put("id", account.id)
                json.put("email", account.email)
                json.put("name", account.displayName)
                json.put("photoUrl", account.photoUrl?.toString())
                json.put("idToken", account.idToken)

                sendGoogleSignInSuccess(callbackId, json.toString())
            } else {
                Log.e(TAG, "[GoogleSignIn] Sign-in returned null account")
                sendGoogleSignInError(callbackId, "Sign-in returned null account")
            }
        } catch (e: ApiException) {
            Log.e(TAG, "[GoogleSignIn] Sign-in failed: ${e.statusCode} - ${e.message}")
            sendGoogleSignInError(callbackId, "Sign-in failed: ${e.statusCode} - ${e.message}")
        } catch (e: Exception) {
            Log.e(TAG, "[GoogleSignIn] Unexpected error: ${e.message}", e)
            sendGoogleSignInError(callbackId, "Unexpected error: ${e.message}")
        }
    }

    /**
     * Send success result to JavaScript callback.
     */
    private fun sendGoogleSignInSuccess(callbackId: String, jsonResult: String) {
        runOnUiThread {
            val escapedJson = jsonResult.replace("'", "\\'").replace("\n", "\\n")
            val script = """
                (function() {
                    var callback = window.__ciris_google_signin_callbacks && window.__ciris_google_signin_callbacks['$callbackId'];
                    if (callback && callback.resolve) {
                        console.log('[CIRISNative] Resolving sign-in callback: $callbackId');
                        callback.resolve(JSON.parse('$escapedJson'));
                        delete window.__ciris_google_signin_callbacks['$callbackId'];
                    } else {
                        console.error('[CIRISNative] No callback found for: $callbackId');
                    }
                })();
            """.trimIndent()
            webView.evaluateJavascript(script) { result ->
                Log.i(TAG, "[GoogleSignIn] Success callback sent: $result")
            }
        }
    }

    /**
     * Send error result to JavaScript callback.
     */
    private fun sendGoogleSignInError(callbackId: String, errorMessage: String) {
        runOnUiThread {
            val escapedError = errorMessage.replace("'", "\\'").replace("\n", "\\n")
            val script = """
                (function() {
                    var callback = window.__ciris_google_signin_callbacks && window.__ciris_google_signin_callbacks['$callbackId'];
                    if (callback && callback.reject) {
                        console.log('[CIRISNative] Rejecting sign-in callback: $callbackId');
                        callback.reject(new Error('$escapedError'));
                        delete window.__ciris_google_signin_callbacks['$callbackId'];
                    } else {
                        console.error('[CIRISNative] No callback found for: $callbackId');
                    }
                })();
            """.trimIndent()
            webView.evaluateJavascript(script) { result ->
                Log.i(TAG, "[GoogleSignIn] Error callback sent: $result")
            }
        }
    }

    private fun startPythonServer() {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                withContext(Dispatchers.Main) {
                    appendToConsole("Starting CIRIS runtime...")
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

        // If we have a Google ID token, perform integrity check + token exchange
        if (googleIdToken != null && authMethod == "google") {
            CoroutineScope(Dispatchers.IO).launch {
                // Step 1: Verify device/app integrity with billing.ciris.ai
                withContext(Dispatchers.Main) {
                    appendToConsole("Verifying device integrity...")
                }

                val integrityResult = verifyDeviceIntegrity()
                if (integrityResult != null && integrityResult.verified) {
                    Log.i(TAG, "Device integrity verified: ${integrityResult.deviceIntegrity}")
                    integrityVerified = true
                    withContext(Dispatchers.Main) {
                        appendToConsole("✓ Device integrity verified")
                    }
                } else {
                    Log.w(TAG, "Device integrity check failed: ${integrityResult?.error ?: "unknown"}")
                    integrityVerified = false
                    withContext(Dispatchers.Main) {
                        appendToConsole("⚠ Device integrity check: ${integrityResult?.error ?: "failed"}")
                        // Continue anyway - integrity is logged but not blocking for now
                    }
                }

                // Step 2: Exchange Google ID token for CIRIS API token
                val exchanged = exchangeGoogleIdToken()
                withContext(Dispatchers.Main) {
                    if (exchanged) {
                        Log.i(TAG, "Successfully exchanged Google ID token for CIRIS token")
                        appendToConsole("✓ Authentication complete")
                    } else {
                        Log.w(TAG, "Token exchange failed, proceeding without CIRIS token")
                        appendToConsole("⚠ Token exchange failed")
                    }

                    // Short delay to let user see status
                    delay(300)

                    // Hide splash/console, show toolbar and Kotlin interact fragment
                    splashContainer.visibility = View.GONE
                    consoleContainer.visibility = View.GONE
                    findViewById<View>(R.id.toolbarInclude).visibility = View.VISIBLE
                    showInteractFragment()
                    loadCreditsBalance()
                }
            }
        } else {
            // Hide splash/console, show toolbar and Kotlin interact fragment (no token exchange needed for API key auth)
            splashContainer.visibility = View.GONE
            consoleContainer.visibility = View.GONE
            findViewById<View>(R.id.toolbarInclude).visibility = View.VISIBLE
            showInteractFragment()
            loadCreditsBalance()
        }
    }

    /**
     * Verify device and app integrity with billing.ciris.ai.
     * This checks that the device is genuine and the app is unmodified.
     */
    private suspend fun verifyDeviceIntegrity(): IntegrityResult? {
        return try {
            integrityManager?.verifyIntegrity()
        } catch (e: Exception) {
            Log.e(TAG, "Integrity verification exception: ${e.message}", e)
            IntegrityResult(verified = false, error = "Exception: ${e.message}")
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
                // Parse JSON response: {"data": {"setup_required": true/false, ...}, "metadata": {...}}
                val gson = com.google.gson.Gson()
                val status = gson.fromJson(response, SetupStatusResponse::class.java)
                Log.i(TAG, "[SetupStatus] Backend says setup_required=${status.data.setup_required}")
                status.data.setup_required
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

    // Response model for setup status (wrapped in SuccessResponse)
    data class SetupStatusData(
        val setup_required: Boolean,
        val config_exists: Boolean?,
        val is_first_run: Boolean?
    )

    // Wrapper for API responses (backend returns {"data": {...}, "metadata": {...}})
    data class SetupStatusResponse(
        val data: SetupStatusData
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
                userRole = tokenResponse.role
                Log.i(TAG, "[TokenExchange] SUCCESS - Got CIRIS access token for user: ${tokenResponse.user_id}, role: ${tokenResponse.role}")
                // Refresh menu to show/hide admin items based on role
                runOnUiThread { invalidateOptionsMenu() }
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

    /**
     * Load and display the user's credit balance in the toolbar.
     */
    private fun loadCreditsBalance() {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val billingApiClient = BillingApiClient(this@MainActivity)
                val result = billingApiClient.getBalance()

                withContext(Dispatchers.Main) {
                    if (result.success) {
                        creditsCountText.text = result.balance.toString()
                    } else {
                        creditsCountText.text = "--"
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error loading credits balance", e)
                withContext(Dispatchers.Main) {
                    creditsCountText.text = "--"
                }
            }
        }
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
                // ALWAYS clear stale ciris_auth_token first - this is what SDK's AuthStore reads
                // We need to ensure the fresh token from this session is used, not a cached one
                var existingAuthToken = localStorage.getItem('ciris_auth_token');
                if (existingAuthToken) {
                    console.log('[Native] Clearing stale ciris_auth_token from previous session');
                    localStorage.removeItem('ciris_auth_token');
                }

                // Always inject the fresh token - we have a valid token from this session
                localStorage.setItem('ciris_access_token', '${cirisAccessToken}');
                localStorage.setItem('access_token', '${cirisAccessToken}');
                // Also set ciris_auth_token which is what SDK's AuthStore reads
                var authTokenJson = JSON.stringify({
                    access_token: '${cirisAccessToken}',
                    token_type: 'Bearer',
                    expires_in: 2592000,
                    user_id: 'native_user',
                    role: '$userRole',
                    created_at: Date.now()
                });
                localStorage.setItem('ciris_auth_token', authTokenJson);
                console.log('[Native] Injected CIRIS access token to ciris_auth_token (role: $userRole)');
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

        // Hide admin menu if user is not ADMIN or SYSTEM_ADMIN
        val isAdmin = userRole == "ADMIN" || userRole == "SYSTEM_ADMIN"
        menu?.findItem(R.id.action_admin)?.isVisible = isAdmin
        Log.i(TAG, "Menu: userRole=$userRole, isAdmin=$isAdmin")

        // Set account icon based on auth method
        val accountItem = menu?.findItem(R.id.action_account)
        if (authMethod == "google" && !userPhotoUrl.isNullOrEmpty()) {
            // Load user's profile picture using Coil
            Log.i(TAG, "Account menu: loading profile picture from $userPhotoUrl")
            loadProfilePicture(accountItem, userPhotoUrl!!)
        } else if (authMethod == "google") {
            // OAuth user without photo - use person icon
            accountItem?.setIcon(R.drawable.ic_account)
            Log.i(TAG, "Account menu: using person icon for OAuth user (no photo URL)")
        }
        // Default icon is meatball from XML for all other cases

        return true
    }

    /**
     * Load user's profile picture into the menu item icon.
     */
    private fun loadProfilePicture(menuItem: MenuItem?, photoUrl: String) {
        if (menuItem == null) return

        CoroutineScope(Dispatchers.IO).launch {
            try {
                val imageLoader = ImageLoader(this@MainActivity)
                val request = ImageRequest.Builder(this@MainActivity)
                    .data(photoUrl)
                    .size(96)  // ActionBar icon size in pixels
                    .transformations(CircleCropTransformation())
                    .build()

                val result = imageLoader.execute(request)
                if (result is SuccessResult) {
                    val drawable = result.drawable
                    withContext(Dispatchers.Main) {
                        menuItem.icon = drawable
                        Log.i(TAG, "Profile picture loaded successfully")
                    }
                } else {
                    Log.w(TAG, "Failed to load profile picture, using fallback")
                    withContext(Dispatchers.Main) {
                        menuItem.setIcon(R.drawable.ic_account)
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error loading profile picture: ${e.message}")
                withContext(Dispatchers.Main) {
                    menuItem.setIcon(R.drawable.ic_account)
                }
            }
        }
    }

    private fun showInteractFragment() {
        Log.i(TAG, "Showing InteractFragment")
        // Hide WebView, show fragment container
        webView.visibility = View.GONE
        fragmentContainer.visibility = View.VISIBLE

        // Create and show fragment
        val fragment = InteractFragment.newInstance(cirisAccessToken)
        supportFragmentManager.beginTransaction()
            .replace(R.id.fragmentContainer, fragment, "interact_fragment")
            .addToBackStack("interact")
            .commit()
    }

    private fun hideFragmentShowWebView() {
        Log.i(TAG, "Hiding fragment, showing WebView")
        // Hide fragment container, show WebView
        fragmentContainer.visibility = View.GONE
        webView.visibility = View.VISIBLE

        // Remove fragment if present
        supportFragmentManager.findFragmentByTag("interact_fragment")?.let {
            supportFragmentManager.beginTransaction().remove(it).commit()
        }
        supportFragmentManager.popBackStack()
    }

    // Keep for backward compatibility - redirects to fragment
    private fun launchInteractActivity() {
        showInteractFragment()
    }

    private fun launchRuntimeActivity() {
        val intent = Intent(this, RuntimeActivity::class.java)
        cirisAccessToken?.let { token ->
            intent.putExtra("access_token", token)
        }
        startActivity(intent)
    }

    /**
     * Handle ciris:// URL scheme for native functionality.
     * Currently supports:
     * - ciris://purchase/{productId} - Launch Google Play purchase flow
     */
    private fun handleCirisUrlScheme(url: String) {
        try {
            val uri = android.net.Uri.parse(url)
            val host = uri.host
            val pathSegments = uri.pathSegments

            when (host) {
                "purchase" -> {
                    // ciris://purchase/{productId}
                    val productId = if (pathSegments.isNotEmpty()) pathSegments[0] else null
                    Log.i(TAG, "Launching purchase flow for product: $productId")
                    val intent = Intent(this, PurchaseActivity::class.java)
                    if (productId != null) {
                        intent.putExtra("product_id", productId)
                    }
                    startActivity(intent)
                }
                else -> {
                    Log.w(TAG, "Unknown CIRIS URL scheme host: $host")
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error handling CIRIS URL scheme: ${e.message}")
        }
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        return when (item.itemId) {
            // System submenu items
            R.id.action_memory_graph -> {
                navigateToWebPage("/memory")
                true
            }
            R.id.action_dashboard -> {
                navigateToWebPage("/dashboard")
                true
            }
            R.id.action_tools -> {
                navigateToWebPage("/tools")
                true
            }
            // Admin submenu items
            R.id.action_admin_system -> {
                navigateToWebPage("/system")
                true
            }
            R.id.action_runtime -> {
                navigateToWebPage("/runtime")
                true
            }
            R.id.action_config -> {
                navigateToWebPage("/config")
                true
            }
            R.id.action_users -> {
                navigateToWebPage("/users")
                true
            }
            R.id.action_wa -> {
                navigateToWebPage("/wa")
                true
            }
            R.id.action_api_explorer -> {
                navigateToWebPage("/api-demo")
                true
            }
            R.id.action_api_docs -> {
                navigateToWebPage("/docs")
                true
            }
            R.id.action_audit -> {
                navigateToWebPage("/audit")
                true
            }
            R.id.action_logs -> {
                navigateToWebPage("/logs")
                true
            }
            // Overflow menu items
            R.id.action_interact -> {
                launchInteractActivity()
                true
            }
            R.id.action_refresh -> {
                webView.reload()
                true
            }
            // Account submenu items
            R.id.action_account_settings -> {
                navigateToWebPage("/account")
                true
            }
            R.id.action_settings -> {
                navigateToWebPage("/account/settings")
                true
            }
            R.id.action_consent -> {
                navigateToWebPage("/account/consent")
                true
            }
            R.id.action_privacy -> {
                navigateToWebPage("/account/privacy")
                true
            }
            R.id.action_api_keys -> {
                navigateToWebPage("/account/api-keys")
                true
            }
            R.id.action_billing -> {
                navigateToWebPage("/billing")
                true
            }
            R.id.action_logout -> {
                performLogout()
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }

    /**
     * Navigate to a page in the webview.
     */
    private fun navigateToWebPage(path: String) {
        // Hide fragment if visible, show WebView
        if (fragmentContainer.visibility == View.VISIBLE) {
            fragmentContainer.visibility = View.GONE
            webView.visibility = View.VISIBLE
            supportFragmentManager.findFragmentByTag("interact_fragment")?.let {
                supportFragmentManager.beginTransaction().remove(it).commit()
            }
            supportFragmentManager.popBackStack()
        }

        val url = "$SERVER_URL$path"
        Log.i(TAG, "Navigating to: $url")
        webView.loadUrl(url)
    }

    /**
     * Perform logout - sign out of Google (if applicable) and return to login screen.
     */
    private fun performLogout() {
        Log.i(TAG, "Performing logout, auth_method: $authMethod")

        // Stop token refresh manager
        tokenRefreshManager?.stop()

        // Sign out from Google if using OAuth
        if (authMethod == "google" && googleSignInHelper != null) {
            googleSignInHelper?.signOut {
                Log.i(TAG, "Google sign-out complete")
                returnToLogin()
            }
        } else {
            returnToLogin()
        }
    }

    /**
     * Return to the login screen.
     */
    private fun returnToLogin() {
        Log.i(TAG, "Returning to login screen")

        // Clear stored tokens
        cirisAccessToken = null
        googleIdToken = null

        // Clear Google user ID from billing SharedPreferences
        val prefs = getSharedPreferences("ciris_settings", MODE_PRIVATE)
        prefs.edit().remove("google_user_id").apply()
        Log.i(TAG, "Cleared Google user ID from billing prefs")

        // Start LoginActivity and clear the activity stack
        val intent = Intent(this, ai.ciris.mobile.auth.LoginActivity::class.java)
        intent.flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
        startActivity(intent)
        finish()
    }

    override fun onBackPressed() {
        // If fragment is showing, go back to WebView
        if (fragmentContainer.visibility == View.VISIBLE) {
            hideFragmentShowWebView()
            return
        }
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
            integrityManager = integrityManager,  // Pass integrity manager for re-verification on refresh
            onTokenRefreshed = { newToken ->
                Log.i(TAG, "Token refreshed, new token length: ${newToken.length}")
                // Update the stored ID token
                googleIdToken = newToken
            },
            onIntegrityChecked = { result ->
                Log.i(TAG, "Integrity re-check on token refresh: verified=${result.verified}")
                integrityVerified = result.verified
                if (!result.verified) {
                    Log.w(TAG, "Device integrity failed on token refresh: ${result.error}")
                }
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

    /**
     * Pre-flight token refresh: Get a fresh Google ID token BEFORE starting Python.
     * This ensures the .env file has a valid token when Python's billing service reads it.
     *
     * Returns the fresh token, or null if refresh failed.
     */
    private suspend fun refreshGoogleTokenBeforeStartup(): String? {
        if (authMethod != "google" || googleSignInHelper == null) {
            Log.i(TAG, "[PreflightTokenRefresh] Skipping - not using Google auth")
            return null
        }

        Log.i(TAG, "[PreflightTokenRefresh] Refreshing Google ID token before Python startup...")

        return suspendCoroutine { continuation ->
            googleSignInHelper!!.silentSignIn { result ->
                when (result) {
                    is GoogleSignInHelper.SignInResult.Success -> {
                        val freshToken = result.account.idToken
                        if (freshToken != null) {
                            Log.i(TAG, "[PreflightTokenRefresh] Got fresh token (${freshToken.length} chars)")
                            // Update our stored token - the main purpose is to write to .env for Python
                            this@MainActivity.googleIdToken = freshToken
                            continuation.resume(freshToken)
                        } else {
                            Log.w(TAG, "[PreflightTokenRefresh] Silent sign-in succeeded but no ID token")
                            continuation.resume(null)
                        }
                    }
                    is GoogleSignInHelper.SignInResult.Error -> {
                        Log.e(TAG, "[PreflightTokenRefresh] Silent sign-in failed: ${result.message}")
                        continuation.resume(null)
                    }
                }
            }
        }
    }

    /**
     * Write a fresh Google ID token to the .env file BEFORE Python starts.
     * This ensures Python's billing service has a valid token on first read.
     */
    private fun writeTokenToEnvFile(token: String): Boolean {
        val envFile = cirisHomePath?.let { File(it, ".env") } ?: run {
            Log.w(TAG, "[PreflightTokenRefresh] Cannot write .env - CIRIS_HOME not set")
            return false
        }

        try {
            if (!envFile.exists()) {
                // Don't create .env file - let the setup wizard handle first-run configuration
                // Only update existing .env files with fresh tokens
                Log.i(TAG, "[PreflightTokenRefresh] No .env file exists - skipping (first-run will be handled by setup wizard)")
                return false
            }

            // Update existing .env file
            var content = envFile.readText()
            var updated = false

            // Update OPENAI_API_KEY
            val openaiPatterns = listOf(
                Regex("""OPENAI_API_KEY="[^"]*""""),
                Regex("""OPENAI_API_KEY='[^']*'"""),
                Regex("""OPENAI_API_KEY=[^\n]*""")
            )
            for (pattern in openaiPatterns) {
                if (pattern.containsMatchIn(content)) {
                    content = pattern.replace(content, """OPENAI_API_KEY="$token"""")
                    updated = true
                    break
                }
            }

            // If OPENAI_API_KEY not found, append it
            if (!updated) {
                content += "\nOPENAI_API_KEY=\"$token\"\n"
                updated = true
            }

            // Also update CIRIS_BILLING_GOOGLE_ID_TOKEN
            val billingPatterns = listOf(
                Regex("""CIRIS_BILLING_GOOGLE_ID_TOKEN="[^"]*""""),
                Regex("""CIRIS_BILLING_GOOGLE_ID_TOKEN='[^']*'"""),
                Regex("""CIRIS_BILLING_GOOGLE_ID_TOKEN=[^\n]*""")
            )
            var billingUpdated = false
            for (pattern in billingPatterns) {
                if (pattern.containsMatchIn(content)) {
                    content = pattern.replace(content, """CIRIS_BILLING_GOOGLE_ID_TOKEN="$token"""")
                    billingUpdated = true
                    break
                }
            }
            if (!billingUpdated) {
                content += "\nCIRIS_BILLING_GOOGLE_ID_TOKEN=\"$token\"\n"
            }

            envFile.writeText(content)
            Log.i(TAG, "[PreflightTokenRefresh] Updated .env file with fresh token")
            return true
        } catch (e: Exception) {
            Log.e(TAG, "[PreflightTokenRefresh] Failed to write .env file: ${e.message}")
            return false
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
