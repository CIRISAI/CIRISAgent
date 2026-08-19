package ai.ciris.mobile.shared
import ai.ciris.mobile.shared.platform.isIOS
import ai.ciris.mobile.shared.platform.openUrlInBrowser
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
import ai.ciris.mobile.shared.models.NodeOwnership
import ai.ciris.mobile.shared.models.nodeOwnershipFrom
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
import ai.ciris.mobile.shared.viewmodels.ConsentObjectsViewModel
import ai.ciris.mobile.shared.viewmodels.NodeSwitcherViewModel
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
import ai.ciris.mobile.shared.viewmodels.NetworkViewModel
import ai.ciris.mobile.shared.viewmodels.SystemViewModel
import ai.ciris.mobile.shared.viewmodels.TelemetryViewModel
import ai.ciris.mobile.shared.viewmodels.UsersViewModel
import ai.ciris.mobile.shared.viewmodels.WiseAuthorityViewModel
import ai.ciris.mobile.shared.viewmodels.TicketsViewModel
import ai.ciris.mobile.shared.viewmodels.SchedulerViewModel
import ai.ciris.mobile.shared.viewmodels.ToolsViewModel
import ai.ciris.mobile.shared.viewmodels.EnvironmentInfoViewModel
import ai.ciris.mobile.shared.viewmodels.DataManagementViewModel
import ai.ciris.mobile.shared.viewmodels.LLMSettingsViewModel
import ai.ciris.mobile.shared.viewmodels.SkillImportViewModel
import ai.ciris.mobile.shared.viewmodels.SkillStudioViewModel
import ai.ciris.mobile.shared.viewmodels.ContactsViewModel
import ai.ciris.mobile.shared.ui.screens.graph.GraphMemoryScreen
import ai.ciris.mobile.shared.ui.screens.SkillStudioScreen
import ai.ciris.mobile.shared.ui.theme.BrightnessPreference
import ai.ciris.mobile.shared.ui.theme.ColorTheme
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.unit.dp
import androidx.compose.ui.Alignment
import androidx.compose.ui.text.font.FontWeight
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull
import kotlinx.coroutines.flow.filterNotNull
import kotlinx.coroutines.flow.first
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Menu
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
import ai.ciris.mobile.shared.ui.icons.*
import ai.ciris.mobile.shared.ui.components.CIRISIcons
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
     *
     * @param forceAccountChooser When true, clear any cached credential
     *   selection (Android: `CredentialManager.clearCredentialState()`,
     *   iOS: equivalent on the Apple/Google SDK in use) before launching
     *   the request so the user sees the full account picker instead of
     *   the auto-resumed last-account. Used by the 2.9.2 personal-install
     *   observer-blocked recovery flow.
     */
    fun onGoogleSignInRequested(
        forceAccountChooser: Boolean = false,
        onResult: (NativeSignInResult) -> Unit,
    )

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
    fun onGoogleSignInRequested(
        forceAccountChooser: Boolean = false,
        onResult: (NativeSignInResult) -> Unit,
    )

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
    /**
     * The **Python brain** (the cognitive/agent API). Everything the shared
     * [CIRISApiClient] addresses by default lives here: `/v1/agent`, `/v1/memory`,
     * `/v1/telemetry`, `/v1/system`, and the wizard's `/v1/setup/status` +
     * `/v1/setup/complete`.
     */
    apiBaseUrl: String = "http://127.0.0.1:8080",
    /**
     * The **ciris-server node** read API (node base :4242 → HTTP :4243). The
     * substrate surface — `/v1/federation`, `/v1/self`, `/v1/accord`, `/v1/health`,
     * `/v1/setup/root`, `/v1/setup/owned-nodes`, `/v1/setup/claim-remote`,
     * `/v1/self/upgrade-owner` — is served natively here and is NEVER proxied from
     * the brain. 8080 never fronts 4243, so a single base URL cannot address both:
     * conflating them is what produced the 2.9.13 first-run loop (FSD §0.1).
     */
    nodeBaseUrl: String = CIRISApiClient.LOCAL_NODE_URL,
    pythonRuntime: PythonRuntime = createPythonRuntime(),
    secureStorage: SecureStorage = createSecureStorage(),
    envFileUpdater: EnvFileUpdater = createEnvFileUpdater(),
    googleSignInCallback: GoogleSignInCallback? = null,
    purchaseLauncher: PurchaseLauncher? = null,
    deviceAttestationCallback: DeviceAttestationCallback? = null,
    onTokenUpdated: ((String) -> Unit)? = null,
    isHAAddonMode: Boolean = false
) {
    val TAG = "CIRISApp"

    // Log callback state on every recomposition
    platformLog(TAG, "[INIT] CIRISApp composable invoked - googleSignInCallback=${if (googleSignInCallback != null) "PRESENT (${googleSignInCallback.hashCode()})" else "NULL"}")

    val coroutineScope = rememberCoroutineScope()
    val apiClient = remember { CIRISApiClient(apiBaseUrl, accessToken) }

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

    // ─── The ONE node-vs-agent gate ──────────────────────────────────────────
    // Universal client: the same app runs against either a bare ciris-server
    // NODE (no brain) or a full CIRIS AGENT. clientMode is the single source of
    // truth — derived ONCE from the /v1/health capability probe (AGENT iff the
    // server reports a cognitive_state / a non-empty agent service map; else
    // NODE) and read everywhere that must branch (the 22 cognitive service
    // lights, "agent" wording, the WORK-state wait). null = not probed yet.
    // nodeVersion drives the non-blocking version-mismatch banner.
    var clientMode by remember { mutableStateOf<ai.ciris.mobile.shared.models.ClientMode?>(null) }
    var nodeVersion by remember { mutableStateOf<String?>(null) }
    val isAgentMode = clientMode?.isAgent ?: true  // default to agent wording until probed

    // Navigation state
    var currentScreen by remember { mutableStateOf<Screen>(Screen.Startup) }

    // Picker flow: when the user taps "Choose from Contacts" in Delegations,
    // we navigate to Contacts in picker mode and stash the result here so the
    // Delegations screen can consume it when the user presses back.
    var contactsPickerSourceScreen by remember { mutableStateOf<Screen?>(null) }
    var pickedDelegationKeyId by remember { mutableStateOf<String?>(null) }

    // Add-Federation-ID (catch-up) return target + one-shot guard. The guided
    // AddFederationIdScreen is reached two ways: manually from Manage Nodes
    // (return there) and auto-presented after login for a legacy owner with no
    // fed-ID (return to Interact). [addFederationIdReturnScreen] records which,
    // and [fedIdCatchupPrompted] makes the auto-present fire at most once per
    // session so returning to Interact doesn't re-trigger it.
    var addFederationIdReturnScreen by remember { mutableStateOf<Screen>(Screen.ManageNodes) }
    var fedIdCatchupPrompted by remember { mutableStateOf(false) }

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

            // Add Federation ID (catch-up) goes back to its origin: Manage Nodes
            // for the manual entry, Interact for the post-login auto-present.
            is Screen.AddFederationId -> addFederationIdReturnScreen

            // DataManagement and LLMSettings go back to Interact (main screen)
            is Screen.DataManagement -> Screen.Interact
            is Screen.LLMSettings -> Screen.Interact
            is Screen.VizSettings -> Screen.Settings

            // Federation sub-screens (reached from Global Commons hub tiles) go
            // back to the Global Commons layer hub. Phase B (2026-05-31): retarget
            // from Screen.Network → Screen.LayerGlobalCommons.
            is Screen.NetworkIdentity,
            is Screen.NetworkMap,
            is Screen.NetworkTrustGraph,
            is Screen.NetworkPeers,
            is Screen.NetworkInterfaces,
            is Screen.NetworkPaths,
            is Screen.NetworkAnnounces,
            is Screen.NetworkQueue,
            is Screen.NetworkDiagnostics,
            is Screen.NetworkContent -> Screen.LayerGlobalCommons
            // Peer detail (parameterised) goes back to the peer list, not the hub
            is Screen.NetworkPeerDetail -> Screen.NetworkPeers

            // Contacts goes back to the picker source (Delegations) or Interact
            is Screen.Contacts -> {
                val src = contactsPickerSourceScreen
                contactsPickerSourceScreen = null
                src ?: Screen.Interact
            }

            // All other screens go back to Interact (main screen)
            else -> Screen.Interact
        }
    }

    // First-run detection state
    var isFirstRun by remember { mutableStateOf<Boolean?>(null) }
    // The brain says it still needs setup and holds no config. Drives ClientMode.NODE
    // (see the gate below) and the "set up the agent" entry point in Settings, which
    // is the ONLY way out of node mode into a configured agent.
    var brainUnconfigured by remember { mutableStateOf(false) }
    var checkingFirstRun by remember { mutableStateOf(false) }

    // Post-setup RECONFIGURING hold. After /v1/setup/complete the runtime
    // reloads and the node-fold takes a while to rebind :4243, so the local
    // node is transiently DOWN. While this is set the startup / first-run /
    // Interact-poll logic must hold ONE stable "reconfiguring" state (re-poll
    // node reachability + ownership) instead of bouncing
    // Setup↔Startup↔Interact↔Login for minutes. Cleared once we land on
    // Login/Setup, or the rebind times out.
    var reconfiguring by remember { mutableStateOf(false) }

    // Login state
    var isLoginLoading by remember { mutableStateOf(false) }
    var loginStatusMessage by remember { mutableStateOf<String?>(null) }
    var loginErrorMessage by remember { mutableStateOf<String?>(null) }

    // 2.9.2 personal-install owner-hint recovery state. ownerHint is
    // refreshed lazily — once via GET /v1/auth/owner-hint when the
    // Login screen first renders, then again from the 403 detail body
    // if a sign-in attempt fails with auth_personal_install_observer_
    // blocked. observerBlocked = true means render the structured
    // recovery card instead of the small red error line.
    var ownerHint by remember { mutableStateOf<ai.ciris.mobile.shared.models.OwnerHint?>(null) }
    var observerBlocked by remember { mutableStateOf(false) }

    // Federation-ID-first startup. The owner's federation identity lives in this
    // device's LOCAL node (its keyring/substrate), NOT the app — the app holds no
    // keys and signs nothing. We probe the LOCAL node's self-key-record ONCE at
    // launch:
    //  - present → Login offers "Sign in as <key_id>"
    //  - absent  → Login offers "Create a new federation ID" (the wizard's
    //              FEDERATION_IDENTITY_SETUP step drives the local node).
    // federationProbed gates rendering so the Login section only appears once we
    // actually know which case we're in.
    var federationIdentityKeyId by remember { mutableStateOf<String?>(null) }
    var federationProbed by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        val keyId = try {
            apiClient.getSelfKeyRecord(
                ai.ciris.mobile.shared.api.CIRISApiClient.LOCAL_NODE_URL
            ).keyId
        } catch (e: Exception) {
            platformLog(TAG, "[INFO][federation] local-node self-key-record probe failed: ${e.message?.take(80)}")
            null
        }
        federationIdentityKeyId = keyId
        federationProbed = true
        platformLog(
            TAG,
            "[INFO][federation] startup probe: " +
                if (keyId != null) "existing identity key_id=$keyId" else "no federation identity yet",
        )
    }

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
    // Pass apiClient to ensure proper base URL (especially in HA addon mode)
    val setupViewModel: SetupViewModel = viewModel { SetupViewModel(apiClient) }
    // Set HA addon mode if running in Home Assistant addon context
    if (isHAAddonMode) {
        setupViewModel.setHAAddonMode(true)
    }
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
    val llmSettingsViewModel: LLMSettingsViewModel = viewModel {
        LLMSettingsViewModel(apiClient)
    }
    val telemetryViewModel: TelemetryViewModel = viewModel {
        TelemetryViewModel(apiClient)
    }
    val billingViewModel: BillingViewModel = viewModel {
        BillingViewModel(apiClient, apiBaseUrl)
    }
    val sessionsViewModel: SessionsViewModel = viewModel {
        SessionsViewModel(apiClient)
    }
    val adaptersViewModel: AdaptersViewModel = viewModel {
        AdaptersViewModel(apiClient, apiBaseUrl)
    }
    val wiseAuthorityViewModel: WiseAuthorityViewModel = viewModel {
        // secureStorage persists the notification dedupe set, so restarting the
        // app does not re-announce approvals the operator has already seen.
        WiseAuthorityViewModel(apiClient, secureStorage)
    }

    // ── HITL approval watch (#938) ──────────────────────────────────────────
    // Runs for the whole authenticated session, NOT per-screen. This is what
    // lets the nav badge and the "new approval arrived" notification exist at
    // all: an approval gate the operator only discovers by navigating to its
    // screen is a silent denial-of-service on the agent. Stopped on logout so a
    // signed-out client isn't polling an endpoint it cannot authenticate to.
    LaunchedEffect(currentAccessToken) {
        if (currentAccessToken != null) {
            wiseAuthorityViewModel.startApprovalWatch()
        } else {
            wiseAuthorityViewModel.stopApprovalWatch()
        }
    }
    // Drives the nav badge — see EpistemicSidebar(badges = ...) below.
    val pendingApprovalCount by wiseAuthorityViewModel.pendingApprovalCount.collectAsState()

    val servicesViewModel: ServicesViewModel = viewModel {
        ServicesViewModel(apiClient)
    }
    val serverConnectionViewModel: ServerConnectionViewModel = viewModel {
        ServerConnectionViewModel(apiClient, pythonRuntime, secureStorage)
    }
    // Node switcher (change #1) + consent-objects (change #3a)
    val nodeSwitcherViewModel: NodeSwitcherViewModel = viewModel {
        NodeSwitcherViewModel(apiClient)
    }
    // Catch-up: an existing logged-in owner whose local node has NO fed-ID
    // (legacy WA claim) must be auto-presented the guided Add Federation ID flow
    // after login — the startup owned-nodes projection ran UNAUTHENTICATED (or
    // pre-claim), so it couldn't know. We hook the FINAL landing screen
    // (Interact) rather than the token assignment so we don't race the several
    // login continuations that set currentScreen afterwards. Once authenticated
    // and on Interact, refresh owned-nodes and reuse the SAME condition Manage
    // Nodes uses to show the entry (ownerHasFedId == false: legacy owner, no
    // fed-ID; null = unknown → fail-closed, don't prompt). One-shot via
    // fedIdCatchupPrompted; naturally false once a fed-ID exists.
    LaunchedEffect(currentScreen, currentAccessToken) {
        if (currentScreen !is Screen.Interact) return@LaunchedEffect
        if (currentAccessToken == null || fedIdCatchupPrompted) return@LaunchedEffect
        try {
            nodeSwitcherViewModel.reload()
        } catch (e: Exception) {
            PlatformLogger.w(TAG, "[fed-id-catchup] owned-nodes reload failed: ${e.message}")
        }
        if (nodeSwitcherViewModel.ownerHasFedId.value == false) {
            fedIdCatchupPrompted = true
            addFederationIdReturnScreen = Screen.Interact
            PlatformLogger.i(TAG, "[fed-id-catchup] legacy owner has no fed-ID — auto-presenting Add Federation ID")
            currentScreen = Screen.AddFederationId
        }
    }
    val consentObjectsViewModel: ConsentObjectsViewModel = viewModel {
        ConsentObjectsViewModel(apiClient)
    }
    val delegationsViewModel: ai.ciris.mobile.shared.viewmodels.DelegationsViewModel = viewModel {
        ai.ciris.mobile.shared.viewmodels.DelegationsViewModel(apiClient)
    }
    // Reverse-quorum moderation (CC 0.5.1 §4.5.13) — drives the per-content
    // "raise with the community" affordance + 48h-window proposal flow.
    val moderationViewModel: ai.ciris.mobile.shared.viewmodels.ModerationViewModel = viewModel {
        ai.ciris.mobile.shared.viewmodels.ModerationViewModel(apiClient)
    }
    // The graded enforcement ladder (/v1/admin/*, tiers 0-4) — the owner's
    // recourse against an admitted-but-hostile peer. Preview -> commit-with-hash.
    val adminLadderViewModel: ai.ciris.mobile.shared.viewmodels.AdminLadderViewModel = viewModel {
        ai.ciris.mobile.shared.viewmodels.AdminLadderViewModel(apiClient)
    }
    val identityManagementViewModel: ai.ciris.mobile.shared.viewmodels.IdentityManagementViewModel = viewModel {
        ai.ciris.mobile.shared.viewmodels.IdentityManagementViewModel(apiClient)
    }
    val contactsViewModel: ContactsViewModel = viewModel {
        ContactsViewModel(apiClient)
    }
    // Delegate moderation duty — the co-scrubbed conferral of slash/moderate/review
    // onto another self, with the sub-delegation depth stated up front.
    val dutyConferralViewModel: ai.ciris.mobile.shared.viewmodels.DutyConferralViewModel = viewModel {
        ai.ciris.mobile.shared.viewmodels.DutyConferralViewModel(apiClient)
    }
    val accordViewModel: ai.ciris.mobile.shared.viewmodels.AccordViewModel = viewModel {
        ai.ciris.mobile.shared.viewmodels.AccordViewModel(apiClient)
    }
    val provisionAccordHolderViewModel:
        ai.ciris.mobile.shared.viewmodels.ProvisionAccordHolderViewModel = viewModel {
        ai.ciris.mobile.shared.viewmodels.ProvisionAccordHolderViewModel(apiClient)
    }
    val accordCeremonyViewModel: ai.ciris.mobile.shared.viewmodels.AccordCeremonyViewModel = viewModel {
        ai.ciris.mobile.shared.viewmodels.AccordCeremonyViewModel(apiClient)
    }
    val safetyViewModel: ai.ciris.mobile.shared.viewmodels.SafetyViewModel = viewModel {
        ai.ciris.mobile.shared.viewmodels.SafetyViewModel(apiClient)
    }
    val skillImportViewModel: SkillImportViewModel = viewModel {
        SkillImportViewModel(apiClient)
    }
    val skillStudioViewModel: SkillStudioViewModel = viewModel {
        SkillStudioViewModel(apiClient)
    }
    val auditViewModel: AuditViewModel = viewModel {
        AuditViewModel(apiClient)
    }
    val logsViewModel: LogsViewModel = viewModel {
        LogsViewModel(apiClient)
    }
    val transportViewModel: ai.ciris.mobile.shared.viewmodels.TransportViewModel = viewModel {
        ai.ciris.mobile.shared.viewmodels.TransportViewModel(apiClient)
    }
    val memoryViewModel: MemoryViewModel = viewModel {
        MemoryViewModel(apiClient)
    }
    val configViewModel: ConfigViewModel = viewModel {
        ConfigViewModel(apiClient)
    }
    // CIRISServer #346/#365 — the mesh-config plane, rendered at the head of
    // the Config screen and kept walled off from the node's own config plane.
    val meshConfigViewModel: ai.ciris.mobile.shared.viewmodels.MeshConfigViewModel = viewModel {
        ai.ciris.mobile.shared.viewmodels.MeshConfigViewModel(apiClient)
    }
    // CIRISServer #367 — the commons (reverse quorum).
    val commonsViewModel: ai.ciris.mobile.shared.viewmodels.CommonsViewModel = viewModel {
        ai.ciris.mobile.shared.viewmodels.CommonsViewModel(apiClient)
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
    val networkViewModel: NetworkViewModel = viewModel {
        NetworkViewModel(apiClient)
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

            // ─── Derive the ONE node-vs-agent gate (server now reachable) ────
            // Probe the NODE's /v1/health ONCE for its version (the mismatch
            // banner) and its role. The node's own health is deliberately bare —
            // `role: "fabric-node"`, `services: {}`, no cognitive_state — and
            // /v1/health is a substrate prefix that is never proxied, so the
            // AGENT enrichment can only come from the brain's /v1/system/health.
            // Probe that second and let it upgrade the gate: AGENT iff either
            // surface reports a cognitive_state / a non-empty service map.
            try {
                val nodeHealth = apiClient.getNodeHealth(nodeBaseUrl)
                nodeVersion = nodeHealth.version
                // Is the brain configured at all? A brain with no config runs 10 of
                // its 22 services to serve the wizard and reports cognitive_state
                // "SETUP" — which reads as an agent to a health probe, and is not
                // one. Only the brain can answer this, so ask before deciding.
                // Unreachable/failed probe => false, i.e. no downgrade: the gate
                // keeps its previous behaviour rather than guessing NODE.
                brainUnconfigured = runCatching {
                    val s = apiClient.getSetupStatus().data
                    s.setup_required && !s.has_env_file
                }.getOrDefault(false)
                var mode = ai.ciris.mobile.shared.models.clientModeFrom(
                    nodeHealth.cognitiveState, nodeHealth.serviceCount, brainUnconfigured
                )
                if (mode.isNode) {
                    // Bare node health — ask the brain whether it is running on top.
                    // brainUnconfigured is passed here too: without it this probe
                    // sees "SETUP" and promotes the half-started brain straight back
                    // to AGENT, undoing the gate above.
                    runCatching { apiClient.getSystemStatus() }
                        .onSuccess { sys ->
                            mode = ai.ciris.mobile.shared.models.clientModeFrom(
                                sys.cognitive_state, sys.services_total, brainUnconfigured
                            )
                        }
                        .onFailure { e ->
                            platformLog(TAG, "[DEBUG][gate] brain health absent (${e.message?.take(60)}) — bare NODE")
                        }
                }
                clientMode = mode
                // Node mode has no 22 cognitive service lights — drive the count
                // from the gate rather than the hardcoded agent default.
                startupViewModel.setClientMode(mode)
                // Push the gate into the shared API client so EVERY poller that
                // shares it stops calling AGENT-only endpoints (history / billing
                // / llm config / WA / adapters / capacity / agent audit / verify)
                // on a bare node — those 404/405 and just flood the log.
                apiClient.setClientMode(mode)
                platformLog(
                    TAG,
                    "[INFO][gate] clientMode=$mode (role=${nodeHealth.role}, " +
                        "cognitive_state=${nodeHealth.cognitiveState}, services=${nodeHealth.serviceCount}, " +
                        "version=${nodeHealth.version})",
                )
            } catch (e: Exception) {
                // Probe failed — leave the gate unset (defaults to agent wording).
                platformLog(TAG, "[WARN][gate] clientMode probe failed: ${e.message?.take(80)}")
            }

            // ─── Post-setup RECONFIGURING hold ──────────────────────────────
            // After /v1/setup/complete the runtime reloads and the node-fold
            // takes a while to rebind :4243, so the LOCAL node is transiently
            // DOWN. The stateless client (#125) keeps no token across a reload,
            // so the old "go straight to Interact" path 401-bounced to Login →
            // first-run → Setup and CYCLED for minutes. Instead HOLD a single
            // stable "reconfiguring" state and poll the local node until it is
            // back AND owned, then route to Login exactly once (the owner signs
            // in). Bounded (~4 min) so a dead rebind surfaces a clear timeout
            // rather than a spinner forever. (CIRISServer#276 shutdown_node()
            // will shorten the rebind; the bound is the safety net.)
            //
            // THREE states, not two (FSD §5). "Reachable-but-no-owner-binding"
            // is NOT the same as "fresh": a node owned the legacy way (ROOT
            // WaCert, no fed-ID owner-binding) is already configured, and
            // sending it back to Setup is the 2.9.13 loop — setup/root 409s and
            // we land right back here. Only FRESH goes to Setup.
            if (reconfiguring) {
                platformLog(TAG, "[INFO] Setup complete — holding reconfiguring state while the node restarts")

                // Keep the startup timer/spinner alive during the hold.
                startupViewModel.setKeepTimerAlive(true)
                startupViewModel.setStatus(LocalizationHelper.getString("mobile.status_reconfiguring"))

                val maxReconfigPolls = 240 // ~4 minutes at 1s cadence
                var reconfigPolls = 0
                var routed = false
                while (reconfigPolls < maxReconfigPolls) {
                    if (isNodeReachable(nodeBaseUrl)) {
                        val ownership = probeNodeOwnership(nodeBaseUrl)
                        if (ownership.isOwned) {
                            // Back + owned (claimed OR legacy-owned) → configured.
                            // The reload invalidated the setup token, so the owner
                            // must sign back in. A legacy-owned node is then
                            // re-rooted on a fed-ID by the Add Federation ID
                            // catch-up (POST /v1/self/upgrade-owner) — never by
                            // re-running the wizard.
                            platformLog(TAG, "[INFO] Node back + $ownership after reconfigure → Login")
                            isFirstRun = false
                            reconfiguring = false
                            startupViewModel.setKeepTimerAlive(false)
                            currentScreen = Screen.Login
                            routed = true
                            break
                        }
                        // Reachable, no ROOT WA and no owner-binding → genuinely fresh.
                        platformLog(TAG, "[INFO] Node back but FRESH after reconfigure → Setup (first-run)")
                        isFirstRun = true
                        reconfiguring = false
                        startupViewModel.setKeepTimerAlive(false)
                        currentScreen = Screen.Setup
                        routed = true
                        break
                    }
                    if (reconfigPolls % 10 == 0) {
                        // Re-assert the stable status (a stray poller may have
                        // overwritten it) — do NOT setPhase() here, that would
                        // cancel this LaunchedEffect.
                        startupViewModel.setStatus(LocalizationHelper.getString("mobile.status_reconfiguring"))
                    }
                    kotlinx.coroutines.delay(1000)
                    reconfigPolls++
                }

                if (!routed) {
                    // Rebind never completed — surface a clear timeout, not a bounce.
                    platformLog(TAG, "[ERROR] Node did not come back after reconfigure within timeout")
                    reconfiguring = false
                    startupViewModel.setKeepTimerAlive(false)
                    startupViewModel.onErrorDetected(
                        LocalizationHelper.getString("mobile.status_reconfiguring_timeout")
                    )
                }
                return@LaunchedEffect
            }

            // Check if this is first run via API
            // Keep timer running and show status while waiting for backend
            startupViewModel.setKeepTimerAlive(true)
            startupViewModel.setStatus(LocalizationHelper.getString("mobile.status_checking_setup"))

            isFirstRun = checkFirstRunStatus(
                apiBaseUrl = apiBaseUrl,
                nodeBaseUrl = nodeBaseUrl,
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
                // First run
                if (isHAAddonMode) {
                    // HA Addon mode - skip login, go directly to setup
                    // HA handles auth via SUPERVISOR_TOKEN
                    platformLog(TAG, "[INFO] First run in HA Addon mode, skipping login, navigating to Setup")
                    currentScreen = Screen.Setup
                } else {
                    // Normal mode - show login screen first
                    platformLog(TAG, "[INFO] First run detected, navigating to Login")
                    currentScreen = Screen.Login
                }
            } else if (isHAAddonMode) {
                // Not first run + HA addon mode - ingress handles auth via HTTP headers
                // No client-side token needed - backend extracts user from Ingress-Token header
                platformLog(TAG, "[INFO] Not first run in HA Addon mode - using ingress auth directly")
                startupViewModel.setStatus(LocalizationHelper.getString("mobile.status_ready"))
                interactViewModel.startPolling()
                currentScreen = HOME_SCREEN
            } else {
                // Not first run, normal mode - try to load stored token and check if valid/refresh if needed
                platformLog(TAG, "[INFO] Not first run, attempting to load and validate stored token")
                // NOTE: Don't change phase here - it would restart the LaunchedEffect and cancel this coroutine!
                // Just update the status message which is shown on the startup screen
                startupViewModel.setStatus(LocalizationHelper.getString("mobile.status_authenticating"))

                // #125 (stateless client): do NOT auto-restore a persisted session
                // token on boot. The token is kept in memory only for the live
                // session; a fresh launch requires re-login. Returning a null token
                // here routes through the existing "No stored token → Login" path
                // below, so the local-node login flow stays intact.
                val tokenResult = try {
                    kotlinx.coroutines.withTimeout(5000) {
                        Result.success<String?>(null)
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
                                startupViewModel.setStatus(
                                    if (isAgentMode) LocalizationHelper.getString("mobile.status_waiting_agent")
                                    else "Connecting to node..."
                                )

                                // Poll for WORK state with timeout
                                var agentReady = false
                                var inDegradedMode = false
                                var pollAttempts = 0
                                val maxPollAttempts = 150 // 30 seconds (150 * 200ms)
                                var lastState = "UNKNOWN"

                                if (!isAgentMode) {
                                    // NODE mode: no cognitive brain / WORK state to wait for.
                                    PlatformLogger.i(TAG, " NODE mode — skipping agent WORK-state wait")
                                    startupViewModel.setStatus("Node ready")
                                    agentReady = true
                                }

                                // Quick check for degraded mode via health endpoint (agent only)
                                if (isAgentMode) {
                                    try {
                                        val health = apiClient.getSystemHealth()
                                        if (health.degradedMode) {
                                            PlatformLogger.i(TAG, " Degraded mode detected - no working LLM provider")
                                            startupViewModel.setStatus("Running in limited mode (no LLM)")
                                            inDegradedMode = true
                                            agentReady = true  // Skip waiting for WORK state
                                        }
                                    } catch (e: Exception) {
                                        PlatformLogger.d(TAG, " Could not check degraded mode: ${e.message?.take(30)}")
                                    }
                                }

                                // Only wait for WORK state if not in degraded mode
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
                                    startupViewModel.setStatus(if (isAgentMode) "Agent ready!" else "Node ready!")
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
                                launch(kotlinx.coroutines.Dispatchers.Default) {
                                    try {
                                        PlatformLogger.i(TAG, " Running boot-time attestation check...")
                                        val verifyResult = apiClient.getVerifyStatus()
                                        PlatformLogger.i(TAG, " Boot attestation: loaded=${verifyResult.loaded}, maxLevel=${verifyResult.maxLevel}, " +
                                            "dns_us=${verifyResult.dnsUsOk}, dns_eu=${verifyResult.dnsEuOk}, https=${verifyResult.httpsUsOk}")
                                    } catch (e: Exception) {
                                        PlatformLogger.w(TAG, " Boot attestation failed: ${e.message}")
                                    }
                                }

                                currentScreen = HOME_SCREEN
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
            // ─── 2.9.4 — Epistemic Commons sidebar shell ─────────────────────
            // Pre-login screens (Startup/Login/Setup/ServerConnection) and the
            // Help utility have no NavSurface; for those the sidebar is hidden
            // and content fills the screen. After login, the sidebar replaces
            // the old top-bar dropdown nav as the SOLE navigation chrome.
            val activeSurface = screenToSurface(currentScreen)
            val showSidebar = currentScreen !is Screen.Startup &&
                currentScreen !is Screen.Login &&
                currentScreen !is Screen.Setup &&
                currentScreen !is Screen.ServerConnection
            // CIRIS Capacity Score state — hoisted from InteractViewModel so
            // HealthReputationScreen renders the same StateFlow that drives
            // the cell-viz dials. Anti-Goodhart constraint per FSD-002 §4.7:
            // operator-facing render only; never re-injected into the agent
            // context.
            val capacityForCard by interactViewModel.cellVizState.collectAsState()
            val uriHandler = androidx.compose.ui.platform.LocalUriHandler.current

            // Mobile-aware nav chrome. On narrow viewports (Material 3 compact
            // window class, <600.dp wide) the EpistemicSidebar is dismissed by
            // default and surfaced through a `ModalNavigationDrawer` — slides
            // in from the left, scrims the content, dismisses on tap-outside,
            // and self-closes when the user selects a destination. A persistent
            // top-left hamburger button (`btn_nav_drawer_open`) overlays the
            // content as the affordance to open the drawer. On wider viewports
            // the sidebar stays permanently in a `Row` alongside content — the
            // existing desktop / tablet layout. The 600.dp breakpoint matches
            // Material 3's WindowWidthSizeClass.Compact boundary.
            val drawerState = rememberDrawerState(DrawerValue.Closed)
            val drawerScope = rememberCoroutineScope()

            val mainScreenContent: @Composable (androidx.compose.ui.Modifier) -> Unit = { contentModifier ->
                androidx.compose.foundation.layout.Box(modifier = contentModifier) {
            when (currentScreen) {
            Screen.Startup -> {
                StartupScreen(viewModel = startupViewModel)
            }

            Screen.Login -> {
                platformLog(TAG, "[DEBUG][Screen.Login] Rendering login screen, googleSignInCallback=${if (googleSignInCallback != null) "PRESENT" else "NULL"}, isFirstRun=$isFirstRun")

                // FIRST RUN shows the Login screen on EVERY platform — including
                // desktop. Desktop has no native Google SDK, but ciris-server 0.5.165+
                // serves a browser sign-in the app collects over /v1/auth/oauth/handoff
                // (CIRISAgent#1028), so `googleSignInCallback == null` no longer means
                // "no OAuth possible" — it only means "use the browser flow." Auto-
                // skipping desktop straight to Setup buried the Google option the user
                // came for; now they land on Login and CHOOSE Google (browser) or local.
                LaunchedEffect(googleSignInCallback, isFirstRun) {
                    when {
                        isFirstRun == true && googleSignInCallback == null ->
                            platformLog(TAG, "[INFO][Screen.Login] Desktop first-run - showing Login (Google via browser handoff, or local)")
                        isFirstRun == true && googleSignInCallback != null ->
                            platformLog(TAG, "[INFO][Screen.Login] Mobile first-run - showing login for OAuth sign-in")
                        googleSignInCallback == null && isFirstRun == false ->
                            platformLog(TAG, "[INFO][Screen.Login] Desktop existing user - showing local login form")
                    }
                }

                // Probe which OAuth providers this build actually has credentials for.
                // A provider is present only when the node was provisioned with its
                // client_id + client_secret (the PKCE secret CI bakes into oauth.json).
                // Absent → grey the sign-in button rather than dangle a door that opens
                // onto redirect_uri_mismatch. Native Apple sign-in (iOS) doesn't ride
                // the node's browser-OAuth creds, so it stays live regardless.
                var googleOAuthAvailable by remember { mutableStateOf(true) }
                LaunchedEffect(Unit) {
                    val providerId = if (isIOS()) "apple" else "google"
                    runCatching { apiClient.getOAuthProviders(nodeBaseUrl) }
                        .onSuccess { providers ->
                            googleOAuthAvailable = isIOS() || providers.any { it.equals(providerId, ignoreCase = true) }
                            platformLog(TAG, "[INFO][OAuthProviders] available=$providers gate=$providerId enabled=$googleOAuthAvailable")
                        }
                        .onFailure { e ->
                            googleOAuthAvailable = isIOS()
                            platformLog(TAG, "[DEBUG][OAuthProviders] probe failed: ${e.message?.take(60)} → enabled=$googleOAuthAvailable")
                        }
                }

                // 2.9.2 — Fetch the personal-install owner hint each time
                // the Login screen renders. Always-fetch (rather than
                // gated on isFirstRun) because: (a) isFirstRun is a state
                // variable seeded at startup and not refreshed on
                // logout, so the post-setup → logout path would
                // otherwise never see a hint; (b) the server returns
                // {"owner_hint": null} on pre-setup devices, so the
                // pre-setup cost is one cheap API call and a null
                // assignment; (c) network blip / pre-2.9.2 backend /
                // multi-tenant server all degrade to a null hint and we
                // render the Login screen exactly like 2.9.1 did.
                LaunchedEffect(Unit) {
                    // PRESENTATION ONLY — the masked "welcome back" string. It
                    // gates nothing (FSD §5); ownership routing uses
                    // /v1/setup/owned-nodes. /v1/auth is node-native, so ask the
                    // NODE, not the brain.
                    runCatching { apiClient.getOwnerHint(nodeBaseUrl) }
                        .onSuccess { hint ->
                            ownerHint = hint
                            if (hint != null) {
                                platformLog(
                                    TAG,
                                    "[INFO][OwnerHint] Loaded: name=${hint.first_name} email=${hint.masked_email}"
                                )
                            } else {
                                platformLog(TAG, "[DEBUG][OwnerHint] null hint (pre-setup or non-personal-install)")
                            }
                        }
                        .onFailure { e ->
                            platformLog(TAG, "[DEBUG][OwnerHint] fetch failed: ${e.message?.take(60)}")
                        }
                }

                Box(modifier = Modifier.fillMaxSize()) {
                LoginScreen(
                    onGoogleSignIn = {
                        platformLog(TAG, "[INFO][onGoogleSignIn] Button click handler invoked, googleSignInCallback=${if (googleSignInCallback != null) "PRESENT" else "NULL"}")
                        if (googleSignInCallback != null) {
                            // Use platform-specific Google sign-in
                            platformLog(TAG, "[INFO][onGoogleSignIn] Callback is not null, calling onGoogleSignInRequested...")
                            isLoginLoading = true
                            loginStatusMessage = LocalizationHelper.getString("mobile.status_signing_in", mapOf("provider" to getOAuthProviderName()))
                            loginErrorMessage = null

                            // 2.9.3 — force the account picker every time. Default
                            // CredentialManager behavior auto-resumes the last-used
                            // Google account; on a personal-install device that's
                            // typically the WRONG account for users with multiple
                            // signed-in accounts on their device, and they had no
                            // affordance to switch (CIRISAgent#794 Bug B). Force-
                            // chooser costs one extra tap on the happy path and
                            // eliminates a whole class of "wrong account" stalls.
                            googleSignInCallback.onGoogleSignInRequested(
                                forceAccountChooser = true,
                            ) { result ->
                                platformLog(TAG, "[INFO][onGoogleSignIn] Got result from native sign-in: ${result::class.simpleName}")
                                isLoginLoading = false
                                loginStatusMessage = null

                                platformLog(TAG, "[DEBUG][onGoogleSignIn] Processing result: $result")
                                when (result) {
                                    is NativeSignInResult.Success -> {
                                        platformLog(TAG, "[INFO] Sign-in success: userId=${result.userId}, email=${result.email}")

                                        // Check if setup is already complete
                                        coroutineScope.launch {
                                            platformLog(TAG, "[INFO] Checking setup status at $apiBaseUrl...")
                                            val setupRequired = checkFirstRunStatus(apiBaseUrl, nodeBaseUrl) // No retries needed here - server is up
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

                                                    // Check for degraded mode first - skip WORK state wait if no LLM
                                                    loginStatusMessage =
                                                        if (isAgentMode) "Waiting for agent..." else "Connecting to node..."
                                                    var agentReady = false
                                                    var inDegradedMode = false
                                                    var pollAttempts = 0

                                                    if (!isAgentMode) {
                                                        // NODE mode: no cognitive brain / WORK state to wait for.
                                                        agentReady = true
                                                    }

                                                    // Quick check for degraded mode via health endpoint (agent only)
                                                    if (isAgentMode) {
                                                        try {
                                                            val health = apiClient.getSystemHealth()
                                                            if (health.degradedMode) {
                                                                PlatformLogger.i(TAG, " Degraded mode detected - no working LLM provider")
                                                                loginStatusMessage = "Running in limited mode (no LLM)"
                                                                inDegradedMode = true
                                                                agentReady = true  // Skip waiting for WORK state
                                                            }
                                                        } catch (e: Exception) {
                                                            PlatformLogger.d(TAG, " Could not check degraded mode: ${e.message?.take(30)}")
                                                        }
                                                    }

                                                    // Only wait for WORK state if not in degraded mode
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

                                                    if (inDegradedMode) {
                                                        loginStatusMessage = "Limited mode - configure LLM"
                                                    }

                                                    // Trigger data loading
                                                    PlatformLogger.i(TAG, " Triggering billingViewModel.loadBalance()...")
                                                    billingViewModel.loadBalance()
                                                    adaptersViewModel.fetchAdapters()
                                                    interactViewModel.startPolling() // Start polling now that token is set

                                                    isLoginLoading = false
                                                    loginStatusMessage = null
                                                    platformLog(TAG, "[INFO] Navigating to home (node) screen")
                                                    currentScreen = HOME_SCREEN
                                                } catch (e: Exception) {
                                                    platformLog(TAG, "[ERROR] Token exchange failed: ${e::class.simpleName}: ${e.message}")
                                                    isLoginLoading = false
                                                    loginStatusMessage = null
                                                    // 2.9.2 — detect the personal-install
                                                    // observer-block 403 and route through
                                                    // the structured recovery card. The
                                                    // server error body looks like:
                                                    //   Token exchange failed (403): {"detail":{"code":"auth_personal_install_observer_blocked","message":"...","owner_hint":{...}}}
                                                    val errText = e.message ?: ""
                                                    if (errText.contains("auth_personal_install_observer_blocked")) {
                                                        observerBlocked = true
                                                        // 2.9.3 — keep the raw server message as a
                                                        // fallback (was cleared to null in 2.9.2,
                                                        // which produced a silent failure when the
                                                        // recovery card also failed to render — see
                                                        // CIRISAgent#794). The Login screen renders
                                                        // the card on observerBlocked AND surfaces
                                                        // errorMessage in the else branch if for any
                                                        // reason the card doesn't render.
                                                        loginErrorMessage =
                                                            "This device is set up for a different account. Choose a different Google account or reset the device."
                                                        val parsedHint = ai.ciris.mobile.shared.utils.parseOwnerHintFromErrorBody(errText)
                                                        if (parsedHint != null) {
                                                            ownerHint = parsedHint
                                                            platformLog(TAG, "[INFO] Observer-blocked recovery — owner_hint=${parsedHint.first_name}/${parsedHint.masked_email}")
                                                        } else {
                                                            // Bugged-install case: server returned the
                                                            // 403 but no owner_hint (no SYSTEM_ADMIN
                                                            // exists). The recovery card renders with
                                                            // a generic body — see ObserverBlocked-
                                                            // RecoveryCard. The setup-status check in
                                                            // 2.9.3 should also auto-route bugged
                                                            // installs back to setup, but the card +
                                                            // Reset device acts as the manual escape.
                                                            platformLog(TAG, "[WARN] Observer-blocked with no owner_hint — bugged install (#794)?")
                                                        }
                                                    } else {
                                                        loginErrorMessage = "Token exchange failed: ${e.message}"
                                                    }
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
                        // DESKTOP: no native Google SDK, so sign in through the
                        // BROWSER against this node's OAuth front door. Until the
                        // node minted a session on callback there was nothing for
                        // this process to hold, so desktop offered local login
                        // only and this branch just said "not available".
                        //
                        // Two processes, one sign-in: we generate a nonce, open the
                        // browser with it, and poll until the node hands the bearer
                        // over. 204 means NOT YET, which is why the loop keeps
                        // going instead of treating a quiet answer as failure.
                        platformLog(TAG, "[INFO][onGoogleSignIn] desktop browser flow (no native SDK)")
                        isLoginLoading = true
                        loginErrorMessage = null
                        loginStatusMessage = LocalizationHelper.getString("auth.browser_signin.waiting")
                        val nonce = buildString {
                            val alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
                            repeat(32) { append(alphabet[kotlin.random.Random.nextInt(alphabet.length)]) }
                        }
                        val signInUrl = apiClient.oauthBrowserLoginUrl("google", nonce, nodeBaseUrl)
                        // Log the URL we hand the browser. A sign-in completed in
                        // some OTHER tab — one opened earlier at the plain
                        // /login URL — carries no app_nonce, parks nothing, and
                        // leaves this poll waiting forever while the node reports
                        // a perfectly successful sign-in. Without this line the
                        // two are indistinguishable from the client side.
                        platformLog(TAG, "[INFO][onGoogleSignIn] opening browser: $signInUrl")
                        openUrlInBrowser(signInUrl)
                        coroutineScope.launch {
                            // ~3 minutes: long enough for a real sign-in with a
                            // password manager and 2FA, short enough that an
                            // abandoned attempt does not spin forever.
                            var token: ai.ciris.mobile.shared.models.OAuthHandoff? = null
                            var attempts = 0
                            while (token == null && attempts < 90) {
                                kotlinx.coroutines.delay(2000)
                                attempts++
                                // After ~20s our own tab has had its chance;
                                // accept a sign-in that completed in a stray
                                // tab rather than spin while the node holds a
                                // perfectly good session.
                                token = apiClient.collectOAuthHandoff(
                                    nonce,
                                    nodeBaseUrl,
                                    allowUnbound = attempts > 10,
                                )
                                // Heartbeat every ~20s: "still waiting" must be
                                // visible, or a stalled flow looks like a crashed one.
                                if (token == null && attempts % 10 == 0) {
                                    platformLog(TAG, "[INFO][onGoogleSignIn] still waiting for the browser (${attempts * 2}s)")
                                }
                            }
                            isLoginLoading = false
                            loginStatusMessage = null
                            val collected = token
                            if (collected == null) {
                                // Say WHICH failure this is. "Sign-in failed" would
                                // cover both "you closed the tab" and "the node is
                                // broken", and only one of those is the user's to fix.
                                loginErrorMessage =
                                    LocalizationHelper.getString("auth.browser_signin.timed_out")
                                platformLog(TAG, "[WARN][onGoogleSignIn] no hand-off after ${attempts * 2}s. If you signed in successfully, the browser tab was probably an OLD one opened without ?app_nonce= — close stray CIRIS sign-in tabs and use the button again.")
                            } else {
                                platformLog(TAG, "[INFO][onGoogleSignIn] desktop browser sign-in collected a session")
                                currentAccessToken = collected.accessToken
                                apiClient.setAccessToken(collected.accessToken)
                                secureStorage.saveAccessToken(collected.accessToken)
                                onTokenUpdated?.invoke(collected.accessToken)
                                if (isFirstRun == true) {
                                    // Hand the identity to the wizard: it derives the
                                    // federation-ID name from <provider>-<subject>, so
                                    // arriving with only a bearer would put the user
                                    // back to inventing a unique name by hand.
                                    setupViewModel.setGoogleAuthState(
                                        isAuth = true,
                                        // Forward the provider's ID token when the node
                                        // sends one (CIRISServer#434, ciris-server
                                        // 0.5.177+). This used to be a hard null, which
                                        // left isGoogleAuth=true with googleIdToken=null
                                        // — and CIRIS_PROXY sends this token AS the LLM
                                        // api_key, so a Google-signed-in desktop user
                                        // could not choose the proxy at all.
                                        idToken = collected.idToken,
                                        email = collected.email,
                                        userId = collected.externalId,
                                        provider = collected.provider,
                                    )
                                    currentScreen = Screen.Setup
                                } else {
                                    interactViewModel.startPolling()
                                    currentScreen = HOME_SCREEN
                                }
                            }
                        }
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
                                val cirisToken = withContext(Dispatchers.Default) {
                                    val authResponse = apiClient.login(username, password)
                                    authResponse.access_token
                                }

                                // SAY WHICH TOKEN THIS IS.
                                //
                                // This read "Got CIRIS access token", copied from the
                                // OAuth exchange path where that is true. Here it is a
                                // LOCAL session bearer from username/password — no
                                // OAuth, no CIRIS services. A user reading his own log
                                // reasonably concluded he had a CIRIS-services token he
                                // had never signed up for.
                                platformLog(TAG, "[INFO] Local sign-in session token: ${cirisToken.take(8)}...${cirisToken.takeLast(4)}")

                                // Set the token on the API client
                                apiClient.setAccessToken(cirisToken)
                                currentAccessToken = cirisToken
                                apiClient.logTokenState()

                                // Save to secure storage
                                secureStorage.saveAccessToken(cirisToken)
                                    .onSuccess { PlatformLogger.i(TAG, " CIRIS token saved to secure storage") }
                                    .onFailure { e -> PlatformLogger.w(TAG, " Failed to save token: ${e.message}") }

                                // Check for degraded mode first - skip WORK state wait if no LLM
                                PlatformLogger.i(TAG, " Local login successful, waiting for ${if (isAgentMode) "agent" else "node"}...")
                                loginStatusMessage =
                                    if (isAgentMode) "Waiting for agent..." else "Connecting to node..."
                                var agentReady = false
                                var inDegradedMode = false
                                var pollAttempts = 0

                                if (!isAgentMode) {
                                    // NODE mode: no cognitive brain / WORK state to wait for.
                                    agentReady = true
                                }

                                // Quick check for degraded mode via health endpoint (agent only)
                                if (isAgentMode) {
                                    try {
                                        val health = apiClient.getSystemHealth()
                                        if (health.degradedMode) {
                                            PlatformLogger.i(TAG, " Degraded mode detected - no working LLM provider")
                                            loginStatusMessage = "Running in limited mode (no LLM)"
                                            inDegradedMode = true
                                            agentReady = true  // Skip waiting for WORK state
                                        }
                                    } catch (e: Exception) {
                                        PlatformLogger.d(TAG, " Could not check degraded mode: ${e.message?.take(30)}")
                                    }
                                }

                                // Only wait for WORK state if not in degraded mode
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

                                if (inDegradedMode) {
                                    loginStatusMessage = "Limited mode - configure LLM"
                                }

                                // Trigger data loading
                                billingViewModel.loadBalance()
                                adaptersViewModel.fetchAdapters()
                                interactViewModel.startPolling()

                                isLoginLoading = false
                                loginStatusMessage = null
                                currentScreen = HOME_SCREEN
                            } catch (e: Exception) {
                                platformLog(TAG, "[ERROR] Local login failed: ${e::class.simpleName}: ${e.message}")
                                isLoginLoading = false
                                loginStatusMessage = null
                                loginErrorMessage = "Login failed: ${e.message}"
                            }
                        }
                    },
                    onServerSettings = { currentScreen = Screen.ServerConnection },
                    onChooseDifferentAccount = {
                        // 2.9.2 recovery action — re-run the native sign-in
                        // with the account chooser forced open. On Android
                        // the GoogleSignInCallback impl calls
                        // CredentialManager.clearCredentialState() before
                        // launching the request, so the user sees Google's
                        // multi-account picker instead of the cached
                        // account. iOS uses the same callback path.
                        platformLog(TAG, "[INFO][onChooseDifferentAccount] Clearing observerBlocked + re-launching sign-in with account picker")
                        observerBlocked = false
                        loginErrorMessage = null
                        if (googleSignInCallback != null) {
                            isLoginLoading = true
                            loginStatusMessage = LocalizationHelper.getString(
                                "mobile.status_signing_in",
                                mapOf("provider" to getOAuthProviderName())
                            )
                            // The forceAccountChooser flag tells the platform
                            // impl to call clearCredentialState() before the
                            // sign-in request — see GoogleSignInCallback
                            // platform implementations.
                            googleSignInCallback.onGoogleSignInRequested(
                                forceAccountChooser = true,
                            ) { result ->
                                isLoginLoading = false
                                loginStatusMessage = null
                                if (result is NativeSignInResult.Error) {
                                    loginErrorMessage = "Sign-in failed: ${result.message}"
                                }
                                // Success path is handled by the original
                                // onGoogleSignIn handler when the user runs
                                // the regular flow next time; for the
                                // recovery dialog we just reset state.
                            }
                        }
                    },
                    onResetSetup = {
                        // 2.9.2 — graceful escape hatch: clear local state
                        // and bounce to setup so a legitimate new owner
                        // can claim the device. Mirrors the existing
                        // settings-screen reset flow.
                        platformLog(TAG, "[INFO][onResetSetup] User initiated device reset from observer-blocked recovery")
                        observerBlocked = false
                        loginErrorMessage = null
                        interactViewModel.resetState()
                        settingsViewModel.logout {
                            currentAccessToken = null
                            startupViewModel.retry()
                            checkingFirstRun = false
                            currentScreen = Screen.Startup
                        }
                    },
                    connectionStatus = serverConnectionViewModel.connectionStatus.collectAsState().value,
                    isLoading = isLoginLoading,
                    statusMessage = loginStatusMessage,
                    errorMessage = loginErrorMessage,
                    ownerHint = ownerHint,
                    observerBlocked = observerBlocked,
                    // Start the local form EXPANDED only where there is no sign-in
                    // alternative. A null callback used to mean exactly that — but desktop
                    // now has the node's browser flow (#1028), and forcing the form there
                    // hides a Google button whose handler is already fully implemented.
                    // That is what shipped in 2.9.14. wasmJs and anything else passing
                    // null keeps the previous behaviour.
                    showLocalLoginForm = (
                        googleSignInCallback == null &&
                            !ai.ciris.mobile.shared.platform.isDesktop() &&
                            isFirstRun == false
                    ),
                    isFirstRun = isFirstRun ?: true,
                    // Grey the sign-in button when this build has no OAuth creds wired
                    // (probed above from the node's /v1/auth/oauth/providers).
                    googleOAuthAvailable = googleOAuthAvailable,
                    // NOTE: no fedID sign-in option here by design — the fedID is the
                    // founder's identity, minted in the first-run wizard and accessed
                    // ONLY via the associated user-account session (log in below). It
                    // is never a credential-less login. First-run users are auto-routed
                    // to the setup wizard upstream (isFirstRun handling).
                )

                    // Non-blocking node-vs-client VERSION-MISMATCH banner. The node
                    // reports its version in /v1/health; when it differs materially
                    // from the app's build (CLIENT_VERSION) we warn but never block —
                    // overlaid at the top so it never disturbs the login layout.
                    if (ai.ciris.mobile.shared.models.isVersionMismatch(nodeVersion)) {
                        VersionMismatchBanner(
                            nodeVersion = nodeVersion ?: "",
                            clientVersion = ai.ciris.mobile.shared.models.CLIENT_VERSION,
                            modifier = Modifier.align(Alignment.TopCenter)
                        )
                    }
                }
            }

            Screen.Setup -> {
                platformLog(TAG, "[DEBUG][Screen.Setup] Rendering setup screen")
                SetupScreen(
                    viewModel = setupViewModel,
                    apiClient = apiClient,
                    // Provide the one-time ownership CLAIM PIN / NodeCode captured
                    // from the LOCAL node's boot banner so the setup flow can
                    // self-claim ownership of this node on COMPLETE. PythonRuntime
                    // latches these asynchronously from the node's boot output
                    // (console stream + boot-log FILE fallback), so the banner can
                    // arrive slightly AFTER the COMPLETE step fires. AWAIT the PIN
                    // with a bounded timeout rather than snapshotting a value that
                    // may still be null at the instant COMPLETE runs.
                    claimPinProvider = {
                        // 1) banner snapshot (if the boot-time latch caught it),
                        // 2) DURABLE <home>/claim_pin file read on-demand — RACE-FREE: the node
                        //    writes claim_pin a few seconds AFTER health answers, so a boot-time
                        //    latch can miss it, but by claim time the file is present,
                        // 3) last resort, await the banner flow with a bounded timeout.
                        pythonRuntimeProtocol.localClaimPin.value
                            ?: pythonRuntimeProtocol.readLocalClaimPin()
                            ?: withTimeoutOrNull(20_000L) {
                                pythonRuntimeProtocol.localClaimPin
                                    .filterNotNull()
                                    .first { it.isNotBlank() }
                            }
                    },
                    // NodeCode may legitimately never come via the banner (the app
                    // then fetches it over HTTP in claimLocalNodeOwnership), so we
                    // only take a snapshot here — no wait — to avoid a needless
                    // stall on the common banner-omits-NodeCode path.
                    nodeCodeProvider = { pythonRuntimeProtocol.localNodeCode.value },
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
                                    val cirisToken = withContext(Dispatchers.Default) {
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
                                        val cirisToken = withContext(Dispatchers.Default) {
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

                            // Reload the node switcher now that the local node is
                            // self-claimed + owned. Its owned-nodes projection ran at
                            // startup when the node was still UNCLAIMED (→ 0 nodes), so
                            // without this reload the just-claimed local node never
                            // appears in the list until an app restart.
                            try {
                                nodeSwitcherViewModel.reload()
                            } catch (e: Exception) {
                                PlatformLogger.w(TAG, "[setup] node-switcher reload after claim failed: ${e.message}")
                            }

                            // After setup completes, Python resumes and starts remaining 12 services
                            // Go back to StartupScreen to show the remaining services starting
                            // Reset the startup phase so it re-polls for services
                            startupViewModel.resetForResume()
                            checkingFirstRun = false  // Allow re-check after startup completes
                            // Hold a STABLE reconfiguring state while the runtime
                            // reloads and :4243 rebinds — no Setup↔Startup↔Interact↔Login cycle.
                            reconfiguring = true
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
                val forceClassicViz by settingsViewModel.forceClassicViz.collectAsState()
                val cellVizConfig by settingsViewModel.cellVizConfig.collectAsState()
                platformLog(TAG, "[CIRISApp] >>> liveBackgroundEnabled=$liveBackgroundEnabled, apiClient=${if (apiClient != null) "present" else "NULL"}")

                // On compact viewports the dropdown-menu top bar is fully
                // redundant with the left-nav drawer (every category routes
                // through the same surfaces). Drop the entire top bar there
                // so the screen content (signet overlay + badges + state +
                // emergency-stop button — all already rendered inside
                // `InteractScreen`) becomes the visible top chrome. On
                // tablet/desktop where the sidebar is permanent and there's
                // no overlay button, keep the full CIRISTopBar for now.
                val showTopBar = !ai.ciris.mobile.shared.ui.nav.LocalIsCompactWindow.current
                Scaffold(
                    topBar = {
                        if (showTopBar) {
                            CIRISTopBar(
                                onSettingsClick = { currentScreen = Screen.Settings },
                                onLLMSettingsClick = { currentScreen = Screen.LLMSettings },
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
                                    // Cancel InteractViewModel polling first — otherwise it keeps polling
                                    // against the about-to-be-revoked token, fires a 401, and
                                    // TokenManager.on401Error races the user's next Sign-In tap → bounce.
                                    interactViewModel.resetState()
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
                    }
                ) { paddingValues ->
                    // Only apply top padding from Scaffold - InteractScreen handles
                    // bottom insets (keyboard + nav bar) via windowInsetsPadding

                    InteractScreen(
                        viewModel = interactViewModel,
                        moderationViewModel = moderationViewModel,
                        onNavigateBack = { /* Already at root */ },
                        onSessionExpired = {
                            if (reconfiguring) {
                                // During the post-setup node reload the token is
                                // EXPECTED to be invalid; the reconfiguring hold
                                // owns navigation. Don't flash Interact then
                                // bounce to Login here — that's the cycle.
                                platformLog(TAG, "[INFO] Session-expired suppressed — reconfiguring hold owns navigation")
                            } else {
                                // Navigate to login screen when session expires
                                platformLog(TAG, "[INFO] Session expired - navigating to login")
                                // Cancel polling before clearing token so a stale 401 doesn't
                                // re-enter via TokenManager and race the next sign-in attempt.
                                interactViewModel.resetState()
                                currentAccessToken = null
                                // Clear stored tokens asynchronously
                                coroutineScope.launch {
                                    secureStorage.deleteAccessToken()
                                }
                                currentScreen = Screen.Login
                            }
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
                            platformLog(TAG, "[INFO] Opening Settings page")
                            currentScreen = Screen.Settings
                        },
                        onOpenLLMSettings = {
                            platformLog(TAG, "[INFO] Opening LLM Settings page from LLM indicator")
                            currentScreen = Screen.LLMSettings
                        },
                        onOpenWiseAuthority = {
                            platformLog(TAG, "[INFO] Opening WiseAuthority page for deferrals")
                            currentScreen = Screen.WiseAuthority
                        },
                        // Node switcher (change #1) + consent-objects (change #3a)
                        nodeSwitcherViewModel = nodeSwitcherViewModel,
                        onAddNode = {
                            platformLog(TAG, "[INFO] Opening ServerConnection to add/edit a node")
                            currentScreen = Screen.ServerConnection
                        },
                        onClaimNode = {
                            platformLog(TAG, "[INFO] Opening ClaimNode to claim a node by NodeCode + PIN")
                            currentScreen = Screen.ClaimNode
                        },
                        consentObjectsViewModel = consentObjectsViewModel,
                        apiClient = apiClient,
                        liveBackgroundEnabled = liveBackgroundEnabled,
                        forceClassicViz = forceClassicViz,
                        colorTheme = colorTheme,
                        isDarkMode = isDarkMode,
                        cellVizConfig = cellVizConfig,
                        modifier = Modifier.padding(top = paddingValues.calculateTopPadding())
                    )
                }
            }

            Screen.Settings -> {
                SettingsScreen(
                    viewModel = settingsViewModel,
                    apiClient = apiClient,
                    secureStorage = secureStorage,
                    brainUnconfigured = brainUnconfigured,
                    onSetUpAgent = {
                        platformLog(TAG, "[INFO] user chose to set up the agent from node mode → Screen.Setup")
                        currentScreen = Screen.Setup
                    },
                    onNavigateBack = { currentScreen = Screen.Interact },
                    onLogout = {
                        PlatformLogger.i("CIRISApp", "[onLogout] User initiated logout")
                        // Cancel InteractViewModel polling before token revocation — see
                        // matching guard in nav-bar onLogoutClick for rationale.
                        interactViewModel.resetState()
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
                    },
                    onNavigateToLLMSettings = {
                        PlatformLogger.i("CIRISApp", "[Settings] Navigating to LLM Settings")
                        currentScreen = Screen.LLMSettings
                    },
                    onNavigateToVizSettings = {
                        PlatformLogger.i("CIRISApp", "[Settings] Navigating to Viz Settings")
                        currentScreen = Screen.VizSettings
                    },
                    // Consent-objects belong under Settings (not the Interact
                    // surface). Routes to the consent management surface.
                    onNavigateToConsent = {
                        PlatformLogger.i("CIRISApp", "[Settings] Navigating to Manage Consent")
                        currentScreen = Screen.ManageConsent
                    }
                )
            }

            Screen.LLMSettings -> {
                LLMSettingsScreen(
                    viewModel = settingsViewModel,
                    llmViewModel = llmSettingsViewModel,
                    apiClient = apiClient,
                    secureStorage = secureStorage,
                    onNavigateBack = {
                        PlatformLogger.i(TAG, "[Screen.LLMSettings] Navigating back to Interact")
                        currentScreen = Screen.Interact
                    }
                )
            }

            Screen.VizSettings -> {
                VizSettingsScreen(
                    viewModel = settingsViewModel,
                    onBack = {
                        PlatformLogger.i(TAG, "[Screen.VizSettings] Navigating back to Settings")
                        currentScreen = Screen.Settings
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
                    onReauthAdapter = { adapterType, authStepId ->
                        PlatformLogger.i("CIRISApp", "[Screen.Adapters] Re-auth for: $adapterType, authStepId=$authStepId")
                        adaptersViewModel.reauthAdapter(adapterType, authStepId)
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
                    onSkillStudio = {
                        PlatformLogger.i("CIRISApp", "[Screen.Adapters] Skill Studio requested")
                        currentScreen = Screen.SkillStudio
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
                val approvals by wiseAuthorityViewModel.approvals.collectAsState()
                val budgetCapability by wiseAuthorityViewModel.budgetCapability.collectAsState()
                val selectedBudgetState by wiseAuthorityViewModel.selectedBudgetState.collectAsState()

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
                    },
                    approvals = approvals,
                    budgetCapability = budgetCapability,
                    // Grant + spend ledger + remaining trust envelope for the
                    // open approval, fetched from GET /v1/tickets/{id}/budget.
                    // The headroom is the same number the spend gate applies;
                    // null when no wallet adapter is loaded, in which case the
                    // row is simply omitted.
                    selectedBudgetState = selectedBudgetState,
                    onApprovalOpened = { approvalId ->
                        wiseAuthorityViewModel.loadBudgetState(approvalId)
                    },
                    onApprovalClosed = { wiseAuthorityViewModel.clearBudgetState() },
                    onGrantBudget = { approvalId, amount, currency, expiryHours, reason, promote, overGrantConfirmed ->
                        PlatformLogger.i(
                            "CIRISApp",
                            "[Screen.WiseAuthority] Granting budget $amount $currency on $approvalId " +
                                "(promote=$promote, overGrantConfirmed=$overGrantConfirmed)"
                        )
                        wiseAuthorityViewModel.grantBudget(
                            approvalId = approvalId,
                            amount = amount,
                            currency = currency,
                            purpose = reason.ifBlank {
                                approvals.firstOrNull { it.id == approvalId }
                                    ?.requestedBudget?.purpose.orEmpty()
                            },
                            expiresInHours = expiryHours,
                            promote = promote,
                            overGrantConfirmed = overGrantConfirmed,
                        )
                    },
                    onPromoteProposal = { approvalId, note ->
                        PlatformLogger.i("CIRISApp", "[Screen.WiseAuthority] Promoting proposal $approvalId")
                        wiseAuthorityViewModel.promoteProposal(approvalId, note.ifBlank { null })
                    },
                    onRejectProposal = { approvalId, reason ->
                        PlatformLogger.i("CIRISApp", "[Screen.WiseAuthority] Rejecting proposal $approvalId")
                        wiseAuthorityViewModel.rejectProposal(approvalId, reason.ifBlank { null })
                    },
                    onDeferProposal = { approvalId, note ->
                        PlatformLogger.i("CIRISApp", "[Screen.WiseAuthority] Deferring proposal $approvalId")
                        wiseAuthorityViewModel.deferProposal(approvalId, note.ifBlank { null })
                    },
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
                    onNavigateBack = { currentScreen = Screen.Interact },
                    // Reflect the existing backend mode: in node mode the "Agent"
                    // log source is disabled/grayed in the source dropdown.
                    isNodeMode = !isAgentMode
                )
            }

            Screen.Transport -> {
                val transportState by transportViewModel.state.collectAsState()

                DisposableEffect(Unit) {
                    PlatformLogger.i(TAG, "[Screen.Transport] Loading transports")
                    transportViewModel.startPolling()
                    onDispose {
                        PlatformLogger.i(TAG, "[Screen.Transport] Disposing")
                        transportViewModel.stopPolling()
                    }
                }

                LaunchedEffect(transportState.error) {
                    transportState.error?.let { error ->
                        PlatformLogger.e(TAG, "[Screen.Transport] error: $error")
                    }
                }

                TransportScreen(
                    state = transportState,
                    onRefresh = { transportViewModel.refresh() },
                    onEnabledChange = { transportViewModel.updateEnabled(it) },
                    onSerialPortChange = { transportViewModel.updateSerialPort(it) },
                    onFrequencyChange = { transportViewModel.updateFrequencyHz(it) },
                    onBandwidthChange = { transportViewModel.updateBandwidthHz(it) },
                    onSpreadingFactorChange = { transportViewModel.updateSpreadingFactor(it) },
                    onCodingRateChange = { transportViewModel.updateCodingRate(it) },
                    onTxPowerChange = { transportViewModel.updateTxPowerDbm(it) },
                    onApply = { transportViewModel.applyRadioConfig() },
                    isNodeMode = !isAgentMode,
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
                    onNavigateBack = { currentScreen = Screen.Interact },
                    meshConfigViewModel = meshConfigViewModel,
                )
            }

            Screen.Commons -> {
                ai.ciris.mobile.shared.ui.screens.commons.CommonsScreen(
                    viewModel = commonsViewModel,
                    onBack = { currentScreen = Screen.Interact },
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
                // The operator surface (GET /v1/node/state) — CIRISServer#369/#370.
                val nodeStateReadout by systemViewModel.nodeState.collectAsState()

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
                    onNavigateBack = { currentScreen = Screen.Interact },
                    nodeState = nodeStateReadout
                )
            }

            Screen.ServerConnection -> {
                PlatformLogger.d(TAG, "[Screen.ServerConnection] Rendering server connection screen")
                ServerConnectionScreen(
                    viewModel = serverConnectionViewModel,
                    onBack = { currentScreen = Screen.Interact }
                )
            }

            Screen.ClaimNode -> {
                // Last UI piece of the founder flow: enter a node's NodeCode +
                // claim PIN → connect/identity-pin → claim SYSTEM_ADMIN. Drives
                // NodeSwitcherViewModel.connectByNodeCode → claimAdmin. Reuses
                // the long-lived hardware federation identity probed at startup.
                PlatformLogger.d(TAG, "[Screen.ClaimNode] Rendering claim-ownership screen")
                ClaimNodeScreen(
                    viewModel = nodeSwitcherViewModel,
                    onBack = { currentScreen = Screen.Interact },
                    // Claim a second node (A then B): clear bootstrap is handled
                    // inside the screen; staying on ClaimNode re-renders fresh.
                    onClaimedAnother = { currentScreen = Screen.ClaimNode },
                    // Consent-objects card lives on the Interact main page.
                    onProceedToConsent = { currentScreen = Screen.Interact },
                )
            }

            Screen.ManageNodes -> {
                // First-class node-management CRUD surface (Manage group). Reuses
                // NodeSwitcherViewModel for list/add/edit/remove/switch; routes to
                // the ClaimNode flow for owner-binding.
                PlatformLogger.d(TAG, "[Screen.ManageNodes] Rendering manage-nodes screen")
                ManageNodesScreen(
                    viewModel = nodeSwitcherViewModel,
                    onBack = { currentScreen = Screen.Interact },
                    onClaimNode = { currentScreen = Screen.ClaimNode },
                    // Catch-up: legacy owner (no fed-ID) → guided Add Federation ID.
                    // Manual entry returns to Manage Nodes (vs. the login auto-
                    // present, which returns to Interact).
                    onAddFederationId = {
                        addFederationIdReturnScreen = Screen.ManageNodes
                        currentScreen = Screen.AddFederationId
                    },
                    // Graph-view data sources: delegations (you → agent),
                    // consent:replication (node ↔ node), plus the shared API
                    // client that powers the live neural background.
                    delegationsViewModel = delegationsViewModel,
                    consentObjectsViewModel = consentObjectsViewModel,
                    apiClient = apiClient,
                )
            }

            Screen.AddFederationId -> {
                // Catch-up guided flow for an existing logged-in owner with NO
                // fed-ID: name → announce decision → confirm → upgrade-owner.
                PlatformLogger.d(TAG, "[Screen.AddFederationId] Rendering add-federation-id screen")
                AddFederationIdScreen(
                    viewModel = nodeSwitcherViewModel,
                    // Return to wherever we came from: Manage Nodes for the manual
                    // entry, Interact for the post-login catch-up auto-present.
                    onBack = { currentScreen = addFederationIdReturnScreen },
                    onDone = { currentScreen = addFederationIdReturnScreen },
                )
            }

            Screen.ManageConsent -> {
                // Consent-objects management (Manage group). Reuses
                // ConsentObjectsViewModel for the bilateral consent:replication
                // peering; links to the existing user-data Consent surface.
                PlatformLogger.d(TAG, "[Screen.ManageConsent] Rendering manage-consent screen")
                ManageConsentScreen(
                    viewModel = consentObjectsViewModel,
                    onBack = { currentScreen = Screen.Interact },
                    onOpenUserConsent = { currentScreen = Screen.Consent },
                    // Trace-consent: the alternative view of the SAME CEG object
                    // the wizard writes. One-tap opt-in/out via the my-data PUT.
                    dataViewModel = dataManagementViewModel,
                    // No node-side peering-revoke (withdraws) endpoint yet — flag
                    // for upstream. Flip when CIRISServer ships it.
                    revokeEndpointAvailable = false,
                )
            }

            Screen.Contacts -> {
                // Contacts / Identities (Manage group): browse known federation
                // peer store. Also reached from Delegations picker flow
                // (contactsPickerSourceScreen != null = picker mode).
                PlatformLogger.d(TAG, "[Screen.Contacts] Rendering contacts screen (picker=${contactsPickerSourceScreen != null})")
                ContactsScreen(
                    viewModel = contactsViewModel,
                    onBack = {
                        val src = contactsPickerSourceScreen
                        contactsPickerSourceScreen = null
                        currentScreen = src ?: Screen.Interact
                    },
                    onPeerPicked = if (contactsPickerSourceScreen != null) { peer ->
                        pickedDelegationKeyId = peer.keyId
                        val src = contactsPickerSourceScreen
                        contactsPickerSourceScreen = null
                        currentScreen = src ?: Screen.Delegations
                    } else null,
                )
            }

            Screen.Delegations -> {
                // Delegations card (Manage group): who the owner has authorized to
                // act on-behalf (active device-auth grants) + approve-new / revoke.
                PlatformLogger.d(TAG, "[Screen.Delegations] Rendering delegations screen")
                DelegationsScreen(
                    viewModel = delegationsViewModel,
                    onBack = { currentScreen = Screen.Interact },
                    onOpenContacts = {
                        contactsPickerSourceScreen = Screen.Delegations
                        contactsViewModel.selectPeer(null) // clear any prior selection
                        currentScreen = Screen.Contacts
                    },
                    pickedIdentityKeyId = pickedDelegationKeyId,
                    onPickedIdentityConsumed = { pickedDelegationKeyId = null },
                )
            }

            Screen.IdentityManagement -> {
                // Identity Management (Manage group): my self fed-ID + the roster of
                // devices (occurrences) bound to it — add / revoke a device, or "log
                // in as yourself on another device". The node signs; the app holds no keys.
                PlatformLogger.d(TAG, "[Screen.IdentityManagement] Rendering identity management screen")
                IdentityManagementScreen(
                    viewModel = identityManagementViewModel,
                    onBack = { currentScreen = Screen.Interact },
                )
            }

            Screen.DutyConferral -> {
                // Delegate moderation duty, reached from the Accord card. Confer
                // slash / moderate / review on another self, stating in one control
                // whether — and how far — they may pass the duty on. Co-scrubbed by
                // the accord holders; the node signs, the app holds no keys.
                PlatformLogger.d(TAG, "[Screen.DutyConferral] Rendering duty conferral screen")
                DutyConferralScreen(
                    viewModel = dutyConferralViewModel,
                    onBack = { currentScreen = Screen.Accord },
                )
            }

            Screen.Accord -> {
                // Accord card (Manage group): the HUMANITY_ACCORD constitutional
                // surface — entrenched family + quorum:2/3 holder roster + pending
                // invocations (CC 4.2.1 per-kind styling) with owner-gated concur.
                PlatformLogger.d(TAG, "[Screen.Accord] Rendering accord screen")
                AccordScreen(
                    viewModel = accordViewModel,
                    onBack = { currentScreen = Screen.Interact },
                    // Found-a-new-accord CTA — shown only when no family exists yet.
                    onStartCeremony = { currentScreen = Screen.AccordCeremony },
                    onConferDuty = { currentScreen = Screen.DutyConferral },
                )
            }

            Screen.AccordCeremony -> {
                // Genesis ceremony (CIRISServer #41): the foolproof guided wizard
                // that stands up a NEW mesh's 2-of-3 human kill-switch — 6 keys
                // (3 primaries + 3 cold spares), cosign, assemble. The app holds no
                // keys; the re-inserted YubiKey signs via the loopback endpoints.
                PlatformLogger.d(TAG, "[Screen.AccordCeremony] Rendering accord genesis ceremony")
                AccordCeremonyScreen(
                    viewModel = accordCeremonyViewModel,
                    onBack = { currentScreen = Screen.Accord },
                )
            }

            Screen.ProvisionAccordHolder -> {
                // Provision Accord Holder (Manage group): the foolproof guided flow
                // that mints a portable-2FA accord-holder identity from an already-
                // FIPS-approved YubiKey + a chosen ML-DSA USB path. Drives the
                // loopback POST /v1/accord/provision-holder; the app holds no keys.
                PlatformLogger.d(TAG, "[Screen.ProvisionAccordHolder] Rendering provision-holder screen")
                ProvisionAccordHolderScreen(
                    viewModel = provisionAccordHolderViewModel,
                    onBack = { currentScreen = Screen.Accord },
                )
            }

            Screen.Moderation -> {
                // Holistic SAFETY surface — moderation as a delegable DUTY.
                // Drives the local node's /v1/safety/{moderation,named-moderator}.
                PlatformLogger.d(TAG, "[Screen.Moderation] Rendering moderation screen")
                ModerationScreen(
                    viewModel = safetyViewModel,
                    // Tiers 0-4 of /v1/admin/* — the enforcement ladder.
                    ladderViewModel = adminLadderViewModel,
                    onBack = { currentScreen = Screen.Interact },
                    // The delegate-moderate-duty flow lives on Family → Delegation.
                    onOpenDelegation = { currentScreen = Screen.Delegation },
                )
            }

            Screen.ChildSafety -> {
                // Holistic SAFETY surface — child-safety / per-group watchlist +
                // the protective posture. Drives /v1/safety/{watchlist,status}.
                PlatformLogger.d(TAG, "[Screen.ChildSafety] Rendering child-safety screen")
                ChildSafetyScreen(
                    viewModel = safetyViewModel,
                    onBack = { currentScreen = Screen.Interact },
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
                        PlatformLogger.i(TAG, "[Screen.DataManagement] Navigating back to Interact")
                        currentScreen = Screen.Interact
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

            Screen.SkillStudio -> {
                // Collect SkillStudioViewModel state
                val skillStudioState by skillStudioViewModel.state.collectAsState()
                val skillStudioDialogState by skillStudioViewModel.dialogState.collectAsState()

                // Initialize with new draft when entering screen
                LaunchedEffect(Unit) {
                    PlatformLogger.i("CIRISApp", "[Screen.SkillStudio] Opening skill studio")
                    skillStudioViewModel.createNewDraft()
                }

                SkillStudioScreen(
                    state = skillStudioState,
                    dialogState = skillStudioDialogState,
                    onNavigateBack = {
                        PlatformLogger.i("CIRISApp", "[Screen.SkillStudio] Navigating back to Adapters")
                        currentScreen = Screen.Adapters
                    },
                    onCreateNew = { skillStudioViewModel.createNewDraft() },
                    onShowPreview = { skillStudioViewModel.showPreview() },
                    onBackToEditing = { skillStudioViewModel.backToEditing() },
                    onImport = { skillStudioViewModel.importAsAdapter() },
                    onValidateAndImport = { skillStudioViewModel.validateAndShowSecurityReport() },
                    // Metadata
                    onUpdateName = { skillStudioViewModel.updateName(it) },
                    onUpdateDescription = { skillStudioViewModel.updateDescription(it) },
                    onUpdateVersion = { skillStudioViewModel.updateVersion(it) },
                    onUpdateCategory = { skillStudioViewModel.updateCategory(it) },
                    onUpdateInstructions = { skillStudioViewModel.updateInstructions(it) },
                    onShowAddTagDialog = { skillStudioViewModel.showAddTagDialog() },
                    onAddTag = { skillStudioViewModel.addTag(it) },
                    onRemoveTag = { skillStudioViewModel.removeTag(it) },
                    // Tools
                    onShowAddToolDialog = { skillStudioViewModel.showAddToolDialog() },
                    onShowEditToolDialog = { skillStudioViewModel.showEditToolDialog(it) },
                    onSaveTool = { skillStudioViewModel.saveTool(it) },
                    onDeleteTool = { skillStudioViewModel.deleteTool(it) },
                    // Parameters
                    onShowAddParameterDialog = { skillStudioViewModel.showAddParameterDialog(it) },
                    onSaveParameter = { skillStudioViewModel.saveParameter(it) },
                    onDeleteParameter = { toolIdx, paramIdx -> skillStudioViewModel.deleteParameter(toolIdx, paramIdx) },
                    // Env Vars
                    onShowAddEnvVarDialog = { skillStudioViewModel.showAddEnvVarDialog() },
                    onShowEditEnvVarDialog = { skillStudioViewModel.showEditEnvVarDialog(it) },
                    onSaveEnvVar = { skillStudioViewModel.saveEnvVar(it) },
                    onDeleteEnvVar = { skillStudioViewModel.deleteEnvVar(it) },
                    // Binaries
                    onAddBinary = { skillStudioViewModel.addBinary(it) },
                    onRemoveBinary = { skillStudioViewModel.removeBinary(it) },
                    // Card expansion
                    onToggleCard = { skillStudioViewModel.toggleCardExpansion(it) },
                    // Dialog
                    onDismissDialog = { skillStudioViewModel.dismissDialog() },
                    // Preview tabs
                    onSetPreviewTab = { skillStudioViewModel.setPreviewTab(it) }
                )
            }

            // ─── 2.9.4 — New Epistemic Commons surfaces ──────────────────────
            Screen.HealthReputation -> {
                ai.ciris.mobile.shared.ui.screens.HealthReputationScreen(
                    state = capacityForCard,
                    onIssueClick = { url -> uriHandler.openUri(url) },
                )
            }
            Screen.NetworkOps -> {
                ai.ciris.mobile.shared.ui.screens.NetworkOpsScreen(
                    viewModel = networkViewModel,
                    onOpenFederationHub = { currentScreen = Screen.LayerGlobalCommons },
                    apiClient = apiClient,
                )
            }
            Screen.Storage -> {
                ai.ciris.mobile.shared.ui.screens.StorageScreen(
                    apiClient = apiClient,
                )
            }
            Screen.Participate -> {
                ai.ciris.mobile.shared.ui.screens.federation.ParticipateScreen(
                    onIssueClick = { url -> uriHandler.openUri(url) },
                )
            }
            Screen.Delegation -> {
                ai.ciris.mobile.shared.ui.screens.federation.DelegationScreen(
                    onIssueClick = { url -> uriHandler.openUri(url) },
                )
            }
            Screen.Constitutional -> {
                ai.ciris.mobile.shared.ui.screens.federation.ConstitutionalScreen(
                    onIssueClick = { url -> uriHandler.openUri(url) },
                )
            }
            Screen.AgentsList -> {
                ai.ciris.mobile.shared.ui.screens.AgentsListScreen(
                    onIssueClick = { url -> uriHandler.openUri(url) },
                )
            }
            // The federation transport hub. Reached via the Global Commons
            // layer in the Commons sidebar group; federation sub-screens
            // back-nav here.
            Screen.LayerGlobalCommons -> {
                ai.ciris.mobile.shared.ui.screens.NetworkScreen(
                    viewModel = networkViewModel,
                    onTileClick = { tile ->
                        currentScreen = when (tile) {
                            ai.ciris.mobile.shared.ui.screens.NetworkTile.IDENTITY -> Screen.NetworkIdentity
                            ai.ciris.mobile.shared.ui.screens.NetworkTile.MAP -> Screen.NetworkMap
                            ai.ciris.mobile.shared.ui.screens.NetworkTile.TRUST_GRAPH -> Screen.NetworkTrustGraph
                            ai.ciris.mobile.shared.ui.screens.NetworkTile.PEERS -> Screen.NetworkPeers
                            ai.ciris.mobile.shared.ui.screens.NetworkTile.INTERFACES -> Screen.NetworkInterfaces
                            ai.ciris.mobile.shared.ui.screens.NetworkTile.PATHS -> Screen.NetworkPaths
                            ai.ciris.mobile.shared.ui.screens.NetworkTile.ANNOUNCES -> Screen.NetworkAnnounces
                            ai.ciris.mobile.shared.ui.screens.NetworkTile.QUEUE -> Screen.NetworkQueue
                            ai.ciris.mobile.shared.ui.screens.NetworkTile.DIAGNOSTICS -> Screen.NetworkDiagnostics
                            ai.ciris.mobile.shared.ui.screens.NetworkTile.CONTENT -> Screen.NetworkContent
                        }
                    },
                )
            }
            // ── Federation sub-screens (reached from NetworkScreen tiles) ──
            Screen.NetworkIdentity -> ai.ciris.mobile.shared.ui.screens.federation.NetworkIdentityScreen(
                apiClient = apiClient,
                onNavigateBack = { currentScreen = Screen.LayerGlobalCommons },
                onIssueClick = { url -> uriHandler.openUri(url) },
            )
            Screen.NetworkMap -> ai.ciris.mobile.shared.ui.screens.federation.NetworkMapScreen(
                apiClient = apiClient,
                onIssueClick = { url -> uriHandler.openUri(url) },
            )
            Screen.NetworkTrustGraph -> ai.ciris.mobile.shared.ui.screens.federation.NetworkTrustGraphScreen(
                apiClient = apiClient,
                onPeerClick = { keyId -> currentScreen = Screen.NetworkPeerDetail(keyId) },
                onIssueClick = { url -> uriHandler.openUri(url) },
            )
            Screen.NetworkPeers -> ai.ciris.mobile.shared.ui.screens.federation.NetworkPeersScreen(
                apiClient = apiClient,
                onNavigateBack = { currentScreen = Screen.LayerGlobalCommons },
                onPeerClick = { keyId -> currentScreen = Screen.NetworkPeerDetail(keyId) },
                onIssueClick = { url -> uriHandler.openUri(url) },
            )
            is Screen.NetworkPeerDetail -> ai.ciris.mobile.shared.ui.screens.federation.NetworkPeerDetailScreen(
                apiClient = apiClient,
                keyId = (currentScreen as Screen.NetworkPeerDetail).keyId,
                onNavigateBack = { currentScreen = Screen.NetworkPeers },
            )
            Screen.NetworkInterfaces -> ai.ciris.mobile.shared.ui.screens.federation.NetworkInterfacesScreen(
                apiClient = apiClient,
                onIssueClick = { url -> uriHandler.openUri(url) },
            )
            Screen.NetworkPaths -> ai.ciris.mobile.shared.ui.screens.federation.NetworkPathsScreen(
                apiClient = apiClient,
                onIssueClick = { url -> uriHandler.openUri(url) },
            )
            Screen.NetworkAnnounces -> ai.ciris.mobile.shared.ui.screens.federation.NetworkAnnouncesScreen(
                apiClient = apiClient,
                onIssueClick = { url -> uriHandler.openUri(url) },
            )
            Screen.NetworkQueue -> ai.ciris.mobile.shared.ui.screens.federation.NetworkQueueScreen(
                apiClient = apiClient,
                onIssueClick = { url -> uriHandler.openUri(url) },
            )
            Screen.NetworkDiagnostics -> ai.ciris.mobile.shared.ui.screens.federation.NetworkDiagnosticsScreen(
                apiClient = apiClient,
                onIssueClick = { url -> uriHandler.openUri(url) },
            )
            Screen.NetworkContent -> ai.ciris.mobile.shared.ui.screens.federation.NetworkContentScreen(
                apiClient = apiClient,
                onIssueClick = { url -> uriHandler.openUri(url) },
            )
            // ── 2.9.4 — CEG 0.6 layer hubs (Identities · Trust · Policies) ──
            Screen.LayerAgent -> ai.ciris.mobile.shared.ui.screens.commons.LayerHubScreen(
                scope = ai.ciris.mobile.shared.ui.nav.CohortScope.AGENT,
                onIssueClick = { url -> uriHandler.openUri(url) },
            )
            Screen.LayerFamily -> ai.ciris.mobile.shared.ui.screens.commons.LayerHubScreen(
                scope = ai.ciris.mobile.shared.ui.nav.CohortScope.FAMILY,
                onIssueClick = { url -> uriHandler.openUri(url) },
            )
            Screen.LayerLocalCommunity -> ai.ciris.mobile.shared.ui.screens.commons.LayerHubScreen(
                scope = ai.ciris.mobile.shared.ui.nav.CohortScope.LOCAL_COMMUNITY,
                onIssueClick = { url -> uriHandler.openUri(url) },
            )
            Screen.LayerGlobalCommunities -> ai.ciris.mobile.shared.ui.screens.commons.LayerHubScreen(
                scope = ai.ciris.mobile.shared.ui.nav.CohortScope.GLOBAL_COMMUNITIES,
                onIssueClick = { url -> uriHandler.openUri(url) },
            )
            // Screen.LayerGlobalCommons handled above alongside Screen.Network —
            // renders the federation transport NetworkScreen.
        }
                } // close Box(modifier = contentModifier)
            } // close mainScreenContent lambda

            androidx.compose.foundation.layout.BoxWithConstraints(
                modifier = androidx.compose.ui.Modifier.fillMaxSize(),
            ) {
                val isCompactWindow = maxWidth < 600.dp

                val sidebarComposable: @Composable () -> Unit = {
                    ai.ciris.mobile.shared.ui.nav.EpistemicSidebar(
                        activeSurface = activeSurface,
                        onSurfaceSelected = { surf ->
                            currentScreen = surfaceToScreen(surf)
                            // Auto-close the drawer on mobile after a
                            // destination is picked so the user lands on the
                            // chosen screen instead of staring at the open
                            // drawer they just used.
                            if (isCompactWindow) {
                                drawerScope.launch { drawerState.close() }
                            }
                        },
                        onIssueClick = { url -> uriHandler.openUri(url) },
                        // "The agent is blocked waiting on you", visible from
                        // every screen. Keyed by NavSurface.id.
                        badges = if (pendingApprovalCount > 0) {
                            mapOf(
                                ai.ciris.mobile.shared.ui.nav.NavSurface.WiseAuthority.id to pendingApprovalCount
                            )
                        } else {
                            emptyMap()
                        },
                        appVersion = "v2.9.4",
                        // Theme strip at the bottom of the drawer — Light /
                        // System / Dark segmented control. Wired straight to
                        // SettingsViewModel so the user can flip themes from
                        // the global nav surface (matches Material 3 nav
                        // drawer guidance for global affordances).
                        brightnessPreference = brightnessPreference,
                        onBrightnessChange = { settingsViewModel.setBrightnessPreference(it) },
                        // CIRIS signet at the top of the drawer doubles as the
                        // close button — matches the open affordance (also a
                        // CIRIS signet) so the icon contract is "tap the CIRIS
                        // signet to toggle the drawer, always and everywhere".
                        onCloseRequest = if (isCompactWindow) {
                            { drawerScope.launch { drawerState.close() } }
                        } else null,
                    )
                }

                if (showSidebar && isCompactWindow) {
                    ModalNavigationDrawer(
                        drawerState = drawerState,
                        drawerContent = {
                            ModalDrawerSheet { sidebarComposable() }
                        },
                    ) {
                        androidx.compose.foundation.layout.Box(
                            modifier = androidx.compose.ui.Modifier.fillMaxSize(),
                        ) {
                            // Federation screens read this to suppress their
                            // own top-bar back arrow on compact viewports —
                            // the global overlay below handles back here.
                            CompositionLocalProvider(
                                ai.ciris.mobile.shared.ui.nav.LocalIsCompactWindow provides true,
                            ) {
                                mainScreenContent(androidx.compose.ui.Modifier.fillMaxSize())
                            }
                            // ─── 3-state global nav icon ───────────────────
                            // ONE button at the top-left, three states:
                            //   1. Drawer OPEN              → hamburger (closes drawer)
                            //   2. Drawer closed, sub-screen → back arrow (back to parent)
                            //   3. Drawer closed, top-level → larger CIRIS signet (opens drawer)
                            // Eliminates the prior "stacked back-arrow + signet"
                            // problem (Samsung-reported) where each federation
                            // Scaffold also rendered its own back arrow. The
                            // federation screens now suppress THEIR back arrow
                            // on compact viewports via `LocalIsCompactWindow`;
                            // this button is the single source of truth.
                            // GLOBAL STANDARD: this top-left icon is the single
                            // back affordance for every sub-screen on compact.
                            // Map each sub-screen to its parent; every screen
                            // listed here suppresses its OWN TopAppBar back arrow
                            // on compact via LocalIsCompactWindow, so the signet/
                            // back never co-exist (Samsung-reported). Roots
                            // (Interact / Login / Layer* hubs) fall to `else` and
                            // show the CIRIS signet (opens the drawer) instead.
                            val backTarget: Screen? = when (currentScreen) {
                                // Federation sub-screens → the Global Commons hub
                                Screen.NetworkIdentity,
                                Screen.NetworkMap,
                                Screen.NetworkTrustGraph,
                                Screen.NetworkPeers,
                                Screen.NetworkInterfaces,
                                Screen.NetworkPaths,
                                Screen.NetworkAnnounces,
                                Screen.NetworkQueue,
                                Screen.NetworkDiagnostics,
                                Screen.NetworkContent -> Screen.LayerGlobalCommons
                                is Screen.NetworkPeerDetail -> Screen.NetworkPeers
                                // Nested sub-screens → their direct parent
                                Screen.GraphMemory -> Screen.Memory
                                Screen.SkillStudio -> Screen.Adapters
                                Screen.VizSettings -> Screen.Settings
                                Screen.ServerConnection -> Screen.Interact
                                Screen.ClaimNode -> Screen.Interact
                                // Sub-screens of the home (Interact)
                                Screen.Adapters,
                                Screen.Audit,
                                Screen.Billing,
                                Screen.Config,
                                Screen.Consent,
                                Screen.DataManagement,
                                Screen.EnvironmentInfo,
                                Screen.Help,
                                Screen.LLMSettings,
                                Screen.Logs,
                                Screen.Transport,
                                Screen.Memory,
                                Screen.Runtime,
                                Screen.Scheduler,
                                Screen.Services,
                                Screen.Sessions,
                                Screen.Settings,
                                Screen.System,
                                Screen.Telemetry,
                                Screen.Tickets,
                                Screen.Tools,
                                Screen.Trust,
                                Screen.Users,
                                Screen.Wallet,
                                Screen.WiseAuthority -> Screen.Interact
                                else -> null
                            }
                            val isDrawerOpen = drawerState.currentValue == DrawerValue.Open
                            val iconTestTag = when {
                                isDrawerOpen -> "btn_nav_drawer_close"
                                backTarget != null -> "btn_nav_back"
                                else -> "btn_nav_drawer_open"
                            }
                            // Container sized to match the status-bar badge row
                            // height (badges ~56dp tall after padding). Top pad
                            // shifted down to vertically center on that row, so
                            // the signet doesn't read as floating above the
                            // badges. Inner glyphs sized to nearly fill (4dp
                            // breathing room) — the prior 36dp signet in a 48dp
                            // box looked under-sized.
                            Box(
                                modifier = androidx.compose.ui.Modifier
                                    .align(androidx.compose.ui.Alignment.TopStart)
                                    // Sit below the system status bar — this is a
                                    // raw overlay (outside the screen's Scaffold),
                                    // so it must consume the status-bar inset
                                    // itself or it renders up under the Android
                                    // clock/notification icons (Samsung-reported).
                                    .statusBarsPadding()
                                    // top = 4.dp matches the status-bar badge row
                                    // (InteractScreen badge Row uses top = 4.dp), so
                                    // the signet's vertical center lines up with the
                                    // badge icons rather than sitting slightly low.
                                    .padding(top = 4.dp, start = 8.dp)
                                    .size(56.dp)
                                    // Theme-aware circular scrim so the glyph never
                                    // disappears: many sub-screen TopAppBars use
                                    // containerColor = colorScheme.primary, which is
                                    // the SAME color the glyph used to be tinted — so
                                    // the back arrow vanished against the bar. Sitting
                                    // the glyph on a `surface` disc guarantees
                                    // surface/onSurface contrast over ANY bar color in
                                    // both light and dark mode. On the home status bar
                                    // (also `surface`) the disc blends in invisibly, so
                                    // the top-level signet looks unchanged.
                                    .background(MaterialTheme.colorScheme.surface, CircleShape)
                                    .testableClickable(iconTestTag) {
                                        when {
                                            isDrawerOpen -> drawerScope.launch { drawerState.close() }
                                            backTarget != null -> { currentScreen = backTarget }
                                            else -> drawerScope.launch { drawerState.open() }
                                        }
                                    },
                                contentAlignment = androidx.compose.ui.Alignment.Center,
                            ) {
                                when {
                                    isDrawerOpen -> Icon(
                                        imageVector = Icons.Filled.Menu,
                                        contentDescription = "Close navigation",
                                        // onSurface (not primary): the glyph sits on the
                                        // `surface` scrim disc, so onSurface guarantees
                                        // contrast regardless of the bar color behind it.
                                        tint = MaterialTheme.colorScheme.onSurface,
                                        modifier = androidx.compose.ui.Modifier.size(40.dp),
                                    )
                                    backTarget != null -> Icon(
                                        imageVector = ai.ciris.mobile.shared.ui.components.CIRISIcons.arrowBack,
                                        contentDescription = "Go back",
                                        // onSurface (not primary): see note above — the
                                        // back arrow used to vanish on primary-colored
                                        // sub-screen TopAppBars (CIRISAgent #title-overlap).
                                        tint = MaterialTheme.colorScheme.onSurface,
                                        modifier = androidx.compose.ui.Modifier.size(40.dp),
                                    )
                                    else -> ai.ciris.mobile.shared.ui.components.CIRISSignet(
                                        modifier = androidx.compose.ui.Modifier.size(52.dp),
                                        tintColor = MaterialTheme.colorScheme.primary,
                                    )
                                }
                            }
                        }
                    }
                } else {
                    androidx.compose.foundation.layout.Row(
                        modifier = androidx.compose.ui.Modifier.fillMaxSize(),
                    ) {
                        if (showSidebar) {
                            sidebarComposable()
                        }
                        mainScreenContent(
                            androidx.compose.ui.Modifier
                                .weight(1f)
                                .fillMaxHeight(),
                        )
                    }
                }
            } // close BoxWithConstraints
        } // close MaterialTheme
    } // CompositionLocalProvider
}

/**
 * Check if setup is required via the BRAIN's `/v1/setup/status`.
 * Uses the API client for platform-independent HTTP handling.
 *
 * `/v1/setup` is split across the two services (FSD §2): `status` + `complete`
 * are the brain's, `root` / `owned-nodes` / `claim-remote` are the node's. So the
 * primary probe goes to [apiBaseUrl] and every degrade path — which asks the node
 * whether it is reachable and owned — goes to [nodeBaseUrl].
 *
 * @param apiBaseUrl base URL of the Python brain (serves /v1/setup/status)
 * @param nodeBaseUrl base URL of the ciris-server node (serves /v1/setup/owned-nodes)
 * @param maxRetries Maximum number of retries on connection error (0 = no retries, just fail)
 * @param onStatusUpdate Optional callback to update status message during retries
 * @return true if setup is required, false if not, null if server unreachable after retries
 */
private suspend fun checkFirstRunStatus(
    apiBaseUrl: String,
    nodeBaseUrl: String,
    maxRetries: Int = 0,
    onStatusUpdate: ((String) -> Unit)? = null
): Boolean? {
    var attempts = 0
    while (attempts <= maxRetries) {
        try {
            platformLog("checkFirstRunStatus", "[INFO] Attempt ${attempts + 1}/${maxRetries + 1}: Checking setup status at $apiBaseUrl")
            val client = CIRISApiClient(apiBaseUrl)
            val setupStatus = client.getSetupStatus()
            platformLog("checkFirstRunStatus", "[INFO] Got setup status: setup_required=${setupStatus.data.setup_required}")

            // "IS THIS A FIRST RUN?" DEPENDS ON TWO STORES, AND THIS ASKED ONE.
            //
            // The brain answers from its own config; the NODE independently knows
            // whether it has ever been claimed. They can disagree, and when they do
            // the node is decisive — an owned node is CONFIGURED, whatever the
            // brain's .env says. Observed live (CIRISAgent#1061):
            //
            //     brain /v1/setup/status      setup_required=true    (.env was gone)
            //     node  /v1/setup/owned-nodes owner present          <- decisive
            //
            // The user got the first-run login, and a Google sign-in there was
            // CORRECTLY refused (auth.oauth.no_local_identity — the owner was a
            // local credential with no OAuth identity linked). Every layer behaved
            // as written; the node looked broken while being right every time. It
            // was reported as "OAuth is broken" and was neither first-run nor
            // broken OAuth.
            //
            // Note where the rule already lived: BOTH degrade branches below
            // consult nodeHasOwner() and explain why. The happy path — the one
            // that runs when nothing is wrong — was the only place it was missing.
            // Re-entering the wizard here would re-claim a node that already has
            // an owner, so this is a correctness fix, not just a UX one.
            // ...AND THE BRAIN MUST ALREADY HAVE ITS CONFIG. This is the half I
            // got wrong in 2.9.26 (CIRISAgent#1075).
            //
            // An owned node means DO NOT RE-CLAIM THE NODE. It does not mean the
            // brain is configured — they are two different stores, which is the
            // whole point of #1061, and I applied that lesson in one direction
            // only. Skipping the wizard on node-ownership alone left a brain with
            // no .env, and the brain's remaining 12 services start ONLY from
            // POST /v1/setup/complete -> runtime.resume_from_first_run():
            //
            //     Config: ~/ciris/.env — NOT FOUND (first run will create it)
            //     [FIRST-RUN] 10/10 minimal services started
            //     ...wizard skipped, user signed in...
            //     cognitiveState=SETUP forever, telemetry/audit/LLM bus absent,
            //     every /v1/system/*, /v1/audit/* and add-provider call 503.
            //
            // The agent could not even be given an LLM provider to escape with.
            //
            // So: node-ownership suppresses the CLAIM, never the setup. If the
            // brain has no config, the wizard runs.
            if (setupStatus.data.setup_required && nodeHasOwner(nodeBaseUrl)) {
                // An OWNED node is not a first run, whether or not the brain is
                // configured. The two cases diverge AFTER this point:
                //
                //   owned + brain configured    -> sign in, full AGENT UI
                //   owned + brain unconfigured  -> ClientMode.NODE, node UI
                //
                // The second is a legitimate state, not a broken agent: the node
                // works and the cognitive half was never set up. Forcing the wizard
                // there (which is what I did in the first pass at this) shows setup
                // to someone who may only want a node.
                //
                // It is NOT a dead end. The brain still starts its 10 first-run
                // services, and Settings offers "set up the agent", which enters the
                // wizard directly. Deliberately NOT the existing rerun-setup path:
                // that deletes .env and restarts, and with no .env to delete it
                // restarts into this same state — a loop.
                val brainHasConfig = setupStatus.data.has_env_file
                platformLog(
                    "checkFirstRunStatus",
                    "[INFO] node has an OWNER → NOT first-run (brain_configured=$brainHasConfig). " +
                        if (brainHasConfig) "Sign in." else "Brain unconfigured → node mode; set up the agent from Settings.",
                )
                return false
            }
            return setupStatus.data.setup_required
        } catch (e: Exception) {
            // FAST-PATH degrade (ciris-server node client): a 404 / deserialize
            // failure from /v1/setup/status means the node simply does NOT serve the
            // agent setup-status endpoint (ciris-server has /v1/setup/root +
            // /v1/setup/claim-remote, not /v1/setup/status). That is NOT transient —
            // retrying 60× hangs "waiting for backend" ~30s. If the node's read API
            // answers, treat as fresh first-run IMMEDIATELY → straight to the wizard.
            val absent = e::class.simpleName?.contains("NoTransformation") == true ||
                e.message?.contains("404") == true ||
                e.message?.contains("/v1/setup/status") == true
            if (absent && isNodeReachable(nodeBaseUrl)) {
                // OWNER-AWARE degrade: setup-status is unavailable, but a node
                // that already has an OWNER — claimed OR legacy-owned — is
                // CONFIGURED, not first-run. Only a genuinely FRESH node is
                // first-run. Without this, the post-setup runtime reload (during
                // which setup-status is briefly unreachable / the node-fold
                // rebinds 4243) degrades to first-run and the app loops the
                // wizard/login forever on an owned node.
                if (nodeHasOwner(nodeBaseUrl)) {
                    platformLog("checkFirstRunStatus", "[INFO] setup-status absent but node has an OWNER → configured, NOT first-run")
                    return false
                }
                platformLog("checkFirstRunStatus", "[INFO] /v1/setup/status absent + node reachable + no owner → first-run (fast degrade)")
                return true
            }
            attempts++
            if (attempts <= maxRetries) {
                platformLog("checkFirstRunStatus", "[INFO] Connection error, retrying in 500ms... (${e::class.simpleName})")
                onStatusUpdate?.invoke(LocalizationHelper.getString("mobile.startup_waiting_backend", mapOf("attempt" to attempts.toString())))
                kotlinx.coroutines.delay(500)
            } else {
                platformLog("checkFirstRunStatus", "[ERROR] Failed to check setup status after ${maxRetries + 1} attempts: ${e::class.simpleName}: ${e.message}")
                // GRACEFUL DEGRADE (ciris-server node client): /v1/setup/status may be
                // unavailable or shaped differently on a node that is otherwise up.
                // If the node's read API answers (GET /v1/identity 2xx), treat this
                // as a fresh first-run so the app reaches the federation-ID wizard
                // instead of dead-ending on "Backend unreachable".
                if (isNodeReachable(nodeBaseUrl)) {
                    // OWNER-AWARE (see the fast-degrade branch above): an owned
                    // node is configured, not first-run — don't loop the wizard
                    // just because setup-status is transiently unreachable.
                    if (nodeHasOwner(nodeBaseUrl)) {
                        platformLog("checkFirstRunStatus", "[INFO] setup status unavailable but node has an OWNER → configured, NOT first-run")
                        return false
                    }
                    platformLog("checkFirstRunStatus", "[INFO] Node reachable but setup status unavailable + no owner - treating as first-run")
                    return true
                }
                return null
            }
        }
    }
    return null
}

/**
 * Lightweight node-up probe for the local ciris-server read API.
 * GET /v1/identity returning any 2xx means the node is serving.
 */
private suspend fun isNodeReachable(nodeBaseUrl: String): Boolean {
    return try {
        CIRISApiClient(nodeBaseUrl).isLocalNodeUp(nodeBaseUrl.trimEnd('/'))
    } catch (_: Exception) {
        false
    }
}

/**
 * Which of the [NodeOwnership] states is the local node in?
 *
 * Reads the two NODE-side signals (FSD §5) and never `/v1/auth/owner-hint`:
 *
 * 1. `GET /v1/setup/owned-nodes` → the CEG owner-binding projection, the same
 *    predicate `require_owner_bound` consults at every owner-gated operation.
 * 2. `GET /v1/setup/status` → the NODE's own first-run predicate (does an active
 *    ROOT WaCert exist), which separates a LEGACY_OWNED node from a FRESH one.
 *
 * Best-effort: a failed owner-binding probe reads as "no binding" and a failed
 * WaCert probe reads as "unknown", which together degrade to [NodeOwnership.FRESH]
 * — the pre-2.9.14 assumption.
 */
private suspend fun probeNodeOwnership(nodeBaseUrl: String): NodeOwnership {
    val client = CIRISApiClient(nodeBaseUrl)
    val ownerBinding = try {
        client.getOwnedNodes(nodeBaseUrl).owner
    } catch (e: Exception) {
        platformLog("probeNodeOwnership", "[DEBUG] owned-nodes probe failed: ${e.message?.take(80)}")
        null
    }
    // Short-circuit: an owner-binding is decisive, no second probe needed.
    if (!ownerBinding.isNullOrBlank()) return NodeOwnership.CLAIMED
    val nodeSetupRequired = try {
        client.getSetupStatus().data.setup_required
    } catch (e: Exception) {
        platformLog("probeNodeOwnership", "[DEBUG] node setup-status probe failed: ${e.message?.take(80)}")
        null
    }
    val state = nodeOwnershipFrom(ownerBinding, nodeSetupRequired)
    platformLog(
        "probeNodeOwnership",
        "[INFO] $state (owner_binding=${ownerBinding ?: "<none>"}, node_setup_required=$nodeSetupRequired)",
    )
    return state
}

/**
 * Does the local node already have an OWNER — in EITHER form? A claimed node and a
 * legacy-owned node are both CONFIGURED (not first-run) even when the brain's
 * /v1/setup/status is transiently unavailable, e.g. during the post-setup runtime
 * reload while the node-fold rebinds 4243.
 */
private suspend fun nodeHasOwner(nodeBaseUrl: String): Boolean =
    probeNodeOwnership(nodeBaseUrl).isOwned

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
    onLLMSettingsClick: () -> Unit = {},
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

    // Suppress the title-slot CIRIS signet on compact viewports — the global
    // 3-state overlay button at the top-left already shows the signet, and
    // rendering it again here produces the "stacked signets" Samsung bug
    // (one at top-left from CIRISApp's overlay, another in the TopAppBar
    // title slot here). On tablet/desktop where the overlay button isn't
    // shown, keep the title signet as the brand mark.
    val showTitleSignet = !ai.ciris.mobile.shared.ui.nav.LocalIsCompactWindow.current

    TopAppBar(
        title = {
            if (showTitleSignet) {
                // CIRIS Signet - geometric brand mark
                CIRISSignet(
                    modifier = Modifier.size(32.dp),
                    tintColor = if (darkMode) Color.White else MaterialTheme.colorScheme.primary
                )
            }
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
                        imageVector = CIRISIcons.build,
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
                        leadingIcon = { Icon(CIRISIcons.build, null) },
                        modifier = Modifier.testableClickable("menu_adapters") { activeCategory = NavCategory.NONE; onAdaptersClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_tools")) },
                        onClick = { activeCategory = NavCategory.NONE; onToolsClick() },
                        leadingIcon = { Icon(CIRISIcons.build, null) },
                        modifier = Modifier.testableClickable("menu_tools") { activeCategory = NavCategory.NONE; onToolsClick() }
                    )
                    DropdownMenuItem(
                        text = { Text("Environment Info") },
                        onClick = { activeCategory = NavCategory.NONE; onEnvironmentInfoClick() },
                        leadingIcon = { Icon(CIRISIcons.info, null) },
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
                        imageVector = CIRISIcons.settings,
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
                        leadingIcon = { Icon(CIRISIcons.settings, null) },
                        modifier = Modifier.testableClickable("menu_settings") { activeCategory = NavCategory.NONE; onSettingsClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_llm_settings")) },
                        onClick = { activeCategory = NavCategory.NONE; onLLMSettingsClick() },
                        leadingIcon = { Icon(CIRISIcons.settings, null) },
                        modifier = Modifier.testableClickable("menu_llm_settings") { activeCategory = NavCategory.NONE; onLLMSettingsClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_agent_config")) },
                        onClick = { activeCategory = NavCategory.NONE; onConfigClick() },
                        leadingIcon = { Icon(CIRISIcons.settings, null) },
                        modifier = Modifier.testableClickable("menu_config") { activeCategory = NavCategory.NONE; onConfigClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_buy_credits")) },
                        onClick = { activeCategory = NavCategory.NONE; onBillingClick() },
                        leadingIcon = { Icon(CIRISIcons.star, null) },
                        modifier = Modifier.testableClickable("menu_billing") { activeCategory = NavCategory.NONE; onBillingClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_help")) },
                        onClick = { activeCategory = NavCategory.NONE; onHelpClick() },
                        leadingIcon = { Icon(CIRISIcons.info, null) },
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
                        imageVector = CIRISIcons.info,
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
                        leadingIcon = { Icon(CIRISIcons.star, null) },
                        modifier = Modifier.testableClickable("menu_memory") { activeCategory = NavCategory.NONE; onMemoryClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_sessions")) },
                        onClick = { activeCategory = NavCategory.NONE; onSessionsClick() },
                        leadingIcon = { Icon(CIRISIcons.log, null) },
                        modifier = Modifier.testableClickable("menu_sessions") { activeCategory = NavCategory.NONE; onSessionsClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_consent")) },
                        onClick = { activeCategory = NavCategory.NONE; onConsentClick() },
                        leadingIcon = { Icon(CIRISIcons.check, null) },
                        modifier = Modifier.testableClickable("menu_consent") { activeCategory = NavCategory.NONE; onConsentClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_audit_trail")) },
                        onClick = { activeCategory = NavCategory.NONE; onAuditClick() },
                        leadingIcon = { Icon(CIRISIcons.log, null) },
                        modifier = Modifier.testableClickable("menu_audit") { activeCategory = NavCategory.NONE; onAuditClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_data_management")) },
                        onClick = { activeCategory = NavCategory.NONE; onDataManagementClick() },
                        leadingIcon = { Icon(CIRISIcons.info, null) },
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
                        imageVector = CIRISIcons.person,
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
                        leadingIcon = { Icon(CIRISIcons.person, null) },
                        modifier = Modifier.testableClickable("menu_wise_authority") { activeCategory = NavCategory.NONE; onWiseAuthorityClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_users")) },
                        onClick = { activeCategory = NavCategory.NONE; onUsersClick() },
                        leadingIcon = { Icon(CIRISIcons.person, null) },
                        modifier = Modifier.testableClickable("menu_users") { activeCategory = NavCategory.NONE; onUsersClick() }
                    )
                    HorizontalDivider(modifier = Modifier.padding(vertical = 4.dp))
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.settings_logout")) },
                        onClick = { activeCategory = NavCategory.NONE; onLogoutClick() },
                        leadingIcon = { Icon(CIRISIcons.exit, null) },
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
                        imageVector = CIRISIcons.moreVert,
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
                        leadingIcon = { Icon(CIRISIcons.info, null) },
                        modifier = Modifier.testableClickable("menu_telemetry") { activeCategory = NavCategory.NONE; onTelemetryClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_services")) },
                        onClick = { activeCategory = NavCategory.NONE; onServicesClick() },
                        leadingIcon = { Icon(CIRISIcons.build, null) },
                        modifier = Modifier.testableClickable("menu_services") { activeCategory = NavCategory.NONE; onServicesClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_logs")) },
                        onClick = { activeCategory = NavCategory.NONE; onLogsClick() },
                        leadingIcon = { Icon(CIRISIcons.log, null) },
                        modifier = Modifier.testableClickable("menu_logs") { activeCategory = NavCategory.NONE; onLogsClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_system")) },
                        onClick = { activeCategory = NavCategory.NONE; onSystemClick() },
                        leadingIcon = { Icon(CIRISIcons.info, null) },
                        modifier = Modifier.testableClickable("menu_system") { activeCategory = NavCategory.NONE; onSystemClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_runtime")) },
                        onClick = { activeCategory = NavCategory.NONE; onRuntimeClick() },
                        leadingIcon = { Icon(CIRISIcons.play, null) },
                        modifier = Modifier.testableClickable("menu_runtime") { activeCategory = NavCategory.NONE; onRuntimeClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_tickets")) },
                        onClick = { activeCategory = NavCategory.NONE; onTicketsClick() },
                        leadingIcon = { Icon(CIRISIcons.log, null) },
                        modifier = Modifier.testableClickable("menu_tickets") { activeCategory = NavCategory.NONE; onTicketsClick() }
                    )
                    DropdownMenuItem(
                        text = { Text(localizedString("mobile.nav_scheduler")) },
                        onClick = { activeCategory = NavCategory.NONE; onSchedulerClick() },
                        leadingIcon = { Icon(CIRISIcons.check, null) },
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
 * The default post-auth landing screen.
 *
 * - **Node client (CIRISBuild.HAS_AGENT == false):** the agent chat
 *   (Screen.Interact) is not a surfaced nav card, so the app opens on the
 *   node-management surface (the Nodes card, NavSurface.Nodes). The Interact
 *   screen object remains defined and reachable; it is simply not the landing
 *   destination and not in the sidebar.
 * - **Agent build (HAS_AGENT == true):** the full agent client — the agent chat
 *   (AGENT_GROUP → NavSurface.Interact) is a first-class surfaced card, so the
 *   app opens on the reasoning-stream chat. Node management stays reachable from
 *   the Manage group.
 *
 * Gated on the flag so the agent's adoption is a single HAS_AGENT flip.
 */
private val HOME_SCREEN: Screen =
    if (CIRISBuild.HAS_AGENT) Screen.Interact else Screen.ManageNodes

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
    object Transport : Screen()  // node transports + LoRa/RNode radio config
    object Memory : Screen()
    object GraphMemory : Screen()
    object Config : Screen()
    object Consent : Screen()
    object System : Screen()
    object Runtime : Screen()
    object Users : Screen()
    object Trust : Screen()
    object NetworkOps : Screen()   // Manage — CIRISEdge local op-view
    object Storage : Screen()      // Manage — CIRISPersist graph/disk view
    object Wallet : Screen()
    object Tickets : Screen()
    object Scheduler : Screen()
    object Tools : Screen()
    object EnvironmentInfo : Screen()
    object SkillImport : Screen()
    object SkillStudio : Screen()
    object DataManagement : Screen()
    object LLMSettings : Screen()
    object VizSettings : Screen()
    object Help : Screen()
    object ServerConnection : Screen()
    // Claim-Ownership: founder enters a node's NodeCode + claim PIN to become
    // its SYSTEM_ADMIN (connect → identity-pin → claim). Flow-only (no sidebar).
    object ClaimNode : Screen()

    // Node management (CRUD over saved NodeProfiles) — first-class Manage-group
    // surface, promoted from the in-page node-switcher dropdown.
    object ManageNodes : Screen()
    // Add Federation ID (catch-up): an existing logged-in owner whose node has NO
    // fed-ID (legacy WA claim) adds one via the session-authed upgrade path
    // (mint → /v1/self/upgrade-owner). Flow-only (reached from Manage Nodes).
    object AddFederationId : Screen()
    // Consent management (consent:replication peering + user-data consent).
    object ManageConsent : Screen()
    // Contacts / Identities — browse the local node's known federation peer store;
    // also used as a picker when delegating to an existing fed-ID.
    object Contacts : Screen()
    // Delegations (device-auth grants — authorize an agent to act on-behalf).
    object Delegations : Screen()
    // Identity Management (my self fed-ID + device roster / occurrences — add /
    // revoke a device; "log in as yourself on another device").
    object IdentityManagement : Screen()
    // Accord (HUMANITY_ACCORD — constitutional 2/3 kill-switch + holder roster).
    object Accord : Screen()
    object DutyConferral : Screen()
    // Provision Accord Holder (mint a portable-2FA accord-holder identity).
    object ProvisionAccordHolder : Screen()
    // Accord Genesis Ceremony (stand up a new mesh's 2-of-3 human kill-switch).
    object AccordCeremony : Screen()

    // Holistic SAFETY surface (CIRISServer v0.4.6 /v1/safety/*) — moderation +
    // child-safety as first-class fabric primitives, built ahead of content.
    object Moderation : Screen()
    object ChildSafety : Screen()

    // 2.9.4 — new Epistemic Commons surfaces.
    // HealthReputation ships with a real card (CellVizState-backed).
    // The other six are Coming Soon placeholders pinned to their substrate issue.
    object HealthReputation : Screen()
    object Participate : Screen()
    object Delegation : Screen()
    object Constitutional : Screen()
    object AgentsList : Screen()

    // Network hub federation sub-screens — all ten live since T-E / T-E-D
    // (2.9.4→2.9.6). Reached via the 10-tile grid on NetworkScreen; not
    // sidebar-navigable.
    object NetworkIdentity : Screen()
    object NetworkMap : Screen()
    object NetworkTrustGraph : Screen()
    object NetworkPeers : Screen()
    object NetworkInterfaces : Screen()
    object NetworkPaths : Screen()
    object NetworkAnnounces : Screen()
    object NetworkQueue : Screen()
    object NetworkDiagnostics : Screen()
    object NetworkContent : Screen()

    /**
     * Parameterised peer-detail route (2.9.4 T-E-UI Batch A). The only
     * federation sub-screen that takes runtime state; rendered via the
     * existing `is Screen.NetworkPeerDetail` arm in the `when` dispatch.
     */
    data class NetworkPeerDetail(val keyId: String) : Screen()

    // 2.9.4 — 5 CEG 0.6 cohort-scope layer hubs (Identities · Trust · Policies).
    // Phase A: each renders LayerHubScreen with the appropriate CohortScope.
    // Phase B: LayerGlobalCommons absorbs the existing NetworkScreen federation
    // hub. Per CEG §02 grammar:137 and `CohortScope.kt` for the 7 → 5 fold.
    object LayerAgent : Screen()
    object LayerFamily : Screen()
    object LayerLocalCommunity : Screen()
    object LayerGlobalCommunities : Screen()
    object LayerGlobalCommons : Screen()
    // CIRISServer #367 — the reverse-quorum plane the cohorts above are the
    // quorum OF. A Commons-group surface, not a settings one: nothing on it is
    // an owner privilege.
    object Commons : Screen()
}

/**
 * Bidirectional bridge between the legacy [Screen] sealed class and the
 * 2.9.4 [NavSurface] taxonomy. The sidebar drives `onSurfaceSelected`;
 * we translate to a Screen and assign `currentScreen`. The active surface
 * is computed back from the Screen so the sidebar's highlight state stays
 * in sync.
 *
 * Pre-login screens (Startup / Login / Setup / ServerConnection) and the
 * Help utility have no NavSurface (they're [FLOW_ONLY_SURFACES]); the
 * function returns null and the sidebar is hidden by the shell.
 */
private fun screenToSurface(s: Screen): ai.ciris.mobile.shared.ui.nav.NavSurface? = when (s) {
    Screen.Interact -> ai.ciris.mobile.shared.ui.nav.NavSurface.Interact
    Screen.Sessions -> ai.ciris.mobile.shared.ui.nav.NavSurface.Sessions
    Screen.Tickets -> ai.ciris.mobile.shared.ui.nav.NavSurface.Tickets
    Screen.Scheduler -> ai.ciris.mobile.shared.ui.nav.NavSurface.Scheduler
    Screen.Services -> ai.ciris.mobile.shared.ui.nav.NavSurface.Services
    Screen.Tools -> ai.ciris.mobile.shared.ui.nav.NavSurface.Tools
    Screen.Telemetry -> ai.ciris.mobile.shared.ui.nav.NavSurface.Telemetry
    Screen.Logs -> ai.ciris.mobile.shared.ui.nav.NavSurface.Logs
    Screen.Transport -> ai.ciris.mobile.shared.ui.nav.NavSurface.Transport
    Screen.Memory -> ai.ciris.mobile.shared.ui.nav.NavSurface.Memory
    Screen.GraphMemory -> ai.ciris.mobile.shared.ui.nav.NavSurface.GraphMemory
    Screen.WiseAuthority -> ai.ciris.mobile.shared.ui.nav.NavSurface.WiseAuthority
    Screen.Settings -> ai.ciris.mobile.shared.ui.nav.NavSurface.AgentSettings
    Screen.LLMSettings -> ai.ciris.mobile.shared.ui.nav.NavSurface.LLMSettings
    Screen.System -> ai.ciris.mobile.shared.ui.nav.NavSurface.System
    Screen.Runtime -> ai.ciris.mobile.shared.ui.nav.NavSurface.Runtime
    Screen.Config -> ai.ciris.mobile.shared.ui.nav.NavSurface.Config
    Screen.SkillStudio, Screen.SkillImport -> ai.ciris.mobile.shared.ui.nav.NavSurface.Skills
    Screen.HealthReputation -> ai.ciris.mobile.shared.ui.nav.NavSurface.HealthReputation
    Screen.Users -> ai.ciris.mobile.shared.ui.nav.NavSurface.Users
    Screen.Adapters -> ai.ciris.mobile.shared.ui.nav.NavSurface.Adapters
    // Federation sub-screens highlight LayerGlobalCommons in the sidebar
    // (the home of the federation hub).
    Screen.NetworkIdentity,
    Screen.NetworkMap,
    Screen.NetworkTrustGraph,
    Screen.NetworkPeers,
    Screen.NetworkInterfaces,
    Screen.NetworkPaths,
    Screen.NetworkAnnounces,
    Screen.NetworkQueue,
    Screen.NetworkDiagnostics,
    Screen.NetworkContent -> ai.ciris.mobile.shared.ui.nav.NavSurface.LayerGlobalCommons
    is Screen.NetworkPeerDetail -> ai.ciris.mobile.shared.ui.nav.NavSurface.LayerGlobalCommons
    Screen.DataManagement -> ai.ciris.mobile.shared.ui.nav.NavSurface.Data
    Screen.Audit -> ai.ciris.mobile.shared.ui.nav.NavSurface.Audit
    Screen.Consent -> ai.ciris.mobile.shared.ui.nav.NavSurface.Consent
    Screen.Trust -> ai.ciris.mobile.shared.ui.nav.NavSurface.Trust
    Screen.NetworkOps -> ai.ciris.mobile.shared.ui.nav.NavSurface.NetworkOps
    Screen.ManageNodes -> ai.ciris.mobile.shared.ui.nav.NavSurface.Nodes
    Screen.ManageConsent -> ai.ciris.mobile.shared.ui.nav.NavSurface.ManageConsent
    Screen.Contacts -> ai.ciris.mobile.shared.ui.nav.NavSurface.Contacts
    Screen.Delegations -> ai.ciris.mobile.shared.ui.nav.NavSurface.Delegations
    Screen.IdentityManagement -> ai.ciris.mobile.shared.ui.nav.NavSurface.IdentityManagement
    Screen.Accord -> ai.ciris.mobile.shared.ui.nav.NavSurface.Accord
        Screen.DutyConferral -> ai.ciris.mobile.shared.ui.nav.NavSurface.Accord
    Screen.ProvisionAccordHolder -> ai.ciris.mobile.shared.ui.nav.NavSurface.ProvisionAccordHolder
    Screen.AccordCeremony -> ai.ciris.mobile.shared.ui.nav.NavSurface.AccordCeremony
    Screen.Moderation -> ai.ciris.mobile.shared.ui.nav.NavSurface.Moderation
    Screen.ChildSafety -> ai.ciris.mobile.shared.ui.nav.NavSurface.ChildSafety
    Screen.Storage -> ai.ciris.mobile.shared.ui.nav.NavSurface.Storage
    Screen.Billing -> ai.ciris.mobile.shared.ui.nav.NavSurface.Billing
    Screen.Wallet -> ai.ciris.mobile.shared.ui.nav.NavSurface.Wallet
    Screen.Participate -> ai.ciris.mobile.shared.ui.nav.NavSurface.Participate
    Screen.EnvironmentInfo -> ai.ciris.mobile.shared.ui.nav.NavSurface.EnvironmentGraph
    Screen.Delegation -> ai.ciris.mobile.shared.ui.nav.NavSurface.Delegation
    Screen.Constitutional -> ai.ciris.mobile.shared.ui.nav.NavSurface.Constitutional
    Screen.AgentsList -> ai.ciris.mobile.shared.ui.nav.NavSurface.AgentsList
    Screen.VizSettings -> ai.ciris.mobile.shared.ui.nav.NavSurface.ClientInterface
    // CEG 0.6 layer hubs (2.9.4 Phase A)
    Screen.LayerAgent -> ai.ciris.mobile.shared.ui.nav.NavSurface.LayerAgent
    Screen.LayerFamily -> ai.ciris.mobile.shared.ui.nav.NavSurface.LayerFamily
    Screen.LayerLocalCommunity -> ai.ciris.mobile.shared.ui.nav.NavSurface.LayerLocalCommunity
    Screen.LayerGlobalCommunities -> ai.ciris.mobile.shared.ui.nav.NavSurface.LayerGlobalCommunities
    Screen.LayerGlobalCommons -> ai.ciris.mobile.shared.ui.nav.NavSurface.LayerGlobalCommons
    Screen.Commons -> ai.ciris.mobile.shared.ui.nav.NavSurface.Commons
    // Flow-only / no sidebar
    Screen.Startup, Screen.Login, Screen.Setup, Screen.ServerConnection, Screen.ClaimNode,
    Screen.AddFederationId, Screen.Help -> null
}

private fun surfaceToScreen(s: ai.ciris.mobile.shared.ui.nav.NavSurface): Screen = when (s) {
    ai.ciris.mobile.shared.ui.nav.NavSurface.Interact -> Screen.Interact
    ai.ciris.mobile.shared.ui.nav.NavSurface.Sessions -> Screen.Sessions
    ai.ciris.mobile.shared.ui.nav.NavSurface.Tickets -> Screen.Tickets
    ai.ciris.mobile.shared.ui.nav.NavSurface.Scheduler -> Screen.Scheduler
    ai.ciris.mobile.shared.ui.nav.NavSurface.Services -> Screen.Services
    ai.ciris.mobile.shared.ui.nav.NavSurface.Tools -> Screen.Tools
    ai.ciris.mobile.shared.ui.nav.NavSurface.Telemetry -> Screen.Telemetry
    ai.ciris.mobile.shared.ui.nav.NavSurface.Logs -> Screen.Logs
    ai.ciris.mobile.shared.ui.nav.NavSurface.Transport -> Screen.Transport
    ai.ciris.mobile.shared.ui.nav.NavSurface.Memory -> Screen.Memory
    ai.ciris.mobile.shared.ui.nav.NavSurface.GraphMemory -> Screen.GraphMemory
    ai.ciris.mobile.shared.ui.nav.NavSurface.WiseAuthority -> Screen.WiseAuthority
    ai.ciris.mobile.shared.ui.nav.NavSurface.AgentSettings -> Screen.Settings
    ai.ciris.mobile.shared.ui.nav.NavSurface.LLMSettings -> Screen.LLMSettings
    ai.ciris.mobile.shared.ui.nav.NavSurface.System -> Screen.System
    ai.ciris.mobile.shared.ui.nav.NavSurface.Runtime -> Screen.Runtime
    ai.ciris.mobile.shared.ui.nav.NavSurface.Config -> Screen.Config
    ai.ciris.mobile.shared.ui.nav.NavSurface.Skills -> Screen.SkillStudio
    ai.ciris.mobile.shared.ui.nav.NavSurface.HealthReputation -> Screen.HealthReputation
    ai.ciris.mobile.shared.ui.nav.NavSurface.Users -> Screen.Users
    ai.ciris.mobile.shared.ui.nav.NavSurface.Adapters -> Screen.Adapters
    ai.ciris.mobile.shared.ui.nav.NavSurface.Data -> Screen.DataManagement
    ai.ciris.mobile.shared.ui.nav.NavSurface.Audit -> Screen.Audit
    ai.ciris.mobile.shared.ui.nav.NavSurface.Consent -> Screen.Consent
    ai.ciris.mobile.shared.ui.nav.NavSurface.Trust -> Screen.Trust
    ai.ciris.mobile.shared.ui.nav.NavSurface.NetworkOps -> Screen.NetworkOps
    ai.ciris.mobile.shared.ui.nav.NavSurface.Nodes -> Screen.ManageNodes
    ai.ciris.mobile.shared.ui.nav.NavSurface.ManageConsent -> Screen.ManageConsent
    ai.ciris.mobile.shared.ui.nav.NavSurface.Contacts -> Screen.Contacts
    ai.ciris.mobile.shared.ui.nav.NavSurface.Delegations -> Screen.Delegations
    ai.ciris.mobile.shared.ui.nav.NavSurface.IdentityManagement -> Screen.IdentityManagement
    ai.ciris.mobile.shared.ui.nav.NavSurface.Accord -> Screen.Accord
    ai.ciris.mobile.shared.ui.nav.NavSurface.ProvisionAccordHolder -> Screen.ProvisionAccordHolder
    ai.ciris.mobile.shared.ui.nav.NavSurface.AccordCeremony -> Screen.AccordCeremony
    // Safety parent routes to its first child (Moderation); the two leaves map 1:1.
    ai.ciris.mobile.shared.ui.nav.NavSurface.Safety -> Screen.Moderation
    ai.ciris.mobile.shared.ui.nav.NavSurface.Moderation -> Screen.Moderation
    ai.ciris.mobile.shared.ui.nav.NavSurface.ChildSafety -> Screen.ChildSafety
    ai.ciris.mobile.shared.ui.nav.NavSurface.Storage -> Screen.Storage
    ai.ciris.mobile.shared.ui.nav.NavSurface.Billing -> Screen.Billing
    ai.ciris.mobile.shared.ui.nav.NavSurface.Wallet -> Screen.Wallet
    ai.ciris.mobile.shared.ui.nav.NavSurface.Participate -> Screen.Participate
    ai.ciris.mobile.shared.ui.nav.NavSurface.EnvironmentGraph -> Screen.EnvironmentInfo
    ai.ciris.mobile.shared.ui.nav.NavSurface.Delegation -> Screen.Delegation
    ai.ciris.mobile.shared.ui.nav.NavSurface.Constitutional -> Screen.Constitutional
    ai.ciris.mobile.shared.ui.nav.NavSurface.AgentsList -> Screen.AgentsList
    ai.ciris.mobile.shared.ui.nav.NavSurface.ClientInterface -> Screen.VizSettings
    // CEG 0.6 layer hubs (2.9.4 Phase A)
    ai.ciris.mobile.shared.ui.nav.NavSurface.LayerAgent -> Screen.LayerAgent
    ai.ciris.mobile.shared.ui.nav.NavSurface.LayerFamily -> Screen.LayerFamily
    ai.ciris.mobile.shared.ui.nav.NavSurface.LayerLocalCommunity -> Screen.LayerLocalCommunity
    ai.ciris.mobile.shared.ui.nav.NavSurface.LayerGlobalCommunities -> Screen.LayerGlobalCommunities
    ai.ciris.mobile.shared.ui.nav.NavSurface.LayerGlobalCommons -> Screen.LayerGlobalCommons
    ai.ciris.mobile.shared.ui.nav.NavSurface.Commons -> Screen.Commons
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

/**
 * Non-blocking node-vs-client VERSION-MISMATCH banner. The connected node reports
 * its version in /v1/health; when it differs materially from the app's build
 * ([ai.ciris.mobile.shared.models.CLIENT_VERSION]) we surface an "update
 * recommended" hint. Purely informational — it never blocks usage.
 */
@Composable
private fun VersionMismatchBanner(
    nodeVersion: String,
    clientVersion: String,
    modifier: Modifier = Modifier
) {
    Surface(
        modifier = modifier
            .fillMaxWidth()
            .statusBarsPadding()
            .padding(8.dp),
        color = MaterialTheme.colorScheme.tertiaryContainer,
        shape = RoundedCornerShape(8.dp),
        tonalElevation = 2.dp
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Icon(
                imageVector = Icons.Filled.Info,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onTertiaryContainer,
                modifier = Modifier.size(18.dp)
            )
            Text(
                text = "Node is v$nodeVersion — app built for v$clientVersion. Update recommended.",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onTertiaryContainer
            )
        }
    }
}
