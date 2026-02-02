package ai.ciris.mobile.shared

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.auth.SilentSignInResult
import ai.ciris.mobile.shared.auth.TokenManager
import ai.ciris.mobile.shared.auth.TokenState
import ai.ciris.mobile.shared.platform.EnvFileUpdater
import ai.ciris.mobile.shared.platform.PythonRuntime
import ai.ciris.mobile.shared.platform.PythonRuntimeProtocol
import ai.ciris.mobile.shared.platform.SecureStorage
import ai.ciris.mobile.shared.platform.createEnvFileUpdater
import ai.ciris.mobile.shared.platform.createPythonRuntime
import ai.ciris.mobile.shared.platform.createSecureStorage
import ai.ciris.mobile.shared.platform.getOAuthProviderName
import ai.ciris.mobile.shared.platform.getOAuthProviderId
import ai.ciris.mobile.shared.platform.platformLog
import ai.ciris.mobile.shared.ui.components.AdapterWizardDialog
import ai.ciris.mobile.shared.ui.screens.*
import ai.ciris.mobile.shared.viewmodels.AdaptersViewModel
import ai.ciris.mobile.shared.viewmodels.AuditViewModel
import ai.ciris.mobile.shared.viewmodels.BillingViewModel
import ai.ciris.mobile.shared.viewmodels.ConfigViewModel
import ai.ciris.mobile.shared.viewmodels.ConsentViewModel
import ai.ciris.mobile.shared.viewmodels.GraphMemoryViewModel
import ai.ciris.mobile.shared.viewmodels.InteractViewModel
import ai.ciris.mobile.shared.viewmodels.LogsViewModel
import ai.ciris.mobile.shared.viewmodels.MemoryViewModel
import ai.ciris.mobile.shared.viewmodels.RuntimeViewModel
import ai.ciris.mobile.shared.viewmodels.ServicesViewModel
import ai.ciris.mobile.shared.viewmodels.SessionsViewModel
import ai.ciris.mobile.shared.viewmodels.SettingsViewModel
import ai.ciris.mobile.shared.viewmodels.SetupViewModel
import ai.ciris.mobile.shared.viewmodels.StartupPhase
import ai.ciris.mobile.shared.viewmodels.StartupViewModel
import ai.ciris.mobile.shared.viewmodels.SystemViewModel
import ai.ciris.mobile.shared.viewmodels.TelemetryViewModel
import ai.ciris.mobile.shared.viewmodels.UsersViewModel
import ai.ciris.mobile.shared.viewmodels.WiseAuthorityViewModel
import ai.ciris.mobile.shared.ui.screens.graph.GraphMemoryScreen
import androidx.compose.foundation.layout.*
import kotlinx.coroutines.launch
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.lifecycle.viewmodel.compose.viewModel
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Main CIRIS app entry point
 * Shared across Android and iOS
 *
 * Navigation flow:
 * 1. StartupScreen (22 service lights, Python init)
 * 2. Check first-run status via /v1/setup/status
 * 3. If first-run: LoginScreen -> SetupScreen (wizard)
 * 4. InteractScreen (main chat interface)
 * 5. SettingsScreen (accessible from top bar)
 */
/**
 * Callback interface for native OAuth Sign-In (Google on Android, Apple on iOS)
 * Platform implementations provide actual SDK integration
 */
interface NativeSignInCallback {
    /**
     * Request interactive sign-in (shows UI).
     * Named onGoogleSignInRequested for backward compatibility with existing Android code.
     */
    fun onGoogleSignInRequested(onResult: (NativeSignInResult) -> Unit)

    /**
     * Attempt silent sign-in (no UI).
     * Returns a fresh token if user is already signed in, or signals that interactive login is needed.
     */
    fun onSilentSignInRequested(onResult: (NativeSignInResult) -> Unit)
}

/**
 * Result of native OAuth Sign-In attempt (Google on Android, Apple on iOS)
 */
sealed class NativeSignInResult {
    data class Success(
        val idToken: String,
        val userId: String,
        val email: String?,
        val displayName: String?,
        val provider: String  // "google" or "apple"
    ) : NativeSignInResult()

    data class Error(val message: String) : NativeSignInResult()
    object Cancelled : NativeSignInResult()
}

// Backward compatibility aliases for Android
typealias GoogleSignInCallback = NativeSignInCallback
typealias GoogleSignInResult = NativeSignInResult

// Apple Sign-In alias for iOS
typealias AppleSignInCallback = NativeSignInCallback
typealias AppleSignInResult = NativeSignInResult

/**
 * Legacy callback interface for Google Sign-In (deprecated, use NativeSignInCallback)
 * Kept for backward compatibility with existing Android code
 */
@Deprecated("Use NativeSignInCallback instead", ReplaceWith("NativeSignInCallback"))
interface LegacyGoogleSignInCallback {
    /**
     * Request interactive Google Sign-In (shows UI).
     */
    fun onGoogleSignInRequested(onResult: (NativeSignInResult) -> Unit)

    /**
     * Attempt silent sign-in (no UI).
     * Returns a fresh token if user is already signed in, or signals that interactive login is needed.
     */
    fun onSilentSignInRequested(onResult: (NativeSignInResult) -> Unit)
}

/**
 * Product information for in-app purchases
 */
data class ProductInfo(
    val id: String,
    val displayName: String,
    val description: String,
    val displayPrice: String,
    val price: Double
)

/**
 * Callback interface for launching in-app purchases
 * Platform implementations provide actual store integration (Google Play, App Store)
 */
interface PurchaseLauncher {
    /**
     * Launch the native purchase flow for a product.
     * @param productId The product ID to purchase (e.g., "credits_100")
     */
    fun launchPurchase(productId: String)

    /**
     * Launch the native purchase flow with auth token (for iOS StoreKit).
     * @param productId The product ID to purchase
     * @param authToken The OAuth token for billing verification
     */
    fun launchPurchaseWithAuth(productId: String, authToken: String) {
        // Default implementation falls back to launchPurchase
        launchPurchase(productId)
    }

    /**
     * Load available products from the store.
     * @param onResult Callback with list of available products
     */
    fun loadProducts(onResult: (List<ProductInfo>) -> Unit) {
        // Default: no products
        onResult(emptyList())
    }

    /**
     * Check if products are currently loading.
     */
    fun isLoading(): Boolean = false

    /**
     * Get current error message if any.
     */
    fun getErrorMessage(): String? = null

    /**
     * Set callback for purchase results.
     * Called by CIRISApp to receive purchase outcomes.
     */
    fun setOnPurchaseResult(callback: PurchaseResultCallback)
}

/**
 * Result of a purchase attempt
 */
sealed class PurchaseResultType {
    data class Success(val creditsAdded: Int, val newBalance: Int) : PurchaseResultType()
    data class Error(val message: String) : PurchaseResultType()
    object Cancelled : PurchaseResultType()
}

/**
 * Callback for purchase results
 */
fun interface PurchaseResultCallback {
    fun onResult(result: PurchaseResultType)
}

// GoogleSignInResult is now a typealias for NativeSignInResult (defined above)

@Composable
fun CIRISApp(
    accessToken: String,
    baseUrl: String = "http://localhost:8080",
    pythonRuntime: PythonRuntime = createPythonRuntime(),
    secureStorage: SecureStorage = createSecureStorage(),
    envFileUpdater: EnvFileUpdater = createEnvFileUpdater(),
    googleSignInCallback: GoogleSignInCallback? = null,
    purchaseLauncher: PurchaseLauncher? = null,
    onTokenUpdated: ((String) -> Unit)? = null
) {
    val TAG = "CIRISApp"

    // Log callback state on every recomposition
    platformLog(TAG, "[INIT] CIRISApp composable invoked - googleSignInCallback=${if (googleSignInCallback != null) "PRESENT (${googleSignInCallback.hashCode()})" else "NULL"}")

    val coroutineScope = rememberCoroutineScope()
    val apiClient = remember { CIRISApiClient(baseUrl, accessToken) }

    // Track the current auth token - will be updated after login/setup
    var currentAccessToken by remember { mutableStateOf<String?>(null) }

    // Navigation state
    var currentScreen by remember { mutableStateOf<Screen>(Screen.Startup) }

    // First-run detection state
    var isFirstRun by remember { mutableStateOf<Boolean?>(null) }
    var checkingFirstRun by remember { mutableStateOf(false) }

    // Flag to skip token re-validation after setup (we just authenticated)
    var justCompletedSetup by remember { mutableStateOf(false) }

    // Login state
    var isLoginLoading by remember { mutableStateOf(false) }
    var loginStatusMessage by remember { mutableStateOf<String?>(null) }

    // OAuth auth state for token exchange after setup (works for both Google and Apple)
    var pendingIdToken by remember { mutableStateOf<String?>(null) }
    var pendingUserId by remember { mutableStateOf<String?>(null) }
    var pendingProvider by remember { mutableStateOf("apple") } // Default to apple on iOS

    // Token Manager for handling token refresh
    val tokenManager = remember { TokenManager(coroutineScope) }

    // Track when CIRIS token exchange completes after silent refresh
    var tokenExchangeComplete by remember { mutableStateOf(false) }

    // Set up silent sign-in callback
    LaunchedEffect(googleSignInCallback) {
        if (googleSignInCallback != null) {
            tokenManager.setSilentSignInCallback {
                // This is called from a coroutine, but onSilentSignInRequested uses callbacks
                // We need to bridge the two
                kotlinx.coroutines.suspendCancellableCoroutine { continuation ->
                    googleSignInCallback.onSilentSignInRequested { result ->
                        val silentResult = when (result) {
                            is NativeSignInResult.Success -> {
                                SilentSignInResult.Success(result.idToken, result.email, result.provider)
                            }
                            is NativeSignInResult.Error -> {
                                // Error code 4 = SIGN_IN_REQUIRED
                                if (result.message.contains("SIGN_IN_REQUIRED") || result.message.startsWith("4:")) {
                                    SilentSignInResult.NeedsInteractiveLogin(4)
                                } else {
                                    SilentSignInResult.Error(result.message)
                                }
                            }
                            NativeSignInResult.Cancelled -> {
                                SilentSignInResult.NeedsInteractiveLogin(12500)
                            }
                        }
                        continuation.resumeWith(Result.success(silentResult))
                    }
                }
            }

            // Set callback for when OAuth ID token is refreshed
            // IMPORTANT: The refreshed token is an OAuth ID token (Google or Apple), NOT a CIRIS access token
            // We need to exchange it with the CIRIS API to get an access token
            tokenManager.setOnTokenRefreshed { idToken, provider ->
                println("[$TAG][INFO] OAuth ID token refreshed by TokenManager (provider=$provider), exchanging for CIRIS token")
                tokenExchangeComplete = false
                coroutineScope.launch {
                    try {
                        // Exchange OAuth ID token for CIRIS access token using correct provider
                        val authResponse = apiClient.nativeAuth(idToken, null, provider)
                        val cirisToken = authResponse.access_token
                        println("[$TAG][INFO] Got CIRIS access token: ${cirisToken.take(8)}...${cirisToken.takeLast(4)}")

                        // Set the CIRIS token on the API client
                        apiClient.setAccessToken(cirisToken)
                        onTokenUpdated?.invoke(cirisToken) // Notify MainActivity for BillingManager
                        currentAccessToken = cirisToken
                        apiClient.logTokenState() // Debug: confirm token was set

                        // Save CIRIS token to secure storage (not the Google ID token!)
                        secureStorage.saveAccessToken(cirisToken)
                            .onSuccess { println("[$TAG][INFO] Refreshed CIRIS token saved to secure storage") }
                            .onFailure { e -> println("[$TAG][WARN] Failed to save refreshed CIRIS token: ${e.message}") }

                        // Update .env file with fresh OAuth ID token for billing
                        println("[$TAG][INFO] Writing OAuth ID token to .env for Python billing...")
                        envFileUpdater.updateEnvWithToken(idToken)
                            .onSuccess { updated ->
                                if (updated) println("[$TAG][INFO] .env updated, .config_reload signal written")
                            }
                            .onFailure { e -> println("[$TAG][ERROR] Failed to update .env: ${e.message}") }

                        // Wait for Python to detect .config_reload and reload .env
                        // ResourceMonitor checks every 1 second, so 1.5s should be sufficient
                        println("[$TAG][INFO] Waiting 1.5s for Python to reload billing token...")
                        kotlinx.coroutines.delay(1500)
                        println("[$TAG][INFO] Python reload wait complete")

                        tokenExchangeComplete = true
                    } catch (e: Exception) {
                        println("[$TAG][ERROR] Failed to exchange refreshed OAuth token: ${e::class.simpleName}: ${e.message}")
                        tokenExchangeComplete = true // Mark complete even on failure to unblock waiting code
                        // On failure, the user may need to re-authenticate
                    }
                }
            }
        }
    }

    // ViewModels
    // Cast to PythonRuntimeProtocol since actual implementations implement it
    val pythonRuntimeProtocol: PythonRuntimeProtocol = pythonRuntime as PythonRuntimeProtocol
    val startupViewModel: StartupViewModel = viewModel {
        StartupViewModel(pythonRuntimeProtocol, apiClient)
    }
    // SetupViewModel is a plain class, not an androidx ViewModel
    val setupViewModel = remember { SetupViewModel() }
    val interactViewModel: InteractViewModel = viewModel {
        InteractViewModel(apiClient)
    }
    val settingsViewModel: SettingsViewModel = viewModel {
        SettingsViewModel(secureStorage, apiClient, envFileUpdater)
    }
    val telemetryViewModel: TelemetryViewModel = viewModel {
        TelemetryViewModel(apiClient)
    }
    val billingViewModel: BillingViewModel = viewModel {
        BillingViewModel(apiClient, baseUrl)
    }
    val sessionsViewModel: SessionsViewModel = viewModel {
        SessionsViewModel(apiClient)
    }
    val adaptersViewModel: AdaptersViewModel = viewModel {
        AdaptersViewModel(apiClient, baseUrl)
    }
    val wiseAuthorityViewModel: WiseAuthorityViewModel = viewModel {
        WiseAuthorityViewModel(apiClient)
    }
    val servicesViewModel: ServicesViewModel = viewModel {
        ServicesViewModel(apiClient)
    }
    val auditViewModel: AuditViewModel = viewModel {
        AuditViewModel(apiClient)
    }
    val logsViewModel: LogsViewModel = viewModel {
        LogsViewModel(apiClient)
    }
    val memoryViewModel: MemoryViewModel = viewModel {
        MemoryViewModel(apiClient)
    }
    val configViewModel: ConfigViewModel = viewModel {
        ConfigViewModel(apiClient)
    }
    val consentViewModel: ConsentViewModel = viewModel {
        ConsentViewModel(apiClient)
    }
    val systemViewModel: SystemViewModel = viewModel {
        SystemViewModel(apiClient)
    }
    val runtimeViewModel: RuntimeViewModel = viewModel {
        RuntimeViewModel(apiClient)
    }
    val graphMemoryViewModel: GraphMemoryViewModel = viewModel {
        GraphMemoryViewModel(apiClient)
    }
    val usersViewModel: UsersViewModel = viewModel {
        UsersViewModel(apiClient)
    }

    // Set up purchase result callback
    LaunchedEffect(purchaseLauncher) {
        purchaseLauncher?.setOnPurchaseResult { result ->
            when (result) {
                is PurchaseResultType.Success -> {
                    println("[$TAG][INFO] Purchase success: creditsAdded=${result.creditsAdded}, newBalance=${result.newBalance}")
                    billingViewModel.onPurchaseSuccess(result.creditsAdded, result.newBalance)
                }
                is PurchaseResultType.Error -> {
                    println("[$TAG][ERROR] Purchase error: ${result.message}")
                    billingViewModel.onPurchaseError(result.message)
                }
                PurchaseResultType.Cancelled -> {
                    println("[$TAG][INFO] Purchase cancelled")
                    billingViewModel.onPurchaseCancelled()
                }
            }
        }
    }

    // Watch startup phase to check first-run when ready
    val phase by startupViewModel.phase.collectAsState()

    LaunchedEffect(phase) {
        if (phase == StartupPhase.READY && !checkingFirstRun) {
            checkingFirstRun = true
            platformLog(TAG, "[INFO] Startup READY, checking first-run status...")

            // If we just completed setup, skip token validation and go directly to Interact
            // The token was literally just created during setup, so it's definitely valid
            if (justCompletedSetup) {
                platformLog(TAG, "[INFO] Just completed setup, skipping token validation")
                justCompletedSetup = false
                interactViewModel.startPolling() // Start polling now that token is set
                currentScreen = Screen.Interact
                return@LaunchedEffect
            }

            // Check if this is first run via API
            isFirstRun = checkFirstRunStatus(baseUrl)
            platformLog(TAG, "[INFO] First run check result: $isFirstRun")

            if (isFirstRun == true) {
                // First run - show login screen first
                platformLog(TAG, "[INFO] First run detected, navigating to Login")
                currentScreen = Screen.Login
            } else {
                // Not first run - try to load stored token and check if valid/refresh if needed
                platformLog(TAG, "[INFO] Not first run, attempting to load and validate stored token")
                secureStorage.getAccessToken()
                    .onSuccess { storedToken ->
                        if (storedToken != null) {
                            platformLog(TAG, "[INFO] Loaded stored token: ${storedToken.take(8)}...${storedToken.takeLast(4)}")

                            // Check token validity and refresh if needed
                            // NOTE: storedToken is a CIRIS access token, not a Google ID token
                            // If refresh is needed, tokenManager will call onSilentSignInRequested
                            // which gets a Google ID token, then onTokenRefreshed callback
                            // exchanges it for a new CIRIS token
                            tokenExchangeComplete = true // Assume no exchange needed initially
                            val tokenValid = tokenManager.checkAndRefreshToken(storedToken)

                            if (tokenValid) {
                                // Check if exchange was triggered (callback sets this to false)
                                if (!tokenExchangeComplete) {
                                    // Token was refreshed - wait for Google->CIRIS exchange to complete
                                    println("[$TAG][INFO] Token was refreshed, waiting for CIRIS token exchange...")
                                    var waitCount = 0
                                    while (!tokenExchangeComplete && waitCount < 50) {
                                        kotlinx.coroutines.delay(100)
                                        waitCount++
                                    }
                                    if (tokenExchangeComplete) {
                                        println("[$TAG][INFO] Token exchange completed")
                                    } else {
                                        println("[$TAG][WARN] Token exchange timed out")
                                    }
                                } else {
                                    // Token was valid without refresh - use the stored CIRIS token directly
                                    println("[$TAG][INFO] Stored token is valid, setting on API client")
                                    apiClient.setAccessToken(storedToken)
                                    onTokenUpdated?.invoke(storedToken) // Notify MainActivity for BillingManager
                                    currentAccessToken = storedToken
                                    apiClient.logTokenState() // Debug: confirm token was set
                                }

                                // Trigger data loading now that we have auth
                                println("[$TAG][INFO] Triggering data load for ViewModels after token set")
                                billingViewModel.loadBalance()
                                adaptersViewModel.fetchAdapters()
                                interactViewModel.startPolling() // Start polling now that token is set
                                currentScreen = Screen.Interact
                            } else {
                                // Token invalid and couldn't refresh - need interactive login
                                println("[$TAG][INFO] Token invalid/expired and silent refresh failed - redirecting to login")
                                currentScreen = Screen.Login
                            }
                        } else {
                            platformLog(TAG, "[WARN] No stored token found, redirecting to login")
                            currentScreen = Screen.Login
                        }
                    }
                    .onFailure { e ->
                        platformLog(TAG, "[ERROR] Failed to load stored token: ${e::class.simpleName}: ${e.message}")
                        currentScreen = Screen.Login
                    }
            }
        }
    }

    MaterialTheme {
        when (currentScreen) {
            Screen.Startup -> {
                StartupScreen(viewModel = startupViewModel)
            }

            Screen.Login -> {
                platformLog(TAG, "[DEBUG][Screen.Login] Rendering login screen, googleSignInCallback=${if (googleSignInCallback != null) "PRESENT" else "NULL"}")
                LoginScreen(
                    onGoogleSignIn = {
                        platformLog(TAG, "[INFO][onGoogleSignIn] Button click handler invoked, googleSignInCallback=${if (googleSignInCallback != null) "PRESENT" else "NULL"}")
                        if (googleSignInCallback != null) {
                            // Use platform-specific Google sign-in
                            platformLog(TAG, "[INFO][onGoogleSignIn] Callback is not null, calling onGoogleSignInRequested...")
                            isLoginLoading = true
                            loginStatusMessage = "Signing in with ${getOAuthProviderName()}..."

                            googleSignInCallback.onGoogleSignInRequested { result ->
                                platformLog(TAG, "[INFO][onGoogleSignIn] Got result from native sign-in: ${result::class.simpleName}")
                                isLoginLoading = false
                                loginStatusMessage = null

                                platformLog(TAG, "[DEBUG][onGoogleSignIn] Processing result: $result")
                                when (result) {
                                    is NativeSignInResult.Success -> {
                                        platformLog(TAG, "[INFO] Sign-in success: userId=${result.userId}, email=${result.email}")

                                        // Check if setup is already complete
                                        coroutineScope.launch {
                                            platformLog(TAG, "[INFO] Checking setup status at $baseUrl...")
                                            val setupRequired = checkFirstRunStatus(baseUrl)
                                            platformLog(TAG, "[INFO] Setup required check result: $setupRequired")

                                            if (!setupRequired) {
                                                // Setup already done - exchange token immediately
                                                platformLog(TAG, "[INFO] Setup already complete, exchanging token directly")
                                                try {
                                                    platformLog(TAG, "[INFO] Calling apiClient.nativeAuth() for provider=${result.provider}...")
                                                    val authResponse = apiClient.nativeAuth(result.idToken, result.userId, result.provider)
                                                    val cirisToken = authResponse.access_token
                                                    platformLog(TAG, "[INFO] Got CIRIS access token: ${cirisToken.take(8)}...${cirisToken.takeLast(4)}")

                                                    // Set the token on the API client
                                                    apiClient.setAccessToken(cirisToken)
                                                    onTokenUpdated?.invoke(cirisToken) // Notify MainActivity for BillingManager
                                                    currentAccessToken = cirisToken
                                                    apiClient.logTokenState() // Debug: confirm token was set

                                                    // Save to secure storage
                                                    secureStorage.saveAccessToken(cirisToken)
                                                        .onSuccess { println("[$TAG][INFO] CIRIS token saved to secure storage") }
                                                        .onFailure { e -> println("[$TAG][WARN] Failed to save token: ${e.message}") }

                                                    // Update .env file with fresh OAuth ID token for billing
                                                    println("[$TAG][INFO] Writing OAuth ID token to .env for Python billing...")
                                                    envFileUpdater.updateEnvWithToken(result.idToken)
                                                        .onSuccess { updated ->
                                                            if (updated) println("[$TAG][INFO] .env updated, .config_reload signal written")
                                                        }
                                                        .onFailure { e -> println("[$TAG][ERROR] Failed to update .env: ${e.message}") }

                                                    // Wait for Python to detect .config_reload and reload .env
                                                    println("[$TAG][INFO] Waiting 1.5s for Python to reload billing token...")
                                                    kotlinx.coroutines.delay(1500)
                                                    println("[$TAG][INFO] Python reload wait complete")

                                                    // Handle new token with TokenManager for periodic refresh
                                                    tokenManager.handleNewToken(result.idToken, result.provider)

                                                    // Trigger data loading
                                                    println("[$TAG][INFO] Triggering billingViewModel.loadBalance()...")
                                                    billingViewModel.loadBalance()
                                                    adaptersViewModel.fetchAdapters()
                                                    interactViewModel.startPolling() // Start polling now that token is set

                                                    platformLog(TAG, "[INFO] Navigating to Screen.Interact")
                                                    currentScreen = Screen.Interact
                                                } catch (e: Exception) {
                                                    platformLog(TAG, "[ERROR] Token exchange failed: ${e::class.simpleName}: ${e.message}")
                                                    loginStatusMessage = "Token exchange failed: ${e.message}"
                                                }
                                            } else {
                                                // Setup needed - go through wizard
                                                platformLog(TAG, "[INFO] Setup required - storing tokens and navigating to Setup wizard (provider=${result.provider})")
                                                pendingIdToken = result.idToken
                                                pendingUserId = result.userId
                                                pendingProvider = result.provider
                                                tokenManager.setCurrentProvider(result.provider)
                                                setupViewModel.setGoogleAuthState(
                                                    isAuth = true,
                                                    idToken = result.idToken,
                                                    email = result.email,
                                                    userId = result.userId
                                                )
                                                platformLog(TAG, "[INFO] Navigating to Screen.Setup")
                                                currentScreen = Screen.Setup
                                            }
                                        }
                                    }
                                    is NativeSignInResult.Error -> {
                                        loginStatusMessage = "Sign-in failed: ${result.message}"
                                    }
                                    NativeSignInResult.Cancelled -> {
                                        // User cancelled, stay on login screen
                                    }
                                }
                            }
                        } else {
                            // No callback provided - show error
                            platformLog(TAG, "[ERROR][onGoogleSignIn] googleSignInCallback is NULL - cannot invoke native sign-in!")
                            loginStatusMessage = "${getOAuthProviderName()} Sign-In not available"
                        }
                    },
                    onLocalLogin = {
                        // Local login - no Google auth, BYOK only
                        setupViewModel.setGoogleAuthState(
                            isAuth = false,
                            idToken = null,
                            email = null,
                            userId = null
                        )
                        currentScreen = Screen.Setup
                    },
                    isLoading = isLoginLoading,
                    statusMessage = loginStatusMessage
                )
            }

            Screen.Setup -> {
                platformLog(TAG, "[DEBUG][Screen.Setup] Rendering setup screen")
                SetupScreen(
                    viewModel = setupViewModel,
                    apiClient = apiClient,
                    onSetupComplete = {
                        platformLog(TAG, "[INFO] onSetupComplete called - exchanging tokens...")
                        // After setup completes, exchange OAuth ID token for CIRIS access token
                        coroutineScope.launch {
                            try {
                                val idToken = pendingIdToken
                                val userId = pendingUserId
                                val provider = pendingProvider

                                if (idToken != null) {
                                    println("[$TAG][INFO] Exchanging OAuth ID token for CIRIS access token (provider=$provider)")
                                    val authResponse = apiClient.nativeAuth(idToken, userId, provider)
                                    val cirisToken = authResponse.access_token
                                    println("[$TAG][INFO] Got CIRIS access token: ${cirisToken.take(8)}...${cirisToken.takeLast(4)}")

                                    // Set the token on the API client
                                    apiClient.setAccessToken(cirisToken)
                                    onTokenUpdated?.invoke(cirisToken) // Notify MainActivity for BillingManager
                                    currentAccessToken = cirisToken
                                    apiClient.logTokenState() // Debug: confirm token was set

                                    // Store token for future sessions
                                    secureStorage.saveAccessToken(cirisToken)
                                        .onSuccess { println("[$TAG][INFO] Token saved to secure storage") }
                                        .onFailure { e -> println("[$TAG][WARN] Failed to save token to secure storage: ${e.message}") }

                                    // Update .env file with fresh OAuth ID token for billing
                                    println("[$TAG][INFO] Writing OAuth ID token to .env for Python billing...")
                                    envFileUpdater.updateEnvWithToken(idToken)
                                        .onSuccess { updated ->
                                            if (updated) println("[$TAG][INFO] .env updated, .config_reload signal written")
                                        }
                                        .onFailure { e -> println("[$TAG][ERROR] Failed to update .env: ${e.message}") }

                                    // Wait for Python to detect .config_reload and reload .env
                                    println("[$TAG][INFO] Waiting 1.5s for Python to reload billing token...")
                                    kotlinx.coroutines.delay(1500)
                                    println("[$TAG][INFO] Python reload wait complete")

                                    // Trigger data loading now that we have auth AND Python has reloaded
                                    println("[$TAG][INFO] Triggering billingViewModel.loadBalance()...")
                                    billingViewModel.loadBalance()
                                    adaptersViewModel.fetchAdapters()

                                    // Clear pending tokens
                                    pendingIdToken = null
                                    pendingUserId = null
                                } else {
                                    println("[$TAG][INFO] No pending OAuth token, using local auth")
                                    // For local login, we'll authenticate with the admin credentials from setup
                                    // The setup wizard should have created the admin user
                                }
                            } catch (e: Exception) {
                                println("[$TAG][ERROR] Token exchange failed: ${e::class.simpleName}: ${e.message}")
                                println("[$TAG][ERROR] Stack trace: ${e.stackTraceToString().take(500)}")
                            }

                            // After setup completes, Python resumes and starts remaining 12 services
                            // Go back to StartupScreen to show the remaining services starting
                            // Reset the startup phase so it re-polls for services
                            startupViewModel.resetForResume()
                            checkingFirstRun = false  // Allow re-check after startup completes
                            justCompletedSetup = true  // Skip token re-validation since we just authenticated
                            currentScreen = Screen.Startup
                        }
                    }
                )
            }

            Screen.Interact -> {
                Scaffold(
                    topBar = {
                        CIRISTopBar(
                            onSettingsClick = { currentScreen = Screen.Settings },
                            onBillingClick = { currentScreen = Screen.Billing },
                            onTelemetryClick = { currentScreen = Screen.Telemetry },
                            onSessionsClick = { currentScreen = Screen.Sessions },
                            onAdaptersClick = { currentScreen = Screen.Adapters },
                            onWiseAuthorityClick = { currentScreen = Screen.WiseAuthority },
                            onServicesClick = { currentScreen = Screen.Services },
                            onAuditClick = { currentScreen = Screen.Audit },
                            onLogsClick = { currentScreen = Screen.Logs },
                            onMemoryClick = { currentScreen = Screen.Memory },
                            onConfigClick = { currentScreen = Screen.Config },
                            onConsentClick = { currentScreen = Screen.Consent },
                            onSystemClick = { currentScreen = Screen.System },
                            onRuntimeClick = { currentScreen = Screen.Runtime },
                            onUsersClick = { currentScreen = Screen.Users }
                        )
                    }
                ) { paddingValues ->
                    // Only apply top padding from Scaffold - InteractScreen handles
                    // bottom insets (keyboard + nav bar) via windowInsetsPadding
                    InteractScreen(
                        viewModel = interactViewModel,
                        onNavigateBack = { /* Already at root */ },
                        onSessionExpired = {
                            // Navigate to login screen when session expires
                            platformLog(TAG, "[INFO] Session expired - navigating to login")
                            currentAccessToken = null
                            // Clear stored tokens asynchronously
                            coroutineScope.launch {
                                secureStorage.deleteAccessToken()
                            }
                            currentScreen = Screen.Login
                        },
                        modifier = Modifier.padding(top = paddingValues.calculateTopPadding())
                    )
                }
            }

            Screen.Settings -> {
                SettingsScreen(
                    viewModel = settingsViewModel,
                    onNavigateBack = { currentScreen = Screen.Interact },
                    onLogout = {
                        println("[CIRISApp][INFO][onLogout] User initiated logout")
                        settingsViewModel.logout {
                            println("[CIRISApp][INFO][onLogout] Logout complete, navigating to Startup")
                            currentScreen = Screen.Startup
                        }
                    },
                    onResetSetup = {
                        println("[CIRISApp][INFO][onResetSetup] Setup reset requested, restarting app...")
                        // Navigate to Startup which will detect first-run and show setup wizard
                        // The .env file has been deleted, so first-run detection will trigger
                        currentScreen = Screen.Startup
                    }
                )
            }

            Screen.Billing -> {
                val currentBalance by billingViewModel.currentBalance.collectAsState()
                val products by billingViewModel.products.collectAsState()
                val isBillingLoading by billingViewModel.isLoading.collectAsState()
                val billingError by billingViewModel.errorMessage.collectAsState()
                val billingSuccess by billingViewModel.successMessage.collectAsState()
                val isByokMode by billingViewModel.isByokMode.collectAsState()

                // Load balance when entering billing screen
                LaunchedEffect(Unit) {
                    println("[$TAG][INFO][Screen.Billing] Loading balance on screen entry")
                    billingViewModel.loadBalance()
                }

                println("[CIRISApp][DEBUG][Screen.Billing] Rendering billing screen: " +
                        "balance=$currentBalance, products=${products.size}, " +
                        "isByok=$isByokMode, isLoading=$isBillingLoading")

                // Display snackbar for error/success messages
                LaunchedEffect(billingError) {
                    if (billingError != null) {
                        println("[CIRISApp][WARN][Screen.Billing] Error: $billingError")
                    }
                }
                LaunchedEffect(billingSuccess) {
                    if (billingSuccess != null) {
                        println("[CIRISApp][INFO][Screen.Billing] Success: $billingSuccess")
                    }
                }

                BillingScreen(
                    currentBalance = currentBalance,
                    products = products,
                    isLoading = isBillingLoading,
                    errorMessage = billingError,
                    onProductClick = { product ->
                        println("[CIRISApp][INFO][Screen.Billing] Product clicked: ${product.productId}")
                        billingViewModel.onProductSelected(product) { selectedProduct ->
                            println("[CIRISApp][INFO][Screen.Billing] Launching purchase for: ${selectedProduct.productId}")
                            if (purchaseLauncher != null) {
                                billingViewModel.onPurchaseStarted(selectedProduct.productId)
                                purchaseLauncher.launchPurchase(selectedProduct.productId)
                            } else {
                                println("[CIRISApp][WARN][Screen.Billing] No purchase launcher available")
                                billingViewModel.onPurchaseError("In-app purchases not available on this platform")
                            }
                        }
                    },
                    onRefresh = {
                        println("[CIRISApp][INFO][Screen.Billing] User triggered refresh")
                        billingViewModel.refresh()
                    },
                    onNavigateBack = {
                        println("[CIRISApp][INFO][Screen.Billing] Navigating back to Interact")
                        currentScreen = Screen.Interact
                    },
                    onDismissError = {
                        billingViewModel.clearError()
                    }
                )
            }

            Screen.Telemetry -> {
                val telemetryData by telemetryViewModel.telemetryData.collectAsState()
                val isTelemetryLoading by telemetryViewModel.isLoading.collectAsState()

                // Start/stop polling based on screen visibility
                DisposableEffect(Unit) {
                    println("[$TAG][INFO][Screen.Telemetry] Starting telemetry polling")
                    telemetryViewModel.startPolling()
                    onDispose {
                        println("[$TAG][INFO][Screen.Telemetry] Stopping telemetry polling")
                        telemetryViewModel.stopPolling()
                    }
                }

                println("[CIRISApp][DEBUG][Screen.Telemetry] Rendering telemetry screen: " +
                        "services=${telemetryData.healthyServices}/${telemetryData.totalServices}, " +
                        "state=${telemetryData.cognitiveState}, isLoading=$isTelemetryLoading")

                TelemetryScreen(
                    telemetryData = telemetryData,
                    isLoading = isTelemetryLoading,
                    onRefresh = {
                        println("[CIRISApp][INFO][Screen.Telemetry] User triggered refresh")
                        telemetryViewModel.refresh()
                    },
                    onNavigateBack = {
                        println("[CIRISApp][INFO][Screen.Telemetry] Navigating back to Interact")
                        currentScreen = Screen.Interact
                    }
                )
            }

            Screen.Sessions -> {
                val currentCognitiveState by sessionsViewModel.currentState.collectAsState()
                val isSessionsLoading by sessionsViewModel.isLoading.collectAsState()
                val isTransitioning by sessionsViewModel.isTransitioning.collectAsState()
                val sessionStatusMessage by sessionsViewModel.statusMessage.collectAsState()
                val sessionErrorMessage by sessionsViewModel.errorMessage.collectAsState()

                // Start/stop polling based on screen visibility
                DisposableEffect(Unit) {
                    println("[$TAG][INFO][Screen.Sessions] Starting sessions polling")
                    sessionsViewModel.startPolling()
                    onDispose {
                        println("[$TAG][INFO][Screen.Sessions] Stopping sessions polling")
                        sessionsViewModel.stopPolling()
                    }
                }

                println("[CIRISApp][DEBUG][Screen.Sessions] Rendering sessions screen: " +
                        "state=$currentCognitiveState, isLoading=$isSessionsLoading, " +
                        "isTransitioning=$isTransitioning")

                // Log status/error messages
                LaunchedEffect(sessionStatusMessage) {
                    if (sessionStatusMessage != null) {
                        println("[CIRISApp][INFO][Screen.Sessions] Status: $sessionStatusMessage")
                    }
                }
                LaunchedEffect(sessionErrorMessage) {
                    if (sessionErrorMessage != null) {
                        println("[CIRISApp][WARN][Screen.Sessions] Error: $sessionErrorMessage")
                    }
                }

                SessionsScreen(
                    currentState = currentCognitiveState,
                    isLoading = isSessionsLoading || isTransitioning,
                    onInitiateSession = { targetState ->
                        println("[CIRISApp][INFO][Screen.Sessions] Initiating session transition: $currentCognitiveState -> $targetState")
                        sessionsViewModel.initiateSession(targetState)
                    },
                    onRefresh = {
                        println("[CIRISApp][INFO][Screen.Sessions] User triggered refresh")
                        sessionsViewModel.refresh()
                    },
                    onNavigateBack = {
                        println("[CIRISApp][INFO][Screen.Sessions] Navigating back to Interact")
                        currentScreen = Screen.Interact
                    }
                )
            }

            Screen.Adapters -> {
                val adaptersList by adaptersViewModel.adapters.collectAsState()
                val isAdaptersConnected by adaptersViewModel.isConnected.collectAsState()
                val isAdaptersLoading by adaptersViewModel.isLoading.collectAsState()
                val adaptersStatusMessage by adaptersViewModel.statusMessage.collectAsState()
                val adaptersOperationInProgress by adaptersViewModel.operationInProgress.collectAsState()
                // Wizard state
                val showWizardDialog by adaptersViewModel.showWizardDialog.collectAsState()
                val moduleTypes by adaptersViewModel.moduleTypes.collectAsState()
                val wizardSession by adaptersViewModel.wizardSession.collectAsState()
                val wizardError by adaptersViewModel.wizardError.collectAsState()
                val wizardLoading by adaptersViewModel.wizardLoading.collectAsState()

                println("[CIRISApp][DEBUG][Screen.Adapters] Rendering adapters screen: " +
                        "adapters=${adaptersList.size}, connected=$isAdaptersConnected, " +
                        "isLoading=$isAdaptersLoading, operationInProgress=$adaptersOperationInProgress")

                // Start polling when screen is visible
                DisposableEffect(Unit) {
                    println("[CIRISApp][INFO][Screen.Adapters] Starting adapter polling")
                    adaptersViewModel.startPolling()
                    onDispose {
                        println("[CIRISApp][INFO][Screen.Adapters] Stopping adapter polling")
                        adaptersViewModel.stopPolling()
                    }
                }

                // Log status messages
                LaunchedEffect(adaptersStatusMessage) {
                    if (adaptersStatusMessage != null) {
                        println("[CIRISApp][INFO][Screen.Adapters] Status: $adaptersStatusMessage")
                    }
                }

                AdaptersScreen(
                    adapters = adaptersList,
                    isConnected = isAdaptersConnected,
                    isLoading = isAdaptersLoading || adaptersOperationInProgress,
                    onReloadAdapter = { adapterId ->
                        println("[CIRISApp][INFO][Screen.Adapters] Reloading adapter: $adapterId")
                        adaptersViewModel.reloadAdapter(adapterId)
                    },
                    onRemoveAdapter = { adapterId ->
                        println("[CIRISApp][INFO][Screen.Adapters] Removing adapter: $adapterId")
                        adaptersViewModel.removeAdapter(adapterId)
                    },
                    onAddAdapter = {
                        println("[CIRISApp][INFO][Screen.Adapters] Add adapter requested")
                        adaptersViewModel.addAdapter()
                    },
                    onRefresh = {
                        println("[CIRISApp][INFO][Screen.Adapters] User triggered refresh")
                        adaptersViewModel.refresh()
                    },
                    onNavigateBack = {
                        println("[CIRISApp][INFO][Screen.Adapters] Navigating back to Interact")
                        currentScreen = Screen.Interact
                    }
                )

                // Adapter wizard dialog - show when dialog is open OR when there's an error to display
                if (showWizardDialog || wizardError != null) {
                    AdapterWizardDialog(
                        moduleTypes = moduleTypes,
                        wizardSession = wizardSession,
                        isLoading = wizardLoading,
                        error = wizardError,
                        onSelectType = { adapterType ->
                            println("[CIRISApp][INFO][AdapterWizard] Selected type: $adapterType")
                            adaptersViewModel.startWizard(adapterType)
                        },
                        onSubmitStep = { stepData ->
                            println("[CIRISApp][INFO][AdapterWizard] Submitting step with ${stepData.size} fields")
                            adaptersViewModel.submitWizardStep(stepData)
                        },
                        onBack = {
                            println("[CIRISApp][INFO][AdapterWizard] Back pressed")
                            adaptersViewModel.wizardBack()
                        },
                        onDismiss = {
                            println("[CIRISApp][INFO][AdapterWizard] Dialog dismissed")
                            adaptersViewModel.closeWizard()
                        }
                    )
                }
            }

            Screen.WiseAuthority -> {
                val waStatus by wiseAuthorityViewModel.waStatus.collectAsState()
                val deferrals by wiseAuthorityViewModel.deferrals.collectAsState()
                val isWALoading by wiseAuthorityViewModel.isLoading.collectAsState()
                val isResolving by wiseAuthorityViewModel.isResolving.collectAsState()
                val waError by wiseAuthorityViewModel.error.collectAsState()
                val waSuccess by wiseAuthorityViewModel.successMessage.collectAsState()

                // Start/stop polling based on screen visibility
                DisposableEffect(Unit) {
                    println("[$TAG][INFO][Screen.WiseAuthority] Starting WA polling")
                    wiseAuthorityViewModel.startPolling()
                    onDispose {
                        println("[$TAG][INFO][Screen.WiseAuthority] Stopping WA polling")
                        wiseAuthorityViewModel.stopPolling()
                    }
                }

                println("[CIRISApp][DEBUG][Screen.WiseAuthority] Rendering WA screen: " +
                        "status=${waStatus?.serviceHealthy}, deferrals=${deferrals.size}, " +
                        "isLoading=$isWALoading, isResolving=$isResolving")

                // Log status/error messages
                LaunchedEffect(waError) {
                    if (waError != null) {
                        println("[CIRISApp][WARN][Screen.WiseAuthority] Error: $waError")
                    }
                }
                LaunchedEffect(waSuccess) {
                    if (waSuccess != null) {
                        println("[CIRISApp][INFO][Screen.WiseAuthority] Success: $waSuccess")
                        wiseAuthorityViewModel.clearSuccess()
                    }
                }

                WiseAuthorityScreen(
                    waStatus = waStatus,
                    deferrals = deferrals,
                    isLoading = isWALoading,
                    isResolving = isResolving,
                    onResolveDeferral = { deferralId, resolution, guidance ->
                        println("[CIRISApp][INFO][Screen.WiseAuthority] Resolving deferral: $deferralId -> $resolution")
                        wiseAuthorityViewModel.resolveDeferral(deferralId, resolution, guidance)
                    },
                    onRefresh = {
                        println("[CIRISApp][INFO][Screen.WiseAuthority] User triggered refresh")
                        wiseAuthorityViewModel.refresh()
                    },
                    onNavigateBack = {
                        println("[CIRISApp][INFO][Screen.WiseAuthority] Navigating back to Interact")
                        currentScreen = Screen.Interact
                    }
                )
            }

            Screen.Services -> {
                val servicesData by servicesViewModel.servicesData.collectAsState()
                val isServicesLoading by servicesViewModel.isLoading.collectAsState()
                val servicesError by servicesViewModel.error.collectAsState()

                // Start/stop polling based on screen visibility
                DisposableEffect(Unit) {
                    println("[$TAG][INFO][Screen.Services] Starting services polling")
                    servicesViewModel.startPolling()
                    onDispose {
                        println("[$TAG][INFO][Screen.Services] Stopping services polling")
                        servicesViewModel.stopPolling()
                    }
                }

                LaunchedEffect(servicesError) {
                    servicesError?.let { error ->
                        println("[$TAG][ERROR][Screen.Services] Services error: $error")
                    }
                }

                println("[CIRISApp][DEBUG][Screen.Services] Rendering services screen: " +
                        "total=${servicesData.totalServices}, healthy=${servicesData.healthyServices}, " +
                        "isLoading=$isServicesLoading")

                ServicesScreen(
                    servicesData = servicesData,
                    isLoading = isServicesLoading,
                    onRefresh = {
                        println("[CIRISApp][INFO][Screen.Services] User triggered refresh")
                        servicesViewModel.refresh()
                    },
                    onDiagnose = {
                        println("[CIRISApp][INFO][Screen.Services] User triggered diagnose")
                        servicesViewModel.runDiagnostics()
                    },
                    onResetCircuitBreakers = { serviceType ->
                        println("[CIRISApp][INFO][Screen.Services] Reset circuit breakers: $serviceType")
                        servicesViewModel.resetCircuitBreakers(serviceType)
                    },
                    onNavigateBack = {
                        println("[CIRISApp][INFO][Screen.Services] Navigating back to Interact")
                        currentScreen = Screen.Interact
                    }
                )
            }

            Screen.Audit -> {
                val auditState by auditViewModel.state.collectAsState()

                // Start/stop polling based on screen visibility
                DisposableEffect(Unit) {
                    println("[$TAG][INFO][Screen.Audit] Starting audit polling")
                    auditViewModel.startPolling()
                    onDispose {
                        println("[$TAG][INFO][Screen.Audit] Stopping audit polling")
                        auditViewModel.stopPolling()
                    }
                }

                LaunchedEffect(auditState.error) {
                    auditState.error?.let { error ->
                        println("[$TAG][ERROR][Screen.Audit] Audit error: $error")
                    }
                }

                println("[CIRISApp][DEBUG][Screen.Audit] Rendering audit screen: " +
                        "entries=${auditState.entries.size}, total=${auditState.totalEntries}, " +
                        "isLoading=${auditState.isLoading}, error=${auditState.error}")

                AuditScreen(
                    auditState = auditState,
                    onRefresh = {
                        println("[CIRISApp][INFO][Screen.Audit] User triggered refresh")
                        auditViewModel.refresh()
                    },
                    onLoadMore = {
                        println("[CIRISApp][INFO][Screen.Audit] Load more requested")
                        auditViewModel.loadMore()
                    },
                    onFilterChange = { filter ->
                        println("[CIRISApp][INFO][Screen.Audit] Filter changed: $filter")
                        auditViewModel.updateFilter(filter)
                    },
                    onNavigateBack = { currentScreen = Screen.Interact }
                )
            }

            Screen.Logs -> {
                val logsState by logsViewModel.state.collectAsState()

                // Start/stop polling based on screen visibility
                DisposableEffect(Unit) {
                    println("[$TAG][INFO][Screen.Logs] Starting logs polling")
                    logsViewModel.startPolling()
                    onDispose {
                        println("[$TAG][INFO][Screen.Logs] Stopping logs polling")
                        logsViewModel.stopPolling()
                    }
                }

                LaunchedEffect(logsState.error) {
                    logsState.error?.let { error ->
                        println("[$TAG][ERROR][Screen.Logs] Logs error: $error")
                    }
                }

                println("[CIRISApp][DEBUG][Screen.Logs] Rendering logs screen: " +
                        "logs=${logsState.logs.size}, isLoading=${logsState.isLoading}, error=${logsState.error}")

                LogsScreen(
                    logsState = logsState,
                    onRefresh = {
                        println("[CIRISApp][INFO][Screen.Logs] User triggered refresh")
                        logsViewModel.refresh()
                    },
                    onFilterChange = { filter ->
                        println("[CIRISApp][INFO][Screen.Logs] Filter changed: $filter")
                        logsViewModel.updateFilter(filter)
                    },
                    onSearchChange = { query ->
                        println("[CIRISApp][INFO][Screen.Logs] Search changed: $query")
                        logsViewModel.updateSearch(query)
                    },
                    onToggleAutoScroll = {
                        println("[CIRISApp][INFO][Screen.Logs] Toggle auto-scroll")
                        logsViewModel.toggleAutoScroll()
                    },
                    onNavigateBack = { currentScreen = Screen.Interact }
                )
            }

            Screen.Memory -> {
                val memoryState by memoryViewModel.state.collectAsState()

                // Start/stop polling based on screen visibility
                DisposableEffect(Unit) {
                    println("[$TAG][INFO][Screen.Memory] Starting memory polling")
                    memoryViewModel.startPolling()
                    onDispose {
                        println("[$TAG][INFO][Screen.Memory] Stopping memory polling")
                        memoryViewModel.stopPolling()
                    }
                }

                LaunchedEffect(memoryState.error) {
                    memoryState.error?.let { error ->
                        println("[$TAG][ERROR][Screen.Memory] Memory error: $error")
                    }
                }

                println("[CIRISApp][DEBUG][Screen.Memory] Rendering memory screen: " +
                        "searchResults=${memoryState.searchResults.size}, timeline=${memoryState.timelineNodes.size}, " +
                        "isLoading=${memoryState.isLoading}, error=${memoryState.error}")

                MemoryScreen(
                    memoryState = memoryState,
                    onRefresh = {
                        println("[CIRISApp][INFO][Screen.Memory] User triggered refresh")
                        memoryViewModel.refresh()
                    },
                    onSearch = { query ->
                        println("[CIRISApp][INFO][Screen.Memory] Search: $query")
                        memoryViewModel.search(query)
                    },
                    onFilterChange = { filter ->
                        println("[CIRISApp][INFO][Screen.Memory] Filter changed: $filter")
                        memoryViewModel.updateFilter(filter)
                    },
                    onNodeSelect = { nodeId ->
                        println("[CIRISApp][INFO][Screen.Memory] Node selected: $nodeId")
                        memoryViewModel.selectNode(nodeId)
                    },
                    onClearSelection = {
                        println("[CIRISApp][INFO][Screen.Memory] Clear selection")
                        memoryViewModel.clearSelection()
                    },
                    onNavigateBack = { currentScreen = Screen.Interact },
                    onSwitchToGraph = {
                        println("[CIRISApp][INFO][Screen.Memory] Switching to graph view")
                        currentScreen = Screen.GraphMemory
                    }
                )
            }

            Screen.GraphMemory -> {
                val graphState by graphMemoryViewModel.displayState.collectAsState()
                val graphFilter by graphMemoryViewModel.filter.collectAsState()
                val graphStats by graphMemoryViewModel.stats.collectAsState()

                LaunchedEffect(Unit) {
                    println("[$TAG][INFO][Screen.GraphMemory] Loading graph data on screen entry")
                    graphMemoryViewModel.setCanvasSize(800f, 600f) // Default size, will be updated
                    graphMemoryViewModel.loadGraphData()
                }

                println("[CIRISApp][DEBUG][Screen.GraphMemory] Rendering graph screen: " +
                        "nodes=${graphState.nodes.size}, edges=${graphState.edges.size}, " +
                        "isLoading=${graphState.isLoading}")

                GraphMemoryScreen(
                    state = graphState,
                    filter = graphFilter,
                    stats = graphStats,
                    onRefresh = {
                        println("[CIRISApp][INFO][Screen.GraphMemory] User triggered refresh")
                        graphMemoryViewModel.refresh()
                    },
                    onFilterChange = { filter ->
                        println("[CIRISApp][INFO][Screen.GraphMemory] Filter changed")
                        graphMemoryViewModel.updateFilter(filter)
                    },
                    onLayoutChange = { layout ->
                        println("[CIRISApp][INFO][Screen.GraphMemory] Layout changed: $layout")
                        graphMemoryViewModel.changeLayout(layout)
                    },
                    onNodeSelected = { nodeId ->
                        println("[CIRISApp][INFO][Screen.GraphMemory] Node selected: $nodeId")
                        graphMemoryViewModel.selectNode(nodeId)
                    },
                    onViewportChange = { viewport ->
                        graphMemoryViewModel.updateViewport(viewport)
                    },
                    onNodeDragStart = { nodeId ->
                        graphMemoryViewModel.startNodeDrag(nodeId)
                    },
                    onNodeDrag = { nodeId, dx, dy ->
                        graphMemoryViewModel.dragNode(nodeId, dx, dy)
                    },
                    onNodeDragEnd = { nodeId ->
                        graphMemoryViewModel.endNodeDrag(nodeId)
                    },
                    onStartSimulation = {
                        println("[CIRISApp][INFO][Screen.GraphMemory] Starting simulation")
                        graphMemoryViewModel.startSimulation()
                    },
                    onStopSimulation = {
                        println("[CIRISApp][INFO][Screen.GraphMemory] Stopping simulation")
                        graphMemoryViewModel.stopSimulation()
                    },
                    onNavigateBack = {
                        println("[CIRISApp][INFO][Screen.GraphMemory] Navigating back to Memory list")
                        currentScreen = Screen.Memory
                    }
                )
            }

            Screen.Config -> {
                val configData by configViewModel.configData.collectAsState()
                val isConfigLoading by configViewModel.isLoading.collectAsState()
                val configSearchQuery by configViewModel.searchQuery.collectAsState()
                val configSelectedCategory by configViewModel.selectedCategory.collectAsState()
                val configExpandedSections by configViewModel.expandedSections.collectAsState()
                val configError by configViewModel.error.collectAsState()

                // Start/stop polling based on screen visibility
                DisposableEffect(Unit) {
                    println("[$TAG][INFO][Screen.Config] Starting config polling")
                    configViewModel.startPolling()
                    onDispose {
                        println("[$TAG][INFO][Screen.Config] Stopping config polling")
                        configViewModel.stopPolling()
                    }
                }

                LaunchedEffect(configError) {
                    configError?.let { error ->
                        println("[$TAG][ERROR][Screen.Config] Config error: $error")
                    }
                }

                println("[CIRISApp][DEBUG][Screen.Config] Rendering config screen: " +
                        "sections=${configData.sections.size}, isLoading=$isConfigLoading")

                ConfigScreen(
                    configData = configData,
                    isLoading = isConfigLoading,
                    searchQuery = configSearchQuery,
                    selectedCategory = configSelectedCategory,
                    expandedSections = configExpandedSections,
                    onSearchQueryChange = { query ->
                        println("[CIRISApp][INFO][Screen.Config] Search changed: $query")
                        configViewModel.updateSearchQuery(query)
                    },
                    onCategorySelect = { category ->
                        println("[CIRISApp][INFO][Screen.Config] Category selected: $category")
                        configViewModel.selectCategory(category)
                    },
                    onToggleSection = { section ->
                        println("[CIRISApp][INFO][Screen.Config] Toggle section: $section")
                        configViewModel.toggleSection(section)
                    },
                    onUpdateConfig = { key, value ->
                        println("[CIRISApp][INFO][Screen.Config] Update config: $key=$value")
                        configViewModel.updateConfig(key, value)
                    },
                    onDeleteConfig = { key ->
                        println("[CIRISApp][INFO][Screen.Config] Delete config: $key")
                        configViewModel.deleteConfig(key)
                    },
                    onRefresh = {
                        println("[CIRISApp][INFO][Screen.Config] User triggered refresh")
                        configViewModel.refresh()
                    },
                    onNavigateBack = { currentScreen = Screen.Interact }
                )
            }

            Screen.Consent -> {
                val consentData by consentViewModel.consentData.collectAsState()
                val isConsentLoading by consentViewModel.isLoading.collectAsState()
                val consentError by consentViewModel.error.collectAsState()

                // Start/stop polling based on screen visibility
                DisposableEffect(Unit) {
                    println("[$TAG][INFO][Screen.Consent] Starting consent polling")
                    consentViewModel.startPolling()
                    onDispose {
                        println("[$TAG][INFO][Screen.Consent] Stopping consent polling")
                        consentViewModel.stopPolling()
                    }
                }

                LaunchedEffect(consentError) {
                    consentError?.let { error ->
                        println("[$TAG][ERROR][Screen.Consent] Consent error: $error")
                    }
                }

                println("[CIRISApp][DEBUG][Screen.Consent] Rendering consent screen: " +
                        "streams=${consentData.availableStreams.size}, isLoading=$isConsentLoading")

                ConsentScreen(
                    consentData = consentData,
                    isLoading = isConsentLoading,
                    onStreamSelect = { streamId ->
                        println("[CIRISApp][INFO][Screen.Consent] Stream selected: $streamId")
                        consentViewModel.changeStream(streamId)
                    },
                    onRequestPartnership = {
                        println("[CIRISApp][INFO][Screen.Consent] Request partnership")
                        consentViewModel.requestPartnership()
                    },
                    onRefresh = {
                        println("[CIRISApp][INFO][Screen.Consent] User triggered refresh")
                        consentViewModel.refresh()
                    },
                    onNavigateBack = { currentScreen = Screen.Interact }
                )
            }

            Screen.System -> {
                val systemData by systemViewModel.systemData.collectAsState()
                val isSystemLoading by systemViewModel.isLoading.collectAsState()
                val systemError by systemViewModel.error.collectAsState()

                // Start/stop polling based on screen visibility
                DisposableEffect(Unit) {
                    println("[$TAG][INFO][Screen.System] Starting system polling")
                    systemViewModel.startPolling()
                    onDispose {
                        println("[$TAG][INFO][Screen.System] Stopping system polling")
                        systemViewModel.stopPolling()
                    }
                }

                LaunchedEffect(systemError) {
                    systemError?.let { error ->
                        println("[$TAG][ERROR][Screen.System] System error: $error")
                    }
                }

                println("[CIRISApp][DEBUG][Screen.System] Rendering system screen: " +
                        "health=${systemData.health}, isPaused=${systemData.isPaused}, isLoading=$isSystemLoading")

                SystemScreen(
                    systemData = systemData,
                    isLoading = isSystemLoading,
                    onPauseRuntime = {
                        println("[CIRISApp][INFO][Screen.System] Pause runtime")
                        systemViewModel.pauseRuntime()
                    },
                    onResumeRuntime = {
                        println("[CIRISApp][INFO][Screen.System] Resume runtime")
                        systemViewModel.resumeRuntime()
                    },
                    onRefresh = {
                        println("[CIRISApp][INFO][Screen.System] User triggered refresh")
                        systemViewModel.refresh()
                    },
                    onNavigateBack = { currentScreen = Screen.Interact }
                )
            }

            Screen.Runtime -> {
                val runtimeData by runtimeViewModel.runtimeData.collectAsState()
                val isRuntimeLoading by runtimeViewModel.isLoading.collectAsState()
                val runtimeError by runtimeViewModel.error.collectAsState()
                val isRuntimeAdmin by runtimeViewModel.isAdmin.collectAsState()

                // Start/stop polling based on screen visibility
                DisposableEffect(Unit) {
                    println("[$TAG][INFO][Screen.Runtime] Starting runtime polling")
                    runtimeViewModel.startPolling()
                    onDispose {
                        println("[$TAG][INFO][Screen.Runtime] Stopping runtime polling")
                        runtimeViewModel.stopPolling()
                    }
                }

                LaunchedEffect(runtimeError) {
                    runtimeError?.let { error ->
                        println("[$TAG][ERROR][Screen.Runtime] Runtime error: $error")
                    }
                }

                println("[CIRISApp][DEBUG][Screen.Runtime] Rendering runtime screen: " +
                        "processorState=${runtimeData.processorState}, cognitiveState=${runtimeData.cognitiveState}, isLoading=$isRuntimeLoading")

                RuntimeScreen(
                    runtimeData = runtimeData,
                    isLoading = isRuntimeLoading,
                    isAdmin = isRuntimeAdmin,
                    onPause = {
                        println("[CIRISApp][INFO][Screen.Runtime] Pause runtime")
                        runtimeViewModel.pauseRuntime()
                    },
                    onResume = {
                        println("[CIRISApp][INFO][Screen.Runtime] Resume runtime")
                        runtimeViewModel.resumeRuntime()
                    },
                    onSingleStep = {
                        println("[CIRISApp][INFO][Screen.Runtime] Single step")
                        runtimeViewModel.singleStep()
                    },
                    onRefresh = {
                        println("[CIRISApp][INFO][Screen.Runtime] User triggered refresh")
                        runtimeViewModel.refresh()
                    },
                    onNavigateBack = { currentScreen = Screen.Interact }
                )
            }

            Screen.Users -> {
                val usersState by usersViewModel.state.collectAsState()

                LaunchedEffect(Unit) {
                    println("[$TAG][INFO][Screen.Users] Loading users on screen entry")
                    usersViewModel.refresh()
                }

                LaunchedEffect(usersState.error) {
                    usersState.error?.let { error ->
                        println("[$TAG][ERROR][Screen.Users] Users error: $error")
                    }
                }

                println("[CIRISApp][DEBUG][Screen.Users] Rendering users screen: " +
                        "users=${usersState.users.size}, total=${usersState.pagination.totalItems}, " +
                        "isLoading=${usersState.isLoading}")

                UsersScreen(
                    state = usersState,
                    onRefresh = {
                        println("[CIRISApp][INFO][Screen.Users] User triggered refresh")
                        usersViewModel.refresh()
                    },
                    onSearch = { query ->
                        println("[CIRISApp][INFO][Screen.Users] Search: $query")
                        usersViewModel.updateSearch(query)
                    },
                    onFilterChange = { filter ->
                        println("[CIRISApp][INFO][Screen.Users] Filter changed")
                        usersViewModel.updateFilter(filter)
                    },
                    onSelectUser = { userId ->
                        println("[CIRISApp][INFO][Screen.Users] User selected: $userId")
                        usersViewModel.selectUser(userId)
                    },
                    onClearSelection = {
                        println("[CIRISApp][INFO][Screen.Users] Clear selection")
                        usersViewModel.clearSelection()
                    },
                    onNextPage = {
                        println("[CIRISApp][INFO][Screen.Users] Next page")
                        usersViewModel.nextPage()
                    },
                    onPreviousPage = {
                        println("[CIRISApp][INFO][Screen.Users] Previous page")
                        usersViewModel.previousPage()
                    },
                    onNavigateBack = { currentScreen = Screen.Interact }
                )
            }
        }
    }
}

/**
 * Check if setup is required via /v1/setup/status API
 * Uses the API client for platform-independent HTTP handling.
 */
private suspend fun checkFirstRunStatus(baseUrl: String): Boolean {
    return try {
        platformLog("checkFirstRunStatus", "[INFO] Creating API client for $baseUrl")
        val client = CIRISApiClient(baseUrl)
        platformLog("checkFirstRunStatus", "[INFO] Calling getSetupStatus()...")
        val setupStatus = client.getSetupStatus()
        platformLog("checkFirstRunStatus", "[INFO] Got setup status: setup_required=${setupStatus.data.setup_required}")
        setupStatus.data.setup_required
    } catch (e: Exception) {
        // On error, assume first run for safety
        platformLog("checkFirstRunStatus", "[ERROR] Failed to check setup status: ${e::class.simpleName}: ${e.message}")
        true
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CIRISTopBar(
    onSettingsClick: () -> Unit,
    onBillingClick: () -> Unit = {},
    onTelemetryClick: () -> Unit = {},
    onSessionsClick: () -> Unit = {},
    onAdaptersClick: () -> Unit = {},
    onWiseAuthorityClick: () -> Unit = {},
    onServicesClick: () -> Unit = {},
    onAuditClick: () -> Unit = {},
    onLogsClick: () -> Unit = {},
    onMemoryClick: () -> Unit = {},
    onConfigClick: () -> Unit = {},
    onConsentClick: () -> Unit = {},
    onSystemClick: () -> Unit = {},
    onRuntimeClick: () -> Unit = {},
    onUsersClick: () -> Unit = {}
) {
    var showMenu by remember { mutableStateOf(false) }

    TopAppBar(
        title = {
            Text("CIRIS")
        },
        actions = {
            IconButton(onClick = onSettingsClick) {
                Icon(
                    imageVector = Icons.Default.Settings,
                    contentDescription = "Settings"
                )
            }

            Box {
                IconButton(onClick = { showMenu = true }) {
                    Icon(
                        imageVector = Icons.Default.MoreVert,
                        contentDescription = "More"
                    )
                }

                DropdownMenu(
                    expanded = showMenu,
                    onDismissRequest = { showMenu = false }
                ) {
                    DropdownMenuItem(
                        text = { Text("Buy Credits") },
                        onClick = {
                            showMenu = false
                            onBillingClick()
                        },
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.Star,
                                contentDescription = null
                            )
                        }
                    )
                    DropdownMenuItem(
                        text = { Text("Telemetry") },
                        onClick = {
                            showMenu = false
                            onTelemetryClick()
                        },
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.Info,
                                contentDescription = null
                            )
                        }
                    )
                    DropdownMenuItem(
                        text = { Text("Sessions") },
                        onClick = {
                            showMenu = false
                            onSessionsClick()
                        },
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.Star,
                                contentDescription = null
                            )
                        }
                    )
                    DropdownMenuItem(
                        text = { Text("Adapters") },
                        onClick = {
                            showMenu = false
                            onAdaptersClick()
                        },
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.Build,
                                contentDescription = null
                            )
                        }
                    )
                    DropdownMenuItem(
                        text = { Text("Wise Authority") },
                        onClick = {
                            showMenu = false
                            onWiseAuthorityClick()
                        },
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.Info,
                                contentDescription = null
                            )
                        }
                    )
                    DropdownMenuItem(
                        text = { Text("Services") },
                        onClick = {
                            showMenu = false
                            onServicesClick()
                        },
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.Build,
                                contentDescription = null
                            )
                        }
                    )
                    DropdownMenuItem(
                        text = { Text("Audit Trail") },
                        onClick = {
                            showMenu = false
                            onAuditClick()
                        },
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.List,
                                contentDescription = null
                            )
                        }
                    )
                    DropdownMenuItem(
                        text = { Text("Logs") },
                        onClick = {
                            showMenu = false
                            onLogsClick()
                        },
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.List,
                                contentDescription = null
                            )
                        }
                    )
                    DropdownMenuItem(
                        text = { Text("Memory") },
                        onClick = {
                            showMenu = false
                            onMemoryClick()
                        },
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.Star,
                                contentDescription = null
                            )
                        }
                    )
                    DropdownMenuItem(
                        text = { Text("Config") },
                        onClick = {
                            showMenu = false
                            onConfigClick()
                        },
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.Settings,
                                contentDescription = null
                            )
                        }
                    )
                    DropdownMenuItem(
                        text = { Text("Consent") },
                        onClick = {
                            showMenu = false
                            onConsentClick()
                        },
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.Check,
                                contentDescription = null
                            )
                        }
                    )
                    DropdownMenuItem(
                        text = { Text("System") },
                        onClick = {
                            showMenu = false
                            onSystemClick()
                        },
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.Info,
                                contentDescription = null
                            )
                        }
                    )
                    DropdownMenuItem(
                        text = { Text("Runtime") },
                        onClick = {
                            showMenu = false
                            onRuntimeClick()
                        },
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.PlayArrow,
                                contentDescription = null
                            )
                        }
                    )
                    DropdownMenuItem(
                        text = { Text("Users") },
                        onClick = {
                            showMenu = false
                            onUsersClick()
                        },
                        leadingIcon = {
                            Icon(
                                imageVector = Icons.Default.Person,
                                contentDescription = null
                            )
                        }
                    )
                }
            }
        },
        colors = TopAppBarDefaults.topAppBarColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer,
            titleContentColor = MaterialTheme.colorScheme.onPrimaryContainer
        )
    )
}

/**
 * Navigation screens
 */
private sealed class Screen {
    object Startup : Screen()
    object Login : Screen()
    object Setup : Screen()
    object Interact : Screen()
    object Settings : Screen()
    object Billing : Screen()
    object Telemetry : Screen()
    object Sessions : Screen()
    object Adapters : Screen()
    object WiseAuthority : Screen()
    object Services : Screen()
    object Audit : Screen()
    object Logs : Screen()
    object Memory : Screen()
    object GraphMemory : Screen()
    object Config : Screen()
    object Consent : Screen()
    object System : Screen()
    object Runtime : Screen()
    object Users : Screen()
}
