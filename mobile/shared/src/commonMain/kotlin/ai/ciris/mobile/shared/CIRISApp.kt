package ai.ciris.mobile.shared

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.auth.SilentSignInResult
import ai.ciris.mobile.shared.auth.TokenManager
import ai.ciris.mobile.shared.auth.TokenState
import ai.ciris.mobile.shared.platform.EnvFileUpdater
import ai.ciris.mobile.shared.platform.PythonRuntimeProtocol
import ai.ciris.mobile.shared.platform.SecureStorage
import ai.ciris.mobile.shared.platform.createEnvFileUpdater
import ai.ciris.mobile.shared.platform.createPythonRuntime
import ai.ciris.mobile.shared.platform.createSecureStorage
import ai.ciris.mobile.shared.ui.screens.*
import ai.ciris.mobile.shared.viewmodels.AdaptersViewModel
import ai.ciris.mobile.shared.viewmodels.BillingViewModel
import ai.ciris.mobile.shared.viewmodels.InteractViewModel
import ai.ciris.mobile.shared.viewmodels.SessionsViewModel
import ai.ciris.mobile.shared.viewmodels.SettingsViewModel
import ai.ciris.mobile.shared.viewmodels.SetupViewModel
import ai.ciris.mobile.shared.viewmodels.StartupPhase
import ai.ciris.mobile.shared.viewmodels.StartupViewModel
import ai.ciris.mobile.shared.viewmodels.TelemetryViewModel
import androidx.compose.foundation.layout.*
import kotlinx.coroutines.launch
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.MoreVert
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Star
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
 * Callback interface for Google Sign-In
 * Platform implementations provide actual Google SDK integration
 */
interface GoogleSignInCallback {
    /**
     * Request interactive Google Sign-In (shows UI).
     */
    fun onGoogleSignInRequested(onResult: (GoogleSignInResult) -> Unit)

    /**
     * Attempt silent sign-in (no UI).
     * Returns a fresh token if user is already signed in, or signals that interactive login is needed.
     */
    fun onSilentSignInRequested(onResult: (GoogleSignInResult) -> Unit)
}

/**
 * Result of Google Sign-In attempt
 */
sealed class GoogleSignInResult {
    data class Success(
        val idToken: String,
        val userId: String,
        val email: String?,
        val displayName: String?
    ) : GoogleSignInResult()

    data class Error(val message: String) : GoogleSignInResult()
    object Cancelled : GoogleSignInResult()
}

@Composable
fun CIRISApp(
    accessToken: String,
    baseUrl: String = "http://localhost:8080",
    pythonRuntime: PythonRuntimeProtocol = createPythonRuntime(),
    secureStorage: SecureStorage = createSecureStorage(),
    envFileUpdater: EnvFileUpdater = createEnvFileUpdater(),
    googleSignInCallback: GoogleSignInCallback? = null
) {
    val TAG = "CIRISApp"
    val coroutineScope = rememberCoroutineScope()
    val apiClient = remember { CIRISApiClient(baseUrl, accessToken) }

    // Track the current auth token - will be updated after login/setup
    var currentAccessToken by remember { mutableStateOf<String?>(null) }

    // Navigation state
    var currentScreen by remember { mutableStateOf<Screen>(Screen.Startup) }

    // First-run detection state
    var isFirstRun by remember { mutableStateOf<Boolean?>(null) }
    var checkingFirstRun by remember { mutableStateOf(false) }

    // Login state
    var isLoginLoading by remember { mutableStateOf(false) }
    var loginStatusMessage by remember { mutableStateOf<String?>(null) }

    // Google auth state for token exchange after setup
    var pendingGoogleIdToken by remember { mutableStateOf<String?>(null) }
    var pendingGoogleUserId by remember { mutableStateOf<String?>(null) }

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
                            is GoogleSignInResult.Success -> {
                                SilentSignInResult.Success(result.idToken, result.email)
                            }
                            is GoogleSignInResult.Error -> {
                                // Error code 4 = SIGN_IN_REQUIRED
                                if (result.message.contains("SIGN_IN_REQUIRED") || result.message.startsWith("4:")) {
                                    SilentSignInResult.NeedsInteractiveLogin(4)
                                } else {
                                    SilentSignInResult.Error(result.message)
                                }
                            }
                            GoogleSignInResult.Cancelled -> {
                                SilentSignInResult.NeedsInteractiveLogin(12500)
                            }
                        }
                        continuation.resumeWith(Result.success(silentResult))
                    }
                }
            }

            // Set callback for when Google ID token is refreshed
            // IMPORTANT: The refreshed token is a Google ID token, NOT a CIRIS access token
            // We need to exchange it with the CIRIS API to get an access token
            tokenManager.setOnTokenRefreshed { googleIdToken ->
                println("[$TAG][INFO] Google ID token refreshed by TokenManager, exchanging for CIRIS token")
                tokenExchangeComplete = false
                coroutineScope.launch {
                    try {
                        // Exchange Google ID token for CIRIS access token
                        val authResponse = apiClient.googleAuth(googleIdToken, null)
                        val cirisToken = authResponse.access_token
                        println("[$TAG][INFO] Got CIRIS access token: ${cirisToken.take(8)}...${cirisToken.takeLast(4)}")

                        // Set the CIRIS token on the API client
                        apiClient.setAccessToken(cirisToken)
                        currentAccessToken = cirisToken

                        // Save CIRIS token to secure storage (not the Google ID token!)
                        secureStorage.saveAccessToken(cirisToken)
                            .onSuccess { println("[$TAG][INFO] Refreshed CIRIS token saved to secure storage") }
                            .onFailure { e -> println("[$TAG][WARN] Failed to save refreshed CIRIS token: ${e.message}") }

                        // Update .env file with fresh Google ID token for billing
                        envFileUpdater.updateEnvWithToken(googleIdToken)
                            .onSuccess { updated ->
                                if (updated) println("[$TAG][INFO] Updated .env with fresh Google ID token for billing")
                            }
                            .onFailure { e -> println("[$TAG][WARN] Failed to update .env: ${e.message}") }

                        tokenExchangeComplete = true
                    } catch (e: Exception) {
                        println("[$TAG][ERROR] Failed to exchange refreshed Google token: ${e::class.simpleName}: ${e.message}")
                        tokenExchangeComplete = true // Mark complete even on failure to unblock waiting code
                        // On failure, the user may need to re-authenticate
                    }
                }
            }
        }
    }

    // ViewModels
    val startupViewModel: StartupViewModel = viewModel {
        StartupViewModel(pythonRuntime, apiClient)
    }
    // SetupViewModel is a plain class, not an androidx ViewModel
    val setupViewModel = remember { SetupViewModel() }
    val interactViewModel: InteractViewModel = viewModel {
        InteractViewModel(apiClient)
    }
    val settingsViewModel: SettingsViewModel = viewModel {
        SettingsViewModel(secureStorage, apiClient)
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

    // Watch startup phase to check first-run when ready
    val phase by startupViewModel.phase.collectAsState()

    LaunchedEffect(phase) {
        if (phase == StartupPhase.READY && !checkingFirstRun) {
            checkingFirstRun = true
            println("[$TAG][INFO] Startup READY, checking first-run status...")

            // Check if this is first run via API
            isFirstRun = checkFirstRunStatus(baseUrl)
            println("[$TAG][INFO] First run check result: $isFirstRun")

            if (isFirstRun == true) {
                // First run - show login screen first
                println("[$TAG][INFO] First run detected, navigating to Login")
                currentScreen = Screen.Login
            } else {
                // Not first run - try to load stored token and check if valid/refresh if needed
                println("[$TAG][INFO] Not first run, attempting to load and validate stored token")
                secureStorage.getAccessToken()
                    .onSuccess { storedToken ->
                        if (storedToken != null) {
                            println("[$TAG][INFO] Loaded stored token: ${storedToken.take(8)}...${storedToken.takeLast(4)}")

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
                                    currentAccessToken = storedToken
                                }

                                // Trigger data loading now that we have auth
                                println("[$TAG][INFO] Triggering data load for ViewModels after token set")
                                billingViewModel.loadBalance()
                                adaptersViewModel.fetchAdapters()
                                currentScreen = Screen.Interact
                            } else {
                                // Token invalid and couldn't refresh - need interactive login
                                println("[$TAG][INFO] Token invalid/expired and silent refresh failed - redirecting to login")
                                currentScreen = Screen.Login
                            }
                        } else {
                            println("[$TAG][WARN] No stored token found, redirecting to login")
                            currentScreen = Screen.Login
                        }
                    }
                    .onFailure { e ->
                        println("[$TAG][ERROR] Failed to load stored token: ${e.message}")
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
                LoginScreen(
                    onGoogleSignIn = {
                        if (googleSignInCallback != null) {
                            // Use platform-specific Google sign-in
                            isLoginLoading = true
                            loginStatusMessage = "Signing in with Google..."

                            googleSignInCallback.onGoogleSignInRequested { result ->
                                isLoginLoading = false
                                loginStatusMessage = null

                                when (result) {
                                    is GoogleSignInResult.Success -> {
                                        println("[$TAG][INFO] Google sign-in success: userId=${result.userId}, email=${result.email}")

                                        // Check if setup is already complete
                                        coroutineScope.launch {
                                            val setupRequired = checkFirstRunStatus(baseUrl)
                                            println("[$TAG][INFO] Setup required check: $setupRequired")

                                            if (!setupRequired) {
                                                // Setup already done - exchange token immediately
                                                println("[$TAG][INFO] Setup already complete, exchanging token directly")
                                                try {
                                                    val authResponse = apiClient.googleAuth(result.idToken, result.userId)
                                                    val cirisToken = authResponse.access_token
                                                    println("[$TAG][INFO] Got CIRIS access token: ${cirisToken.take(8)}...${cirisToken.takeLast(4)}")

                                                    // Set the token on the API client
                                                    apiClient.setAccessToken(cirisToken)
                                                    currentAccessToken = cirisToken

                                                    // Save to secure storage
                                                    secureStorage.saveAccessToken(cirisToken)
                                                        .onSuccess { println("[$TAG][INFO] CIRIS token saved to secure storage") }
                                                        .onFailure { e -> println("[$TAG][WARN] Failed to save token: ${e.message}") }

                                                    // Update .env file with fresh Google ID token for billing
                                                    envFileUpdater.updateEnvWithToken(result.idToken)
                                                        .onSuccess { updated ->
                                                            if (updated) println("[$TAG][INFO] Updated .env with fresh Google ID token for billing")
                                                        }
                                                        .onFailure { e -> println("[$TAG][WARN] Failed to update .env: ${e.message}") }

                                                    // Handle new token with TokenManager for periodic refresh
                                                    tokenManager.handleNewToken(result.idToken)

                                                    // Trigger data loading
                                                    println("[$TAG][INFO] Triggering data load for ViewModels")
                                                    billingViewModel.loadBalance()
                                                    adaptersViewModel.fetchAdapters()

                                                    currentScreen = Screen.Interact
                                                } catch (e: Exception) {
                                                    println("[$TAG][ERROR] Token exchange failed: ${e.message}")
                                                    loginStatusMessage = "Token exchange failed: ${e.message}"
                                                }
                                            } else {
                                                // Setup needed - go through wizard
                                                pendingGoogleIdToken = result.idToken
                                                pendingGoogleUserId = result.userId
                                                setupViewModel.setGoogleAuthState(
                                                    isAuth = true,
                                                    idToken = result.idToken,
                                                    email = result.email,
                                                    userId = result.userId
                                                )
                                                currentScreen = Screen.Setup
                                            }
                                        }
                                    }
                                    is GoogleSignInResult.Error -> {
                                        loginStatusMessage = "Sign-in failed: ${result.message}"
                                    }
                                    GoogleSignInResult.Cancelled -> {
                                        // User cancelled, stay on login screen
                                    }
                                }
                            }
                        } else {
                            // No callback provided - show error
                            loginStatusMessage = "Google Sign-In not available"
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
                SetupScreen(
                    viewModel = setupViewModel,
                    apiClient = apiClient,
                    onSetupComplete = {
                        println("[$TAG][INFO] Setup complete, exchanging tokens...")
                        // After setup completes, exchange Google ID token for CIRIS access token
                        coroutineScope.launch {
                            try {
                                val idToken = pendingGoogleIdToken
                                val userId = pendingGoogleUserId

                                if (idToken != null) {
                                    println("[$TAG][INFO] Exchanging Google ID token for CIRIS access token")
                                    val authResponse = apiClient.googleAuth(idToken, userId)
                                    val cirisToken = authResponse.access_token
                                    println("[$TAG][INFO] Got CIRIS access token: ${cirisToken.take(8)}...${cirisToken.takeLast(4)}")

                                    // Set the token on the API client
                                    apiClient.setAccessToken(cirisToken)
                                    currentAccessToken = cirisToken

                                    // Trigger data loading now that we have auth
                                    println("[$TAG][INFO] Triggering data load for ViewModels after Google auth")
                                    billingViewModel.loadBalance()
                                    adaptersViewModel.fetchAdapters()

                                    // Store token for future sessions
                                    secureStorage.saveAccessToken(cirisToken)
                                        .onSuccess { println("[$TAG][INFO] Token saved to secure storage") }
                                        .onFailure { e -> println("[$TAG][WARN] Failed to save token to secure storage: ${e.message}") }

                                    // Update .env file with fresh Google ID token for billing
                                    envFileUpdater.updateEnvWithToken(idToken)
                                        .onSuccess { updated ->
                                            if (updated) println("[$TAG][INFO] Updated .env with fresh Google ID token for billing")
                                        }
                                        .onFailure { e -> println("[$TAG][WARN] Failed to update .env: ${e.message}") }

                                    // Clear pending tokens
                                    pendingGoogleIdToken = null
                                    pendingGoogleUserId = null
                                } else {
                                    println("[$TAG][INFO] No pending Google token, using local auth")
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
                            onAdaptersClick = { currentScreen = Screen.Adapters }
                        )
                    }
                ) { paddingValues ->
                    InteractScreen(
                        viewModel = interactViewModel,
                        onNavigateBack = { /* Already at root */ },
                        modifier = Modifier.padding(paddingValues)
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
                    onProductClick = { product ->
                        println("[CIRISApp][INFO][Screen.Billing] Product clicked: ${product.productId}")
                        billingViewModel.onProductSelected(product) { selectedProduct ->
                            // Platform-specific purchase flow would be triggered here
                            // For now, just log that we're ready to purchase
                            println("[CIRISApp][INFO][Screen.Billing] Ready to purchase: ${selectedProduct.productId}")
                            // On Android, this would call BillingManager.launchPurchaseFlow()
                            // On iOS, this would call StoreKit APIs
                        }
                    },
                    onRefresh = {
                        println("[CIRISApp][INFO][Screen.Billing] User triggered refresh")
                        billingViewModel.refresh()
                    },
                    onNavigateBack = {
                        println("[CIRISApp][INFO][Screen.Billing] Navigating back to Interact")
                        currentScreen = Screen.Interact
                    }
                )
            }

            Screen.Telemetry -> {
                val telemetryData by telemetryViewModel.telemetryData.collectAsState()
                val isTelemetryLoading by telemetryViewModel.isLoading.collectAsState()

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
            }
        }
    }
}

/**
 * Check if setup is required via /v1/setup/status API
 */
private suspend fun checkFirstRunStatus(baseUrl: String): Boolean = withContext(Dispatchers.IO) {
    try {
        val url = java.net.URL("$baseUrl/v1/setup/status")
        val connection = url.openConnection() as java.net.HttpURLConnection
        connection.connectTimeout = 5000
        connection.readTimeout = 5000
        connection.requestMethod = "GET"

        if (connection.responseCode == 200) {
            val response = connection.inputStream.bufferedReader().readText()
            connection.disconnect()
            // Parse JSON response - look for "setup_required": true
            response.contains("\"setup_required\"") &&
                response.contains("\"setup_required\": true") ||
                response.contains("\"setup_required\":true")
        } else {
            connection.disconnect()
            // If we can't check, assume first run for safety
            true
        }
    } catch (e: Exception) {
        // On error, assume first run
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
    onAdaptersClick: () -> Unit = {}
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
}
