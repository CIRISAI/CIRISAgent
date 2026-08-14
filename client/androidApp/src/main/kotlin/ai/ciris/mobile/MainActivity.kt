package ai.ciris.mobile

import ai.ciris.mobile.billing.BillingManager
import ai.ciris.mobile.billing.PurchaseResult
import ai.ciris.mobile.billing.VerifyResult
import ai.ciris.mobile.integrity.PlayIntegrityManager
import ai.ciris.mobile.integrity.PlayIntegrityResult
import ai.ciris.mobile.shared.CIRISApp
import ai.ciris.mobile.shared.DeviceAttestationCallback
import ai.ciris.mobile.shared.DeviceAttestationResult
import ai.ciris.mobile.shared.GoogleSignInCallback
import ai.ciris.mobile.shared.NativeSignInResult
import ai.ciris.mobile.shared.PurchaseLauncher
import ai.ciris.mobile.shared.PurchaseResultCallback
import ai.ciris.mobile.shared.PurchaseResultType
import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.config.CIRISConfig
import ai.ciris.mobile.shared.platform.AppRestarter
import ai.ciris.mobile.shared.platform.PythonRuntime
import ai.ciris.mobile.shared.localization.LocalizationResourceLoader
import ai.ciris.mobile.shared.platform.initCellVizProbe
import ai.ciris.mobile.shared.platform.initLocalInferenceProbe
import ai.ciris.mobile.shared.platform.initUrlOpener
import ai.ciris.mobile.shared.diagnostics.NetworkDiagnosticsAndroid
import ai.ciris.mobile.shared.testing.AndroidTestAutomationServer
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.SupervisorJob
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import com.google.android.gms.auth.api.signin.GoogleSignIn
import com.google.android.gms.auth.api.signin.GoogleSignInClient
import com.google.android.gms.auth.api.signin.GoogleSignInOptions
import com.google.android.gms.common.api.ApiException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

/**
 * MainActivity for CIRIS Android (KMP version)
 *
 * Flow:
 * 1. Show minimal Python init splash
 * 2. Start Python runtime & CIRIS server
 * 3. Once server responds, show CIRISApp (which has its own StartupScreen with 22 lights)
 * 4. CIRISApp handles navigation to InteractScreen or SettingsScreen
 */
class MainActivity : ComponentActivity() {

    private val TAG = "MainActivity"
    private val RC_SIGN_IN = 9001

    // Google Sign-In
    private lateinit var googleSignInClient: GoogleSignInClient
    private var pendingGoogleSignInCallback: ((NativeSignInResult) -> Unit)? = null

    // Google Play Billing
    private lateinit var billingManager: BillingManager
    private var purchaseResultCallback: PurchaseResultCallback? = null

    // Google Play Integrity
    private lateinit var playIntegrityManager: PlayIntegrityManager
    private val integrityScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    // API client for purchase verification (will be set when server is ready)
    private var apiClient: CIRISApiClient? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Enable edge-to-edge display (fixes Samsung nav bar cutoff)
        enableEdgeToEdge()

        // Initialize AppRestarter for app restart functionality (used by Settings reset)
        AppRestarter.init(this, MainActivity::class.java)

        // Initialize URL opener for browser links
        initUrlOpener(this)

        // Initialize local-inference capability probe (needs app context to
        // query ActivityManager for RAM size).
        initLocalInferenceProbe(this)

        // Initialize cell-viz capability probe (same pattern — needs app
        // context to read RAM / ABI before the Interact screen decides
        // which visualization to render).
        initCellVizProbe(this)

        // Initialize Python runtime (Chaquopy)
        if (!Python.isStarted()) {
            Log.i(TAG, "Initializing Python runtime...")
            Python.start(AndroidPlatform(this))
            Log.i(TAG, "Python runtime started")
        }

        // Initialize localization resource loader with app context
        LocalizationResourceLoader.init(applicationContext)
        Log.i(TAG, "Localization resource loader initialized")

        // Enable test mode for debug builds (TEST_MODE_ENABLED is set in build.gradle)
        AndroidTestAutomationServer.forceTestMode = BuildConfig.TEST_MODE_ENABLED
        // Start test automation server if test mode is enabled
        AndroidTestAutomationServer.startIfEnabled()

        // Initialize Google Sign-In
        initGoogleSignIn()

        // Initialize Google Play Billing
        initBilling()

        setContent {
            var pythonReady by remember { mutableStateOf(false) }
            var statusMessage by remember { mutableStateOf("Starting Python...") }
            var pythonError by remember { mutableStateOf<String?>(null) }

            LaunchedEffect(Unit) {
                // Start logcat reader for service status updates
                launch {
                    startLogcatReader()
                }

                // FILE-based capture of the node's one-time ownership CLAIM PIN.
                // The node writes its boot banner to log FILES (not the filtered
                // logcat stream the reader above consumes), so tail those files so
                // the PIN is latched even when logcat never carries the banner.
                launch {
                    tailNodeLogsForOwnership()
                }

                // Run network diagnostics to debug CIRISVerify connectivity
                launch(Dispatchers.IO) {
                    try {
                        Log.i(TAG, "Running CIRIS network diagnostics...")
                        NetworkDiagnosticsAndroid.runAllDiagnostics()
                        Log.i(TAG, "Network diagnostics completed")
                    } catch (e: Exception) {
                        Log.e(TAG, "Network diagnostics failed", e)
                    }
                }

                // Start Python server
                launch {
                    statusMessage = "Loading CIRIS..."

                    // Show CIRISApp immediately - StartupScreen will handle animation
                    // The logcat reader is already running and tracking service count
                    Log.i(TAG, "Showing CIRISApp immediately for startup animation")
                    pythonReady = true

                    // Start Python via foreground service (survives activity backgrounding for OAuth)
                    if (!PythonRuntimeService.isRunning) {
                        Log.i(TAG, "Starting PythonRuntimeService...")
                        val serviceIntent = Intent(this@MainActivity, PythonRuntimeService::class.java)
                        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                            startForegroundService(serviceIntent)
                        } else {
                            startService(serviceIntent)
                        }
                    } else {
                        Log.i(TAG, "PythonRuntimeService already running")
                    }
                }
            }

            if (pythonReady) {
                // Show the full KMP app with native StartupScreen (22 lights)
                CIRISApp(
                    accessToken = "pending", // Will be set after auth
                    // The Python brain. The ciris-server node read API is
                    // separate (:4243) and takes the CIRISApp default —
                    // 8080 never fronts 4243 (FSD FIRST_RUN_WIZARD_2.9.14 §2).
                    apiBaseUrl = "http://localhost:8080",
                    googleSignInCallback = googleSignInCallback,
                    purchaseLauncher = purchaseLauncher,
                    deviceAttestationCallback = deviceAttestationCallback,
                    onTokenUpdated = { token ->
                        // Update the billing API client with the new token
                        Log.i(TAG, "Token updated, setting on billing apiClient")
                        apiClient?.setAccessToken(token)
                    }
                )
            } else {
                // Minimal splash while Python starts
                PythonInitSplash(statusMessage)
            }
        }
    }

    /**
     * Initialize Google Sign-In client
     */
    private fun initGoogleSignIn() {
        val gso = GoogleSignInOptions.Builder(GoogleSignInOptions.DEFAULT_SIGN_IN)
            .requestIdToken(CIRISConfig.GOOGLE_WEB_CLIENT_ID)
            .requestEmail()
            .requestProfile()
            .build()

        googleSignInClient = GoogleSignIn.getClient(this, gso)
        Log.i(TAG, "Google Sign-In initialized with client ID: ${CIRISConfig.GOOGLE_WEB_CLIENT_ID.take(20)}...")
    }

    /**
     * Initialize Google Play Billing
     */
    private fun initBilling() {
        Log.i(TAG, "Initializing Google Play Billing...")

        // Create API client for purchase verification
        apiClient = CIRISApiClient("http://localhost:8080")

        billingManager = BillingManager(
            context = this,
            onVerifyPurchase = { purchaseToken, productId, packageName ->
                // Verify purchase via API
                val client = apiClient
                if (client != null) {
                    try {
                        val result = client.verifyGooglePlayPurchase(purchaseToken, productId, packageName)
                        VerifyResult(
                            success = result.success,
                            creditsAdded = result.creditsAdded,
                            newBalance = result.newBalance,
                            alreadyProcessed = result.alreadyProcessed,
                            error = result.error
                        )
                    } catch (e: Exception) {
                        Log.e(TAG, "Purchase verification failed", e)
                        VerifyResult(success = false, error = "Verification failed: ${e.message}")
                    }
                } else {
                    Log.e(TAG, "API client not initialized")
                    VerifyResult(success = false, error = "API client not ready")
                }
            }
        )

        // Set up purchase result callback
        billingManager.onPurchaseResult = { result ->
            Log.i(TAG, "Purchase result received: $result")
            val purchaseResultType = when (result) {
                is PurchaseResult.Success -> {
                    PurchaseResultType.Success(result.creditsAdded, result.newBalance)
                }
                is PurchaseResult.Error -> {
                    PurchaseResultType.Error(result.message)
                }
                PurchaseResult.Cancelled -> {
                    PurchaseResultType.Cancelled
                }
            }
            purchaseResultCallback?.onResult(purchaseResultType)
        }

        billingManager.initialize()
        Log.i(TAG, "Google Play Billing initialized")

        // Initialize Play Integrity (uses Python API, not Kotlin JNI)
        playIntegrityManager = PlayIntegrityManager(this, apiClient!!)
        Log.i(TAG, "Google Play Integrity initialized (via Python API)")
    }

    /**
     * DeviceAttestationCallback implementation for CIRISApp
     */
    private val deviceAttestationCallback = object : DeviceAttestationCallback {
        override fun onDeviceAttestationRequested(onResult: (DeviceAttestationResult) -> Unit) {
            Log.i(TAG, "Device attestation requested")
            integrityScope.launch {
                val result = playIntegrityManager.attestDevice()
                withContext(Dispatchers.Main) {
                    val attestationResult = when {
                        result.verified -> DeviceAttestationResult.Success(
                            verified = true,
                            verdict = result.verdict ?: "VERIFIED",
                            meetsStrongIntegrity = result.meetsStrongIntegrity,
                            meetsDeviceIntegrity = result.meetsDeviceIntegrity,
                            meetsBasicIntegrity = result.meetsBasicIntegrity
                        )
                        result.error != null -> DeviceAttestationResult.Error(result.error)
                        else -> DeviceAttestationResult.Error("Unknown error")
                    }
                    Log.i(TAG, "Device attestation result: $attestationResult")
                    onResult(attestationResult)
                }
            }
        }
    }

    /**
     * PurchaseLauncher implementation for CIRISApp
     */
    private val purchaseLauncher = object : PurchaseLauncher {
        override fun launchPurchase(productId: String) {
            Log.i(TAG, "Launching purchase for product: $productId")
            billingManager.launchPurchaseFlowById(this@MainActivity, productId)
        }

        override fun setOnPurchaseResult(callback: PurchaseResultCallback) {
            Log.i(TAG, "Setting purchase result callback")
            purchaseResultCallback = callback
        }
    }

    /**
     * GoogleSignInCallback implementation for CIRISApp
     */
    private val googleSignInCallback = object : GoogleSignInCallback {
        override fun onGoogleSignInRequested(
            forceAccountChooser: Boolean,
            onResult: (NativeSignInResult) -> Unit,
        ) {
            Log.i(TAG, "Google Sign-In requested from CIRISApp (interactive, forceAccountChooser=$forceAccountChooser)")
            pendingGoogleSignInCallback = onResult
            if (forceAccountChooser) {
                // 2.9.2 personal-install observer-blocked recovery:
                // sign out of the cached account so Google's chooser
                // re-prompts for which account to use, instead of
                // auto-resuming the same wrong account the user just
                // tried. silentSignIn / signInIntent both honour the
                // post-signOut state.
                googleSignInClient.signOut().addOnCompleteListener {
                    Log.i(TAG, "Google Sign-In cache cleared — launching picker")
                    val signInIntent = googleSignInClient.signInIntent
                    startActivityForResult(signInIntent, RC_SIGN_IN)
                }
            } else {
                val signInIntent = googleSignInClient.signInIntent
                startActivityForResult(signInIntent, RC_SIGN_IN)
            }
        }

        override fun onSilentSignInRequested(onResult: (NativeSignInResult) -> Unit) {
            Log.i(TAG, "Silent Sign-In requested from CIRISApp")

            // Check if we have a cached account first
            val cachedAccount = GoogleSignIn.getLastSignedInAccount(this@MainActivity)
            if (cachedAccount != null) {
                Log.i(TAG, "Found cached account: ${cachedAccount.email}")
            }

            // Attempt silent sign-in to get fresh token
            googleSignInClient.silentSignIn()
                .addOnSuccessListener { account ->
                    Log.i(TAG, "Silent Sign-In successful: ${account.email}")
                    val token = account.idToken
                    if (token != null) {
                        onResult(NativeSignInResult.Success(
                            idToken = token,
                            userId = account.id ?: "",
                            email = account.email,
                            displayName = account.displayName,
                            provider = "google"
                        ))
                    } else {
                        Log.w(TAG, "Silent Sign-In returned null token")
                        onResult(NativeSignInResult.Error("4: SIGN_IN_REQUIRED - No token returned"))
                    }
                }
                .addOnFailureListener { e ->
                    val errorCode = if (e is ApiException) e.statusCode else -1
                    Log.w(TAG, "Silent Sign-In failed: code=$errorCode, message=${e.message}")

                    // Error code 4 = SIGN_IN_REQUIRED - user needs to interactively sign in
                    if (errorCode == 4) {
                        onResult(NativeSignInResult.Error("4: SIGN_IN_REQUIRED"))
                    } else {
                        onResult(NativeSignInResult.Error("$errorCode: ${e.message}"))
                    }
                }
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)

        if (requestCode == RC_SIGN_IN) {
            val callback = pendingGoogleSignInCallback
            pendingGoogleSignInCallback = null

            try {
                val task = GoogleSignIn.getSignedInAccountFromIntent(data)
                val account = task.getResult(ApiException::class.java)

                Log.i(TAG, "Google Sign-In successful: ${account.email}")

                val result = NativeSignInResult.Success(
                    idToken = account.idToken ?: "",
                    userId = account.id ?: "",
                    email = account.email,
                    displayName = account.displayName,
                    provider = "google"
                )

                callback?.invoke(result)

            } catch (e: ApiException) {
                Log.e(TAG, "Google Sign-In failed: ${e.statusCode} - ${e.message}")

                val result = when (e.statusCode) {
                    12501 -> NativeSignInResult.Cancelled // SIGN_IN_CANCELLED
                    else -> NativeSignInResult.Error("Sign-in failed: ${e.statusCode}")
                }

                callback?.invoke(result)
            }
        }
    }

    private suspend fun checkServerOnce(): Boolean = withContext(Dispatchers.IO) {
        try {
            val url = URL("http://localhost:8080/v1/system/health")
            val connection = url.openConnection() as HttpURLConnection
            connection.connectTimeout = 2000
            connection.readTimeout = 2000

            val ready = connection.responseCode == 200
            connection.disconnect()
            return@withContext ready
        } catch (e: Exception) {
            return@withContext false
        }
    }

    private suspend fun startLogcatReader() = withContext(Dispatchers.IO) {
        try {
            // Kill any existing logcat reader and get a new generation ID
            // This ensures stale readers from activity recreation don't corrupt state
            val generation = PythonRuntime.prepareNewLogcatReader()
            PythonRuntime.resetPrepCount()
            Log.i(TAG, "Starting logcat reader (generation $generation)")

            // Use -T 100 to catch recent messages (last 100 lines) plus new ones
            // This handles the race condition where Python starts outputting prep steps
            // before the logcat reader is fully initialized
            val process = Runtime.getRuntime().exec(arrayOf("logcat", "-v", "raw", "-T", "100", "python.stdout:I", "python.stderr:W", "CIRISVerify:I", "*:S"))

            // Register process and check if still valid
            if (!PythonRuntime.registerLogcatProcess(process, generation)) {
                Log.w(TAG, "Logcat reader cancelled before starting (generation changed)")
                return@withContext
            }

            val reader = process.inputStream.bufferedReader()

            // Pattern for service startup: [SERVICE 1/22] ... STARTED
            val servicePattern = Regex("""\[SERVICE (\d+)/(\d+)\].*STARTED""")
            // Pattern for PREP steps: [1/8], [2/8], etc. (pydantic setup + code integrity)
            val prepPattern = Regex("""\[(\d+)/(\d+)\]""")
            // Pattern for VERIFY messages from CIRISVerify
            val verifyPattern = Regex("""VERIFY""")

            while (true) {
                // Check if this reader is still valid (newer one may have started)
                if (!PythonRuntime.isLogcatGenerationValid(generation)) {
                    Log.i(TAG, "Logcat reader stopping (generation $generation is stale)")
                    process.destroy()
                    break
                }

                val line = reader.readLine() ?: break
                if (line.isNotBlank()) {
                    // Forward raw line through callback for ViewModel processing
                    // This enables slot-based UI tracking in StartupViewModel
                    PythonRuntime.forwardLogLine(line)

                    // Check for service startup
                    servicePattern.find(line)?.let { match ->
                        val serviceNum = match.groupValues[1].toIntOrNull() ?: 0
                        val total = match.groupValues[2].toIntOrNull() ?: 22
                        PythonRuntime.updateServiceCount(serviceNum, total)
                        Log.d(TAG, "Service $serviceNum started (${PythonRuntime.servicesOnline}/$total)")
                        return@let
                    }

                    // Check for PREP steps (pydantic setup + code integrity)
                    // Only match if it's NOT a SERVICE line (to avoid double-counting)
                    if (!line.contains("SERVICE")) {
                        prepPattern.find(line)?.let { match ->
                            val stepNum = match.groupValues[1].toIntOrNull() ?: 0
                            val total = match.groupValues[2].toIntOrNull() ?: 8
                            PythonRuntime.updatePrepCount(stepNum, total)
                            Log.d(TAG, "Prep step $stepNum/$total: $line")
                            return@let
                        }
                    }

                    // Forward VERIFY messages for attestation tracking
                    if (verifyPattern.containsMatchIn(line)) {
                        PythonRuntime.onVerifyMessage(line)
                        Log.d(TAG, "Verify: $line")
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Logcat reader error: ${e.message}")
        }
    }

    /**
     * Resolve the directory the in-process ciris-server node writes its logs to.
     * CIRIS_HOME is set by CirisVerify.setup() to `filesDir/ciris`; the node's
     * logs (including the boot banner) live under `$CIRIS_HOME/logs`.
     */
    private fun resolveNodeLogsDir(): File {
        val home = System.getenv("CIRIS_HOME")
            ?.takeIf { it.isNotEmpty() }
            ?.let { File(it) }
            ?: File(filesDir, "ciris")
        return File(home, "logs")
    }

    /**
     * FILE-based fallback for capturing the node's one-time ownership CLAIM PIN.
     *
     * The node emits its "OWNERSHIP UNCLAIMED" banner (carrying the one-time
     * CLAIM PIN + NodeCode) at boot, but writes it to log FILES under
     * `$CIRIS_HOME/logs` — NOT to the filtered logcat stream [startLogcatReader]
     * consumes (that filter is `python.stdout/stderr` + `CIRISVerify` only). So a
     * logcat-only capture misses the banner entirely. Here we tail the node's
     * boot logs and feed each line through the SAME ownership parser
     * ([PythonRuntime.scanFileLineForOwnership] → parseOwnershipBanner), so the
     * PIN is latched from the file regardless of what logcat carried.
     *
     * Bounded + self-terminating: polls until the PIN is captured or a deadline
     * elapses. The parser is idempotent (first match wins), so re-reading a file
     * across polls is harmless.
     */
    private suspend fun tailNodeLogsForOwnership() = withContext(Dispatchers.IO) {
        try {
            val deadline = System.currentTimeMillis() + 120_000L
            while (System.currentTimeMillis() < deadline) {
                if (PythonRuntime.isClaimPinCaptured()) {
                    Log.i(TAG, "Ownership CLAIM PIN captured — stopping node-log tail")
                    return@withContext
                }
                val logsDir = resolveNodeLogsDir()
                if (logsDir.isDirectory) {
                    // Boot banner lands in the current/boot server logs; scan the
                    // node's boot + rolling logs, newest first.
                    val candidates = logsDir.listFiles { f ->
                        f.isFile && (
                            f.name == "latest.log" ||
                            f.name.startsWith("ciris-server.log") ||
                            f.name.startsWith("ciris_agent_")
                        )
                    }?.sortedByDescending { it.lastModified() } ?: emptyArray<File>().toList()

                    for (f in candidates) {
                        if (PythonRuntime.isClaimPinCaptured()) break
                        try {
                            f.bufferedReader().useLines { seq ->
                                // Banner is early in the file; cap the scan so a
                                // large rolling log never turns this into a hog.
                                seq.take(20_000).forEach { line ->
                                    if (line.isNotBlank()) {
                                        PythonRuntime.scanFileLineForOwnership(line)
                                    }
                                }
                            }
                        } catch (e: Exception) {
                            Log.d(TAG, "Node-log tail: read failed for ${f.name}: ${e.message}")
                        }
                    }
                }
                delay(1000)
            }
            if (!PythonRuntime.isClaimPinCaptured()) {
                Log.w(TAG, "Node-log ownership tail: CLAIM PIN not seen before deadline")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Node-log ownership tail error: ${e.message}")
        }
    }

    override fun onResume() {
        super.onResume()
        // Process any pending purchases when activity resumes
        if (::billingManager.isInitialized) {
            billingManager.processPendingPurchases()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        // Clean up billing connection
        if (::billingManager.isInitialized) {
            billingManager.endConnection()
        }
        // Stop test automation server
        AndroidTestAutomationServer.stop()
    }
}

@Composable
private fun PythonInitSplash(status: String) {
    Surface(
        modifier = Modifier.fillMaxSize(),
        color = Color(0xFF1a1a2e)
    ) {
        Column(
            modifier = Modifier.fillMaxSize(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            Text(
                text = "CIRIS",
                fontSize = 48.sp,
                color = Color(0xFF00d4ff)
            )

            Spacer(Modifier.height(24.dp))

            CircularProgressIndicator(color = Color(0xFF00d4ff))

            Spacer(Modifier.height(16.dp))

            Text(
                text = status,
                fontSize = 14.sp,
                color = Color(0xFFaaaaaa)
            )
        }
    }
}
