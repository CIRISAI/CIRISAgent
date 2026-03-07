package ai.ciris.mobile.shared
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.TestAutomation
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable

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
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
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
 * Callback interface for Play Integrity / App Attest device attestation.
 * Android implements with Google Play Integrity API.
 * iOS implements with App Attest (placeholder).
 */
interface DeviceAttestationCallback {
    /**
     * Request device attestation.
     * @param onResult Callback with attestation result
     */
    fun onDeviceAttestationRequested(onResult: (DeviceAttestationResult) -> Unit)
}

/**
 * Result of device attestation (Play Integrity on Android, App Attest on iOS)
 */
sealed class DeviceAttestationResult {
    data class Success(
        val verified: Boolean,
        val verdict: String,  // e.g., "MEETS_STRONG_INTEGRITY", "MEETS_DEVICE_INTEGRITY"
        val meetsStrongIntegrity: Boolean = false,
        val meetsDeviceIntegrity: Boolean = false,
        val meetsBasicIntegrity: Boolean = false
    ) : DeviceAttestationResult()

    data class Error(val message: String) : DeviceAttestationResult()
    object NotSupported : DeviceAttestationResult()
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
    deviceAttestationCallback: DeviceAttestationCallback? = null,
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

    // Track screen changes for test automation
    LaunchedEffect(currentScreen) {
        TestAutomation.setCurrentScreen(currentScreen::class.simpleName ?: "unknown")
    }

    // First-run detection state
    var isFirstRun by remember { mutableStateOf<Boolean?>(null) }
    var checkingFirstRun by remember { mutableStateOf(false) }

    // Flag to skip token re-validation after setup (we just authenticated)
    var justCompletedSetup by remember { mutableStateOf(false) }

    // Login state
    var isLoginLoading by remember { mutableStateOf(false) }
    var loginStatusMessage by remember { mutableStateOf<String?>(null) }
    var loginErrorMessage by remember { mutableStateOf<String?>(null) }

    // OAuth auth state for token exchange after setup (works for both Google and Apple)
    var pendingIdToken by remember { mutableStateOf<String?>(null) }
    var pendingUserId by remember { mutableStateOf<String?>(null) }
    var pendingProvider by remember { mutableStateOf("apple") } // Default to apple on iOS

    // Token Manager for handling token refresh
    val tokenManager = remember {
        TokenManager(coroutineScope).also { TokenManager.setShared(it) }
    }

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
                PlatformLogger.i(TAG, " OAuth ID token refreshed by TokenManager (provider=$provider), exchanging for CIRIS token")
                tokenExchangeComplete = false
                coroutineScope.launch {
                    try {
                        // Exchange OAuth ID token for CIRIS access token using correct provider
                        val authResponse = apiClient.nativeAuth(idToken, null, provider)
                        val cirisToken = authResponse.access_token
                        PlatformLogger.i(TAG, " Got CIRIS access token: ${cirisToken.take(8)}...${cirisToken.takeLast(4)}")

                        // Set the CIRIS token on the API client
                        apiClient.setAccessToken(cirisToken)
                        onTokenUpdated?.invoke(cirisToken) // Notify MainActivity for BillingManager
                        currentAccessToken = cirisToken
                        apiClient.logTokenState() // Debug: confirm token was set

                        // Save CIRIS token to secure storage (not the Google ID token!)
                        secureStorage.saveAccessToken(cirisToken)
                            .onSuccess { PlatformLogger.i(TAG, " Refreshed CIRIS token saved to secure storage") }
                            .onFailure { e -> PlatformLogger.w(TAG, " Failed to save refreshed CIRIS token: ${e.message}") }

                        // Update .env file with fresh OAuth ID token for billing
                        PlatformLogger.i(TAG, " Writing OAuth ID token to .env for Python billing...")
                        envFileUpdater.updateEnvWithToken(idToken)
                            .onSuccess { updated ->
                                if (updated) PlatformLogger.i(TAG, " .env updated, .config_reload signal written")
                            }
                            .onFailure { e -> PlatformLogger.e(TAG, " Failed to update .env: ${e.message}") }

                        // Wait for Python to detect .config_reload and reload .env
                        // ResourceMonitor checks every 1 second, so 1.5s should be sufficient
                        PlatformLogger.i(TAG, " Waiting 1.5s for Python to reload billing token...")
                        kotlinx.coroutines.delay(1500)
                        PlatformLogger.i(TAG, " Python reload wait complete")

                        tokenExchangeComplete = true
                    } catch (e: Exception) {
                        PlatformLogger.e(TAG, " Failed to exchange refreshed OAuth token: ${e::class.simpleName}: ${e.message}")
                        tokenExchangeComplete = true // Mark complete even on failure to unblock waiting code
                        // On failure, the user may need to re-authenticate
                    }
                }
            }
        }
    }

    // Monitor .token_refresh_needed signal from Python billing provider
    // Polls every 10 seconds (matches old Android TokenRefreshManager)
    LaunchedEffect(Unit) {
        while (true) {
            kotlinx.coroutines.delay(10_000)
            if (envFileUpdater.checkTokenRefreshSignal()) {
                PlatformLogger.i(TAG, "Token refresh signal detected from Python - triggering silent refresh")
                tokenManager.on401Error()
            }
        }
    }

    // ViewModels
    // Cast to PythonRuntimeProtocol since actual implementations implement it
    val pythonRuntimeProtocol: PythonRuntimeProtocol = pythonRuntime as PythonRuntimeProtocol
    val startupViewModel: StartupViewModel = viewModel {
        StartupViewModel(pythonRuntimeProtocol, apiClient)
    }
    // SetupViewModel needs to survive configuration changes and app backgrounding
    val setupViewModel: SetupViewModel = viewModel { SetupViewModel() }
    val interactViewModel: InteractViewModel = viewModel {
        InteractViewModel(apiClient)
    }
    // Set device attestation callback so InteractViewModel can trigger Play Integrity at startup
    interactViewModel.setDeviceAttestationCallback(deviceAttestationCallback)
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
                    PlatformLogger.i(TAG, " Purchase success: creditsAdded=${result.creditsAdded}, newBalance=${result.newBalance}")
                    billingViewModel.onPurchaseSuccess(result.creditsAdded, result.newBalance)
                }
                is PurchaseResultType.Error -> {
                    PlatformLogger.e(TAG, " Purchase error: ${result.message}")
                    billingViewModel.onPurchaseError(result.message)
                }
                PurchaseResultType.Cancelled -> {
                    PlatformLogger.i(TAG, " Purchase cancelled")
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
                                    PlatformLogger.i(TAG, " Token was refreshed, waiting for CIRIS token exchange...")
                                    var waitCount = 0
                                    while (!tokenExchangeComplete && waitCount < 50) {
                                        kotlinx.coroutines.delay(100)
                                        waitCount++
                                    }
                                    if (tokenExchangeComplete) {
                                        PlatformLogger.i(TAG, " Token exchange completed")
                                    } else {
                                        PlatformLogger.w(TAG, " Token exchange timed out")
                                    }
                                } else {
                                    // Token was valid without refresh - use the stored CIRIS token directly
                                    PlatformLogger.i(TAG, " Stored token is valid, setting on API client")
                                    apiClient.setAccessToken(storedToken)
                                    onTokenUpdated?.invoke(storedToken) // Notify MainActivity for BillingManager
                                    currentAccessToken = storedToken
                                    apiClient.logTokenState() // Debug: confirm token was set
                                }

                                // Trigger data loading now that we have auth
                                PlatformLogger.i(TAG, " Triggering data load for ViewModels after token set")
                                billingViewModel.loadBalance()
                                adaptersViewModel.fetchAdapters()
                                interactViewModel.startPolling() // Start polling now that token is set

                                // Run CIRISVerify attestation at boot (not first run)
                                launch(kotlinx.coroutines.Dispatchers.IO) {
                                    try {
                                        PlatformLogger.i(TAG, " Running boot-time attestation check...")
                                        val verifyResult = apiClient.getVerifyStatus()
                                        PlatformLogger.i(TAG, " Boot attestation: loaded=${verifyResult.loaded}, maxLevel=${verifyResult.maxLevel}, " +
                                            "dns_us=${verifyResult.dnsUsOk}, dns_eu=${verifyResult.dnsEuOk}, https=${verifyResult.httpsUsOk}")
                                    } catch (e: Exception) {
                                        PlatformLogger.w(TAG, " Boot attestation failed: ${e.message}")
                                    }
                                }

                                currentScreen = Screen.Interact
                            } else {
                                // Token invalid and couldn't refresh - need interactive login
                                PlatformLogger.i(TAG, " Token invalid/expired and silent refresh failed - redirecting to login")
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
                platformLog(TAG, "[DEBUG][Screen.Login] Rendering login screen, googleSignInCallback=${if (googleSignInCallback != null) "PRESENT" else "NULL"}, isFirstRun=$isFirstRun")

                // On desktop during FIRST RUN ONLY, auto-trigger setup since OAuth is not available
                // For existing users (isFirstRun=false), show the login screen to enter admin credentials
                LaunchedEffect(googleSignInCallback, isFirstRun) {
                    if (googleSignInCallback == null && isFirstRun == true) {
                        platformLog(TAG, "[INFO][Screen.Login] Desktop first-run detected (no OAuth) - going to setup")
                        setupViewModel.setGoogleAuthState(
                            isAuth = false,
                            idToken = null,
                            email = null,
                            userId = null
                        )
                        currentScreen = Screen.Setup
                    } else if (googleSignInCallback == null && isFirstRun == false) {
                        platformLog(TAG, "[INFO][Screen.Login] Desktop existing user - showing local login form")
                        // Stay on login screen - user needs to enter admin credentials
                    }
                }

                LoginScreen(
                    onGoogleSignIn = {
                        platformLog(TAG, "[INFO][onGoogleSignIn] Button click handler invoked, googleSignInCallback=${if (googleSignInCallback != null) "PRESENT" else "NULL"}")
                        if (googleSignInCallback != null) {
                            // Use platform-specific Google sign-in
                            platformLog(TAG, "[INFO][onGoogleSignIn] Callback is not null, calling onGoogleSignInRequested...")
                            isLoginLoading = true
                            loginStatusMessage = "Signing in with ${getOAuthProviderName()}..."
                            loginErrorMessage = null

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
                                                        .onSuccess { PlatformLogger.i(TAG, " CIRIS token saved to secure storage") }
                                                        .onFailure { e -> PlatformLogger.w(TAG, " Failed to save token: ${e.message}") }

                                                    // Update .env file with fresh OAuth ID token for billing
                                                    PlatformLogger.i(TAG, " Writing OAuth ID token to .env for Python billing...")
                                                    envFileUpdater.updateEnvWithToken(result.idToken)
                                                        .onSuccess { updated ->
                                                            if (updated) PlatformLogger.i(TAG, " .env updated, .config_reload signal written")
                                                        }
                                                        .onFailure { e -> PlatformLogger.e(TAG, " Failed to update .env: ${e.message}") }

                                                    // Wait for Python to detect .config_reload and reload .env
                                                    PlatformLogger.i(TAG, " Waiting 1.5s for Python to reload billing token...")
                                                    kotlinx.coroutines.delay(1500)
                                                    PlatformLogger.i(TAG, " Python reload wait complete")

                                                    // Handle new token with TokenManager for periodic refresh
                                                    tokenManager.handleNewToken(result.idToken, result.provider)

                                                    // Trigger data loading
                                                    PlatformLogger.i(TAG, " Triggering billingViewModel.loadBalance()...")
                                                    billingViewModel.loadBalance()
                                                    adaptersViewModel.fetchAdapters()
                                                    interactViewModel.startPolling() // Start polling now that token is set

                                                    platformLog(TAG, "[INFO] Navigating to Screen.Interact")
                                                    currentScreen = Screen.Interact
                                                } catch (e: Exception) {
                                                    platformLog(TAG, "[ERROR] Token exchange failed: ${e::class.simpleName}: ${e.message}")
                                                    loginErrorMessage = "Token exchange failed: ${e.message}"
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
                                        loginErrorMessage = "Sign-in failed: ${result.message}"
                                    }
                                    NativeSignInResult.Cancelled -> {
                                        // User cancelled, stay on login screen
                                    }
                                }
                            }
                        } else {
                            // No callback provided - show error
                            platformLog(TAG, "[ERROR][onGoogleSignIn] googleSignInCallback is NULL - cannot invoke native sign-in!")
                            loginErrorMessage = "${getOAuthProviderName()} Sign-In not available"
                        }
                    },
                    onLocalLogin = {
                        // First run - go to setup wizard for BYOK setup
                        platformLog(TAG, "[INFO][onLocalLogin] First run - going to setup for BYOK")
                        loginErrorMessage = null
                        setupViewModel.setGoogleAuthState(
                            isAuth = false,
                            idToken = null,
                            email = null,
                            userId = null
                        )
                        currentScreen = Screen.Setup
                    },
                    onLocalLoginSubmit = { username, password ->
                        // Handle local login form submission
                        platformLog(TAG, "[INFO][onLocalLoginSubmit] Logging in with username: $username")
                        isLoginLoading = true
                        loginStatusMessage = "Logging in..."
                        loginErrorMessage = null

                        coroutineScope.launch {
                            try {
                                val cirisToken = withContext(Dispatchers.IO) {
                                    val authResponse = apiClient.login(username, password)
                                    authResponse.access_token
                                }

                                platformLog(TAG, "[INFO] Got CIRIS access token: ${cirisToken.take(8)}...${cirisToken.takeLast(4)}")

                                // Set the token on the API client
                                apiClient.setAccessToken(cirisToken)
                                currentAccessToken = cirisToken
                                apiClient.logTokenState()

                                // Save to secure storage
                                secureStorage.saveAccessToken(cirisToken)
                                    .onSuccess { PlatformLogger.i(TAG, " CIRIS token saved to secure storage") }
                                    .onFailure { e -> PlatformLogger.w(TAG, " Failed to save token: ${e.message}") }

                                // Trigger data loading
                                PlatformLogger.i(TAG, " Local login successful, triggering data load...")
                                billingViewModel.loadBalance()
                                adaptersViewModel.fetchAdapters()
                                interactViewModel.startPolling()

                                isLoginLoading = false
                                loginStatusMessage = null
                                currentScreen = Screen.Interact
                            } catch (e: Exception) {
                                platformLog(TAG, "[ERROR] Local login failed: ${e::class.simpleName}: ${e.message}")
                                isLoginLoading = false
                                loginStatusMessage = null
                                loginErrorMessage = "Login failed: ${e.message}"
                            }
                        }
                    },
                    isLoading = isLoginLoading,
                    statusMessage = loginStatusMessage,
                    errorMessage = loginErrorMessage,
                    showLocalLoginForm = (googleSignInCallback == null && isFirstRun == false),
                    isFirstRun = isFirstRun ?: true
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
                        // Run on IO dispatcher to avoid blocking main thread during network/file operations
                        coroutineScope.launch {
                            try {
                                val idToken = pendingIdToken
                                val userId = pendingUserId
                                val provider = pendingProvider

                                if (idToken != null) {
                                    // Network and file operations on IO dispatcher
                                    val cirisToken = withContext(Dispatchers.IO) {
                                        PlatformLogger.i(TAG, " Exchanging OAuth ID token for CIRIS access token (provider=$provider)")
                                        val authResponse = apiClient.nativeAuth(idToken, userId, provider)
                                        val token = authResponse.access_token
                                        PlatformLogger.i(TAG, " Got CIRIS access token: ${token.take(8)}...${token.takeLast(4)}")

                                        // Store token for future sessions
                                        secureStorage.saveAccessToken(token)
                                            .onSuccess { PlatformLogger.i(TAG, " Token saved to secure storage") }
                                            .onFailure { e -> PlatformLogger.w(TAG, " Failed to save token to secure storage: ${e.message}") }

                                        // Update .env file with fresh OAuth ID token for billing
                                        PlatformLogger.i(TAG, " Writing OAuth ID token to .env for Python billing...")
                                        envFileUpdater.updateEnvWithToken(idToken)
                                            .onSuccess { updated ->
                                                if (updated) PlatformLogger.i(TAG, " .env updated, .config_reload signal written")
                                            }
                                            .onFailure { e -> PlatformLogger.e(TAG, " Failed to update .env: ${e.message}") }

                                        token
                                    }

                                    // UI updates on main thread
                                    apiClient.setAccessToken(cirisToken)
                                    onTokenUpdated?.invoke(cirisToken) // Notify MainActivity for BillingManager
                                    currentAccessToken = cirisToken
                                    apiClient.logTokenState() // Debug: confirm token was set

                                    // Wait for Python to detect .config_reload and reload .env
                                    PlatformLogger.i(TAG, " Waiting 1.5s for Python to reload billing token...")
                                    kotlinx.coroutines.delay(1500)
                                    PlatformLogger.i(TAG, " Python reload wait complete")

                                    // Trigger data loading now that we have auth AND Python has reloaded
                                    PlatformLogger.i(TAG, " Triggering billingViewModel.loadBalance()...")
                                    billingViewModel.loadBalance()
                                    adaptersViewModel.fetchAdapters()

                                    // Clear pending tokens
                                    pendingIdToken = null
                                    pendingUserId = null
                                } else {
                                    PlatformLogger.i(TAG, " No pending OAuth token, using local auth")
                                    // For local login, authenticate with the admin credentials from setup
                                    val setupState = setupViewModel.state.value
                                    val username = setupState.username.ifEmpty { "admin" }
                                    val password = setupState.userPassword

                                    if (password.isNotEmpty()) {
                                        PlatformLogger.i(TAG, " Logging in with local credentials: $username")
                                        val cirisToken = withContext(Dispatchers.IO) {
                                            val authResponse = apiClient.login(username, password)
                                            val token = authResponse.access_token
                                            PlatformLogger.i(TAG, " Got CIRIS access token: ${token.take(8)}...${token.takeLast(4)}")

                                            // Store token for future sessions
                                            secureStorage.saveAccessToken(token)
                                                .onSuccess { PlatformLogger.i(TAG, " Token saved to secure storage") }
                                                .onFailure { e -> PlatformLogger.w(TAG, " Failed to save token to secure storage: ${e.message}") }

                                            token
                                        }

                                        // UI updates on main thread
                                        apiClient.setAccessToken(cirisToken)
                                        currentAccessToken = cirisToken
                                        apiClient.logTokenState()
                                    } else {
                                        PlatformLogger.w(TAG, " No password set for local user, skipping auto-login")
                                    }
                                }
                            } catch (e: Exception) {
                                PlatformLogger.e(TAG, " Token exchange failed: ${e::class.simpleName}: ${e.message}")
                                PlatformLogger.e(TAG, " Stack trace: ${e.stackTraceToString().take(500)}")
                            }

                            // After setup completes, Python resumes and starts remaining 12 services
                            // Go back to StartupScreen to show the remaining services starting
                            // Reset the startup phase so it re-polls for services
                            startupViewModel.resetForResume()
                            checkingFirstRun = false  // Allow re-check after startup completes
                            justCompletedSetup = true  // Skip token re-validation since we just authenticated
                            currentScreen = Screen.Startup
                        }
                    },
                    onBackToLogin = {
                        platformLog(TAG, "[INFO] Back to login from setup wizard")
                        setupViewModel.resetState()  // Clear any partial setup state
                        currentScreen = Screen.Login
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
                        onOpenTrustPage = {
                            platformLog(TAG, "[INFO] Opening Trust page")
                            currentScreen = Screen.Trust
                        },
                        onOpenBilling = {
                            platformLog(TAG, "[INFO] Opening Billing page from credits")
                            currentScreen = Screen.Billing
                        },
                        modifier = Modifier.padding(top = paddingValues.calculateTopPadding())
                    )
                }
            }

            Screen.Settings -> {
                SettingsScreen(
                    viewModel = settingsViewModel,
                    apiClient = apiClient,
                    onNavigateBack = { currentScreen = Screen.Interact },
                    onLogout = {
                        PlatformLogger.i("CIRISApp", "[onLogout] User initiated logout")
                        settingsViewModel.logout {
                            PlatformLogger.i("CIRISApp", "[onLogout] Logout complete, navigating to Startup")
                            currentScreen = Screen.Startup
                        }
                    },
                    onResetSetup = {
                        PlatformLogger.i("CIRISApp", "[onResetSetup] Setup reset requested, restarting app...")
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
                    PlatformLogger.i(TAG, "[Screen.Billing] Loading balance on screen entry")
                    billingViewModel.loadBalance()
                }

                PlatformLogger.d("CIRISApp", "[Screen.Billing] Rendering billing screen: " +
                        "balance=$currentBalance, products=${products.size}, " +
                        "isByok=$isByokMode, isLoading=$isBillingLoading")

                // Display snackbar for error/success messages
                LaunchedEffect(billingError) {
                    if (billingError != null) {
                        PlatformLogger.w("CIRISApp", "[Screen.Billing] Error: $billingError")
                    }
                }
                LaunchedEffect(billingSuccess) {
                    if (billingSuccess != null) {
                        PlatformLogger.i("CIRISApp", "[Screen.Billing] Success: $billingSuccess")
                    }
                }

                BillingScreen(
                    currentBalance = currentBalance,
                    products = products,
                    isLoading = isBillingLoading,
                    errorMessage = billingError,
                    onProductClick = { product ->
                        PlatformLogger.i("CIRISApp", "[Screen.Billing] Product clicked: ${product.productId}")
                        billingViewModel.onProductSelected(product) { selectedProduct ->
                            PlatformLogger.i("CIRISApp", "[Screen.Billing] Launching purchase for: ${selectedProduct.productId}")
                            if (purchaseLauncher != null) {
                                billingViewModel.onPurchaseStarted(selectedProduct.productId)
                                purchaseLauncher.launchPurchase(selectedProduct.productId)
                            } else {
                                PlatformLogger.w("CIRISApp", "[Screen.Billing] No purchase launcher available")
                                billingViewModel.onPurchaseError("In-app purchases not available on this platform")
                            }
                        }
                    },
                    onRefresh = {
                        PlatformLogger.i("CIRISApp", "[Screen.Billing] User triggered refresh")
                        billingViewModel.refresh()
                    },
                    onNavigateBack = {
                        PlatformLogger.i("CIRISApp", "[Screen.Billing] Navigating back to Interact")
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
                    PlatformLogger.i(TAG, "[Screen.Telemetry] Starting telemetry polling")
                    telemetryViewModel.startPolling()
                    onDispose {
                        PlatformLogger.i(TAG, "[Screen.Telemetry] Stopping telemetry polling")
                        telemetryViewModel.stopPolling()
                    }
                }

                PlatformLogger.d("CIRISApp", "[Screen.Telemetry] Rendering telemetry screen: " +
                        "services=${telemetryData.healthyServices}/${telemetryData.totalServices}, " +
                        "state=${telemetryData.cognitiveState}, isLoading=$isTelemetryLoading")

                TelemetryScreen(
                    telemetryData = telemetryData,
                    isLoading = isTelemetryLoading,
                    onRefresh = {
                        PlatformLogger.i("CIRISApp", "[Screen.Telemetry] User triggered refresh")
                        telemetryViewModel.refresh()
                    },
                    onNavigateBack = {
                        PlatformLogger.i("CIRISApp", "[Screen.Telemetry] Navigating back to Interact")
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
                    PlatformLogger.i(TAG, "[Screen.Sessions] Starting sessions polling")
                    sessionsViewModel.startPolling()
                    onDispose {
                        PlatformLogger.i(TAG, "[Screen.Sessions] Stopping sessions polling")
                        sessionsViewModel.stopPolling()
                    }
                }

                PlatformLogger.d("CIRISApp", "[Screen.Sessions] Rendering sessions screen: " +
                        "state=$currentCognitiveState, isLoading=$isSessionsLoading, " +
                        "isTransitioning=$isTransitioning")

                // Log status/error messages
                LaunchedEffect(sessionStatusMessage) {
                    if (sessionStatusMessage != null) {
                        PlatformLogger.i("CIRISApp", "[Screen.Sessions] Status: $sessionStatusMessage")
                    }
                }
                LaunchedEffect(sessionErrorMessage) {
                    if (sessionErrorMessage != null) {
                        PlatformLogger.w("CIRISApp", "[Screen.Sessions] Error: $sessionErrorMessage")
                    }
                }

                SessionsScreen(
                    currentState = currentCognitiveState,
                    isLoading = isSessionsLoading || isTransitioning,
                    onInitiateSession = { targetState ->
                        PlatformLogger.i("CIRISApp", "[Screen.Sessions] Initiating session transition: $currentCognitiveState -> $targetState")
                        sessionsViewModel.initiateSession(targetState)
                    },
                    onRefresh = {
                        PlatformLogger.i("CIRISApp", "[Screen.Sessions] User triggered refresh")
                        sessionsViewModel.refresh()
                    },
                    onNavigateBack = {
                        PlatformLogger.i("CIRISApp", "[Screen.Sessions] Navigating back to Interact")
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
                val loadableAdapters by adaptersViewModel.loadableAdapters.collectAsState()
                val wizardSession by adaptersViewModel.wizardSession.collectAsState()
                val wizardError by adaptersViewModel.wizardError.collectAsState()
                val wizardLoading by adaptersViewModel.wizardLoading.collectAsState()
                val discoveredItems by adaptersViewModel.discoveredItems.collectAsState()
                val discoveryExecuted by adaptersViewModel.discoveryExecuted.collectAsState()

                PlatformLogger.d("CIRISApp", "[Screen.Adapters] Rendering adapters screen: " +
                        "adapters=${adaptersList.size}, connected=$isAdaptersConnected, " +
                        "isLoading=$isAdaptersLoading, operationInProgress=$adaptersOperationInProgress")

                // Start polling when screen is visible
                DisposableEffect(Unit) {
                    PlatformLogger.i("CIRISApp", "[Screen.Adapters] Starting adapter polling")
                    adaptersViewModel.startPolling()
                    onDispose {
                        PlatformLogger.i("CIRISApp", "[Screen.Adapters] Stopping adapter polling")
                        adaptersViewModel.stopPolling()
                    }
                }

                // Log status messages
                LaunchedEffect(adaptersStatusMessage) {
                    if (adaptersStatusMessage != null) {
                        PlatformLogger.i("CIRISApp", "[Screen.Adapters] Status: $adaptersStatusMessage")
                    }
                }

                AdaptersScreen(
                    adapters = adaptersList,
                    isConnected = isAdaptersConnected,
                    isLoading = isAdaptersLoading || adaptersOperationInProgress,
                    onReloadAdapter = { adapterId ->
                        PlatformLogger.i("CIRISApp", "[Screen.Adapters] Reloading adapter: $adapterId")
                        adaptersViewModel.reloadAdapter(adapterId)
                    },
                    onRemoveAdapter = { adapterId ->
                        PlatformLogger.i("CIRISApp", "[Screen.Adapters] Removing adapter: $adapterId")
                        adaptersViewModel.removeAdapter(adapterId)
                    },
                    onAddAdapter = {
                        PlatformLogger.i("CIRISApp", "[Screen.Adapters] Add adapter requested")
                        adaptersViewModel.addAdapter()
                    },
                    onRefresh = {
                        PlatformLogger.i("CIRISApp", "[Screen.Adapters] User triggered refresh")
                        adaptersViewModel.refresh()
                    },
                    onNavigateBack = {
                        PlatformLogger.i("CIRISApp", "[Screen.Adapters] Navigating back to Interact")
                        currentScreen = Screen.Interact
                    }
                )

                // Adapter wizard dialog - show when dialog is open OR when there's an error to display
                val currentOauthUrl by adaptersViewModel.oauthUrl.collectAsState()
                val awaitingOAuthCallback by adaptersViewModel.awaitingOAuthCallback.collectAsState()
                val selectOptions by adaptersViewModel.selectOptions.collectAsState()

                if (showWizardDialog || wizardError != null) {
                    AdapterWizardDialog(
                        loadableAdapters = loadableAdapters,
                        wizardSession = wizardSession,
                        isLoading = wizardLoading,
                        error = wizardError,
                        discoveredItems = discoveredItems,
                        discoveryExecuted = discoveryExecuted,
                        oauthUrl = currentOauthUrl,
                        awaitingOAuthCallback = awaitingOAuthCallback,
                        selectOptions = selectOptions,
                        onSelectType = { adapterType ->
                            PlatformLogger.i("CIRISApp", "[AdapterWizard] Selected type: $adapterType")
                            adaptersViewModel.startWizard(adapterType)
                        },
                        onLoadDirectly = { adapterType ->
                            PlatformLogger.i("CIRISApp", "[AdapterWizard] Loading directly: $adapterType")
                            adaptersViewModel.loadAdapterDirectly(adapterType)
                        },
                        onSubmitStep = { stepData ->
                            PlatformLogger.i("CIRISApp", "[AdapterWizard] Submitting step with ${stepData.size} fields")
                            adaptersViewModel.submitWizardStep(stepData)
                        },
                        onSelectDiscoveredItem = { item ->
                            PlatformLogger.i("CIRISApp", "[AdapterWizard] Selected discovered item: ${item.label}")
                            adaptersViewModel.selectDiscoveredItem(item)
                        },
                        onSubmitManualUrl = { url ->
                            PlatformLogger.i("CIRISApp", "[AdapterWizard] Submitting manual URL: $url")
                            adaptersViewModel.submitManualUrl(url)
                        },
                        onRetryDiscovery = {
                            PlatformLogger.i("CIRISApp", "[AdapterWizard] Retrying discovery")
                            adaptersViewModel.executeDiscoveryStep()
                        },
                        onInitiateOAuth = {
                            PlatformLogger.i("CIRISApp", "[AdapterWizard] Initiating OAuth")
                            adaptersViewModel.initiateOAuthStep()
                        },
                        onCheckOAuthStatus = {
                            adaptersViewModel.checkOAuthOnResume()
                        },
                        onBack = {
                            PlatformLogger.i("CIRISApp", "[AdapterWizard] Back pressed")
                            adaptersViewModel.wizardBack()
                        },
                        onDismiss = {
                            PlatformLogger.i("CIRISApp", "[AdapterWizard] Dialog dismissed")
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
                    PlatformLogger.i(TAG, "[Screen.WiseAuthority] Starting WA polling")
                    wiseAuthorityViewModel.startPolling()
                    onDispose {
                        PlatformLogger.i(TAG, "[Screen.WiseAuthority] Stopping WA polling")
                        wiseAuthorityViewModel.stopPolling()
                    }
                }

                PlatformLogger.d("CIRISApp", "[Screen.WiseAuthority] Rendering WA screen: " +
                        "status=${waStatus?.serviceHealthy}, deferrals=${deferrals.size}, " +
                        "isLoading=$isWALoading, isResolving=$isResolving")

                // Log status/error messages
                LaunchedEffect(waError) {
                    if (waError != null) {
                        PlatformLogger.w("CIRISApp", "[Screen.WiseAuthority] Error: $waError")
                    }
                }
                LaunchedEffect(waSuccess) {
                    if (waSuccess != null) {
                        PlatformLogger.i("CIRISApp", "[Screen.WiseAuthority] Success: $waSuccess")
                        wiseAuthorityViewModel.clearSuccess()
                    }
                }

                WiseAuthorityScreen(
                    waStatus = waStatus,
                    deferrals = deferrals,
                    isLoading = isWALoading,
                    isResolving = isResolving,
                    onResolveDeferral = { deferralId, resolution, guidance ->
                        PlatformLogger.i("CIRISApp", "[Screen.WiseAuthority] Resolving deferral: $deferralId -> $resolution")
                        wiseAuthorityViewModel.resolveDeferral(deferralId, resolution, guidance)
                    },
                    onRefresh = {
                        PlatformLogger.i("CIRISApp", "[Screen.WiseAuthority] User triggered refresh")
                        wiseAuthorityViewModel.refresh()
                    },
                    onNavigateBack = {
                        PlatformLogger.i("CIRISApp", "[Screen.WiseAuthority] Navigating back to Interact")
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
                    PlatformLogger.i(TAG, "[Screen.Services] Starting services polling")
                    servicesViewModel.startPolling()
                    onDispose {
                        PlatformLogger.i(TAG, "[Screen.Services] Stopping services polling")
                        servicesViewModel.stopPolling()
                    }
                }

                LaunchedEffect(servicesError) {
                    servicesError?.let { error ->
                        PlatformLogger.e(TAG, "[Screen.Services] Services error: $error")
                    }
                }

                PlatformLogger.d("CIRISApp", "[Screen.Services] Rendering services screen: " +
                        "total=${servicesData.totalServices}, healthy=${servicesData.healthyServices}, " +
                        "isLoading=$isServicesLoading")

                ServicesScreen(
                    servicesData = servicesData,
                    isLoading = isServicesLoading,
                    onRefresh = {
                        PlatformLogger.i("CIRISApp", "[Screen.Services] User triggered refresh")
                        servicesViewModel.refresh()
                    },
                    onDiagnose = {
                        PlatformLogger.i("CIRISApp", "[Screen.Services] User triggered diagnose")
                        servicesViewModel.runDiagnostics()
                    },
                    onResetCircuitBreakers = { serviceType ->
                        PlatformLogger.i("CIRISApp", "[Screen.Services] Reset circuit breakers: $serviceType")
                        servicesViewModel.resetCircuitBreakers(serviceType)
                    },
                    onNavigateBack = {
                        PlatformLogger.i("CIRISApp", "[Screen.Services] Navigating back to Interact")
                        currentScreen = Screen.Interact
                    }
                )
            }

            Screen.Audit -> {
                val auditState by auditViewModel.state.collectAsState()

                // Start/stop polling based on screen visibility
                DisposableEffect(Unit) {
                    PlatformLogger.i(TAG, "[Screen.Audit] Starting audit polling")
                    auditViewModel.startPolling()
                    onDispose {
                        PlatformLogger.i(TAG, "[Screen.Audit] Stopping audit polling")
                        auditViewModel.stopPolling()
                    }
                }

                LaunchedEffect(auditState.error) {
                    auditState.error?.let { error ->
                        PlatformLogger.e(TAG, "[Screen.Audit] Audit error: $error")
                    }
                }

                PlatformLogger.d("CIRISApp", "[Screen.Audit] Rendering audit screen: " +
                        "entries=${auditState.entries.size}, total=${auditState.totalEntries}, " +
                        "isLoading=${auditState.isLoading}, error=${auditState.error}")

                AuditScreen(
                    auditState = auditState,
                    onRefresh = {
                        PlatformLogger.i("CIRISApp", "[Screen.Audit] User triggered refresh")
                        auditViewModel.refresh()
                    },
                    onLoadMore = {
                        PlatformLogger.i("CIRISApp", "[Screen.Audit] Load more requested")
                        auditViewModel.loadMore()
                    },
                    onFilterChange = { filter ->
                        PlatformLogger.i("CIRISApp", "[Screen.Audit] Filter changed: $filter")
                        auditViewModel.updateFilter(filter)
                    },
                    onNavigateBack = { currentScreen = Screen.Interact }
                )
            }

            Screen.Logs -> {
                val logsState by logsViewModel.state.collectAsState()

                // Start/stop polling based on screen visibility
                DisposableEffect(Unit) {
                    PlatformLogger.i(TAG, "[Screen.Logs] Starting logs polling")
                    logsViewModel.startPolling()
                    onDispose {
                        PlatformLogger.i(TAG, "[Screen.Logs] Stopping logs polling")
                        logsViewModel.stopPolling()
                    }
                }

                LaunchedEffect(logsState.error) {
                    logsState.error?.let { error ->
                        PlatformLogger.e(TAG, "[Screen.Logs] Logs error: $error")
                    }
                }

                PlatformLogger.d("CIRISApp", "[Screen.Logs] Rendering logs screen: " +
                        "logs=${logsState.logs.size}, isLoading=${logsState.isLoading}, error=${logsState.error}")

                LogsScreen(
                    logsState = logsState,
                    onRefresh = {
                        PlatformLogger.i("CIRISApp", "[Screen.Logs] User triggered refresh")
                        logsViewModel.refresh()
                    },
                    onFilterChange = { filter ->
                        PlatformLogger.i("CIRISApp", "[Screen.Logs] Filter changed: $filter")
                        logsViewModel.updateFilter(filter)
                    },
                    onSearchChange = { query ->
                        PlatformLogger.i("CIRISApp", "[Screen.Logs] Search changed: $query")
                        logsViewModel.updateSearch(query)
                    },
                    onToggleAutoScroll = {
                        PlatformLogger.i("CIRISApp", "[Screen.Logs] Toggle auto-scroll")
                        logsViewModel.toggleAutoScroll()
                    },
                    onNavigateBack = { currentScreen = Screen.Interact }
                )
            }

            Screen.Memory -> {
                val memoryState by memoryViewModel.state.collectAsState()

                // Start/stop polling based on screen visibility
                DisposableEffect(Unit) {
                    PlatformLogger.i(TAG, "[Screen.Memory] Starting memory polling")
                    memoryViewModel.startPolling()
                    onDispose {
                        PlatformLogger.i(TAG, "[Screen.Memory] Stopping memory polling")
                        memoryViewModel.stopPolling()
                    }
                }

                LaunchedEffect(memoryState.error) {
                    memoryState.error?.let { error ->
                        PlatformLogger.e(TAG, "[Screen.Memory] Memory error: $error")
                    }
                }

                PlatformLogger.d("CIRISApp", "[Screen.Memory] Rendering memory screen: " +
                        "searchResults=${memoryState.searchResults.size}, timeline=${memoryState.timelineNodes.size}, " +
                        "isLoading=${memoryState.isLoading}, error=${memoryState.error}")

                MemoryScreen(
                    memoryState = memoryState,
                    onRefresh = {
                        PlatformLogger.i("CIRISApp", "[Screen.Memory] User triggered refresh")
                        memoryViewModel.refresh()
                    },
                    onSearch = { query ->
                        PlatformLogger.i("CIRISApp", "[Screen.Memory] Search: $query")
                        memoryViewModel.search(query)
                    },
                    onFilterChange = { filter ->
                        PlatformLogger.i("CIRISApp", "[Screen.Memory] Filter changed: $filter")
                        memoryViewModel.updateFilter(filter)
                    },
                    onNodeSelect = { nodeId ->
                        PlatformLogger.i("CIRISApp", "[Screen.Memory] Node selected: $nodeId")
                        memoryViewModel.selectNode(nodeId)
                    },
                    onClearSelection = {
                        PlatformLogger.i("CIRISApp", "[Screen.Memory] Clear selection")
                        memoryViewModel.clearSelection()
                    },
                    onNavigateBack = { currentScreen = Screen.Interact },
                    onSwitchToGraph = {
                        PlatformLogger.i("CIRISApp", "[Screen.Memory] Switching to graph view")
                        currentScreen = Screen.GraphMemory
                    }
                )
            }

            Screen.GraphMemory -> {
                val graphState by graphMemoryViewModel.displayState.collectAsState()
                val graphFilter by graphMemoryViewModel.filter.collectAsState()
                val graphStats by graphMemoryViewModel.stats.collectAsState()

                LaunchedEffect(Unit) {
                    PlatformLogger.i(TAG, "[Screen.GraphMemory] Loading graph data on screen entry")
                    graphMemoryViewModel.setCanvasSize(800f, 600f) // Default size, will be updated
                    graphMemoryViewModel.loadGraphData()
                }

                PlatformLogger.d("CIRISApp", "[Screen.GraphMemory] Rendering graph screen: " +
                        "nodes=${graphState.nodes.size}, edges=${graphState.edges.size}, " +
                        "isLoading=${graphState.isLoading}")

                GraphMemoryScreen(
                    state = graphState,
                    filter = graphFilter,
                    stats = graphStats,
                    onRefresh = {
                        PlatformLogger.i("CIRISApp", "[Screen.GraphMemory] User triggered refresh")
                        graphMemoryViewModel.refresh()
                    },
                    onFilterChange = { filter ->
                        PlatformLogger.i("CIRISApp", "[Screen.GraphMemory] Filter changed")
                        graphMemoryViewModel.updateFilter(filter)
                    },
                    onLayoutChange = { layout ->
                        PlatformLogger.i("CIRISApp", "[Screen.GraphMemory] Layout changed: $layout")
                        graphMemoryViewModel.changeLayout(layout)
                    },
                    onNodeSelected = { nodeId ->
                        PlatformLogger.i("CIRISApp", "[Screen.GraphMemory] Node selected: $nodeId")
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
                        PlatformLogger.i("CIRISApp", "[Screen.GraphMemory] Starting simulation")
                        graphMemoryViewModel.startSimulation()
                    },
                    onStopSimulation = {
                        PlatformLogger.i("CIRISApp", "[Screen.GraphMemory] Stopping simulation")
                        graphMemoryViewModel.stopSimulation()
                    },
                    onNavigateBack = {
                        PlatformLogger.i("CIRISApp", "[Screen.GraphMemory] Navigating back to Memory list")
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
                    PlatformLogger.i(TAG, "[Screen.Config] Starting config polling")
                    configViewModel.startPolling()
                    onDispose {
                        PlatformLogger.i(TAG, "[Screen.Config] Stopping config polling")
                        configViewModel.stopPolling()
                    }
                }

                LaunchedEffect(configError) {
                    configError?.let { error ->
                        PlatformLogger.e(TAG, "[Screen.Config] Config error: $error")
                    }
                }

                PlatformLogger.d("CIRISApp", "[Screen.Config] Rendering config screen: " +
                        "sections=${configData.sections.size}, isLoading=$isConfigLoading")

                ConfigScreen(
                    configData = configData,
                    isLoading = isConfigLoading,
                    searchQuery = configSearchQuery,
                    selectedCategory = configSelectedCategory,
                    expandedSections = configExpandedSections,
                    onSearchQueryChange = { query ->
                        PlatformLogger.i("CIRISApp", "[Screen.Config] Search changed: $query")
                        configViewModel.updateSearchQuery(query)
                    },
                    onCategorySelect = { category ->
                        PlatformLogger.i("CIRISApp", "[Screen.Config] Category selected: $category")
                        configViewModel.selectCategory(category)
                    },
                    onToggleSection = { section ->
                        PlatformLogger.i("CIRISApp", "[Screen.Config] Toggle section: $section")
                        configViewModel.toggleSection(section)
                    },
                    onUpdateConfig = { key, value ->
                        PlatformLogger.i("CIRISApp", "[Screen.Config] Update config: $key=$value")
                        configViewModel.updateConfig(key, value)
                    },
                    onDeleteConfig = { key ->
                        PlatformLogger.i("CIRISApp", "[Screen.Config] Delete config: $key")
                        configViewModel.deleteConfig(key)
                    },
                    onRefresh = {
                        PlatformLogger.i("CIRISApp", "[Screen.Config] User triggered refresh")
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
                    PlatformLogger.i(TAG, "[Screen.Consent] Starting consent polling")
                    consentViewModel.startPolling()
                    onDispose {
                        PlatformLogger.i(TAG, "[Screen.Consent] Stopping consent polling")
                        consentViewModel.stopPolling()
                    }
                }

                LaunchedEffect(consentError) {
                    consentError?.let { error ->
                        PlatformLogger.e(TAG, "[Screen.Consent] Consent error: $error")
                    }
                }

                PlatformLogger.d("CIRISApp", "[Screen.Consent] Rendering consent screen: " +
                        "streams=${consentData.availableStreams.size}, isLoading=$isConsentLoading")

                ConsentScreen(
                    consentData = consentData,
                    isLoading = isConsentLoading,
                    onStreamSelect = { streamId ->
                        PlatformLogger.i("CIRISApp", "[Screen.Consent] Stream selected: $streamId")
                        consentViewModel.changeStream(streamId)
                    },
                    onRequestPartnership = {
                        PlatformLogger.i("CIRISApp", "[Screen.Consent] Request partnership")
                        consentViewModel.requestPartnership()
                    },
                    onRefresh = {
                        PlatformLogger.i("CIRISApp", "[Screen.Consent] User triggered refresh")
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
                    PlatformLogger.i(TAG, "[Screen.System] Starting system polling")
                    systemViewModel.startPolling()
                    onDispose {
                        PlatformLogger.i(TAG, "[Screen.System] Stopping system polling")
                        systemViewModel.stopPolling()
                    }
                }

                LaunchedEffect(systemError) {
                    systemError?.let { error ->
                        PlatformLogger.e(TAG, "[Screen.System] System error: $error")
                    }
                }

                PlatformLogger.d("CIRISApp", "[Screen.System] Rendering system screen: " +
                        "health=${systemData.health}, isPaused=${systemData.isPaused}, isLoading=$isSystemLoading")

                SystemScreen(
                    systemData = systemData,
                    isLoading = isSystemLoading,
                    onPauseRuntime = {
                        PlatformLogger.i("CIRISApp", "[Screen.System] Pause runtime")
                        systemViewModel.pauseRuntime()
                    },
                    onResumeRuntime = {
                        PlatformLogger.i("CIRISApp", "[Screen.System] Resume runtime")
                        systemViewModel.resumeRuntime()
                    },
                    onRefresh = {
                        PlatformLogger.i("CIRISApp", "[Screen.System] User triggered refresh")
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
                    PlatformLogger.i(TAG, "[Screen.Runtime] Starting runtime polling")
                    runtimeViewModel.startPolling()
                    onDispose {
                        PlatformLogger.i(TAG, "[Screen.Runtime] Stopping runtime polling")
                        runtimeViewModel.stopPolling()
                    }
                }

                LaunchedEffect(runtimeError) {
                    runtimeError?.let { error ->
                        PlatformLogger.e(TAG, "[Screen.Runtime] Runtime error: $error")
                    }
                }

                PlatformLogger.d("CIRISApp", "[Screen.Runtime] Rendering runtime screen: " +
                        "processorState=${runtimeData.processorState}, cognitiveState=${runtimeData.cognitiveState}, isLoading=$isRuntimeLoading")

                RuntimeScreen(
                    runtimeData = runtimeData,
                    isLoading = isRuntimeLoading,
                    isAdmin = isRuntimeAdmin,
                    onPause = {
                        PlatformLogger.i("CIRISApp", "[Screen.Runtime] Pause runtime")
                        runtimeViewModel.pauseRuntime()
                    },
                    onResume = {
                        PlatformLogger.i("CIRISApp", "[Screen.Runtime] Resume runtime")
                        runtimeViewModel.resumeRuntime()
                    },
                    onSingleStep = {
                        PlatformLogger.i("CIRISApp", "[Screen.Runtime] Single step")
                        runtimeViewModel.singleStep()
                    },
                    onRefresh = {
                        PlatformLogger.i("CIRISApp", "[Screen.Runtime] User triggered refresh")
                        runtimeViewModel.refresh()
                    },
                    onNavigateBack = { currentScreen = Screen.Interact }
                )
            }

            Screen.Users -> {
                val usersState by usersViewModel.state.collectAsState()

                LaunchedEffect(Unit) {
                    PlatformLogger.i(TAG, "[Screen.Users] Loading users on screen entry")
                    usersViewModel.refresh()
                }

                LaunchedEffect(usersState.error) {
                    usersState.error?.let { error ->
                        PlatformLogger.e(TAG, "[Screen.Users] Users error: $error")
                    }
                }

                PlatformLogger.d("CIRISApp", "[Screen.Users] Rendering users screen: " +
                        "users=${usersState.users.size}, total=${usersState.pagination.totalItems}, " +
                        "isLoading=${usersState.isLoading}")

                UsersScreen(
                    state = usersState,
                    onRefresh = {
                        PlatformLogger.i("CIRISApp", "[Screen.Users] User triggered refresh")
                        usersViewModel.refresh()
                    },
                    onSearch = { query ->
                        PlatformLogger.i("CIRISApp", "[Screen.Users] Search: $query")
                        usersViewModel.updateSearch(query)
                    },
                    onFilterChange = { filter ->
                        PlatformLogger.i("CIRISApp", "[Screen.Users] Filter changed")
                        usersViewModel.updateFilter(filter)
                    },
                    onSelectUser = { userId ->
                        PlatformLogger.i("CIRISApp", "[Screen.Users] User selected: $userId")
                        usersViewModel.selectUser(userId)
                    },
                    onClearSelection = {
                        PlatformLogger.i("CIRISApp", "[Screen.Users] Clear selection")
                        usersViewModel.clearSelection()
                    },
                    onNextPage = {
                        PlatformLogger.i("CIRISApp", "[Screen.Users] Next page")
                        usersViewModel.nextPage()
                    },
                    onPreviousPage = {
                        PlatformLogger.i("CIRISApp", "[Screen.Users] Previous page")
                        usersViewModel.previousPage()
                    },
                    onNavigateBack = { currentScreen = Screen.Interact }
                )
            }

            Screen.Trust -> {
                TrustPage(
                    apiClient = apiClient,
                    onNavigateBack = {
                        PlatformLogger.i("CIRISApp", "[Screen.Trust] Navigating back to Interact")
                        currentScreen = Screen.Interact
                    },
                    deviceAttestationCallback = deviceAttestationCallback
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
            IconButton(
                onClick = onSettingsClick,
                modifier = Modifier.testableClickable("btn_settings") { onSettingsClick() }
            ) {
                Icon(
                    imageVector = Icons.Default.Settings,
                    contentDescription = "Settings"
                )
            }

            Box {
                IconButton(
                    onClick = { showMenu = true },
                    modifier = Modifier.testableClickable("btn_menu") { showMenu = true }
                ) {
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
                        },
                        modifier = Modifier.testableClickable("menu_adapters") {
                            showMenu = false
                            onAdaptersClick()
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
    object Trust : Screen()
}
