package ai.ciris.mobile.shared

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.platform.PythonRuntime
import ai.ciris.mobile.shared.platform.SecureStorage
import ai.ciris.mobile.shared.platform.createPythonRuntime
import ai.ciris.mobile.shared.platform.createSecureStorage
import ai.ciris.mobile.shared.ui.screens.*
import ai.ciris.mobile.shared.viewmodels.InteractViewModel
import ai.ciris.mobile.shared.viewmodels.SettingsViewModel
import ai.ciris.mobile.shared.viewmodels.SetupViewModel
import ai.ciris.mobile.shared.viewmodels.StartupPhase
import ai.ciris.mobile.shared.viewmodels.StartupViewModel
import androidx.compose.foundation.layout.*
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
    fun onGoogleSignInRequested(onResult: (GoogleSignInResult) -> Unit)
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
    pythonRuntime: PythonRuntime = createPythonRuntime(),
    secureStorage: SecureStorage = createSecureStorage(),
    googleSignInCallback: GoogleSignInCallback? = null
) {
    val apiClient = remember { CIRISApiClient(baseUrl, accessToken) }

    // Navigation state
    var currentScreen by remember { mutableStateOf<Screen>(Screen.Startup) }

    // First-run detection state
    var isFirstRun by remember { mutableStateOf<Boolean?>(null) }
    var checkingFirstRun by remember { mutableStateOf(false) }

    // Login state
    var isLoginLoading by remember { mutableStateOf(false) }
    var loginStatusMessage by remember { mutableStateOf<String?>(null) }

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

    // Watch startup phase to check first-run when ready
    val phase by startupViewModel.phase.collectAsState()

    LaunchedEffect(phase) {
        if (phase == StartupPhase.READY && !checkingFirstRun) {
            checkingFirstRun = true
            // Check if this is first run via API
            isFirstRun = checkFirstRunStatus(baseUrl)

            if (isFirstRun == true) {
                // First run - show login screen first
                currentScreen = Screen.Login
            } else {
                currentScreen = Screen.Interact
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
                                        setupViewModel.setGoogleAuthState(
                                            isAuth = true,
                                            idToken = result.idToken,
                                            email = result.email,
                                            userId = result.userId
                                        )
                                        currentScreen = Screen.Setup
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
                        // After setup completes, Python resumes and starts remaining 12 services
                        // Go back to StartupScreen to show the remaining services starting
                        // Reset the startup phase so it re-polls for services
                        startupViewModel.resetForResume()
                        checkingFirstRun = false  // Allow re-check after startup completes
                        currentScreen = Screen.Startup
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
                        // TODO: Clear tokens and restart
                        currentScreen = Screen.Startup
                    }
                )
            }

            Screen.Billing -> {
                // TODO: Implement BillingViewModel and connect to API
                BillingScreen(
                    currentBalance = -1,
                    products = emptyList(),
                    isLoading = false,
                    onProductClick = { /* TODO */ },
                    onRefresh = { /* TODO */ },
                    onNavigateBack = { currentScreen = Screen.Interact }
                )
            }

            Screen.Telemetry -> {
                // TODO: Implement TelemetryViewModel and connect to API
                TelemetryScreen(
                    telemetryData = TelemetryData(),
                    isLoading = false,
                    onRefresh = { /* TODO */ },
                    onNavigateBack = { currentScreen = Screen.Interact }
                )
            }

            Screen.Sessions -> {
                // TODO: Implement SessionsViewModel and connect to API
                SessionsScreen(
                    currentState = "WORK",
                    isLoading = false,
                    onInitiateSession = { /* TODO */ },
                    onRefresh = { /* TODO */ },
                    onNavigateBack = { currentScreen = Screen.Interact }
                )
            }

            Screen.Adapters -> {
                // TODO: Implement AdaptersViewModel and connect to API
                AdaptersScreen(
                    adapters = emptyList(),
                    isConnected = true,
                    isLoading = false,
                    onReloadAdapter = { /* TODO */ },
                    onRemoveAdapter = { /* TODO */ },
                    onAddAdapter = { /* TODO */ },
                    onRefresh = { /* TODO */ },
                    onNavigateBack = { currentScreen = Screen.Interact }
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
