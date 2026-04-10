package ai.ciris.mobile.shared
import ai.ciris.mobile.shared.platform.PlatformBackHandler
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
import ai.ciris.mobile.shared.localization.CurrencyHelper
import ai.ciris.mobile.shared.localization.CurrencyManager
import ai.ciris.mobile.shared.localization.LocalCurrency
import ai.ciris.mobile.shared.localization.LocalLocalization
import ai.ciris.mobile.shared.localization.LocalizationHelper
import ai.ciris.mobile.shared.localization.LocalizationManager
import ai.ciris.mobile.shared.localization.createLocalizationResourceLoader
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.ui.components.AdapterWizardDialog
import ai.ciris.mobile.shared.ui.components.CIRISSignet
import ai.ciris.mobile.shared.ui.components.SkillImportDialog
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
import ai.ciris.mobile.shared.viewmodels.ServerConnectionViewModel
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
import ai.ciris.mobile.shared.viewmodels.TicketsViewModel
import ai.ciris.mobile.shared.viewmodels.SchedulerViewModel
import ai.ciris.mobile.shared.viewmodels.ToolsViewModel
import ai.ciris.mobile.shared.viewmodels.EnvironmentInfoViewModel
import ai.ciris.mobile.shared.viewmodels.DataManagementViewModel
import ai.ciris.mobile.shared.viewmodels.SkillImportViewModel
import ai.ciris.mobile.shared.ui.screens.graph.GraphMemoryScreen
import ai.ciris.mobile.shared.ui.theme.BrightnessPreference
import ai.ciris.mobile.shared.ui.theme.ColorTheme
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.unit.dp
import androidx.compose.ui.Alignment
import androidx.compose.ui.text.font.FontWeight
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.delay
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
import androidx.compose.material.icons.filled.ExitToApp
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
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
 * Typed purchase errors for robust error handling and retry logic.
 */
sealed class PurchaseError {
    data class AuthRequired(val message: String = "Sign in required") : PurchaseError()
    data class TokenExpired(val message: String = "Session expired") : PurchaseError()
    data class ServerError(val statusCode: Int, val message: String) : PurchaseError()
    data class NetworkError(val message: String) : PurchaseError()
    data class StoreError(val message: String) : PurchaseError()

    fun toUserMessage(): String = when (this) {
        is AuthRequired -> "Please sign in to make purchases"
        is TokenExpired -> "Session expired. Please try your purchase again."
        is ServerError -> "Server error ($statusCode). Please try again."
        is NetworkError -> "Network error. Check your connection."
        is StoreError -> message
    }
}

/**
 * Result of a purchase attempt
 */
sealed class PurchaseResultType {
    data class Success(val creditsAdded: Int, val newBalance: Int) : PurchaseResultType()
    data class Error(val message: String, val errorType: PurchaseError? = null) : PurchaseResultType()
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
    baseUrl: String = "http://127.0.0.1:8080",
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

    // Start test automation server on non-desktop platforms (desktop starts it in Main.kt)
    LaunchedEffect(Unit) {
        if (!ai.ciris.mobile.shared.platform.isDesktop() && TestAutomation.isEnabled()) {
            PlatformLogger.i(TAG, "Test mode enabled on mobile — starting test automation server")
            ai.ciris.mobile.shared.platform.startTestAutomationServer()
        }
    }

    // Initialize localization manager for runtime language switching
    val resourceLoader = remember { createLocalizationResourceLoader() }
    val localizationManager = remember {
        LocalizationManager(coroutineScope, secureStorage, resourceLoader).also {
            LocalizationHelper.setManager(it)
        }
    }

    // Initialize currency manager for wallet display
    val currencyManager = remember {
        CurrencyManager(coroutineScope, secureStorage).also {
            CurrencyHelper.setManager(it)
        }
    }

    // Initialize localization and currency on startup
    LaunchedEffect(Unit) {
        PlatformLogger.i(TAG, "Initializing localization...")
        localizationManager.initialize()
        PlatformLogger.i(TAG, "Initializing currency...")
        currencyManager.initialize()
    }

    // Track the current auth token - will be updated after login/setup
    var currentAccessToken by remember { mutableStateOf<String?>(null) }

    // Sync language changes to backend when user is authenticated
    // Track the previous language to detect actual changes (not initial load)
    var previousLanguage by remember { mutableStateOf<String?>(null) }
    val currentLanguage by localizationManager.currentLanguage.collectAsState()

    val hasExplicitLanguage by localizationManager.hasExplicitLanguageSelection.collectAsState()

    LaunchedEffect(currentLanguage, currentAccessToken) {
        // Only sync if:
        // 1. We have a valid token (user is authenticated)
        // 2. This is a real change (not initial load)
        // 3. The language was explicitly selected by user (not temporary rotation)
        if (currentAccessToken != null && previousLanguage != null && previousLanguage != currentLanguage && hasExplicitLanguage) {
            PlatformLogger.i(TAG, "Language changed from $previousLanguage to $currentLanguage, syncing to backend...")
            try {
                val success = apiClient.updateUserLanguage(currentLanguage)
                if (success) {
                    PlatformLogger.i(TAG, "Language synced to backend successfully: $currentLanguage")
                } else {
                    PlatformLogger.w(TAG, "Failed to sync language to backend")
                }
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "Error syncing language to backend: ${e.message}")
            }
        }
        // Always update previous language after processing
        previousLanguage = currentLanguage
    }

    // Navigation state
    var currentScreen by remember { mutableStateOf<Screen>(Screen.Startup) }

    // Track screen changes for test automation
    LaunchedEffect(currentScreen) {
        TestAutomation.setCurrentScreen(currentScreen::class.simpleName ?: "unknown")
    }

    // Handle system back button - navigate back to appropriate parent screen
    PlatformBackHandler(enabled = currentScreen !is Screen.Startup && currentScreen !is Screen.Interact) {
        currentScreen = when (currentScreen) {
            // Login/Setup flow - don't go back, let user complete the flow
            is Screen.Login, is Screen.Setup -> currentScreen

            // GraphMemory goes back to Memory list
            is Screen.GraphMemory -> Screen.Memory

            // DataManagement goes back to Settings
            is Screen.DataManagement -> Screen.Settings

            // All other screens go back to Interact (main screen)
            else -> Screen.Interact
        }
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
    // Observe language changes for pipeline label localization
    // This updates pipeline labels when localization becomes ready or language changes
    interactViewModel.observeLanguageChanges(localizationManager)
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
    val serverConnectionViewModel: ServerConnectionViewModel = viewModel {
        ServerConnectionViewModel(apiClient, pythonRuntime, secureStorage)
    }
    val skillImportViewModel: SkillImportViewModel = viewModel {
        SkillImportViewModel(apiClient)
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
    val ticketsViewModel: TicketsViewModel = viewModel {
        TicketsViewModel(apiClient)
    }
    val schedulerViewModel: SchedulerViewModel = viewModel {
        SchedulerViewModel(apiClient)
    }
    val toolsViewModel: ToolsViewModel = viewModel {
        ToolsViewModel(apiClient)
    }
    val environmentInfoViewModel: EnvironmentInfoViewModel = viewModel {
        EnvironmentInfoViewModel(apiClient)
    }
    val dataManagementViewModel: DataManagementViewModel = viewModel {
        DataManagementViewModel(apiClient, secureStorage, envFileUpdater)
    }

    // Set up purchase result callback — routes through handlePurchaseResult for typed error handling
    LaunchedEffect(purchaseLauncher) {
        purchaseLauncher?.setOnPurchaseResult { result ->
            PlatformLogger.i(TAG, " Purchase result: $result")
            billingViewModel.handlePurchaseResult(result)
        }
    }

    // Watch startup phase to check first-run when ready
    val phase by startupViewModel.phase.collectAsState()

    LaunchedEffect(phase) {
        if (phase == StartupPhase.READY && !checkingFirstRun) {
            checkingFirstRun = true
            platformLog(TAG, "[INFO] Startup READY, checking first-run status...")

            // If we just completed setup, wait for agent WORK state before navigating to Interact
            // The token was literally just created during setup, so it's definitely valid
            if (justCompletedSetup) {
                platformLog(TAG, "[INFO] Just completed setup, waiting for agent WORK state...")
                justCompletedSetup = false

                // Keep timer running during backend polling
                startupViewModel.setKeepTimerAlive(true)

                // Wait for agent to reach WORK state
                // NOTE: Don't call setPhase() here - it would cancel this LaunchedEffect!
                startupViewModel.setStatus(LocalizationHelper.getString("mobile.status_waiting_agent"))

                var agentReady = false
                var pollAttempts = 0
                val maxPollAttempts = 150 // 30 seconds
                var lastState = "UNKNOWN"

                while (pollAttempts < maxPollAttempts && !agentReady) {
                    try {
                        val status = apiClient.getSystemStatus()
                        val cogState = (status.cognitive_state ?: "UNKNOWN").uppercase()

                        if (cogState != lastState) {
                            PlatformLogger.i(TAG, " Agent state: $cogState")
                            startupViewModel.setStatus("Agent state: $cogState")
                            lastState = cogState
                        }

                        if (cogState == "WORK") {
                            PlatformLogger.i(TAG, " Agent reached WORK state!")
                            agentReady = true
                            break
                        }
                    } catch (e: Exception) {
                        if (pollAttempts % 10 == 0) {
                            PlatformLogger.d(TAG, " Waiting for server... (${e.message?.take(30)})")
                            startupViewModel.setStatus(LocalizationHelper.getString("mobile.status_connecting_backend"))
                        }
                    }
                    kotlinx.coroutines.delay(200)
                    pollAttempts++
                }

                if (!agentReady) {
                    PlatformLogger.w(TAG, " Agent did not reach WORK state within timeout, proceeding anyway")
                    startupViewModel.setStatus("Agent ready (timeout)")
                } else {
                    startupViewModel.setStatus("Agent ready!")
                }
                kotlinx.coroutines.delay(500)

                // Stop timer before navigating away
                startupViewModel.setKeepTimerAlive(false)

                interactViewModel.startPolling() // Start polling now that token is set
                currentScreen = Screen.Interact
                return@LaunchedEffect
            }

            // Check if this is first run via API
            // Keep timer running and show status while waiting for backend
            startupViewModel.setKeepTimerAlive(true)
            startupViewModel.setStatus(LocalizationHelper.getString("mobile.status_checking_setup"))

            isFirstRun = checkFirstRunStatus(
                baseUrl = baseUrl,
                maxRetries = 60,  // Wait up to 30 seconds (60 * 500ms)
                onStatusUpdate = { status ->
                    startupViewModel.setStatus(status)
                }
            )

            startupViewModel.setKeepTimerAlive(false)
            platformLog(TAG, "[INFO] First run check result: $isFirstRun")

            if (isFirstRun == null) {
                // Server unreachable after all retries - show error
                platformLog(TAG, "[ERROR] Backend unreachable, cannot determine setup status")
                startupViewModel.onErrorDetected("Backend unreachable. Please restart the app.")
                return@LaunchedEffect
            } else if (isFirstRun == true) {
                // First run - show login screen first
                platformLog(TAG, "[INFO] First run detected, navigating to Login")
                currentScreen = Screen.Login
            } else {
                // Not first run - try to load stored token and check if valid/refresh if needed
                platformLog(TAG, "[INFO] Not first run, attempting to load and validate stored token")
                // NOTE: Don't change phase here - it would restart the LaunchedEffect and cancel this coroutine!
                // Just update the status message which is shown on the startup screen
                startupViewModel.setStatus(LocalizationHelper.getString("mobile.status_authenticating"))

                // Add timeout for token loading (shouldn't take more than 5 seconds)
                val tokenResult = try {
                    kotlinx.coroutines.withTimeout(5000) {
                        secureStorage.getAccessToken()
                    }
                } catch (e: kotlinx.coroutines.TimeoutCancellationException) {
                    startupViewModel.setStatus("Token load timeout!")
                    platformLog(TAG, "[ERROR] Token loading timed out after 5 seconds")
                    Result.failure<String?>(Exception("Token loading timed out"))
                } catch (e: Exception) {
                    startupViewModel.setStatus("Token load error: ${e.message?.take(30)}")
                    platformLog(TAG, "[ERROR] Token loading failed: ${e.message}")
                    Result.failure<String?>(e)
                }

                tokenResult.onSuccess { storedToken ->
                        if (storedToken != null) {
                            platformLog(TAG, "[INFO] Loaded stored token: ${storedToken.take(8)}...${storedToken.takeLast(4)}")
                            startupViewModel.setStatus(LocalizationHelper.getString("mobile.status_token_loaded"))

                            // Check token validity and refresh if needed
                            // NOTE: storedToken is a CIRIS access token, not a Google ID token
                            // If refresh is needed, tokenManager will call onSilentSignInRequested
                            // which gets a Google ID token, then onTokenRefreshed callback
                            // exchanges it for a new CIRIS token
                            tokenExchangeComplete = true // Assume no exchange needed initially
                            startupViewModel.setStatus(LocalizationHelper.getString("mobile.status_checking_expiry"))
                            val tokenValid = tokenManager.checkAndRefreshToken(storedToken)

                            if (tokenValid) {
                                // Check if exchange was triggered (callback sets this to false)
                                if (!tokenExchangeComplete) {
                                    // Token was refreshed - wait for Google->CIRIS exchange to complete
                                    PlatformLogger.i(TAG, " Token was refreshed, waiting for CIRIS token exchange...")
                                    startupViewModel.setStatus(LocalizationHelper.getString("mobile.status_refreshing_token"))
                                    var waitCount = 0
                                    while (!tokenExchangeComplete && waitCount < 50) {
                                        kotlinx.coroutines.delay(100)
                                        waitCount++
                                        if (waitCount % 10 == 0) {
                                            startupViewModel.setStatus("Token exchange... ${waitCount/10}s")
                                        }
                                    }
                                    if (tokenExchangeComplete) {
                                        PlatformLogger.i(TAG, " Token exchange completed")
                                        startupViewModel.setStatus("Token exchange complete")
                                    } else {
                                        PlatformLogger.w(TAG, " Token exchange timed out")
                                        startupViewModel.setStatus("Token exchange timeout")
                                    }
                                } else {
                                    // Token was valid without refresh - but we need to verify it works with the backend
                                    // (backend may have restarted, invalidating old tokens)
                                    PlatformLogger.i(TAG, " Stored token not expired, verifying with backend...")
                                    startupViewModel.setStatus(LocalizationHelper.getString("mobile.status_verifying_token"))
                                    apiClient.setAccessToken(storedToken)

                                    // Test API call to verify token is actually accepted
                                    try {
                                        val status = apiClient.getSystemStatus()
                                        PlatformLogger.i(TAG, " Token verified OK - backend status: ${status.status}")
                                        startupViewModel.setStatus("Token verified OK")
                                        // Token verified OK - use it
                                        onTokenUpdated?.invoke(storedToken)
                                        currentAccessToken = storedToken
                                        apiClient.logTokenState()
                                    } catch (e: Exception) {
                                        val errorMsg = e.message ?: ""
                                        if (errorMsg.contains("401") || errorMsg.contains("Unauthorized", ignoreCase = true)) {
                                            PlatformLogger.w(TAG, " Token rejected by backend (401) - triggering refresh")
                                            startupViewModel.setStatus(LocalizationHelper.getString("mobile.status_token_rejected"))
                                            tokenManager.on401Error()
                                            // Wait for refresh to complete - callback will set apiClient token
                                            var refreshWait = 0
                                            while (refreshWait < 50) {
                                                kotlinx.coroutines.delay(100)
                                                refreshWait++
                                                if (refreshWait % 10 == 0) {
                                                    startupViewModel.setStatus("Refreshing... ${refreshWait/10}s")
                                                }
                                                // Check if token exchange completed (callback sets this)
                                                if (tokenExchangeComplete && currentAccessToken != storedToken) {
                                                    PlatformLogger.i(TAG, " Token exchange completed after refresh")
                                                    startupViewModel.setStatus("Token refreshed!")
                                                    break
                                                }
                                            }
                                            // Token was refreshed by callback - don't overwrite with old token
                                            apiClient.logTokenState()
                                        } else {
                                            PlatformLogger.w(TAG, " Backend check failed (non-auth): ${e.message}")
                                            startupViewModel.setStatus("Backend error: ${e.message?.take(30)}")
                                            // Non-401 error - use stored token anyway
                                            onTokenUpdated?.invoke(storedToken)
                                            currentAccessToken = storedToken
                                            apiClient.logTokenState()
                                        }
                                    }
                                }

                                // Wait for agent to reach WORK state before showing Interact
                                // NOTE: Don't call setPhase() here - it would cancel this LaunchedEffect!
                                // The status message is sufficient for user feedback
                                // Keep timer running during backend polling
                                startupViewModel.setKeepTimerAlive(true)
                                startupViewModel.setStatus(LocalizationHelper.getString("mobile.status_waiting_agent"))

                                // Poll for WORK state with timeout
                                var agentReady = false
                                var pollAttempts = 0
                                val maxPollAttempts = 150 // 30 seconds (150 * 200ms)
                                var lastState = "UNKNOWN"

                                while (pollAttempts < maxPollAttempts && !agentReady) {
                                    try {
                                        val status = apiClient.getSystemStatus()
                                        val cogState = (status.cognitive_state ?: "UNKNOWN").uppercase()

                                        if (cogState != lastState) {
                                            PlatformLogger.i(TAG, " Agent state: $cogState")
                                            startupViewModel.setStatus("Agent state: $cogState")
                                            lastState = cogState
                                        }

                                        if (cogState == "WORK") {
                                            PlatformLogger.i(TAG, " Agent reached WORK state!")
                                            agentReady = true
                                            break
                                        }
                                    } catch (e: Exception) {
                                        // Server not ready yet, keep polling
                                        if (pollAttempts % 10 == 0) {
                                            PlatformLogger.d(TAG, " Waiting for server... (${e.message?.take(30)})")
                                            startupViewModel.setStatus(LocalizationHelper.getString("mobile.status_connecting_backend"))
                                        }
                                    }
                                    kotlinx.coroutines.delay(200)
                                    pollAttempts++
                                }

                                if (!agentReady) {
                                    PlatformLogger.w(TAG, " Agent did not reach WORK state within timeout, proceeding anyway")
                                    startupViewModel.setStatus("Agent ready (timeout)")
                                } else {
                                    startupViewModel.setStatus("Agent ready!")
                                }

                                // Brief pause to show ready state
                                kotlinx.coroutines.delay(500)

                                // Stop timer before navigating away
                                startupViewModel.setKeepTimerAlive(false)

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
                            startupViewModel.setStatus("No stored token, login required")
                            kotlinx.coroutines.delay(500)
                            currentScreen = Screen.Login
                        }
                    }
                    .onFailure { e ->
                        platformLog(TAG, "[ERROR] Failed to load stored token: ${e::class.simpleName}: ${e.message}")
                        startupViewModel.setStatus("Token error: ${e.message?.take(30)}")
                        kotlinx.coroutines.delay(1000) // Show error briefly
                        currentScreen = Screen.Login
                    }
            }
        }
    }

    // Collect theme preferences for immediate application
    val brightnessPreference by settingsViewModel.brightnessPreference.collectAsState()
    val selectedColorTheme by settingsViewModel.colorTheme.collectAsState()
    val systemInDarkTheme = isSystemInDarkTheme()
    val isDarkMode = when (brightnessPreference) {
        BrightnessPreference.LIGHT -> false
        BrightnessPreference.DARK -> true
        BrightnessPreference.SYSTEM -> systemInDarkTheme
    }

    // Apply color scheme with selected color theme applied immediately
    val colorScheme = if (isDarkMode) {
        darkColorScheme(
            primary = selectedColorTheme.primary,
            secondary = selectedColorTheme.secondary,
            tertiary = selectedColorTheme.tertiary
        )
    } else {
        lightColorScheme(
            primary = selectedColorTheme.primary,
            secondary = selectedColorTheme.secondary,
            tertiary = selectedColorTheme.tertiary
        )
    }

    // Provide localization and currency to entire Compose tree
    CompositionLocalProvider(
        LocalLocalization provides localizationManager,
        LocalCurrency provides currencyManager
    ) {
        MaterialTheme(colorScheme = colorScheme) {
            when (currentScreen) {
            Screen.Startup -> {
                StartupScreen(viewModel = startupViewModel)
            }

            Screen.Login -> {
                platformLog(TAG, "[DEBUG][Screen.Login] Rendering login screen, googleSignInCallback=${if (googleSignInCallback != null) "PRESENT" else "NULL"}, isFirstRun=$isFirstRun")

                // During FIRST RUN, go to setup wizard
                // Desktop: auto-trigger since no OAuth; iOS: show login first for auth
                LaunchedEffect(googleSignInCallback, isFirstRun) {
                    if (isFirstRun == true && googleSignInCallback == null) {
                        // Desktop: no OAuth, go directly to setup
                        platformLog(TAG, "[INFO][Screen.Login] Desktop first-run detected (no OAuth) - going to setup")
                        setupViewModel.setGoogleAuthState(
                            isAuth = false,
                            idToken = null,
                            email = null,
                            userId = null
                        )
                        currentScreen = Screen.Setup
                    } else if (isFirstRun == true && googleSignInCallback != null) {
                        // iOS/Android: first run with OAuth - show login so user can sign in,
                        // then auth flow will detect first user and redirect to setup
                        platformLog(TAG, "[INFO][Screen.Login] Mobile first-run - showing login for OAuth sign-in")
                    } else if (googleSignInCallback == null && isFirstRun == false) {
                        platformLog(TAG, "[INFO][Screen.Login] Desktop existing user - showing local login form")
                    }
                }

                LoginScreen(
                    onGoogleSignIn = {
                        platformLog(TAG, "[INFO][onGoogleSignIn] Button click handler invoked, googleSignInCallback=${if (googleSignInCallback != null) "PRESENT" else "NULL"}")
                        if (googleSignInCallback != null) {
                            // Use platform-specific Google sign-in
                            platformLog(TAG, "[INFO][onGoogleSignIn] Callback is not null, calling onGoogleSignInRequested...")
                            isLoginLoading = true
                            loginStatusMessage = LocalizationHelper.getString("mobile.status_signing_in", mapOf("provider" to getOAuthProviderName()))
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
                                            val setupRequired = checkFirstRunStatus(baseUrl) // No retries needed here - server is up
                                            platformLog(TAG, "[INFO] Setup required check result: $setupRequired")

                                            if (setupRequired == false) {
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

                                                    // Wait for agent WORK state
                                                    loginStatusMessage = "Waiting for agent..."
                                                    var agentReady = false
                                                    var pollAttempts = 0
                                                    while (pollAttempts < 150 && !agentReady) {
                                                        try {
                                                            val status = apiClient.getSystemStatus()
                                                            val cogState = status.cognitive_state ?: "UNKNOWN"
                                                            if (cogState.uppercase() == "WORK") {
                                                                agentReady = true
                                                                break
                                                            }
                                                            loginStatusMessage = "Agent state: $cogState"
                                                        } catch (e: Exception) {
                                                            loginStatusMessage = "Connecting to backend..."
                                                        }
                                                        kotlinx.coroutines.delay(200)
                                                        pollAttempts++
                                                    }

                                                    // Trigger data loading
                                                    PlatformLogger.i(TAG, " Triggering billingViewModel.loadBalance()...")
                                                    billingViewModel.loadBalance()
                                                    adaptersViewModel.fetchAdapters()
                                                    interactViewModel.startPolling() // Start polling now that token is set

                                                    isLoginLoading = false
                                                    loginStatusMessage = null
                                                    platformLog(TAG, "[INFO] Navigating to Screen.Interact")
                                                    currentScreen = Screen.Interact
                                                } catch (e: Exception) {
                                                    platformLog(TAG, "[ERROR] Token exchange failed: ${e::class.simpleName}: ${e.message}")
                                                    isLoginLoading = false
                                                    loginStatusMessage = null
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
                                                    userId = result.userId,
                                                    provider = result.provider
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
                        loginStatusMessage = LocalizationHelper.getString("mobile.status_logging_in")
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

                                // Wait for agent WORK state
                                PlatformLogger.i(TAG, " Local login successful, waiting for agent...")
                                loginStatusMessage = "Waiting for agent..."
                                var agentReady = false
                                var pollAttempts = 0
                                while (pollAttempts < 150 && !agentReady) {
                                    try {
                                        val status = apiClient.getSystemStatus()
                                        val cogState = status.cognitive_state ?: "UNKNOWN"
                                        if (cogState.uppercase() == "WORK") {
                                            agentReady = true
                                            break
                                        }
                                        loginStatusMessage = "Agent state: $cogState"
                                    } catch (e: Exception) {
                                        loginStatusMessage = "Connecting to backend..."
                                    }
                                    kotlinx.coroutines.delay(200)
                                    pollAttempts++
                                }

                                // Trigger data loading
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
                    onServerSettings = { currentScreen = Screen.ServerConnection },
                    connectionStatus = serverConnectionViewModel.connectionStatus.collectAsState().value,
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

                                    // Store OAuth token in TokenManager for billing purchases
                                    tokenManager.handleNewToken(idToken, provider ?: "apple")

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
                // Live background state from settings (collect before Scaffold for top bar)
                val liveBackgroundEnabled by settingsViewModel.liveBackgroundEnabled.collectAsState()
                val colorTheme by settingsViewModel.colorTheme.collectAsState()
                platformLog(TAG, "[CIRISApp] >>> liveBackgroundEnabled=$liveBackgroundEnabled, apiClient=${if (apiClient != null) "present" else "NULL"}")

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
                            onMemoryClick = { currentScreen = Screen.GraphMemory },  // Default to 3D cylinder view
                            onConfigClick = { currentScreen = Screen.Config },
                            onConsentClick = { currentScreen = Screen.Consent },
                            onDataManagementClick = { currentScreen = Screen.DataManagement },
                            onSystemClick = { currentScreen = Screen.System },
                            onRuntimeClick = { currentScreen = Screen.Runtime },
                            onUsersClick = { currentScreen = Screen.Users },
                            onTicketsClick = { currentScreen = Screen.Tickets },
                            onSchedulerClick = { currentScreen = Screen.Scheduler },
                            onToolsClick = { currentScreen = Screen.Tools },
                            onEnvironmentInfoClick = { currentScreen = Screen.EnvironmentInfo },
                            onHelpClick = { currentScreen = Screen.Help },
                            onLogoutClick = {
                                PlatformLogger.i("CIRISApp", "[onLogout] User initiated logout from nav bar")
                                settingsViewModel.logout {
                                    PlatformLogger.i("CIRISApp", "[onLogout] Logout complete, navigating to Login")
                                    currentAccessToken = null
                                    currentScreen = Screen.Login
                                }
                            },
                            darkMode = isDarkMode,
                            // Theme picker
                            colorTheme = colorTheme,
                            brightnessPreference = brightnessPreference,
                            onColorThemeChange = { settingsViewModel.setColorTheme(it) },
                            onBrightnessChange = { settingsViewModel.setBrightnessPreference(it) }
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
                        onOpenWalletPage = {
                            platformLog(TAG, "[INFO] Opening Wallet page")
                            currentScreen = Screen.Wallet
                        },
                        onOpenBilling = {
                            platformLog(TAG, "[INFO] Opening Billing page from credits")
                            currentScreen = Screen.Billing
                        },
                        onOpenSystem = {
                            platformLog(TAG, "[INFO] Opening Server Connection page from Local status badge")
                            currentScreen = Screen.ServerConnection
                        },
                        onOpenSettings = {
                            platformLog(TAG, "[INFO] Opening Settings page from LLM indicator")
                            currentScreen = Screen.Settings
                        },
                        onOpenWiseAuthority = {
                            platformLog(TAG, "[INFO] Opening WiseAuthority page for deferrals")
                            currentScreen = Screen.WiseAuthority
                        },
                        apiClient = apiClient,
                        liveBackgroundEnabled = liveBackgroundEnabled,
                        colorTheme = colorTheme,
                        isDarkMode = isDarkMode,
                        modifier = Modifier.padding(top = paddingValues.calculateTopPadding())
                    )
                }
            }

            Screen.Settings -> {
                SettingsScreen(
                    viewModel = settingsViewModel,
                    apiClient = apiClient,
                    secureStorage = secureStorage,
                    onNavigateBack = { currentScreen = Screen.Interact },
                    onLogout = {
                        PlatformLogger.i("CIRISApp", "[onLogout] User initiated logout")
                        settingsViewModel.logout {
                            PlatformLogger.i("CIRISApp", "[onLogout] Logout complete, navigating to Login")
                            currentAccessToken = null
                            currentScreen = Screen.Login
                        }
                    },
                    onResetSetup = {
                        PlatformLogger.i("CIRISApp", "[onResetSetup] Setup reset — restarting runtime via signal")
                        // AppRestarter writes .restart_signal → Python watchdog restarts runtime
                        // retry() resets StartupViewModel and re-polls until new runtime is healthy
                        startupViewModel.retry()
                        checkingFirstRun = false  // Allow first-run re-check after restart
                        currentScreen = Screen.Startup
                    },
                    onNavigateToDataManagement = {
                        PlatformLogger.i("CIRISApp", "[Settings] Navigating to Data Management")
                        currentScreen = Screen.DataManagement
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
                                coroutineScope.launch {
                                    val maxRetries = 2
                                    var attempt = 0

                                    while (attempt < maxRetries) {
                                        attempt++
                                        val oauthToken = tokenManager.ensureValidToken()
                                        if (oauthToken != null) {
                                            PlatformLogger.i("CIRISApp", "[Screen.Billing] Token valid, launching purchase (attempt $attempt)")
                                            purchaseLauncher.launchPurchaseWithAuth(selectedProduct.productId, oauthToken)
                                            return@launch
                                        }

                                        if (attempt < maxRetries) {
                                            PlatformLogger.w("CIRISApp", "[Screen.Billing] Token null on attempt $attempt, forcing refresh...")
                                            tokenManager.on401Error()
                                            delay(2000)
                                        }
                                    }

                                    PlatformLogger.e("CIRISApp", "[Screen.Billing] All token attempts exhausted ($maxRetries)")
                                    billingViewModel.onPurchaseError("Please sign in to make purchases")
                                }
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

            Screen.Help -> {
                HelpScreen(
                    onNavigateBack = {
                        platformLog(TAG, "[Screen.Help] Navigating back to Interact")
                        currentScreen = Screen.Interact
                    }
                )
            }

            Screen.Telemetry -> {
                val telemetryData by telemetryViewModel.telemetryData.collectAsState()
                val isTelemetryLoading by telemetryViewModel.isLoading.collectAsState()

                // Export destinations state
                val exportDestinations by telemetryViewModel.exportDestinations.collectAsState()
                val showDestinationDialog by telemetryViewModel.showDestinationDialog.collectAsState()
                val editingDestination by telemetryViewModel.editingDestination.collectAsState()
                val testResult by telemetryViewModel.testResult.collectAsState()

                // Start/stop polling and load destinations based on screen visibility
                DisposableEffect(Unit) {
                    PlatformLogger.i(TAG, "[Screen.Telemetry] Starting telemetry polling")
                    telemetryViewModel.startPolling()
                    telemetryViewModel.loadExportDestinations()
                    onDispose {
                        PlatformLogger.i(TAG, "[Screen.Telemetry] Stopping telemetry polling")
                        telemetryViewModel.stopPolling()
                    }
                }

                PlatformLogger.d("CIRISApp", "[Screen.Telemetry] Rendering telemetry screen: " +
                        "services=${telemetryData.healthyServices}/${telemetryData.totalServices}, " +
                        "state=${telemetryData.cognitiveState}, isLoading=$isTelemetryLoading, " +
                        "exportDestinations=${exportDestinations.size}")

                TelemetryScreen(
                    telemetryData = telemetryData,
                    isLoading = isTelemetryLoading,
                    onRefresh = {
                        PlatformLogger.i("CIRISApp", "[Screen.Telemetry] User triggered refresh")
                        telemetryViewModel.refresh()
                        telemetryViewModel.loadExportDestinations()
                    },
                    onNavigateBack = {
                        PlatformLogger.i("CIRISApp", "[Screen.Telemetry] Navigating back to Interact")
                        currentScreen = Screen.Interact
                    },
                    // Export destinations
                    exportDestinations = exportDestinations,
                    showDestinationDialog = showDestinationDialog,
                    editingDestination = editingDestination,
                    testResult = testResult,
                    onAddDestination = {
                        PlatformLogger.i("CIRISApp", "[Screen.Telemetry] Adding export destination")
                        telemetryViewModel.showAddDestinationDialog()
                    },
                    onEditDestination = { dest ->
                        PlatformLogger.i("CIRISApp", "[Screen.Telemetry] Editing destination: ${dest.id}")
                        telemetryViewModel.showEditDestinationDialog(dest)
                    },
                    onDeleteDestination = { id ->
                        PlatformLogger.i("CIRISApp", "[Screen.Telemetry] Deleting destination: $id")
                        telemetryViewModel.deleteDestination(id)
                    },
                    onToggleDestination = { id ->
                        PlatformLogger.i("CIRISApp", "[Screen.Telemetry] Toggling destination: $id")
                        telemetryViewModel.toggleDestinationEnabled(id)
                    },
                    onTestDestination = { id ->
                        PlatformLogger.i("CIRISApp", "[Screen.Telemetry] Testing destination: $id")
                        telemetryViewModel.testDestination(id)
                    },
                    onSaveDestination = { dest ->
                        PlatformLogger.i("CIRISApp", "[Screen.Telemetry] Saving destination: ${dest.name}")
                        telemetryViewModel.saveDestination(dest)
                    },
                    onDismissDialog = {
                        PlatformLogger.d("CIRISApp", "[Screen.Telemetry] Dismissing destination dialog")
                        telemetryViewModel.dismissDestinationDialog()
                    },
                    onClearTestResult = {
                        telemetryViewModel.clearTestResult()
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
                // Expansion state
                val expandedAdapterIds by adaptersViewModel.expandedAdapterIds.collectAsState()
                val adapterDetails by adaptersViewModel.adapterDetails.collectAsState()

                PlatformLogger.d("CIRISApp", "[Screen.Adapters] Rendering adapters screen: " +
                        "adapters=${adaptersList.size}, connected=$isAdaptersConnected, " +
                        "isLoading=$isAdaptersLoading, operationInProgress=$adaptersOperationInProgress")

                // Fetch adapters immediately and start polling when screen is visible
                DisposableEffect(Unit) {
                    PlatformLogger.i("CIRISApp", "[Screen.Adapters] Fetching adapters and starting polling")
                    adaptersViewModel.fetchAdapters()  // Immediate fetch on screen entry
                    adaptersViewModel.startPolling()   // Then poll for updates
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
                    expandedAdapterIds = expandedAdapterIds,
                    adapterDetails = adapterDetails,
                    onToggleExpanded = { adapterId ->
                        PlatformLogger.d("CIRISApp", "[Screen.Adapters] Toggling expansion for: $adapterId")
                        adaptersViewModel.toggleExpanded(adapterId)
                    },
                    onEditConfig = { adapterType ->
                        PlatformLogger.i("CIRISApp", "[Screen.Adapters] Edit config for: $adapterType")
                        adaptersViewModel.editAdapterConfig(adapterType)
                    },
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
                    onImportSkill = {
                        PlatformLogger.i("CIRISApp", "[Screen.Adapters] Import skill requested")
                        currentScreen = Screen.SkillImport
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
                val expandedServiceIds by servicesViewModel.expandedServiceIds.collectAsState()

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
                    expandedServiceIds = expandedServiceIds,
                    onToggleServiceExpanded = { serviceId ->
                        PlatformLogger.d("CIRISApp", "[Screen.Services] Toggle expansion: $serviceId")
                        servicesViewModel.toggleServiceExpanded(serviceId)
                    },
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
                    cylinderLayout = graphMemoryViewModel.cylinderLayout,
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

            Screen.ServerConnection -> {
                PlatformLogger.d(TAG, "[Screen.ServerConnection] Rendering server connection screen")
                ServerConnectionScreen(
                    viewModel = serverConnectionViewModel,
                    onBack = { currentScreen = Screen.Interact }
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

            Screen.Tickets -> {
                val ticketsState by ticketsViewModel.state.collectAsState()

                LaunchedEffect(Unit) {
                    PlatformLogger.i(TAG, "[Screen.Tickets] Loading tickets on screen entry")
                    ticketsViewModel.startPolling()
                }

                DisposableEffect(Unit) {
                    onDispose {
                        ticketsViewModel.stopPolling()
                    }
                }

                TicketsScreen(
                    state = ticketsState,
                    onRefresh = {
                        PlatformLogger.i("CIRISApp", "[Screen.Tickets] User triggered refresh")
                        ticketsViewModel.refresh()
                    },
                    onFilterChange = { filter ->
                        PlatformLogger.i("CIRISApp", "[Screen.Tickets] Filter changed")
                        ticketsViewModel.updateFilter(filter)
                    },
                    onSelectTicket = { ticket ->
                        PlatformLogger.i("CIRISApp", "[Screen.Tickets] Ticket selected: ${ticket?.ticketId}")
                        ticketsViewModel.selectTicket(ticket)
                    },
                    onNavigateBack = { currentScreen = Screen.Interact },
                    onShowCreateDialog = { sop ->
                        PlatformLogger.i("CIRISApp", "[Screen.Tickets] Show create dialog for SOP: $sop")
                        ticketsViewModel.showCreateTicketDialog(sop)
                    },
                    onHideCreateDialog = {
                        PlatformLogger.i("CIRISApp", "[Screen.Tickets] Hide create dialog")
                        ticketsViewModel.hideCreateTicketDialog()
                    },
                    onCreateTicket = { sop, email, userIdentifier, notes ->
                        PlatformLogger.i("CIRISApp", "[Screen.Tickets] Create ticket: sop=$sop, email=$email")
                        ticketsViewModel.createTicket(sop, email, userIdentifier, notes)
                    }
                )
            }

            Screen.Scheduler -> {
                val schedulerState by schedulerViewModel.state.collectAsState()

                LaunchedEffect(Unit) {
                    PlatformLogger.i(TAG, "[Screen.Scheduler] Loading scheduler data on screen entry")
                    schedulerViewModel.startPolling()
                }

                DisposableEffect(Unit) {
                    onDispose {
                        schedulerViewModel.stopPolling()
                    }
                }

                SchedulerScreen(
                    state = schedulerState,
                    onRefresh = {
                        PlatformLogger.i("CIRISApp", "[Screen.Scheduler] User triggered refresh")
                        schedulerViewModel.refresh()
                    },
                    onNavigateBack = { currentScreen = Screen.Interact },
                    onShowCreateDialog = {
                        PlatformLogger.i("CIRISApp", "[Screen.Scheduler] Show create dialog")
                        schedulerViewModel.showCreateTaskDialog()
                    },
                    onHideCreateDialog = {
                        PlatformLogger.i("CIRISApp", "[Screen.Scheduler] Hide create dialog")
                        schedulerViewModel.hideCreateTaskDialog()
                    },
                    onCreateTask = { name, goalDescription, triggerPrompt, deferUntil, scheduleCron ->
                        PlatformLogger.i("CIRISApp", "[Screen.Scheduler] Create task: name=$name, recurring=${scheduleCron != null}")
                        schedulerViewModel.createTask(name, goalDescription, triggerPrompt, deferUntil, scheduleCron)
                    },
                    onCancelTask = { taskId ->
                        PlatformLogger.i("CIRISApp", "[Screen.Scheduler] Cancel task: $taskId")
                        schedulerViewModel.cancelTask(taskId)
                    }
                )
            }

            Screen.Tools -> {
                val toolsState by toolsViewModel.state.collectAsState()

                LaunchedEffect(Unit) {
                    PlatformLogger.i(TAG, "[Screen.Tools] Loading tools on screen entry")
                    toolsViewModel.startPolling()
                }

                DisposableEffect(Unit) {
                    onDispose {
                        toolsViewModel.stopPolling()
                    }
                }

                ToolsScreen(
                    state = toolsState,
                    filteredTools = toolsViewModel.getFilteredTools(),
                    categories = toolsViewModel.getCategories(),
                    providers = toolsViewModel.getProviders(),
                    onRefresh = {
                        PlatformLogger.i("CIRISApp", "[Screen.Tools] User triggered refresh")
                        toolsViewModel.refresh()
                    },
                    onSearchQueryChange = { query ->
                        toolsViewModel.updateSearchQuery(query)
                    },
                    onCategoryFilter = { category ->
                        toolsViewModel.filterByCategory(category)
                    },
                    onProviderFilter = { provider ->
                        toolsViewModel.filterByProvider(provider)
                    },
                    onNavigateBack = { currentScreen = Screen.Interact }
                )
            }

            Screen.EnvironmentInfo -> {
                val environmentInfoState by environmentInfoViewModel.state.collectAsState()

                LaunchedEffect(Unit) {
                    PlatformLogger.i(TAG, "[Screen.EnvironmentInfo] Loading environment info on screen entry")
                    environmentInfoViewModel.startPolling()
                }

                EnvironmentInfoScreen(
                    state = environmentInfoState,
                    onRefresh = {
                        PlatformLogger.i("CIRISApp", "[Screen.EnvironmentInfo] User triggered refresh")
                        environmentInfoViewModel.refresh()
                    },
                    onNavigateBack = { currentScreen = Screen.Interact },
                    onCategorySelected = { category ->
                        PlatformLogger.d("CIRISApp", "[Screen.EnvironmentInfo] Category selected: $category")
                        environmentInfoViewModel.setCategory(category)
                    },
                    onAddItem = {
                        PlatformLogger.d("CIRISApp", "[Screen.EnvironmentInfo] Add item clicked")
                        environmentInfoViewModel.showAddDialog(true)
                    },
                    onCreateItem = { name, category, quantity, condition, notes ->
                        PlatformLogger.i("CIRISApp", "[Screen.EnvironmentInfo] Creating item: $name")
                        environmentInfoViewModel.createItem(name, category, quantity, condition, notes)
                    },
                    onDeleteItem = { nodeId ->
                        PlatformLogger.i("CIRISApp", "[Screen.EnvironmentInfo] Deleting item: $nodeId")
                        environmentInfoViewModel.deleteItem(nodeId)
                    },
                    onDismissAddDialog = {
                        environmentInfoViewModel.showAddDialog(false)
                    }
                )
            }

            Screen.DataManagement -> {
                DataManagementScreen(
                    viewModel = dataManagementViewModel,
                    onNavigateBack = {
                        PlatformLogger.i(TAG, "[Screen.DataManagement] Navigating back to Settings")
                        currentScreen = Screen.Settings
                    },
                    onResetSetup = {
                        PlatformLogger.i(TAG, "[Screen.DataManagement] Reset triggered, restarting via Startup")
                        // Clear stale ViewModel state so old messages don't survive the wipe
                        interactViewModel.resetState()
                        if (ai.ciris.mobile.shared.platform.isDesktop()) {
                            // Desktop: kill the Python server via HTTP then let startup relaunch it fresh
                            PlatformLogger.i(TAG, "[Screen.DataManagement] Desktop: killing Python server via local-shutdown API")
                            currentScreen = Screen.Startup
                            checkingFirstRun = false
                            coroutineScope.launch {
                                try {
                                    // Call the local-shutdown endpoint to kill the server process
                                    apiClient.postLocalShutdown()
                                    PlatformLogger.i(TAG, "[Screen.DataManagement] local-shutdown sent")
                                } catch (e: Exception) {
                                    PlatformLogger.e(TAG, "[Screen.DataManagement] local-shutdown error (expected): ${e.message}")
                                }
                                // Also call pythonRuntime.shutdown() to clear internal state
                                pythonRuntime.shutdown()
                                // Wait for server process to fully exit and port to free
                                // On Linux, TCP TIME_WAIT can hold the port for a while
                                PlatformLogger.i(TAG, "[Screen.DataManagement] Waiting for server to exit and port to free...")
                                kotlinx.coroutines.delay(6000)
                                PlatformLogger.i(TAG, "[Screen.DataManagement] Triggering startup retry")
                                startupViewModel.retry()
                            }
                        } else {
                            // Mobile: server restarts in-process via watchdog.
                            // Wait for server to shut down and come back with fresh config.
                            currentAccessToken = null
                            (apiClient as? ai.ciris.mobile.shared.api.CIRISApiClient)?.clearAccessToken()
                            coroutineScope.launch {
                                PlatformLogger.i(TAG, "[Screen.DataManagement] Mobile: waiting for server restart after reset...")

                                // Wait for server to go down (max 10s)
                                var downDetected = false
                                for (i in 1..20) {
                                    kotlinx.coroutines.delay(500)
                                    try {
                                        apiClient.getSystemStatus()
                                    } catch (_: Exception) {
                                        PlatformLogger.i(TAG, "[Screen.DataManagement] Server went down after ${i * 500}ms")
                                        downDetected = true
                                        break
                                    }
                                }
                                if (!downDetected) {
                                    PlatformLogger.w(TAG, "[Screen.DataManagement] Server didn't go down, proceeding anyway")
                                }

                                // Wait for server to come back (max 30s)
                                for (i in 1..60) {
                                    kotlinx.coroutines.delay(500)
                                    try {
                                        apiClient.getSystemStatus()
                                        PlatformLogger.i(TAG, "[Screen.DataManagement] Server back up after ${i * 500}ms")
                                        break
                                    } catch (_: Exception) {
                                        if (i % 10 == 0) {
                                            PlatformLogger.d(TAG, "[Screen.DataManagement] Waiting for server... ${i * 500}ms")
                                        }
                                    }
                                }

                                startupViewModel.retry()
                                checkingFirstRun = false
                                currentScreen = Screen.Startup
                            }
                        }
                    }
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

            Screen.Wallet -> {
                WalletPage(
                    apiClient = apiClient,
                    onNavigateBack = {
                        PlatformLogger.i("CIRISApp", "[Screen.Wallet] Navigating back to Interact")
                        currentScreen = Screen.Interact
                    }
                )
            }

            Screen.SkillImport -> {
                // Collect SkillImportViewModel state
                val importPhase by skillImportViewModel.importPhase.collectAsState()
                val skillMdContent by skillImportViewModel.skillMdContent.collectAsState()
                val sourceUrl by skillImportViewModel.sourceUrl.collectAsState()
                val preview by skillImportViewModel.preview.collectAsState()
                val importResult by skillImportViewModel.importResult.collectAsState()
                val isSkillLoading by skillImportViewModel.isLoading.collectAsState()
                val skillError by skillImportViewModel.error.collectAsState()

                // Initialize dialog state when entering screen
                LaunchedEffect(Unit) {
                    PlatformLogger.i("CIRISApp", "[Screen.SkillImport] Opening skill import")
                    skillImportViewModel.openImportDialog()
                }

                SkillImportDialog(
                    phase = importPhase,
                    skillMdContent = skillMdContent,
                    sourceUrl = sourceUrl,
                    preview = preview,
                    importResult = importResult,
                    isLoading = isSkillLoading,
                    error = skillError,
                    onContentChanged = { skillImportViewModel.updateSkillMdContent(it) },
                    onSourceUrlChanged = { skillImportViewModel.updateSourceUrl(it) },
                    onPreview = { skillImportViewModel.previewSkill() },
                    onImport = { skillImportViewModel.importSkill() },
                    onDismiss = {
                        PlatformLogger.i("CIRISApp", "[Screen.SkillImport] Closing skill import")
                        skillImportViewModel.closeImportDialog()
                        currentScreen = Screen.Adapters
                    }
                )
            }
        }
    }
    } // CompositionLocalProvider
}

/**
 * Check if setup is required via /v1/setup/status API
 * Uses the API client for platform-independent HTTP handling.
 *
 * @param baseUrl The API base URL
 * @param maxRetries Maximum number of retries on connection error (0 = no retries, just fail)
 * @param onStatusUpdate Optional callback to update status message during retries
 * @return true if setup is required, false if not, null if server unreachable after retries
 */
private suspend fun checkFirstRunStatus(
    baseUrl: String,
    maxRetries: Int = 0,
    onStatusUpdate: ((String) -> Unit)? = null
): Boolean? {
    var attempts = 0
    while (attempts <= maxRetries) {
        try {
            platformLog("checkFirstRunStatus", "[INFO] Attempt ${attempts + 1}/${maxRetries + 1}: Checking setup status at $baseUrl")
            val client = CIRISApiClient(baseUrl)
            val setupStatus = client.getSetupStatus()
            platformLog("checkFirstRunStatus", "[INFO] Got setup status: setup_required=${setupStatus.data.setup_required}")
            return setupStatus.data.setup_required
        } catch (e: Exception) {
            attempts++
            if (attempts <= maxRetries) {
                platformLog("checkFirstRunStatus", "[INFO] Connection error, retrying in 500ms... (${e::class.simpleName})")
                onStatusUpdate?.invoke(LocalizationHelper.getString("mobile.startup_waiting_backend", mapOf("attempt" to attempts.toString())))
                kotlinx.coroutines.delay(500)
            } else {
                platformLog("checkFirstRunStatus", "[ERROR] Failed to check setup status after ${maxRetries + 1} attempts: ${e::class.simpleName}: ${e.message}")
                return null
            }
        }
    }
    return null
}

/**
 * Category-based navigation for the top bar.
 * Categories:
 * - Adapters & Tools: Adapters, Tools
 * - Config & Credits: Settings, Config, Buy Credits
 * - Data & Privacy: Memory, Sessions, Consent, Audit Trail
 * - Governance: Human Deferrals
 * - Advanced: Telemetry, Services, Logs, System, Runtime, Users, Tickets, Scheduler
 */
private enum class NavCategory {
    NONE, ADAPTERS, CONFIG, DATA, GOVERNANCE, ADVANCED
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
    onDataManagementClick: () -> Unit = {},
    onSystemClick: () -> Unit = {},
    onRuntimeClick: () -> Unit = {},
    onUsersClick: () -> Unit = {},
    onTicketsClick: () -> Unit = {},
    onSchedulerClick: () -> Unit = {},
    onToolsClick: () -> Unit = {},
    onEnvironmentInfoClick: () -> Unit = {},
    onHelpClick: () -> Unit = {},
    onLogoutClick: () -> Unit = {},
    darkMode: Boolean = false,
    // Theme picker
    colorTheme: ColorTheme = ColorTheme.DEFAULT,
    brightnessPreference: BrightnessPreference = BrightnessPreference.SYSTEM,
    onColorThemeChange: (ColorTheme) -> Unit = {},
    onBrightnessChange: (BrightnessPreference) -> Unit = {}
) {
    var activeCategory by remember { mutableStateOf(NavCategory.NONE) }
    var showThemePicker by remember { mutableStateOf(false) }

    // Theme picker dialog
    if (showThemePicker) {
        ThemePickerDialog(
            currentTheme = colorTheme,
            currentBrightness = brightnessPreference,
            onThemeSelected = onColorThemeChange,
            onBrightnessSelected = onBrightnessChange,
            onDismiss = { showThemePicker = false }
        )
    }

    // Dark mode colors for live background
    val containerColor = if (darkMode) Color(0xFF0D1117) else MaterialTheme.colorScheme.primaryContainer
    val contentColor = if (darkMode) Color.White else MaterialTheme.colorScheme.onPrimaryContainer
    val accentColor = if (darkMode) Color(0xFF7DD3FC) else MaterialTheme.colorScheme.primary

    TopAppBar(
        title = {
            // CIRIS Signet - geometric brand mark
            CIRISSignet(
                modifier = Modifier.size(32.dp),
                tintColor = if (darkMode) Color.White else MaterialTheme.colorScheme.primary
            )
        },
        actions = {
            // Category 1: Adapters & Tools
            Box {
                IconButton(
                    onClick = { activeCategory = if (activeCategory == NavCategory.ADAPTERS) NavCategory.NONE else NavCategory.ADAPTERS },
                    modifier = Modifier.testableClickable("btn_adapters_menu") {
                        activeCategory = if (activeCategory == NavCategory.ADAPTERS) NavCategory.NONE else NavCategory.ADAPTERS
                    }
                ) {
                    Icon(
                        imageVector = Icons.Default.Build,
                        contentDescription = "Adapters & Tools",
                        tint = if (activeCategory == NavCategory.ADAPTERS) accentColor else contentColor
                    )
                }
                DropdownMenu(
                    expanded = activeCategory == NavCategory.ADAPTERS,
                    onDismissRequest = { activeCategory = NavCategory.NONE }
                ) {
                    Text(
                        text = localizedString("mobile.nav_adapters_tools"),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_adapters")) },
                        onClick = { activeCategory = NavCategory.NONE; onAdaptersClick() },
                        leadingIcon = { Icon(Icons.Default.Build, null) },
                        modifier = Modifier.testableClickable("menu_adapters") { activeCategory = NavCategory.NONE; onAdaptersClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_tools")) },
                        onClick = { activeCategory = NavCategory.NONE; onToolsClick() },
                        leadingIcon = { Icon(Icons.Default.Build, null) },
                        modifier = Modifier.testableClickable("menu_tools") { activeCategory = NavCategory.NONE; onToolsClick() }
                    )
                    DropdownMenuItem(
                        text = { Text("Environment Info") },
                        onClick = { activeCategory = NavCategory.NONE; onEnvironmentInfoClick() },
                        leadingIcon = { Icon(Icons.Default.Info, null) },
                        modifier = Modifier.testableClickable("menu_environment_info") { activeCategory = NavCategory.NONE; onEnvironmentInfoClick() }
                    )
                }
            }

            // Category 2: Config & Credits
            Box {
                IconButton(
                    onClick = { activeCategory = if (activeCategory == NavCategory.CONFIG) NavCategory.NONE else NavCategory.CONFIG },
                    modifier = Modifier.testableClickable("btn_config_menu") {
                        activeCategory = if (activeCategory == NavCategory.CONFIG) NavCategory.NONE else NavCategory.CONFIG
                    }
                ) {
                    Icon(
                        imageVector = Icons.Default.Settings,
                        contentDescription = "Config & Credits",
                        tint = if (activeCategory == NavCategory.CONFIG) accentColor else contentColor
                    )
                }
                DropdownMenu(
                    expanded = activeCategory == NavCategory.CONFIG,
                    onDismissRequest = { activeCategory = NavCategory.NONE }
                ) {
                    Text(
                        text = localizedString("mobile.nav_config_credits"),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_app_theme")) },
                        onClick = { activeCategory = NavCategory.NONE; showThemePicker = true },
                        leadingIcon = {
                            // Show current theme color as icon
                            Box(
                                modifier = Modifier
                                    .size(24.dp)
                                    .background(colorTheme.primary, CircleShape)
                            )
                        }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_app_settings")) },
                        onClick = { activeCategory = NavCategory.NONE; onSettingsClick() },
                        leadingIcon = { Icon(Icons.Default.Settings, null) },
                        modifier = Modifier.testableClickable("menu_settings") { activeCategory = NavCategory.NONE; onSettingsClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_agent_config")) },
                        onClick = { activeCategory = NavCategory.NONE; onConfigClick() },
                        leadingIcon = { Icon(Icons.Default.Settings, null) },
                        modifier = Modifier.testableClickable("menu_config") { activeCategory = NavCategory.NONE; onConfigClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_buy_credits")) },
                        onClick = { activeCategory = NavCategory.NONE; onBillingClick() },
                        leadingIcon = { Icon(Icons.Default.Star, null) },
                        modifier = Modifier.testableClickable("menu_billing") { activeCategory = NavCategory.NONE; onBillingClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_help")) },
                        onClick = { activeCategory = NavCategory.NONE; onHelpClick() },
                        leadingIcon = { Icon(Icons.Default.Info, null) },
                        modifier = Modifier.testableClickable("menu_help") { activeCategory = NavCategory.NONE; onHelpClick() }
                    )
                }
            }

            // Category 3: Data & Privacy
            Box {
                IconButton(
                    onClick = { activeCategory = if (activeCategory == NavCategory.DATA) NavCategory.NONE else NavCategory.DATA },
                    modifier = Modifier.testableClickable("btn_data_menu") {
                        activeCategory = if (activeCategory == NavCategory.DATA) NavCategory.NONE else NavCategory.DATA
                    }
                ) {
                    Icon(
                        imageVector = Icons.Default.Info,
                        contentDescription = "Data & Privacy",
                        tint = if (activeCategory == NavCategory.DATA) accentColor else contentColor
                    )
                }
                DropdownMenu(
                    expanded = activeCategory == NavCategory.DATA,
                    onDismissRequest = { activeCategory = NavCategory.NONE }
                ) {
                    Text(
                        text = localizedString("mobile.nav_data_privacy"),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_memory")) },
                        onClick = { activeCategory = NavCategory.NONE; onMemoryClick() },
                        leadingIcon = { Icon(Icons.Default.Star, null) },
                        modifier = Modifier.testableClickable("menu_memory") { activeCategory = NavCategory.NONE; onMemoryClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_sessions")) },
                        onClick = { activeCategory = NavCategory.NONE; onSessionsClick() },
                        leadingIcon = { Icon(Icons.Default.List, null) },
                        modifier = Modifier.testableClickable("menu_sessions") { activeCategory = NavCategory.NONE; onSessionsClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_consent")) },
                        onClick = { activeCategory = NavCategory.NONE; onConsentClick() },
                        leadingIcon = { Icon(Icons.Default.Check, null) },
                        modifier = Modifier.testableClickable("menu_consent") { activeCategory = NavCategory.NONE; onConsentClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_audit_trail")) },
                        onClick = { activeCategory = NavCategory.NONE; onAuditClick() },
                        leadingIcon = { Icon(Icons.Default.List, null) },
                        modifier = Modifier.testableClickable("menu_audit") { activeCategory = NavCategory.NONE; onAuditClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_data_management")) },
                        onClick = { activeCategory = NavCategory.NONE; onDataManagementClick() },
                        leadingIcon = { Icon(Icons.Default.Info, null) },
                        modifier = Modifier.testableClickable("menu_data_management") { activeCategory = NavCategory.NONE; onDataManagementClick() }
                    )
                }
            }

            // Category 4: Account & Governance (person icon with users, deferrals, logout)
            Box {
                IconButton(
                    onClick = { activeCategory = if (activeCategory == NavCategory.GOVERNANCE) NavCategory.NONE else NavCategory.GOVERNANCE },
                    modifier = Modifier.testableClickable("btn_governance_menu") {
                        activeCategory = if (activeCategory == NavCategory.GOVERNANCE) NavCategory.NONE else NavCategory.GOVERNANCE
                    }
                ) {
                    Icon(
                        imageVector = Icons.Default.Person,
                        contentDescription = "Account",
                        tint = if (activeCategory == NavCategory.GOVERNANCE) accentColor else contentColor
                    )
                }
                DropdownMenu(
                    expanded = activeCategory == NavCategory.GOVERNANCE,
                    onDismissRequest = { activeCategory = NavCategory.NONE }
                ) {
                    Text(
                        text = localizedString("mobile.nav_governance"),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_human_deferrals")) },
                        onClick = { activeCategory = NavCategory.NONE; onWiseAuthorityClick() },
                        leadingIcon = { Icon(Icons.Default.Person, null) },
                        modifier = Modifier.testableClickable("menu_wise_authority") { activeCategory = NavCategory.NONE; onWiseAuthorityClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_users")) },
                        onClick = { activeCategory = NavCategory.NONE; onUsersClick() },
                        leadingIcon = { Icon(Icons.Default.Person, null) },
                        modifier = Modifier.testableClickable("menu_users") { activeCategory = NavCategory.NONE; onUsersClick() }
                    )
                    HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.settings_logout")) },
                        onClick = { activeCategory = NavCategory.NONE; onLogoutClick() },
                        leadingIcon = { Icon(Icons.Default.ExitToApp, null) },
                        modifier = Modifier.testableClickable("menu_logout") { activeCategory = NavCategory.NONE; onLogoutClick() }
                    )
                }
            }

            // Category 5: Advanced (overflow for power users)
            Box {
                IconButton(
                    onClick = { activeCategory = if (activeCategory == NavCategory.ADVANCED) NavCategory.NONE else NavCategory.ADVANCED },
                    modifier = Modifier.testableClickable("btn_menu") {
                        activeCategory = if (activeCategory == NavCategory.ADVANCED) NavCategory.NONE else NavCategory.ADVANCED
                    }
                ) {
                    Icon(
                        imageVector = Icons.Default.MoreVert,
                        contentDescription = "Advanced",
                        tint = if (activeCategory == NavCategory.ADVANCED) accentColor else contentColor
                    )
                }
                DropdownMenu(
                    expanded = activeCategory == NavCategory.ADVANCED,
                    onDismissRequest = { activeCategory = NavCategory.NONE }
                ) {
                    Text(
                        text = localizedString("mobile.nav_advanced"),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary,
                        modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_telemetry")) },
                        onClick = { activeCategory = NavCategory.NONE; onTelemetryClick() },
                        leadingIcon = { Icon(Icons.Default.Info, null) },
                        modifier = Modifier.testableClickable("menu_telemetry") { activeCategory = NavCategory.NONE; onTelemetryClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_services")) },
                        onClick = { activeCategory = NavCategory.NONE; onServicesClick() },
                        leadingIcon = { Icon(Icons.Default.Build, null) },
                        modifier = Modifier.testableClickable("menu_services") { activeCategory = NavCategory.NONE; onServicesClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_logs")) },
                        onClick = { activeCategory = NavCategory.NONE; onLogsClick() },
                        leadingIcon = { Icon(Icons.Default.List, null) },
                        modifier = Modifier.testableClickable("menu_logs") { activeCategory = NavCategory.NONE; onLogsClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_system")) },
                        onClick = { activeCategory = NavCategory.NONE; onSystemClick() },
                        leadingIcon = { Icon(Icons.Default.Info, null) },
                        modifier = Modifier.testableClickable("menu_system") { activeCategory = NavCategory.NONE; onSystemClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_runtime")) },
                        onClick = { activeCategory = NavCategory.NONE; onRuntimeClick() },
                        leadingIcon = { Icon(Icons.Default.PlayArrow, null) },
                        modifier = Modifier.testableClickable("menu_runtime") { activeCategory = NavCategory.NONE; onRuntimeClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_tickets")) },
                        onClick = { activeCategory = NavCategory.NONE; onTicketsClick() },
                        leadingIcon = { Icon(Icons.Default.List, null) },
                        modifier = Modifier.testableClickable("menu_tickets") { activeCategory = NavCategory.NONE; onTicketsClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_scheduler")) },
                        onClick = { activeCategory = NavCategory.NONE; onSchedulerClick() },
                        leadingIcon = { Icon(Icons.Default.Check, null) },
                        modifier = Modifier.testableClickable("menu_scheduler") { activeCategory = NavCategory.NONE; onSchedulerClick() }
                    )
                }
            }

        },
        colors = TopAppBarDefaults.topAppBarColors(
            containerColor = containerColor,
            titleContentColor = contentColor,
            actionIconContentColor = contentColor
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
    object Wallet : Screen()
    object Tickets : Screen()
    object Scheduler : Screen()
    object Tools : Screen()
    object EnvironmentInfo : Screen()
    object SkillImport : Screen()
    object DataManagement : Screen()
    object Help : Screen()
    object ServerConnection : Screen()
}

/**
 * Theme picker dialog - accessible from top bar gear menu.
 */
@Composable
private fun ThemePickerDialog(
    currentTheme: ColorTheme,
    currentBrightness: BrightnessPreference,
    onThemeSelected: (ColorTheme) -> Unit,
    onBrightnessSelected: (BrightnessPreference) -> Unit,
    onDismiss: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(localizedString("mobile.nav_app_theme")) },
        text = {
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Brightness selection
                Text(
                    text = localizedString("mobile.nav_brightness"),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Medium
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    BrightnessPreference.entries.forEach { pref ->
                        FilterChip(
                            selected = currentBrightness == pref,
                            onClick = { onBrightnessSelected(pref) },
                            label = { Text(pref.displayName) }
                        )
                    }
                }

                // Color theme grid
                Text(
                    text = localizedString("mobile.nav_color_theme"),
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Medium
                )

                val themes = ColorTheme.entries.toList()
                val chunkedThemes = themes.chunked(4)

                chunkedThemes.forEach { row ->
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(6.dp)
                    ) {
                        row.forEach { theme ->
                            ThemeColorChip(
                                theme = theme,
                                isSelected = currentTheme == theme,
                                onClick = { onThemeSelected(theme) },
                                modifier = Modifier.weight(1f)
                            )
                        }
                        // Fill remaining space
                        repeat(4 - row.size) {
                            Spacer(modifier = Modifier.weight(1f))
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) {
                Text(localizedString("mobile.common_done"))
            }
        }
    )
}

/**
 * Compact theme color chip for the dialog.
 */
@Composable
private fun ThemeColorChip(
    theme: ColorTheme,
    isSelected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = if (isSelected) MaterialTheme.colorScheme.primaryContainer
               else MaterialTheme.colorScheme.surface,
        modifier = modifier
            .border(
                width = if (isSelected) 2.dp else 1.dp,
                color = if (isSelected) MaterialTheme.colorScheme.primary
                       else MaterialTheme.colorScheme.outline.copy(alpha = 0.3f),
                shape = RoundedCornerShape(8.dp)
            )
            .clickable { onClick() }
    ) {
        Column(
            modifier = Modifier.padding(6.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            // Color dots
            Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                Box(
                    modifier = Modifier
                        .size(12.dp)
                        .background(theme.primary, CircleShape)
                )
                Box(
                    modifier = Modifier
                        .size(12.dp)
                        .background(theme.secondary, CircleShape)
                )
                Box(
                    modifier = Modifier
                        .size(12.dp)
                        .background(theme.tertiary, CircleShape)
                )
            }
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = theme.displayName,
                style = MaterialTheme.typography.labelSmall,
                maxLines = 1
            )
        }
    }
}
