package ai.ciris.mobile

import ai.ciris.mobile.billing.BillingManager
import ai.ciris.mobile.billing.PurchaseResult
import ai.ciris.mobile.billing.VerifyResult
import ai.ciris.mobile.shared.CIRISApp
import ai.ciris.mobile.shared.GoogleSignInCallback
import ai.ciris.mobile.shared.GoogleSignInResult
import ai.ciris.mobile.shared.PurchaseLauncher
import ai.ciris.mobile.shared.PurchaseResultCallback
import ai.ciris.mobile.shared.PurchaseResultType
import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.config.CIRISConfig
import ai.ciris.mobile.shared.platform.PythonRuntime
import android.content.Intent
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
    private var pendingGoogleSignInCallback: ((GoogleSignInResult) -> Unit)? = null

    // Google Play Billing
    private lateinit var billingManager: BillingManager
    private var purchaseResultCallback: PurchaseResultCallback? = null

    // API client for purchase verification (will be set when server is ready)
    private var apiClient: CIRISApiClient? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Enable edge-to-edge display (fixes Samsung nav bar cutoff)
        enableEdgeToEdge()

        // Initialize Python runtime (Chaquopy)
        if (!Python.isStarted()) {
            Log.i(TAG, "Initializing Python runtime...")
            Python.start(AndroidPlatform(this))
            Log.i(TAG, "Python runtime started")
        }

        // Initialize Google Sign-In
        initGoogleSignIn()

        // Initialize Google Play Billing
        initBilling()

        setContent {
            var pythonReady by remember { mutableStateOf(false) }
            var statusMessage by remember { mutableStateOf("Starting Python...") }

            LaunchedEffect(Unit) {
                // Start logcat reader for service status updates
                launch {
                    startLogcatReader()
                }

                // Start Python server
                launch {
                    statusMessage = "Loading CIRIS..."

                    // Start Python mobile_main in background thread
                    Thread {
                        try {
                            Log.i(TAG, "Starting mobile_main.main()...")
                            val py = Python.getInstance()
                            val module = py.getModule("mobile_main")
                            module.callAttr("main")
                        } catch (e: Exception) {
                            Log.e(TAG, "Python runtime error", e)
                        }
                    }.start()

                    // Wait for server to respond
                    statusMessage = "Waiting for server..."
                    val ready = waitForServer()

                    if (ready) {
                        Log.i(TAG, "Server ready - showing CIRISApp")
                        pythonReady = true
                    } else {
                        statusMessage = "Server failed to start"
                    }
                }
            }

            if (pythonReady) {
                // Show the full KMP app with native StartupScreen (22 lights)
                CIRISApp(
                    accessToken = "pending", // Will be set after auth
                    baseUrl = "http://localhost:8080",
                    googleSignInCallback = googleSignInCallback,
                    purchaseLauncher = purchaseLauncher
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
        override fun onGoogleSignInRequested(onResult: (GoogleSignInResult) -> Unit) {
            Log.i(TAG, "Google Sign-In requested from CIRISApp (interactive)")
            pendingGoogleSignInCallback = onResult
            val signInIntent = googleSignInClient.signInIntent
            startActivityForResult(signInIntent, RC_SIGN_IN)
        }

        override fun onSilentSignInRequested(onResult: (GoogleSignInResult) -> Unit) {
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
                        onResult(GoogleSignInResult.Success(
                            idToken = token,
                            userId = account.id ?: "",
                            email = account.email,
                            displayName = account.displayName
                        ))
                    } else {
                        Log.w(TAG, "Silent Sign-In returned null token")
                        onResult(GoogleSignInResult.Error("4: SIGN_IN_REQUIRED - No token returned"))
                    }
                }
                .addOnFailureListener { e ->
                    val errorCode = if (e is ApiException) e.statusCode else -1
                    Log.w(TAG, "Silent Sign-In failed: code=$errorCode, message=${e.message}")

                    // Error code 4 = SIGN_IN_REQUIRED - user needs to interactively sign in
                    if (errorCode == 4) {
                        onResult(GoogleSignInResult.Error("4: SIGN_IN_REQUIRED"))
                    } else {
                        onResult(GoogleSignInResult.Error("$errorCode: ${e.message}"))
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

                val result = GoogleSignInResult.Success(
                    idToken = account.idToken ?: "",
                    userId = account.id ?: "",
                    email = account.email,
                    displayName = account.displayName
                )

                callback?.invoke(result)

            } catch (e: ApiException) {
                Log.e(TAG, "Google Sign-In failed: ${e.statusCode} - ${e.message}")

                val result = when (e.statusCode) {
                    12501 -> GoogleSignInResult.Cancelled // SIGN_IN_CANCELLED
                    else -> GoogleSignInResult.Error("Sign-in failed: ${e.statusCode}")
                }

                callback?.invoke(result)
            }
        }
    }

    private suspend fun waitForServer(): Boolean = withContext(Dispatchers.IO) {
        var attempts = 0
        val maxAttempts = 60

        while (attempts < maxAttempts) {
            delay(1000)
            attempts++

            try {
                val url = URL("http://localhost:8080/v1/system/health")
                val connection = url.openConnection() as HttpURLConnection
                connection.connectTimeout = 2000
                connection.readTimeout = 2000

                if (connection.responseCode == 200) {
                    connection.disconnect()
                    Log.i(TAG, "Server ready after $attempts seconds")
                    return@withContext true
                }
                connection.disconnect()
            } catch (e: Exception) {
                // Server not ready
            }
        }
        return@withContext false
    }

    private suspend fun startLogcatReader() = withContext(Dispatchers.IO) {
        try {
            PythonRuntime.resetServiceCount()

            val process = Runtime.getRuntime().exec("logcat -v raw python.stdout:I python.stderr:W *:S")
            val reader = process.inputStream.bufferedReader()
            val servicePattern = Regex("""\[SERVICE (\d+)/(\d+)\].*STARTED""")

            while (true) {
                val line = reader.readLine() ?: break
                if (line.isNotBlank()) {
                    val match = servicePattern.find(line)
                    if (match != null) {
                        val serviceNum = match.groupValues[1].toIntOrNull() ?: 0
                        val total = match.groupValues[2].toIntOrNull() ?: 22
                        PythonRuntime.updateServiceCount(serviceNum, total)
                        Log.d(TAG, "Service $serviceNum started (${PythonRuntime.servicesOnline}/$total)")
                    }
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Logcat reader error: ${e.message}")
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
