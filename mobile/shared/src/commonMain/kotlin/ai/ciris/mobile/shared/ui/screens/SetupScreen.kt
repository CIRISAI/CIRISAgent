package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.Platform
import ai.ciris.mobile.shared.models.SetupMode
import ai.ciris.mobile.shared.models.filterAdaptersForPlatform
import ai.ciris.mobile.shared.platform.LocalInferenceCapability
import ai.ciris.mobile.shared.platform.LocalInferenceTier
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.getOAuthProviderName
import ai.ciris.mobile.shared.platform.getPlatform
import ai.ciris.mobile.shared.platform.probeLocalInferenceCapability
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.platform.TestAutomation

import ai.ciris.mobile.shared.models.ConfigCompleteData
import ai.ciris.mobile.shared.models.ConfigSessionData
import ai.ciris.mobile.shared.models.ConfigStepResultData
import ai.ciris.mobile.shared.models.DiscoveredItemData
import ai.ciris.mobile.shared.models.LoadableAdaptersData
import ai.ciris.mobile.shared.ui.components.AdapterWizardDialog
import ai.ciris.mobile.shared.ui.components.LocalLlmServerDiscovery
import ai.ciris.mobile.shared.ui.components.rememberLocalLlmDiscoveryState
import ai.ciris.mobile.shared.viewmodels.DeviceAuthStatus
import ai.ciris.mobile.shared.viewmodels.LlmValidationResult
import ai.ciris.mobile.shared.viewmodels.ModelInfo
import ai.ciris.mobile.shared.viewmodels.SetupStep
import ai.ciris.mobile.shared.viewmodels.SetupFormState
import ai.ciris.mobile.shared.viewmodels.SetupViewModel
import ai.ciris.mobile.shared.viewmodels.SUPPORTED_LANGUAGES
import ai.ciris.mobile.shared.viewmodels.LocationGranularity
import androidx.compose.animation.AnimatedVisibility
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.derivedStateOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalFocusManager
import ai.ciris.mobile.shared.platform.openUrlInBrowser
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ai.ciris.mobile.shared.ui.theme.ColorTheme
import ai.ciris.mobile.shared.ui.theme.SemanticColors

private const val TAG = "SetupScreen"

/**
 * Setup Wizard Screen - EXACTLY matches android/app/.../setup/ fragments
 *
 * Uses LIGHT THEME with colors from android/app/src/main/res/values/colors.xml:
 * - text_primary: #1F2937 (dark gray)
 * - text_secondary: #6B7280 (medium gray)
 * - success_light: #D1FAE5, success_dark: #065F46, success_text: #047857
 * - info_light: #DBEAFE, info_dark: #1E40AF, info_text: #1D4ED8
 */

// Colors for light-themed setup wizard
// Uses SemanticColors for status indicators (success/error/warning/info)
// while maintaining the light background design
private object SetupColors {
    // Get semantic colors for light mode
    private val semantic = SemanticColors.forTheme(ColorTheme.DEFAULT, isDark = false)

    val Background = Color.White
    val TextPrimary = Color(0xFF1F2937)
    val TextSecondary = Color(0xFF6B7280)

    // Success (green) - derived from SemanticColors light mode
    val SuccessLight = semantic.surfaceSuccess
    val SuccessBorder = Color(0xFF6EE7B7)
    val SuccessDark = semantic.onSuccess
    val SuccessText = semantic.success

    // Info (blue) - derived from SemanticColors light mode
    val InfoLight = semantic.surfaceInfo
    val InfoBorder = Color(0xFF93C5FD)
    val InfoDark = semantic.onInfo
    val InfoText = semantic.info

    // Error (red) - derived from SemanticColors light mode
    val ErrorLight = semantic.surfaceError
    val ErrorDark = semantic.onError
    val ErrorText = semantic.error

    // Gray for cards
    val GrayLight = Color(0xFFF3F4F6)

    // Primary accent
    val Primary = Color(0xFF667eea)
}

/**
 * Format population number for display (e.g., 12,691,836 -> "12.7M")
 */
private fun formatPopulation(pop: Int): String {
    return when {
        pop >= 1_000_000 -> "${(pop / 100_000) / 10.0}M"
        pop >= 1_000 -> "${(pop / 100) / 10.0}K"
        else -> pop.toString()
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SetupScreen(
    viewModel: SetupViewModel,
    apiClient: CIRISApiClient,
    onSetupComplete: () -> Unit,
    onBackToLogin: (() -> Unit)? = null,  // Optional callback to return to login screen
    modifier: Modifier = Modifier
) {
    val state by viewModel.state.collectAsState()
    val coroutineScope = rememberCoroutineScope()
    val semantic = SemanticColors.forTheme(ColorTheme.DEFAULT, isDark = false)

    // Observe text input requests for test automation
    val textInputRequest by TestAutomation.textInputRequests.collectAsState()

    // Handle incoming text input requests
    LaunchedEffect(textInputRequest) {
        textInputRequest?.let { request ->
            when (request.testTag) {
                "input_public_api_email" -> {
                    if (request.clearFirst) {
                        viewModel.setPublicApiEmail(request.text)
                    } else {
                        viewModel.setPublicApiEmail(state.publicApiEmail + request.text)
                    }
                    TestAutomation.clearTextInputRequest()
                }
                "input_username" -> {
                    if (request.clearFirst) {
                        viewModel.setUsername(request.text)
                    } else {
                        viewModel.setUsername(state.username + request.text)
                    }
                    TestAutomation.clearTextInputRequest()
                }
                "input_password" -> {
                    if (request.clearFirst) {
                        viewModel.setUserPassword(request.text)
                    } else {
                        viewModel.setUserPassword(state.userPassword + request.text)
                    }
                    TestAutomation.clearTextInputRequest()
                }
                "input_api_key" -> {
                    if (request.clearFirst) {
                        viewModel.setLlmApiKey(request.text)
                    } else {
                        viewModel.setLlmApiKey(state.llmApiKey + request.text)
                    }
                    TestAutomation.clearTextInputRequest()
                }
                "input_llm_model_text" -> {
                    if (request.clearFirst) {
                        viewModel.setLlmModel(request.text)
                    } else {
                        viewModel.setLlmModel(state.llmModel + request.text)
                    }
                    TestAutomation.clearTextInputRequest()
                }
                "input_llm_base_url" -> {
                    if (request.clearFirst) {
                        viewModel.setLlmBaseUrl(request.text)
                    } else {
                        viewModel.setLlmBaseUrl(state.llmBaseUrl + request.text)
                    }
                    TestAutomation.clearTextInputRequest()
                }
            }
        }
    }

    // Set up the wizard API for adapter configuration
    LaunchedEffect(Unit) {
        viewModel.setWizardApi(object : SetupViewModel.AdapterWizardApi {
            override suspend fun getLoadableAdapters(): LoadableAdaptersData {
                return apiClient.getLoadableAdapters()
            }
            override suspend fun startAdapterConfiguration(adapterType: String): ConfigSessionData {
                return apiClient.startAdapterConfiguration(adapterType)
            }
            override suspend fun executeConfigurationStep(sessionId: String, stepData: Map<String, String>): ConfigStepResultData {
                return apiClient.executeConfigurationStep(sessionId, stepData)
            }
            override suspend fun getConfigurationSessionStatus(sessionId: String): ConfigSessionData {
                return apiClient.getConfigurationSessionStatus(sessionId)
            }
            override suspend fun completeAdapterConfiguration(sessionId: String): ConfigCompleteData {
                return apiClient.completeAdapterConfiguration(sessionId)
            }
        })
    }

    // Load adapters and templates when entering OPTIONAL_FEATURES step
    LaunchedEffect(state.currentStep) {
        if (state.currentStep == SetupStep.OPTIONAL_FEATURES) {
            // Load adapters if not already loaded
            if (state.availableAdapters.isEmpty()) {
                // Fetch all adapters from server, then filter client-side based on platform
                // This approach works for both iOS and Android (KMP)
                viewModel.loadAvailableAdapters {
                    val allAdapters = apiClient.getSetupAdapters()
                    val currentPlatform = when (getPlatform()) {
                        ai.ciris.mobile.shared.platform.Platform.IOS -> Platform.IOS
                        ai.ciris.mobile.shared.platform.Platform.ANDROID -> Platform.ANDROID
                        ai.ciris.mobile.shared.platform.Platform.DESKTOP -> Platform.DESKTOP
                    }
                    filterAdaptersForPlatform(
                        adapters = allAdapters,
                        platform = currentPlatform,
                        useCirisServices = state.useCirisProxy()
                    )
                }
            }
            // Load templates if not already loaded
            if (state.availableTemplates.isEmpty()) {
                viewModel.loadAvailableTemplates {
                    apiClient.getSetupTemplates()
                }
            }
        }
    }

    // Adapter Wizard Dialog (shown when configuring adapters that require setup)
    if (state.showAdapterWizard) {
        // Create a minimal LoadableAdaptersData for the dialog to show wizard steps
        // The wizard session is what drives the actual steps
        val wizardLoadableAdapters = state.adapterWizardType?.let { adapterType ->
            state.availableAdapters.find { it.id == adapterType }?.let { adapter ->
                LoadableAdaptersData(
                    adapters = listOf(
                        ai.ciris.mobile.shared.models.LoadableAdapterData(
                            adapterType = adapter.id,
                            name = adapter.name,
                            description = adapter.description,
                            requiresConfiguration = adapter.requires_config,
                            workflowType = null,
                            stepCount = state.adapterWizardSession?.totalSteps ?: 0,
                            requiresOauth = false,
                            serviceTypes = emptyList(),
                            platformAvailable = true
                        )
                    ),
                    totalCount = 1,
                    configurableCount = 1,
                    directLoadCount = 0
                )
            }
        }

        AdapterWizardDialog(
            loadableAdapters = wizardLoadableAdapters,
            wizardSession = state.adapterWizardSession,
            isLoading = state.adapterWizardLoading,
            error = state.adapterWizardError,
            discoveredItems = state.adapterDiscoveredItems,
            discoveryExecuted = state.adapterDiscoveryExecuted,
            oauthUrl = state.adapterOAuthUrl,
            awaitingOAuthCallback = state.adapterAwaitingOAuthCallback,
            selectOptions = state.adapterSelectOptions,
            onSelectType = { /* Not used - we go directly to wizard session */ },
            onLoadDirectly = { /* Not used during setup */ },
            onSubmitStep = { stepData -> viewModel.submitAdapterWizardStep(stepData) },
            onSelectDiscoveredItem = { item -> viewModel.selectAdapterDiscoveredItem(item) },
            onSubmitManualUrl = { url -> viewModel.submitAdapterManualUrl(url) },
            onRetryDiscovery = { viewModel.executeAdapterDiscoveryStep() },
            onInitiateOAuth = { viewModel.initiateAdapterOAuthStep() },
            onCheckOAuthStatus = { viewModel.checkAdapterOAuthOnResume() },
            onBack = { viewModel.adapterWizardBack() },
            onDismiss = { viewModel.closeAdapterWizard() }
        )
    }

    Surface(
        modifier = modifier.fillMaxSize(),
        color = SetupColors.Background
    ) {
        Column(modifier = Modifier.fillMaxSize()) {
            // Step indicators at top
            StepIndicators(
                currentStep = state.currentStep,
                isNodeFlow = state.isNodeFlow,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 16.dp, horizontal = 24.dp)
            )

            // Step content
            Box(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
            ) {
                when (state.currentStep) {
                    SetupStep.WELCOME -> WelcomeStep(
                        viewModel = viewModel,
                        state = state,
                        apiClient = apiClient
                    )
                    SetupStep.NODE_AUTH -> NodeAuthStep(viewModel, state, apiClient)
                    SetupStep.PREFERENCES -> PreferencesStep(viewModel, state)
                    SetupStep.LLM_CONFIGURATION -> LlmConfigurationStep(viewModel, state, apiClient)
                    SetupStep.OPTIONAL_FEATURES -> OptionalFeaturesStep(viewModel, state)
                    SetupStep.ACCOUNT_AND_CONFIRMATION -> AccountConfirmationStep(viewModel, state)
                    SetupStep.VERIFY_SETUP -> OptionalFeaturesStep(viewModel, state) // Legacy - redirects to OPTIONAL_FEATURES
                    SetupStep.COMPLETE -> CompleteStep(onSetupComplete)
                }
            }

            // Error display for submission failures
            state.submissionError?.let { error ->
                val isAlreadyConfigured = error.contains("already", ignoreCase = true) ||
                                          error.contains("configured", ignoreCase = true) ||
                                          error.contains("completed", ignoreCase = true)

                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(if (isAlreadyConfigured) semantic.surfaceWarning else SetupColors.ErrorLight)
                        .padding(16.dp)
                ) {
                    Text(
                        text = if (isAlreadyConfigured) localizedString("mobile.setup_already_complete") else localizedString("mobile.setup_error"),
                        fontWeight = FontWeight.Bold,
                        color = if (isAlreadyConfigured) semantic.onWarning else SetupColors.ErrorDark
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = error,
                        fontSize = 14.sp,
                        color = if (isAlreadyConfigured) semantic.onWarning else SetupColors.ErrorDark
                    )
                    if (isAlreadyConfigured) {
                        Spacer(modifier = Modifier.height(12.dp))
                        Button(
                            onClick = {
                                PlatformLogger.i(TAG, " User chose to skip setup (already configured)")
                                onSetupComplete()
                            },
                            modifier = Modifier.testableClickable("btn_continue_to_app") {
                                PlatformLogger.i(TAG, " User chose to skip setup (already configured)")
                                onSetupComplete()
                            },
                            colors = ButtonDefaults.buttonColors(
                                containerColor = SetupColors.Primary
                            )
                        ) {
                            Text(localizedString("mobile.setup_continue_app"))
                        }
                    }
                }
            }

            // Navigation buttons - with navigation bar padding to avoid overlap
            NavigationButtons(
                currentStep = state.currentStep,
                canProceed = state.canProceedFromCurrentStep(),
                validationError = state.getStepValidationError(),
                isSubmitting = state.isSubmitting,
                isNodeFlow = state.isNodeFlow,
                onNext = {
                    PlatformLogger.i(TAG, " onNext clicked, currentStep=${state.currentStep}, canProceed=${state.canProceedFromCurrentStep()}, isNodeFlow=${state.isNodeFlow}")
                    // Determine if this is the final step before COMPLETE
                    // - Normal flow: ACCOUNT_AND_CONFIRMATION is the final step
                    // - Node flow: OPTIONAL_FEATURES is the final step (skips ACCOUNT_AND_CONFIRMATION)
                    val isFinalStep = state.currentStep == SetupStep.ACCOUNT_AND_CONFIRMATION ||
                        (state.isNodeFlow && state.currentStep == SetupStep.OPTIONAL_FEATURES)

                    if (isFinalStep) {
                        // On final step, submit setup to API then advance
                        PlatformLogger.i(TAG, " Final step - launching coroutine to submit setup")
                        coroutineScope.launch {
                            PlatformLogger.i(TAG, " Coroutine started - calling viewModel.completeSetup")
                            try {
                                // Run API call on IO dispatcher to avoid blocking main thread
                                // Setup can take 20+ seconds as Python initializes services
                                val result = withContext(Dispatchers.IO) {
                                    viewModel.completeSetup { request ->
                                        // Make API call to /v1/setup/complete
                                        PlatformLogger.i(TAG, " Calling apiClient.completeSetup with provider=${request.llm_provider}")
                                        apiClient.completeSetup(request)
                                    }
                                }
                                PlatformLogger.i(TAG, " completeSetup returned: success=${result.success}, error=${result.error}")
                                if (result.success) {
                                    PlatformLogger.i(TAG, " Setup successful - advancing to next step")
                                    viewModel.nextStep()
                                } else {
                                    PlatformLogger.i(TAG, " ERROR: Setup failed: ${result.error}")
                                    // Error is now shown in UI via state.submissionError
                                }
                            } catch (e: Exception) {
                                PlatformLogger.i(TAG, " EXCEPTION in completeSetup: ${e.message}")
                                e.printStackTrace()
                            }
                        }
                    } else {
                        PlatformLogger.i(TAG, " Not final step - calling viewModel.nextStep()")
                        viewModel.nextStep()
                    }
                },
                onBack = {
                    // If backing out of NODE_AUTH, also reset server-side device auth state
                    if (state.isNodeFlow && state.currentStep == SetupStep.NODE_AUTH) {
                        PlatformLogger.i(TAG, "Backing out of NODE_AUTH - resetting server device auth state")
                        coroutineScope.launch(Dispatchers.IO) {
                            try {
                                apiClient.resetDeviceAuthOnServer()
                            } catch (e: Exception) {
                                PlatformLogger.w(TAG, "Failed to reset device auth on server: ${e.message}")
                            }
                        }
                    }
                    viewModel.previousStep()
                },
                onBackToLogin = onBackToLogin,
                modifier = Modifier
                    .fillMaxWidth()
                    .navigationBarsPadding()
                    .padding(horizontal = 24.dp, vertical = 16.dp)
            )
        }
    }
}

// ========== Step Indicators ==========
@Composable
private fun StepIndicators(
    currentStep: SetupStep,
    isNodeFlow: Boolean = false,
    modifier: Modifier = Modifier
) {
    val steps = if (isNodeFlow) {
        listOf(
            SetupStep.WELCOME to "1",
            SetupStep.NODE_AUTH to "2",
            SetupStep.LLM_CONFIGURATION to "3",
            SetupStep.OPTIONAL_FEATURES to "4"
        )
    } else {
        listOf(
            SetupStep.WELCOME to "1",
            SetupStep.LLM_CONFIGURATION to "2",
            SetupStep.OPTIONAL_FEATURES to "3",
            SetupStep.ACCOUNT_AND_CONFIRMATION to "4"
        )
    }

    Row(
        modifier = modifier.testable("setup_step_indicators"),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically
    ) {
        steps.forEachIndexed { index, (step, number) ->
            val isActive = currentStep >= step
            val isComplete = currentStep > step
            val stepName = step.name.lowercase()

            Box(
                modifier = Modifier
                    .size(32.dp)
                    .testable("step_indicator_$stepName", if (isComplete) "complete" else if (isActive) "active" else "inactive")
                    .background(
                        color = if (isActive) SetupColors.Primary else SetupColors.GrayLight,
                        shape = CircleShape
                    ),
                contentAlignment = Alignment.Center
            ) {
                Text(
                    text = if (isComplete) "✓" else number,
                    color = if (isActive) Color.White else SetupColors.TextSecondary,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold
                )
            }

            if (index < steps.size - 1) {
                Box(
                    modifier = Modifier
                        .width(48.dp)
                        .height(2.dp)
                        .background(
                            color = if (currentStep > step) SetupColors.Primary else SetupColors.GrayLight
                        )
                )
            }
        }
    }
}

// ========== Welcome Step (fragment_setup_welcome.xml) ==========
// NOTE: Google sign-in button is NOT here - it's in LoginScreen.kt
// This screen shows different cards based on whether user already signed in with Google
@Composable
private fun WelcomeStep(
    viewModel: SetupViewModel,
    state: SetupFormState,
    apiClient: CIRISApiClient,
    modifier: Modifier = Modifier
) {
    val isGoogleAuth = state.isGoogleAuth
    var detailsExpanded by remember { mutableStateOf(false) }
    val scrollState = rememberScrollState()

    // Track if there's more content below
    val showScrollIndicator by remember {
        derivedStateOf {
            scrollState.value < scrollState.maxValue - 50
        }
    }

    Box(modifier = modifier.fillMaxSize()) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(24.dp)
                .verticalScroll(scrollState),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
        // Badge: "✓ 100% Free & Open Source"
        Surface(
            shape = RoundedCornerShape(8.dp),
            color = SetupColors.SuccessLight,
            modifier = Modifier.padding(bottom = 16.dp)
        ) {
            Text(
                text = "✓ ${localizedString("mobile.setup_free_badge")}",
                color = SetupColors.SuccessText,
                fontSize = 14.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
            )
        }

        // Register Your Agent card — always visible, above the fold
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = SetupColors.SuccessLight,
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 16.dp)
                .border(1.dp, SetupColors.SuccessBorder, RoundedCornerShape(12.dp))
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    Text(
                        text = localizedString("mobile.setup_register_title"),
                        color = SetupColors.SuccessDark,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = SetupColors.SuccessLight
                    ) {
                        Text(
                            text = localizedString("mobile.setup_register_optional"),
                            color = SetupColors.SuccessDark,
                            fontSize = 10.sp,
                            fontWeight = FontWeight.Medium,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                }
                Text(
                    text = localizedString("mobile.setup_register_desc"),
                    color = SetupColors.SuccessText,
                    fontSize = 13.sp,
                    lineHeight = 18.sp,
                    modifier = Modifier.padding(top = 4.dp, bottom = 8.dp)
                )

                // Benefits list
                Column(modifier = Modifier.padding(bottom = 12.dp)) {
                    BenefitRow(localizedString("mobile.setup_register_audit"))
                    BenefitRow(localizedString("mobile.setup_register_ratchet"))
                    BenefitRow(localizedString("mobile.setup_register_scoring"))
                    BenefitRow(localizedString("mobile.setup_register_template"))
                }

                Text(
                    text = localizedString("mobile.setup_register_bond"),
                    color = SetupColors.SuccessDark,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.padding(bottom = 8.dp)
                )

                Button(
                    onClick = {
                        // Set default portal URL and enter node flow
                        viewModel.updateNodeUrl("https://portal.ciris.ai")
                        viewModel.enterNodeFlow()
                    },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = SetupColors.SuccessDark
                    ),
                    modifier = Modifier.fillMaxWidth().testableClickable("btn_connect_portal") {
                        viewModel.updateNodeUrl("https://portal.ciris.ai")
                        viewModel.enterNodeFlow()
                    }
                ) {
                    Text(localizedString("mobile.setup_register_connect"), fontWeight = FontWeight.Bold)
                }

                Text(
                    text = localizedString("mobile.setup_register_key_note"),
                    color = SetupColors.TextSecondary,
                    fontSize = 11.sp,
                    textAlign = TextAlign.Center,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 8.dp)
                )

                Text(
                    text = localizedString("mobile.setup_register_sales"),
                    color = SetupColors.TextSecondary,
                    fontSize = 11.sp,
                    textAlign = TextAlign.Center,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 4.dp)
                )

                // Skip option
                Text(
                    text = localizedString("mobile.setup_register_skip"),
                    color = SetupColors.TextSecondary,
                    fontSize = 11.sp,
                    textAlign = TextAlign.Center,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 8.dp)
                )
            }
        }

        // Main description
        Text(
            text = localizedString("setup.welcome_desc"),
            color = SetupColors.TextPrimary,
            fontSize = 16.sp,
            textAlign = TextAlign.Center,
            lineHeight = 24.sp,
            modifier = Modifier.padding(bottom = 16.dp)
        )

        // AI Nature Disclaimer - first-run awareness
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = SetupColors.InfoLight,
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 24.dp)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = "ℹ️ ${localizedString("mobile.setup_what_ciris")}",
                    color = SetupColors.InfoDark,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(bottom = 8.dp)
                )
                Text(
                    text = localizedString("mobile.setup_what_ciris_desc"),
                    color = SetupColors.InfoText,
                    fontSize = 13.sp,
                    lineHeight = 18.sp
                )
            }
        }

        // Card: Google user - "You're ready to go!"
        if (isGoogleAuth) {
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = SetupColors.SuccessLight,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 16.dp)
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.padding(bottom = 8.dp)
                    ) {
                        Text(
                            text = "✓",
                            color = SetupColors.SuccessDark,
                            fontSize = 24.sp,
                            modifier = Modifier.padding(end = 12.dp)
                        )
                        Text(
                            text = localizedString("mobile.setup_google_ready"),
                            color = SetupColors.SuccessDark,
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                    Text(
                        text = localizedString("mobile.setup_google_desc", mapOf("provider" to getOAuthProviderName())),
                        color = SetupColors.SuccessText,
                        fontSize = 14.sp,
                        lineHeight = 20.sp
                    )

                    // Expandable details
                    Text(
                        text = if (detailsExpanded) "▼ ${localizedString("mobile.setup_details_expand")}" else "▶ ${localizedString("mobile.setup_details_expand")}",
                        color = SetupColors.SuccessDark,
                        fontSize = 13.sp,
                        modifier = Modifier
                            .padding(top = 12.dp)
                            .testableClickable("btn_toggle_details") { detailsExpanded = !detailsExpanded }
                    )

                    AnimatedVisibility(visible = detailsExpanded) {
                        Text(
                            text = localizedString("mobile.setup_details_content"),
                            color = SetupColors.SuccessText,
                            fontSize = 13.sp,
                            lineHeight = 18.sp,
                            modifier = Modifier.padding(top = 8.dp)
                        )
                    }
                }
            }
        } else {
            // Card: Non-Google user - "Quick Setup Required"
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = SetupColors.InfoLight,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 16.dp)
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    Text(
                        text = localizedString("mobile.setup_required_title"),
                        color = SetupColors.InfoDark,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(bottom = 8.dp)
                    )
                    Text(
                        text = localizedString("mobile.setup_required_desc"),
                        color = SetupColors.InfoText,
                        fontSize = 14.sp,
                        lineHeight = 20.sp
                    )
                }
            }
        }

        // How it works section
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = SetupColors.GrayLight,
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = localizedString("mobile.setup_how_title"),
                    color = SetupColors.TextPrimary,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(bottom = 8.dp)
                )
                Text(
                    text = localizedString("mobile.setup_how_desc"),
                    color = SetupColors.TextSecondary,
                    fontSize = 14.sp,
                    lineHeight = 20.sp
                )
            }
        }

            // Bottom padding for scroll indicator
            Spacer(modifier = Modifier.height(32.dp))
        }

        // Scroll indicator arrow - shows when there's more content below
        AnimatedVisibility(
            visible = showScrollIndicator,
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .padding(bottom = 8.dp)
        ) {
            Surface(
                shape = CircleShape,
                color = SetupColors.Primary.copy(alpha = 0.9f),
                modifier = Modifier.size(36.dp)
            ) {
                Box(
                    contentAlignment = Alignment.Center,
                    modifier = Modifier.fillMaxSize()
                ) {
                    Text(
                        text = "↓",
                        color = Color.White,
                        fontSize = 18.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
            }
        }
    }
}

// ========== License Auth Step (Device Authorization via Portal/Registry) ==========
@Composable
private fun NodeAuthStep(
    viewModel: SetupViewModel,
    state: SetupFormState,
    apiClient: CIRISApiClient,
    modifier: Modifier = Modifier
) {
    val coroutineScope = rememberCoroutineScope()
    val deviceAuth = state.deviceAuth
    val clipboardManager = LocalClipboardManager.current
    var showCopiedToast by remember { mutableStateOf(false) }

    // Start connection when entering this step if not yet started
    LaunchedEffect(Unit) {
        if (deviceAuth.status == DeviceAuthStatus.IDLE) {
            // TODO: Wire to actual API call via apiClient.
            // MVP: The startNodeConnection method accepts a lambda for platform-specific HTTP.
            viewModel.startNodeConnection { nodeUrl ->
                apiClient.connectToNode(nodeUrl)
            }
        }
    }

    // Manual polling triggered by "All Done!" button instead of automatic polling
    // This prevents "unable to resolve localhost" when app returns from browser
    var isChecking by remember { mutableStateOf(false) }
    var checkError by remember { mutableStateOf<String?>(null) }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(24.dp)
            .verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = localizedString("mobile.setup_node_register"),
            color = SetupColors.TextPrimary,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 8.dp)
        )

        Text(
            text = localizedString("mobile.setup_registering").replace("{url}", deviceAuth.nodeUrl),
            color = SetupColors.TextSecondary,
            fontSize = 14.sp,
            modifier = Modifier.padding(bottom = 16.dp)
        )

        // Self-custody explanation card
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = SetupColors.SuccessLight.copy(alpha = 0.3f),
            modifier = Modifier.fillMaxWidth().padding(bottom = 20.dp)
        ) {
            Column(
                modifier = Modifier.padding(16.dp)
            ) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.padding(bottom = 8.dp)
                ) {
                    Text(
                        text = "🔐",
                        fontSize = 18.sp,
                        modifier = Modifier.padding(end = 8.dp)
                    )
                    Text(
                        text = localizedString("mobile.setup_node_self_custody_title"),
                        color = SetupColors.SuccessDark,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
                Text(
                    text = localizedString("mobile.setup_node_self_custody_desc"),
                    color = SetupColors.TextSecondary,
                    fontSize = 12.sp,
                    lineHeight = 18.sp
                )
            }
        }

        when (deviceAuth.status) {
            DeviceAuthStatus.IDLE, DeviceAuthStatus.CONNECTING -> {
                CircularProgressIndicator(
                    color = SetupColors.Primary,
                    modifier = Modifier.padding(16.dp)
                )
                Text(
                    text = localizedString("mobile.setup_node_connecting"),
                    color = SetupColors.TextSecondary,
                    fontSize = 14.sp
                )
            }

            DeviceAuthStatus.WAITING -> {
                // Use verification URL as provided by server (includes device code)
                val fullVerificationUrl = deviceAuth.verificationUri

                // Verification URL card
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = SetupColors.InfoLight,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(20.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Text(
                            text = localizedString("mobile.setup_node_open_browser"),
                            color = SetupColors.InfoDark,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Bold,
                            textAlign = TextAlign.Center,
                            modifier = Modifier.padding(bottom = 12.dp)
                        )

                        // Clickable URL
                        Surface(
                            shape = RoundedCornerShape(8.dp),
                            color = Color.White,
                            modifier = Modifier
                                .fillMaxWidth()
                                .clickable {
                                    openUrlInBrowser(fullVerificationUrl)
                                }
                        ) {
                            Text(
                                text = fullVerificationUrl,
                                color = SetupColors.Primary,
                                fontSize = 14.sp,
                                textAlign = TextAlign.Center,
                                textDecoration = TextDecoration.Underline,
                                modifier = Modifier.padding(12.dp)
                            )
                        }

                        Spacer(modifier = Modifier.height(12.dp))

                        // Action buttons row
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            // Open in browser button
                            Button(
                                onClick = { openUrlInBrowser(fullVerificationUrl) },
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = SetupColors.Primary
                                ),
                                modifier = Modifier.weight(1f).testableClickable("btn_open_browser") {
                                    openUrlInBrowser(fullVerificationUrl)
                                }
                            ) {
                                Text(localizedString("mobile.setup_node_open"), fontSize = 13.sp)
                            }

                            // Copy to clipboard button
                            OutlinedButton(
                                onClick = {
                                    clipboardManager.setText(AnnotatedString(fullVerificationUrl))
                                    showCopiedToast = true
                                    coroutineScope.launch {
                                        delay(2000)
                                        showCopiedToast = false
                                    }
                                },
                                modifier = Modifier.weight(1f).testableClickable("btn_copy_url") {
                                    clipboardManager.setText(AnnotatedString(fullVerificationUrl))
                                    showCopiedToast = true
                                    coroutineScope.launch {
                                        delay(2000)
                                        showCopiedToast = false
                                    }
                                }
                            ) {
                                Text(
                                    if (showCopiedToast) localizedString("mobile.setup_node_copied") else localizedString("mobile.setup_node_copy"),
                                    fontSize = 13.sp
                                )
                            }
                        }

                        if (deviceAuth.userCode.isNotBlank()) {
                            Spacer(modifier = Modifier.height(12.dp))
                            Text(
                                text = localizedString("mobile.setup_code").replace("{code}", deviceAuth.userCode),
                                color = SetupColors.InfoDark,
                                fontSize = 18.sp,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.height(24.dp))

                // "All Done!" button for manual check after returning from browser
                if (isChecking) {
                    CircularProgressIndicator(
                        color = SetupColors.Primary,
                        modifier = Modifier.size(24.dp),
                        strokeWidth = 2.dp
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = localizedString("mobile.setup_node_checking"),
                        color = SetupColors.TextSecondary,
                        fontSize = 14.sp
                    )
                } else {
                    Text(
                        text = localizedString("mobile.setup_node_after_auth"),
                        color = SetupColors.TextSecondary,
                        fontSize = 14.sp,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.padding(bottom = 16.dp)
                    )

                    Button(
                        onClick = {
                            PlatformLogger.i("SetupScreen", "[ALL_DONE] ========== BUTTON CLICKED ==========")
                            PlatformLogger.i("SetupScreen", "[ALL_DONE] Current deviceAuth status: ${viewModel.state.value.deviceAuth.status}")
                            PlatformLogger.i("SetupScreen", "[ALL_DONE] deviceCode: ${viewModel.state.value.deviceAuth.deviceCode.take(16)}...")
                            PlatformLogger.i("SetupScreen", "[ALL_DONE] portalUrl: ${viewModel.state.value.deviceAuth.portalUrl}")
                            isChecking = true
                            checkError = null
                            coroutineScope.launch {
                                try {
                                    PlatformLogger.i("SetupScreen", "[ALL_DONE] Calling viewModel.pollNodeAuthStatus...")
                                    viewModel.pollNodeAuthStatus { deviceCode, portalUrl ->
                                        PlatformLogger.i("SetupScreen", "[ALL_DONE] Poll lambda invoked: deviceCode=${deviceCode.take(16)}..., portalUrl=$portalUrl")
                                        PlatformLogger.i("SetupScreen", "[ALL_DONE] Calling apiClient.pollNodeAuthStatus...")
                                        val result = apiClient.pollNodeAuthStatus(deviceCode, portalUrl)
                                        PlatformLogger.i("SetupScreen", "[ALL_DONE] API call returned: status=${result.status}, keyId=${result.keyId}, error=${result.error}")
                                        result
                                    }
                                    PlatformLogger.i("SetupScreen", "[ALL_DONE] Poll complete, final status: ${viewModel.state.value.deviceAuth.status}")
                                } catch (e: Exception) {
                                    PlatformLogger.e("SetupScreen", "[ALL_DONE] Poll EXCEPTION: ${e.message}")
                                    PlatformLogger.e("SetupScreen", "[ALL_DONE] Exception type: ${e::class.simpleName}")
                                    checkError = e.message ?: "Check failed"
                                } finally {
                                    isChecking = false
                                    PlatformLogger.i("SetupScreen", "[ALL_DONE] ========== BUTTON HANDLER COMPLETE ==========")
                                }
                            }
                        },
                        colors = ButtonDefaults.buttonColors(
                            containerColor = SetupColors.SuccessDark
                        ),
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(56.dp)
                            .testable("btn_all_done")
                    ) {
                        Text(
                            localizedString("mobile.setup_node_all_done"),
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }

                    checkError?.let { error ->
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = error,
                            color = Color.Red,
                            fontSize = 12.sp,
                            textAlign = TextAlign.Center
                        )
                    }
                }
            }

            DeviceAuthStatus.COMPLETE -> {
                // Success card
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = SetupColors.SuccessLight,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(20.dp)) {
                        Text(
                            text = "✓ ${localizedString("mobile.setup_node_authorized")}",
                            color = SetupColors.SuccessDark,
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(bottom = 12.dp)
                        )

                        // Self-custody key bound indicator
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.padding(bottom = 8.dp)
                        ) {
                            Text(
                                text = "🔐",
                                fontSize = 14.sp,
                                modifier = Modifier.padding(end = 6.dp)
                            )
                            Text(
                                text = localizedString("mobile.setup_node_key_bound"),
                                color = SetupColors.SuccessText,
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Medium
                            )
                        }

                        deviceAuth.provisionedTemplate?.let {
                            Text(
                                text = localizedString("mobile.setup_template").replace("{name}", it),
                                color = SetupColors.SuccessText,
                                fontSize = 14.sp
                            )
                        }
                        if (deviceAuth.provisionedAdapters.isNotEmpty()) {
                            Text(
                                text = localizedString("mobile.setup_adapters_list").replace("{list}", deviceAuth.provisionedAdapters.joinToString(", ")),
                                color = SetupColors.SuccessText,
                                fontSize = 14.sp
                            )
                        }
                        deviceAuth.orgId?.let {
                            Text(
                                text = localizedString("mobile.setup_organization").replace("{org}", it),
                                color = SetupColors.SuccessText,
                                fontSize = 14.sp
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))
                Text(
                    text = localizedString("mobile.setup_node_next_hint"),
                    color = SetupColors.TextSecondary,
                    fontSize = 14.sp,
                    textAlign = TextAlign.Center
                )
            }

            DeviceAuthStatus.ERROR -> {
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = SetupColors.ErrorLight,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(20.dp)) {
                        Text(
                            text = localizedString("mobile.setup_node_failed"),
                            color = SetupColors.ErrorDark,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(bottom = 8.dp)
                        )
                        Text(
                            text = deviceAuth.error ?: "Unknown error",
                            color = SetupColors.ErrorText,
                            fontSize = 14.sp
                        )
                    }
                }
                Spacer(modifier = Modifier.height(16.dp))
                Button(
                    onClick = {
                        coroutineScope.launch {
                            viewModel.startNodeConnection { nodeUrl ->
                                apiClient.connectToNode(nodeUrl)
                            }
                        }
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = SetupColors.Primary),
                    modifier = Modifier.testableClickable("btn_retry_connection") {
                        coroutineScope.launch {
                            viewModel.startNodeConnection { nodeUrl ->
                                apiClient.connectToNode(nodeUrl)
                            }
                        }
                    }
                ) {
                    Text(localizedString("startup.startup_retry"))
                }
            }
        }
    }
}

// ========== LLM Configuration Step (fragment_setup_llm.xml) ==========
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun LlmConfigurationStep(
    viewModel: SetupViewModel,
    state: SetupFormState,
    apiClient: CIRISApiClient,
    modifier: Modifier = Modifier
) {
    // State for connection testing
    var isTesting by remember { mutableStateOf(false) }
    var testResult by remember { mutableStateOf<LlmValidationResult?>(null) }
    var availableModels by remember { mutableStateOf<List<ModelInfo>>(emptyList()) }
    val coroutineScope = rememberCoroutineScope()

    // State for local LLM server discovery (finds running servers on network)
    val discoveryState = rememberLocalLlmDiscoveryState()

    // Probe on-device inference capability (checks if system CAN run local inference)
    // Cheap: ActivityManager/NSProcessInfo call + disk check
    val localInference: LocalInferenceCapability = remember { probeLocalInferenceCapability() }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(24.dp)
            .verticalScroll(rememberScrollState())
    ) {
        Text(
            text = localizedString("setup.llm_title"),
            color = SetupColors.TextPrimary,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 8.dp)
        )

        Text(
            text = localizedString("setup.llm_desc"),
            color = SetupColors.TextSecondary,
            fontSize = 14.sp,
            modifier = Modifier.padding(bottom = 24.dp)
        )

        // On-device Gemma 4 option. Shown only when the device capability
        // probe reports a capable mobile phone, or when the platform is iOS
        // with capable hardware but no model bundle installed yet (stub).
        // Hidden entirely on desktop and low-spec devices so the wizard is
        // not cluttered with options that cannot run.
        if (!localInference.isHidden) {
            LocalInferenceOptionCard(
                capability = localInference,
                isSelected = state.setupMode == SetupMode.LOCAL_ON_DEVICE,
                onSelect = { viewModel.setSetupMode(SetupMode.LOCAL_ON_DEVICE) },
            )
        }

        // CIRIS Proxy card (for Google users in CIRIS_PROXY mode)
        if (state.isGoogleAuth && state.setupMode == SetupMode.CIRIS_PROXY) {
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = SetupColors.SuccessLight,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 16.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.padding(bottom = 8.dp)
                    ) {
                        Text(
                            text = "✓",
                            color = SetupColors.SuccessDark,
                            fontSize = 20.sp,
                            modifier = Modifier.padding(end = 8.dp)
                        )
                        Text(
                            text = localizedString("mobile.setup_free_ready"),
                            color = SetupColors.SuccessDark,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                    Text(
                        text = localizedString("mobile.setup_free_desc").replace("{provider}", getOAuthProviderName()),
                        color = SetupColors.SuccessText,
                        fontSize = 14.sp,
                        lineHeight = 20.sp
                    )
                }
            }

            // Advanced option link
            TextButton(
                onClick = { viewModel.setSetupMode(SetupMode.BYOK) },
                modifier = Modifier
                    .padding(bottom = 16.dp)
                    .testableClickable("btn_switch_to_byok") { viewModel.setSetupMode(SetupMode.BYOK) }
            ) {
                Text(
                    text = localizedString("mobile.setup_own_provider"),
                    color = SetupColors.TextSecondary,
                    fontSize = 14.sp
                )
            }
        }

        // BYOK mode header (for Google users who switched to BYOK)
        if (state.isGoogleAuth && state.setupMode == SetupMode.BYOK) {
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = SetupColors.InfoLight,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 16.dp)
            ) {
                Row(
                    modifier = Modifier.padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = localizedString("mobile.setup_using_own"),
                            color = SetupColors.InfoDark,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Bold
                        )
                        Text(
                            text = localizedString("mobile.setup_switch_back"),
                            color = SetupColors.InfoText,
                            fontSize = 12.sp
                        )
                    }
                    TextButton(
                        onClick = { viewModel.setSetupMode(SetupMode.CIRIS_PROXY) },
                        modifier = Modifier.testableClickable("btn_use_free_ai") {
                            viewModel.setSetupMode(SetupMode.CIRIS_PROXY)
                        }
                    ) {
                        Text(localizedString("mobile.setup_use_free"), color = SetupColors.InfoDark)
                    }
                }
            }
        }

        // BYOK configuration (shown when in BYOK mode or for non-Google
        // users). Hidden when the user picked on-device inference —
        // that mode owns its entire card above and needs no API key,
        // base URL, or model text input.
        if (state.setupMode != SetupMode.LOCAL_ON_DEVICE &&
            (state.setupMode == SetupMode.BYOK || !state.isGoogleAuth)) {
            // Provider selection
            Text(
                text = localizedString("mobile.setup_provider"),
                color = SetupColors.TextPrimary,
                fontSize = 14.sp,
                fontWeight = FontWeight.Medium,
                modifier = Modifier.padding(bottom = 8.dp)
            )

            var providerExpanded by remember { mutableStateOf(false) }
            // Use dynamic provider list from ViewModel
            val providers = viewModel.availableProviders

            // Get display name for current provider
            val currentProviderDisplay = providers.find { it.first == state.llmProvider }?.second ?: state.llmProvider

            ExposedDropdownMenuBox(
                expanded = providerExpanded,
                onExpandedChange = { providerExpanded = it }
            ) {
                OutlinedTextField(
                    value = currentProviderDisplay,
                    onValueChange = {},
                    readOnly = true,
                    modifier = Modifier
                        .fillMaxWidth()
                        .menuAnchor()
                        .testableClickable("input_llm_provider") { providerExpanded = !providerExpanded },
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedTextColor = SetupColors.TextPrimary,
                        unfocusedTextColor = SetupColors.TextPrimary,
                        focusedBorderColor = SetupColors.Primary,
                        unfocusedBorderColor = SetupColors.TextSecondary.copy(alpha = 0.5f),
                        cursorColor = SetupColors.Primary
                    )
                )

                ExposedDropdownMenu(
                    expanded = providerExpanded,
                    onDismissRequest = { providerExpanded = false }
                ) {
                    providers.forEach { (key, label) ->
                        DropdownMenuItem(
                            text = { Text(label) },
                            onClick = {
                                viewModel.setLlmProvider(key)
                                providerExpanded = false
                            },
                            modifier = Modifier.testableClickable("menu_provider_$key") {
                                viewModel.setLlmProvider(key)
                                providerExpanded = false
                            }
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Local providers that need endpoint URL
            val isLocalProvider = state.llmProvider in listOf("local", "local_inference", "openai_compatible", "other")

            // Local Inference Server Discovery UI
            if (state.llmProvider == "local_inference") {
                LocalLlmServerDiscovery(
                    state = discoveryState,
                    apiClient = apiClient,
                    onServerSelected = { server ->
                        // Set base URL from discovered server
                        val baseUrl = when (server.serverType) {
                            "ollama" -> "${server.url}/v1"
                            else -> "${server.url}/v1"
                        }
                        viewModel.setLlmBaseUrl(baseUrl)

                        // Populate availableModels from discovered server
                        if (server.models.isNotEmpty()) {
                            availableModels = server.models.map { modelId ->
                                ModelInfo(
                                    id = modelId,
                                    displayName = modelId,
                                    contextWindow = null,
                                    cirisCompatible = true,
                                    cirisRecommended = false
                                )
                            }
                            // Auto-select first model
                            viewModel.setLlmModel(server.models.first())
                        }
                    },
                    primaryColor = SetupColors.Primary,
                    surfaceColor = SetupColors.Background,
                    textColor = SetupColors.TextPrimary,
                    secondaryTextColor = SetupColors.TextSecondary
                )

                Spacer(modifier = Modifier.height(16.dp))
            }

            // Endpoint URL for local providers (show for all local providers)
            if (isLocalProvider) {
                Text(
                    text = "Endpoint URL (optional)",
                    color = SetupColors.TextPrimary,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.padding(bottom = 8.dp)
                )

                OutlinedTextField(
                    value = state.llmBaseUrl,
                    onValueChange = { viewModel.setLlmBaseUrl(it) },
                    modifier = Modifier.fillMaxWidth().testable("input_llm_base_url"),
                    placeholder = { Text("http://localhost:11434/v1", color = SetupColors.TextSecondary) },
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedTextColor = SetupColors.TextPrimary,
                        unfocusedTextColor = SetupColors.TextPrimary,
                        focusedBorderColor = SetupColors.Primary,
                        unfocusedBorderColor = SetupColors.TextSecondary.copy(alpha = 0.5f),
                        cursorColor = SetupColors.Primary
                    ),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(16.dp))
            }

            // API Key input (optional for local providers)
            if (state.llmProvider !in listOf("local", "local_inference")) {
                val apiKeyLabel = if (isLocalProvider) {
                    "API Key (optional)"
                } else {
                    localizedString("mobile.setup_api_key_label")
                }
                Text(
                    text = apiKeyLabel,
                    color = SetupColors.TextPrimary,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.padding(bottom = 8.dp)
                )

                var showApiKey by remember { mutableStateOf(false) }

                OutlinedTextField(
                    value = state.llmApiKey,
                    onValueChange = { viewModel.setLlmApiKey(it) },
                    modifier = Modifier.fillMaxWidth().testable("input_api_key"),
                    placeholder = { Text("sk-...", color = SetupColors.TextSecondary) },
                    visualTransformation = if (showApiKey) VisualTransformation.None else PasswordVisualTransformation(),
                    trailingIcon = {
                        TextButton(
                            onClick = { showApiKey = !showApiKey },
                            modifier = Modifier.testableClickable("btn_toggle_api_key") { showApiKey = !showApiKey }
                        ) {
                            Text(
                                text = if (showApiKey) "Hide" else "Show",
                                color = SetupColors.Primary,
                                fontSize = 12.sp
                            )
                        }
                    },
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedTextColor = SetupColors.TextPrimary,
                        unfocusedTextColor = SetupColors.TextPrimary,
                        focusedBorderColor = SetupColors.Primary,
                        unfocusedBorderColor = SetupColors.TextSecondary.copy(alpha = 0.5f),
                        cursorColor = SetupColors.Primary
                    ),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(16.dp))
            }

            // Model selection - dropdown if models available, text field otherwise
            Text(
                text = if (availableModels.isNotEmpty()) "Model" else "Model (optional)",
                color = SetupColors.TextPrimary,
                fontSize = 14.sp,
                fontWeight = FontWeight.Medium,
                modifier = Modifier.padding(bottom = 8.dp)
            )

            if (availableModels.isNotEmpty()) {
                // Show dropdown with live models from provider
                var modelExpanded by remember { mutableStateOf(false) }
                val selectedModel = availableModels.find { it.id == state.llmModel }

                ExposedDropdownMenuBox(
                    expanded = modelExpanded,
                    onExpandedChange = { modelExpanded = it }
                ) {
                    OutlinedTextField(
                        value = selectedModel?.displayName ?: state.llmModel.ifEmpty { "Select a model" },
                        onValueChange = {},
                        readOnly = true,
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor()
                            .testableClickable("input_llm_model") { modelExpanded = !modelExpanded },
                        trailingIcon = {
                            if (selectedModel?.cirisRecommended == true) {
                                Text("★", color = SetupColors.Primary, fontSize = 16.sp)
                            }
                        },
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = SetupColors.TextPrimary,
                            unfocusedTextColor = SetupColors.TextPrimary,
                            focusedBorderColor = SetupColors.Primary,
                            unfocusedBorderColor = SetupColors.TextSecondary.copy(alpha = 0.5f),
                            cursorColor = SetupColors.Primary
                        )
                    )

                    ExposedDropdownMenu(
                        expanded = modelExpanded,
                        onDismissRequest = { modelExpanded = false }
                    ) {
                        // Show recommended models first
                        val sortedModels = availableModels.sortedByDescending {
                            when {
                                it.cirisRecommended -> 2
                                it.cirisCompatible -> 1
                                else -> 0
                            }
                        }
                        sortedModels.forEach { model ->
                            DropdownMenuItem(
                                text = {
                                    Row(
                                        modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Column(modifier = Modifier.weight(1f)) {
                                            Text(
                                                text = model.displayName,
                                                fontWeight = if (model.cirisRecommended) FontWeight.Bold else FontWeight.Normal
                                            )
                                            if (model.contextWindow != null) {
                                                Text(
                                                    text = "${model.contextWindow / 1000}K context",
                                                    fontSize = 11.sp,
                                                    color = SetupColors.TextSecondary
                                                )
                                            }
                                        }
                                        Row {
                                            if (model.cirisRecommended) {
                                                Surface(
                                                    shape = RoundedCornerShape(4.dp),
                                                    color = SetupColors.SuccessLight
                                                ) {
                                                    Text(
                                                        "★ Best",
                                                        fontSize = 10.sp,
                                                        color = SetupColors.SuccessDark,
                                                        modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
                                                    )
                                                }
                                            } else if (model.cirisCompatible) {
                                                Surface(
                                                    shape = RoundedCornerShape(4.dp),
                                                    color = SetupColors.InfoLight
                                                ) {
                                                    Text(
                                                        "Compatible",
                                                        fontSize = 10.sp,
                                                        color = SetupColors.InfoDark,
                                                        modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
                                                    )
                                                }
                                            }
                                        }
                                    }
                                },
                                onClick = {
                                    viewModel.setLlmModel(model.id)
                                    modelExpanded = false
                                },
                                modifier = Modifier.testableClickable("menu_model_${model.id.replace("/", "_").replace(":", "_")}") {
                                    viewModel.setLlmModel(model.id)
                                    modelExpanded = false
                                }
                            )
                        }
                    }
                }

                Text(
                    text = "★ = " + localizedString("mobile.setup_configured"), // Using "Configured" as best match for "Recommended"
                    color = SetupColors.TextSecondary,
                    fontSize = 11.sp,
                    modifier = Modifier.padding(top = 4.dp)
                )
            } else {
                // Fallback to text input before validation
                OutlinedTextField(
                    value = state.llmModel,
                    onValueChange = { viewModel.setLlmModel(it) },
                    modifier = Modifier.fillMaxWidth().testable("input_llm_model_text"),
                    placeholder = {
                        Text(
                            text = when (state.llmProvider) {
                                "openai" -> "gpt-4o"
                                "anthropic" -> "claude-sonnet-4-5-20250514"
                                "google" -> "gemini-2.0-flash"
                                "openrouter" -> "anthropic/claude-sonnet-4"
                                "groq" -> "llama-3.3-70b-versatile"
                                "together" -> "meta-llama/Llama-3.3-70B-Instruct-Turbo"
                                "local", "local_inference" -> "llama3.2"
                                else -> "model-name"
                            },
                            color = SetupColors.TextSecondary
                        )
                    },
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedTextColor = SetupColors.TextPrimary,
                        unfocusedTextColor = SetupColors.TextPrimary,
                        focusedBorderColor = SetupColors.Primary,
                        unfocusedBorderColor = SetupColors.TextSecondary.copy(alpha = 0.5f),
                        cursorColor = SetupColors.Primary
                    ),
                    singleLine = true
                )
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Test Connection button
            OutlinedButton(
                onClick = {
                    if (!isTesting) {
                        isTesting = true
                        testResult = null
                        coroutineScope.launch(Dispatchers.IO) {
                            try {
                                // Provider is now stored as key directly (e.g., "openai", "local")
                                val providerId = state.llmProvider
                                val result = apiClient.validateLlmConfiguration(
                                    provider = providerId,
                                    apiKey = state.llmApiKey,
                                    baseUrl = state.llmBaseUrl.takeIf { it.isNotEmpty() },
                                    model = state.llmModel.takeIf { it.isNotEmpty() }
                                )

                                // If validation succeeded, fetch available models
                                val models = if (result.valid) {
                                    apiClient.listModels(
                                        provider = providerId,
                                        apiKey = state.llmApiKey,
                                        baseUrl = state.llmBaseUrl.takeIf { it.isNotEmpty() }
                                    )
                                } else emptyList()

                                withContext(Dispatchers.Main) {
                                    testResult = result
                                    availableModels = models
                                    isTesting = false

                                    // Auto-select the best model if none is currently selected
                                    if (models.isNotEmpty() && state.llmModel.isEmpty()) {
                                        // Prefer recommended, then compatible, then first available
                                        val bestModel = models.firstOrNull { it.cirisRecommended }
                                            ?: models.firstOrNull { it.cirisCompatible }
                                            ?: models.first()
                                        viewModel.setLlmModel(bestModel.id)
                                        PlatformLogger.i(TAG, "Auto-selected model: ${bestModel.id}")
                                    }
                                }
                            } catch (e: Exception) {
                                withContext(Dispatchers.Main) {
                                    testResult = LlmValidationResult(
                                        valid = false,
                                        message = "Connection failed",
                                        error = e.message ?: "Unknown error"
                                    )
                                    isTesting = false
                                }
                            }
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth().testable("btn_test_connection"),
                enabled = !isTesting && (isLocalProvider || state.llmApiKey.isNotEmpty()),
                colors = ButtonDefaults.outlinedButtonColors(
                    contentColor = SetupColors.Primary
                )
            ) {
                if (isTesting) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        strokeWidth = 2.dp,
                        color = SetupColors.Primary
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(localizedString("mobile.setup_testing"))
                } else {
                    Text(localizedString("mobile.setup_test_connection"))
                }
            }

            // Show test result
            testResult?.let { result ->
                Spacer(modifier = Modifier.height(12.dp))
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = if (result.valid) SetupColors.SuccessLight else SetupColors.ErrorLight,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier.padding(12.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = if (result.valid) "✓" else "✗",
                            fontSize = 18.sp,
                            color = if (result.valid) SetupColors.SuccessDark else SetupColors.ErrorDark,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(end = 8.dp)
                        )
                        Column {
                            Text(
                                text = result.message,
                                color = if (result.valid) SetupColors.SuccessDark else SetupColors.ErrorDark,
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Medium
                            )
                            result.error?.let { error ->
                                Text(
                                    text = error,
                                    color = SetupColors.ErrorText,
                                    fontSize = 12.sp
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

/**
 * Card for selecting on-device Gemma 4 inference during setup.
 *
 * Three visible states, driven by [LocalInferenceCapability]:
 *
 * 1. Capable (E2B or E4B) — card is selectable and, when selected,
 *    highlighted. Shows the tier so the user knows which model will run.
 * 2. iOS stub — card is shown but disabled, labelled "Coming soon".
 *    Lets the user know the path exists without offering a broken click.
 * 3. Incapable — card is not rendered (handled by the caller via
 *    [LocalInferenceCapability.isHidden]).
 */
@Composable
private fun LocalInferenceOptionCard(
    capability: LocalInferenceCapability,
    isSelected: Boolean,
    onSelect: () -> Unit,
) {
    val isStub = capability.isComingSoon
    val backgroundColor = when {
        isSelected -> SetupColors.SuccessLight
        isStub -> SetupColors.InfoLight
        else -> SetupColors.InfoLight
    }
    val titleColor = if (isStub) SetupColors.InfoDark else SetupColors.SuccessDark
    val bodyColor = if (isStub) SetupColors.InfoText else SetupColors.SuccessText

    val tierLabel = when (capability.tier) {
        LocalInferenceTier.CAPABLE_E4B -> "Gemma 4 E4B"
        LocalInferenceTier.CAPABLE_E2B -> "Gemma 4 E2B"
        LocalInferenceTier.IOS_STUB -> "Coming soon"
        LocalInferenceTier.INCAPABLE -> "Unavailable"
    }

    val titleText = if (isStub) {
        "On-Device (Coming Soon)"
    } else {
        "On-Device Local — $tierLabel"
    }

    val cardModifier = Modifier
        .fillMaxWidth()
        .padding(bottom = 16.dp)
        .then(
            if (!isStub) {
                Modifier.testableClickable("btn_select_local_on_device") { onSelect() }
            } else {
                Modifier.testable("card_local_on_device_stub")
            }
        )

    Surface(
        shape = RoundedCornerShape(12.dp),
        color = backgroundColor,
        modifier = cardModifier,
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.padding(bottom = 8.dp),
            ) {
                Text(
                    text = if (isSelected) "✓" else if (isStub) "⏳" else "📱",
                    color = titleColor,
                    fontSize = 20.sp,
                    modifier = Modifier.padding(end = 8.dp),
                )
                Text(
                    text = titleText,
                    color = titleColor,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold,
                )
            }
            Text(
                text = capability.reason,
                color = bodyColor,
                fontSize = 13.sp,
                lineHeight = 18.sp,
                modifier = Modifier.padding(bottom = 4.dp),
            )
            if (capability.totalRamGb > 0.0) {
                val rounded = (capability.totalRamGb * 10).toLong() / 10.0
                Text(
                    text = "Detected device RAM: $rounded GB",
                    color = bodyColor,
                    fontSize = 12.sp,
                )
            }
        }
    }
}

// ========== Optional Features Step ==========
@Composable
private fun OptionalFeaturesStep(
    viewModel: SetupViewModel,
    state: SetupFormState,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(24.dp)
            .verticalScroll(rememberScrollState())
    ) {
        Text(
            text = localizedString("mobile.setup_optional_title"),
            color = SetupColors.TextPrimary,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 8.dp)
        )

        Text(
            text = localizedString("mobile.setup_optional_desc"),
            color = SetupColors.TextSecondary,
            fontSize = 14.sp,
            modifier = Modifier.padding(bottom = 24.dp)
        )

        // Accord Metrics Consent Card
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = SetupColors.InfoLight,
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 16.dp)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.padding(bottom = 8.dp)
                ) {
                    Text(
                        text = "📊",
                        fontSize = 20.sp,
                        modifier = Modifier.padding(end = 8.dp)
                    )
                    Text(
                        text = localizedString("mobile.setup_alignment_title"),
                        color = SetupColors.InfoDark,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold
                    )
                }

                Text(
                    text = localizedString("mobile.setup_alignment_desc"),
                    color = SetupColors.InfoText,
                    fontSize = 14.sp,
                    lineHeight = 20.sp,
                    modifier = Modifier.padding(bottom = 12.dp)
                )

                Text(
                    text = localizedString("mobile.setup_data_shared"),
                    color = SetupColors.InfoDark,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.padding(bottom = 4.dp)
                )

                Column(modifier = Modifier.padding(start = 8.dp, bottom = 12.dp)) {
                    DataPointRow("Reasoning quality scores", SetupColors.InfoText)
                    DataPointRow("Decision patterns (no message content)", SetupColors.InfoText)
                    DataPointRow("LLM provider and API base URL", SetupColors.InfoText)
                    DataPointRow("Performance metrics", SetupColors.InfoText)
                }

                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.testableClickable("item_accord_metrics_consent") {
                        viewModel.setAccordMetricsConsent(!state.accordMetricsConsent)
                    }
                ) {
                    Checkbox(
                        checked = state.accordMetricsConsent,
                        onCheckedChange = { viewModel.setAccordMetricsConsent(it) },
                        colors = CheckboxDefaults.colors(
                            checkedColor = SetupColors.Primary,
                            uncheckedColor = SetupColors.TextSecondary
                        )
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = localizedString("mobile.setup_alignment_agree"),
                        color = SetupColors.InfoDark,
                        fontSize = 14.sp
                    )
                }

                // Optional: Include location in traces (only show if city selected and metrics consent given)
                AnimatedVisibility(visible = state.accordMetricsConsent && state.city.isNotEmpty()) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier
                            .padding(top = 8.dp)
                            .testableClickable("item_share_location_traces") {
                                viewModel.setShareLocationInTraces(!state.shareLocationInTraces)
                            }
                    ) {
                        Checkbox(
                            checked = state.shareLocationInTraces,
                            onCheckedChange = { viewModel.setShareLocationInTraces(it) },
                            colors = CheckboxDefaults.colors(
                                checkedColor = SetupColors.Primary,
                                uncheckedColor = SetupColors.TextSecondary
                            )
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = localizedString("mobile.setup_include_location"),
                            color = SetupColors.InfoDark,
                            fontSize = 14.sp
                        )
                    }
                }
            }
        }

        // Navigation & Weather Services Card
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = SetupColors.SuccessLight,
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 16.dp)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.padding(bottom = 8.dp)
                ) {
                    Text(
                        text = "🌍",
                        fontSize = 20.sp,
                        modifier = Modifier.padding(end = 8.dp)
                    )
                    Text(
                        text = localizedString("mobile.setup_nav_weather_title"),
                        color = SetupColors.SuccessDark,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold
                    )
                }

                Text(
                    text = localizedString("mobile.setup_nav_weather_desc"),
                    color = SetupColors.SuccessText,
                    fontSize = 14.sp,
                    lineHeight = 20.sp,
                    modifier = Modifier.padding(bottom = 12.dp)
                )

                Text(
                    text = localizedString("mobile.setup_nav_features"),
                    color = SetupColors.SuccessDark,
                    fontSize = 13.sp,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.padding(bottom = 4.dp)
                )

                Column(modifier = Modifier.padding(start = 8.dp, bottom = 12.dp)) {
                    DataPointRow("Convert addresses to coordinates", SetupColors.SuccessText)
                    DataPointRow("Get current weather by location name", SetupColors.SuccessText)
                    DataPointRow("Calculate routes and distances", SetupColors.SuccessText)
                    DataPointRow("Weather forecasts (US locations)", SetupColors.SuccessText)
                }

                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.testableClickable("item_public_api_services") {
                        viewModel.setPublicApiServicesEnabled(!state.publicApiServicesEnabled)
                    }
                ) {
                    Checkbox(
                        checked = state.publicApiServicesEnabled,
                        onCheckedChange = { viewModel.setPublicApiServicesEnabled(it) },
                        colors = CheckboxDefaults.colors(
                            checkedColor = SetupColors.Primary,
                            uncheckedColor = SetupColors.TextSecondary
                        )
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = localizedString("mobile.setup_nav_enable"),
                        color = SetupColors.SuccessDark,
                        fontSize = 14.sp
                    )
                }

                // Email input (shown when enabled)
                AnimatedVisibility(visible = state.publicApiServicesEnabled) {
                    Column(modifier = Modifier.padding(top = 12.dp)) {
                        Text(
                            text = localizedString("mobile.setup_contact_email"),
                            color = SetupColors.SuccessDark,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Medium,
                            modifier = Modifier.padding(bottom = 4.dp)
                        )
                        OutlinedTextField(
                            value = state.publicApiEmail,
                            onValueChange = { viewModel.setPublicApiEmail(it) },
                            placeholder = { Text("your@email.com", color = SetupColors.TextSecondary) },
                            singleLine = true,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email),
                            modifier = Modifier
                                .fillMaxWidth()
                                .testable("input_public_api_email"),
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedTextColor = SetupColors.TextPrimary,
                                unfocusedTextColor = SetupColors.TextPrimary,
                                cursorColor = SetupColors.Primary,
                                focusedBorderColor = SetupColors.Primary,
                                unfocusedBorderColor = SetupColors.SuccessBorder
                            )
                        )
                        Text(
                            text = localizedString("mobile.setup_contact_hint"),
                            color = SetupColors.SuccessText,
                            fontSize = 12.sp,
                            modifier = Modifier.padding(top = 4.dp)
                        )
                    }
                }
            }
        }

        // Adapters Section
        Text(
            text = localizedString("mobile.setup_adapters_title"),
            color = SetupColors.TextPrimary,
            fontSize = 16.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 8.dp, top = 8.dp)
        )

        Text(
            text = localizedString("mobile.setup_adapters_desc"),
            color = SetupColors.TextSecondary,
            fontSize = 14.sp,
            modifier = Modifier.padding(bottom = 12.dp)
        )

        if (state.adaptersLoading) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 24.dp),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator(color = SetupColors.Primary)
            }
        } else if (state.availableAdapters.isEmpty()) {
            // Show default adapters when API hasn't loaded them
            AdapterToggleItem(
                name = "REST API",
                description = "RESTful API server with built-in web interface",
                isEnabled = true,
                isRequired = true,
                requiresConfig = false,
                isConfigured = false,
                onToggle = {},
                onConfigure = null
            )
        } else {
            state.availableAdapters.forEach { adapter ->
                val isEnabled = state.enabledAdapterIds.contains(adapter.id)
                val isRequired = adapter.id == "api"
                val isConfigured = state.configuredAdapterData.containsKey(adapter.id)

                AdapterToggleItem(
                    name = adapter.name,
                    description = adapter.description,
                    isEnabled = isEnabled,
                    isRequired = isRequired,
                    requiresConfig = adapter.requires_config,
                    isConfigured = isConfigured,
                    configFields = adapter.config_fields,
                    onToggle = { enabled ->
                        if (!isRequired) {
                            if (enabled && adapter.requires_config && !isConfigured) {
                                // Launch the wizard for adapters that require configuration
                                viewModel.startAdapterWizard(adapter.id)
                            } else {
                                viewModel.toggleAdapter(adapter.id, enabled)
                            }
                        }
                    },
                    onConfigure = {
                        // Allow re-configuration of already configured adapters
                        viewModel.startAdapterWizard(adapter.id)
                    }
                )

                Spacer(modifier = Modifier.height(8.dp))
            }
        }

        // Section 3: Advanced Settings (collapsible)
        Spacer(modifier = Modifier.height(16.dp))

        Surface(
            shape = RoundedCornerShape(8.dp),
            color = SetupColors.GrayLight,
            modifier = Modifier
                .fillMaxWidth()
                .testableClickable("item_toggle_advanced_settings") {
                    viewModel.setShowAdvancedSettings(!state.showAdvancedSettings)
                }
        ) {
            Row(
                modifier = Modifier.padding(12.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = if (state.showAdvancedSettings) "▼" else "▶",
                    color = SetupColors.TextSecondary,
                    fontSize = 14.sp
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    text = localizedString("mobile.setup_advanced"),
                    color = SetupColors.TextPrimary,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium
                )
            }
        }

        AnimatedVisibility(visible = state.showAdvancedSettings) {
            Surface(
                shape = RoundedCornerShape(8.dp),
                color = Color.White,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp)
                    .border(1.dp, SetupColors.GrayLight, RoundedCornerShape(8.dp))
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = localizedString("mobile.setup_template_title"),
                        color = SetupColors.TextPrimary,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium,
                        modifier = Modifier.padding(bottom = 4.dp)
                    )
                    Text(
                        text = localizedString("mobile.setup_template_desc"),
                        color = SetupColors.TextSecondary,
                        fontSize = 12.sp,
                        modifier = Modifier.padding(bottom = 12.dp)
                    )

                    if (state.templatesLoading) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(24.dp),
                            color = SetupColors.Primary
                        )
                    } else if (state.availableTemplates.isEmpty()) {
                        Text(
                            text = localizedString("mobile.setup_template_default"),
                            color = SetupColors.TextSecondary,
                            fontSize = 13.sp
                        )
                    } else {
                        state.availableTemplates.forEach { template ->
                            val isSelected = template.id == state.selectedTemplateId
                            Surface(
                                shape = RoundedCornerShape(8.dp),
                                color = if (isSelected) SetupColors.Primary.copy(alpha = 0.1f) else Color.Transparent,
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 4.dp)
                                    .clickable { viewModel.setSelectedTemplate(template.id) }
                                    .border(
                                        width = if (isSelected) 2.dp else 1.dp,
                                        color = if (isSelected) SetupColors.Primary else SetupColors.GrayLight,
                                        shape = RoundedCornerShape(8.dp)
                                    )
                            ) {
                                Column(modifier = Modifier.padding(12.dp)) {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Text(
                                            text = template.name,
                                            color = if (isSelected) SetupColors.Primary else SetupColors.TextPrimary,
                                            fontSize = 14.sp,
                                            fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Medium
                                        )
                                        if (template.id == "default" || template.id == "ally") {
                                            Spacer(modifier = Modifier.width(8.dp))
                                            Text(
                                                text = "(" + localizedString("mobile.setup_configured") + ")",
                                                color = SetupColors.SuccessText,
                                                fontSize = 11.sp
                                            )
                                        }
                                    }
                                    Text(
                                        text = template.description,
                                        color = SetupColors.TextSecondary,
                                        fontSize = 12.sp,
                                        modifier = Modifier.padding(top = 4.dp)
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun DataPointRow(text: String, color: Color) {
    Row(modifier = Modifier.padding(vertical = 2.dp)) {
        Text("•", color = color, fontSize = 14.sp)
        Spacer(modifier = Modifier.width(8.dp))
        Text(text, color = color, fontSize = 13.sp)
    }
}

@Composable
private fun BenefitRow(text: String) {
    Row(
        modifier = Modifier.padding(vertical = 2.dp),
        verticalAlignment = Alignment.Top
    ) {
        Text("✓", color = SetupColors.SuccessDark, fontSize = 12.sp)
        Spacer(modifier = Modifier.width(6.dp))
        Text(
            text = text,
            color = SetupColors.SuccessText,
            fontSize = 12.sp,
            lineHeight = 16.sp
        )
    }
}

@Composable
private fun AdapterToggleItem(
    name: String,
    description: String,
    isEnabled: Boolean,
    isRequired: Boolean,
    requiresConfig: Boolean,
    isConfigured: Boolean = false,
    configFields: List<String> = emptyList(),
    onToggle: (Boolean) -> Unit,
    onConfigure: (() -> Unit)? = null
) {
    val semantic = SemanticColors.forTheme(ColorTheme.DEFAULT, isDark = false)

    val adapterTag = name.lowercase().replace(" ", "_")
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = if (isEnabled) SetupColors.SuccessLight else SetupColors.GrayLight,
        modifier = Modifier
            .fillMaxWidth()
            .testableClickable("adapter_toggle_$adapterTag") {
                if (!isRequired) onToggle(!isEnabled)
            }
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = name,
                        color = SetupColors.TextPrimary,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium
                    )
                    if (isRequired) {
                        Spacer(modifier = Modifier.width(8.dp))
                        Surface(
                            shape = RoundedCornerShape(4.dp),
                            color = SetupColors.Primary.copy(alpha = 0.2f)
                        ) {
                            Text(
                                text = localizedString("mobile.common_required"),
                                color = SetupColors.Primary,
                                fontSize = 10.sp,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                            )
                        }
                    }
                    if (requiresConfig && isEnabled) {
                        Spacer(modifier = Modifier.width(8.dp))
                        if (isConfigured) {
                            // Show configured badge (green)
                            Surface(
                                shape = RoundedCornerShape(4.dp),
                                color = semantic.surfaceSuccess
                            ) {
                                Text(
                                    text = localizedString("mobile.setup_configured"),
                                    color = semantic.onSuccess,
                                    fontSize = 10.sp,
                                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                                )
                            }
                        } else {
                            // Show needs config badge (warning)
                            Surface(
                                shape = RoundedCornerShape(4.dp),
                                color = semantic.surfaceWarning
                            ) {
                                Text(
                                    text = localizedString("mobile.setup_needs_config"),
                                    color = semantic.onWarning,
                                    fontSize = 10.sp,
                                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                                )
                            }
                        }
                    }
                }
                Text(
                    text = description,
                    color = SetupColors.TextSecondary,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(top = 2.dp)
                )

                // Show configure button for configurable adapters
                if (requiresConfig && isEnabled && onConfigure != null) {
                    TextButton(
                        onClick = onConfigure,
                        modifier = Modifier
                            .padding(top = 4.dp)
                            .testableClickable("btn_configure_${name.lowercase().replace(" ", "_")}") { onConfigure() }
                    ) {
                        Text(
                            text = if (isConfigured) "Reconfigure" else "Configure Now",
                            color = SetupColors.Primary,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Medium
                        )
                    }
                } else if (requiresConfig && configFields.isNotEmpty() && isEnabled && !isConfigured) {
                    Text(
                        text = localizedString("mobile.setup_required_fields").replace("{fields}", configFields.joinToString(", ")),
                        color = semantic.onWarning,
                        fontSize = 11.sp,
                        modifier = Modifier.padding(top = 4.dp)
                    )
                }
            }

            Switch(
                checked = isEnabled,
                onCheckedChange = onToggle,
                enabled = !isRequired,
                colors = SwitchDefaults.colors(
                    checkedThumbColor = Color.White,
                    checkedTrackColor = SetupColors.Primary,
                    uncheckedThumbColor = Color.White,
                    uncheckedTrackColor = SetupColors.TextSecondary.copy(alpha = 0.5f)
                )
            )
        }
    }
}

// ========== Account & Confirmation Step ==========
@Composable
private fun AccountConfirmationStep(
    viewModel: SetupViewModel,
    state: SetupFormState,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(24.dp)
            .verticalScroll(rememberScrollState())
    ) {
        Text(
            text = localizedString("setup.confirm_title"),
            color = SetupColors.TextPrimary,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 8.dp)
        )

        Text(
            text = localizedString("setup.confirm_desc"),
            color = SetupColors.TextSecondary,
            fontSize = 14.sp,
            modifier = Modifier.padding(bottom = 24.dp)
        )

        // Google Connected card (for Google users)
        if (state.isGoogleAuth) {
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = SetupColors.SuccessLight,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 16.dp)
            ) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        text = getOAuthProviderName() + " " + localizedString("mobile.setup_account_title"),
                        color = SetupColors.SuccessDark,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(bottom = 4.dp)
                    )
                    Text(
                        text = state.googleEmail ?: "",
                        color = SetupColors.SuccessText,
                        fontSize = 14.sp,
                        modifier = Modifier.padding(bottom = 8.dp)
                    )
                    Text(
                        text = localizedString("mobile.setup_oauth_desc").replace("{provider}", getOAuthProviderName()),
                        color = SetupColors.SuccessText,
                        fontSize = 13.sp,
                        lineHeight = 18.sp
                    )
                }
            }
        }

        // Setup Summary
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = SetupColors.GrayLight,
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 16.dp)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = localizedString("mobile.setup_summary"),
                    color = SetupColors.TextPrimary,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(bottom = 12.dp)
                )

                SummaryRow(
                    label = "AI",
                    value = if (state.useCirisProxy()) "Free AI Access (via ${getOAuthProviderName()})" else state.llmProvider
                )
                SummaryRow(label = "Assistant", value = viewModel.getSelectedTemplateName())
                if (state.isGoogleAuth) {
                    SummaryRow(label = "Sign-in", value = "${getOAuthProviderName()} Account")
                }
            }
        }

        // Account creation (for non-Google users only)
        if (!state.isGoogleAuth) {
            Text(
                text = localizedString("mobile.setup_account_title"),
                color = SetupColors.TextPrimary,
                fontSize = 16.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(bottom = 8.dp)
            )

            Text(
                text = localizedString("mobile.setup_account_desc"),
                color = SetupColors.TextSecondary,
                fontSize = 14.sp,
                modifier = Modifier.padding(bottom = 16.dp)
            )

            OutlinedTextField(
                value = state.username,
                onValueChange = { viewModel.setUsername(it) },
                modifier = Modifier.fillMaxWidth().testable("input_username"),
                label = { Text(localizedString("mobile.login_username"), color = SetupColors.TextSecondary) },
                colors = OutlinedTextFieldDefaults.colors(
                    focusedTextColor = SetupColors.TextPrimary,
                    unfocusedTextColor = SetupColors.TextPrimary,
                    focusedBorderColor = SetupColors.Primary,
                    unfocusedBorderColor = SetupColors.TextSecondary.copy(alpha = 0.5f),
                    focusedLabelColor = SetupColors.Primary,
                    unfocusedLabelColor = SetupColors.TextSecondary,
                    cursorColor = SetupColors.Primary
                ),
                singleLine = true
            )

            Spacer(modifier = Modifier.height(12.dp))

            var showPassword by remember { mutableStateOf(false) }

            OutlinedTextField(
                value = state.userPassword,
                onValueChange = { viewModel.setUserPassword(it) },
                modifier = Modifier.fillMaxWidth().testable("input_password"),
                label = { Text(localizedString("mobile.login_password_label"), color = SetupColors.TextSecondary) },
                visualTransformation = if (showPassword) VisualTransformation.None else PasswordVisualTransformation(),
                trailingIcon = {
                    TextButton(
                        onClick = { showPassword = !showPassword },
                        modifier = Modifier.testableClickable("btn_toggle_password") { showPassword = !showPassword }
                    ) {
                        Text(if (showPassword) "Hide" else "Show", color = SetupColors.Primary)
                    }
                },
                colors = OutlinedTextFieldDefaults.colors(
                    focusedTextColor = SetupColors.TextPrimary,
                    unfocusedTextColor = SetupColors.TextPrimary,
                    focusedBorderColor = SetupColors.Primary,
                    unfocusedBorderColor = SetupColors.TextSecondary.copy(alpha = 0.5f),
                    focusedLabelColor = SetupColors.Primary,
                    unfocusedLabelColor = SetupColors.TextSecondary,
                    cursorColor = SetupColors.Primary
                ),
                singleLine = true
            )

            if (state.userPassword.isNotEmpty() && state.userPassword.length < 8) {
                Text(
                    text = localizedString("mobile.setup_password_hint"),
                    color = SetupColors.ErrorText,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(start = 4.dp, top = 4.dp)
                )
            }
        }
    }
}

@Composable
private fun SummaryRow(label: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            color = SetupColors.TextSecondary,
            fontSize = 14.sp
        )
        Text(
            text = value,
            color = SetupColors.TextPrimary,
            fontSize = 14.sp,
            fontWeight = FontWeight.Medium
        )
    }
}

// ========== Complete Step ==========
@Composable
private fun CompleteStep(
    onSetupComplete: () -> Unit,
    modifier: Modifier = Modifier
) {
    LaunchedEffect(Unit) {
        kotlinx.coroutines.delay(2000)
        onSetupComplete()
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(
            text = "✓",
            color = SetupColors.SuccessDark,
            fontSize = 64.sp
        )

        Spacer(modifier = Modifier.height(24.dp))

        Text(
            text = localizedString("mobile.setup_complete_title"),
            color = SetupColors.TextPrimary,
            fontSize = 24.sp,
            fontWeight = FontWeight.Bold,
            textAlign = TextAlign.Center
        )

        Spacer(modifier = Modifier.height(16.dp))

        Text(
            text = localizedString("mobile.setup_complete_desc"),
            color = SetupColors.TextSecondary,
            fontSize = 16.sp,
            textAlign = TextAlign.Center
        )

        Spacer(modifier = Modifier.height(24.dp))

        CircularProgressIndicator(color = SetupColors.Primary)
    }
}

// ========== Navigation Buttons ==========
@Composable
private fun NavigationButtons(
    currentStep: SetupStep,
    canProceed: Boolean,
    validationError: String?,
    isSubmitting: Boolean,
    isNodeFlow: Boolean,
    onNext: () -> Unit,
    onBack: () -> Unit,
    onBackToLogin: (() -> Unit)? = null,  // Optional callback to return to login screen
    modifier: Modifier = Modifier
) {
    Column(modifier = modifier) {
        // Show validation error if present
        if (validationError != null && !canProceed) {
            Surface(
                color = SetupColors.ErrorLight,
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 12.dp)
            ) {
                Text(
                    text = validationError,
                    color = SetupColors.ErrorText,
                    fontSize = 14.sp,
                    modifier = Modifier.padding(12.dp)
                )
            }
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Back button - on WELCOME step, go back to Login if callback provided
            if (currentStep == SetupStep.WELCOME && onBackToLogin != null) {
                OutlinedButton(
                    onClick = onBackToLogin,
                    enabled = !isSubmitting,
                    modifier = Modifier.weight(1f).testableClickable("btn_back_to_login") { onBackToLogin() },
                    colors = ButtonDefaults.outlinedButtonColors(
                        contentColor = SetupColors.TextSecondary
                    )
                ) {
                    Text(localizedString("mobile.setup_back_login"))
                }
            } else if (currentStep != SetupStep.WELCOME && currentStep != SetupStep.COMPLETE) {
                OutlinedButton(
                    onClick = onBack,
                    enabled = !isSubmitting,
                    modifier = Modifier.weight(1f).testableClickable("btn_back") { onBack() },
                    colors = ButtonDefaults.outlinedButtonColors(
                        contentColor = SetupColors.TextSecondary
                    )
                ) {
                    Text(localizedString("setup.back"))
                }
            }

            // Next/Finish button
            if (currentStep != SetupStep.COMPLETE) {
                Button(
                    onClick = onNext,
                    enabled = canProceed && !isSubmitting,
                    // Use equal weights if back button is visible, otherwise double width on WELCOME
                    modifier = Modifier
                        .weight(if (currentStep == SetupStep.WELCOME && onBackToLogin == null) 2f else 1f)
                        .testableClickable("btn_next") { onNext() },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = SetupColors.Primary,
                        contentColor = Color.White
                    )
                ) {
                    if (isSubmitting) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(20.dp),
                            color = Color.White,
                            strokeWidth = 2.dp
                        )
                    } else {
                        // Determine button text based on step and flow type
                        val isFinalStep = currentStep == SetupStep.ACCOUNT_AND_CONFIRMATION ||
                            (isNodeFlow && currentStep == SetupStep.OPTIONAL_FEATURES)
                        Text(
                            when {
                                currentStep == SetupStep.WELCOME -> "${localizedString("setup.continue")} →"
                                isFinalStep -> localizedString("setup.finish")
                                else -> localizedString("setup.next")
                            }
                        )
                    }
                }
            }
        }
    }
}

/**
 * Preferences Step - Language and Location selection
 * Mirrors the CLI wizard's language/location prompts (wizard.py:324-395)
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PreferencesStep(
    viewModel: SetupViewModel,
    state: SetupFormState,
    modifier: Modifier = Modifier
) {
    val scrollState = rememberScrollState()
    var showLanguageDropdown by remember { mutableStateOf(false) }
    val focusManager = LocalFocusManager.current

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(24.dp)
            .verticalScroll(scrollState),
        verticalArrangement = Arrangement.spacedBy(24.dp)
    ) {
        // Header
        Text(
            text = localizedString("setup.prefs_title"),
            fontSize = 24.sp,
            fontWeight = FontWeight.Bold,
            color = SetupColors.TextPrimary
        )

        Text(
            text = localizedString("setup.prefs_desc"),
            fontSize = 14.sp,
            color = SetupColors.TextSecondary
        )

        // Language Selection
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = SetupColors.GrayLight,
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = localizedString("setup.prefs_language_label"),
                    fontWeight = FontWeight.SemiBold,
                    fontSize = 16.sp,
                    color = SetupColors.TextPrimary
                )

                Spacer(modifier = Modifier.height(12.dp))

                // Language dropdown
                Box {
                    Surface(
                        shape = RoundedCornerShape(8.dp),
                        color = Color.White,
                        modifier = Modifier
                            .fillMaxWidth()
                            .clickable { showLanguageDropdown = true }
                            .border(1.dp, SetupColors.TextSecondary.copy(alpha = 0.3f), RoundedCornerShape(8.dp))
                    ) {
                        Row(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(16.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            val selectedLang = SUPPORTED_LANGUAGES.find { it.code == state.preferredLanguage }
                            Text(
                                text = selectedLang?.let { "${it.nativeName} (${it.englishName})" } ?: "English",
                                color = SetupColors.TextPrimary
                            )
                            Text(text = "▼", color = SetupColors.TextSecondary)
                        }
                    }

                    DropdownMenu(
                        expanded = showLanguageDropdown,
                        onDismissRequest = { showLanguageDropdown = false }
                    ) {
                        SUPPORTED_LANGUAGES.forEach { lang ->
                            DropdownMenuItem(
                                text = {
                                    Text("${lang.nativeName} (${lang.englishName})")
                                },
                                onClick = {
                                    viewModel.setPreferredLanguage(lang.code)
                                    showLanguageDropdown = false
                                }
                            )
                        }
                    }
                }
            }
        }

        // Location Selection - Simple city text entry with typeahead
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = SetupColors.GrayLight,
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                // Use ExposedDropdownMenuBox for proper dropdown positioning (shows above keyboard)
                ExposedDropdownMenuBox(
                    expanded = state.locationSearchResults.isNotEmpty(),
                    onExpandedChange = { /* Controlled by search results */ }
                ) {
                    OutlinedTextField(
                        value = state.locationSearchQuery,
                        onValueChange = { viewModel.searchLocations(it) },
                        label = { Text(localizedString("setup.prefs_city_label"), color = SetupColors.TextPrimary) },
                        placeholder = { Text(localizedString("setup.prefs_city_hint"), color = SetupColors.TextSecondary) },
                        modifier = Modifier.fillMaxWidth().menuAnchor().testable("input_location_search"),
                        singleLine = true,
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedTextColor = SetupColors.TextPrimary,
                            unfocusedTextColor = SetupColors.TextPrimary,
                            focusedBorderColor = SetupColors.Primary,
                            unfocusedBorderColor = SetupColors.TextSecondary.copy(alpha = 0.5f),
                            focusedLabelColor = SetupColors.Primary,
                            unfocusedLabelColor = SetupColors.TextSecondary,
                            cursorColor = SetupColors.Primary
                        ),
                        trailingIcon = {
                            if (state.locationSearchLoading) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(20.dp),
                                    strokeWidth = 2.dp
                                )
                            } else if (state.locationSearchQuery.isNotEmpty()) {
                                IconButton(onClick = { viewModel.clearLocationSearch() }) {
                                    Icon(Icons.Default.Clear, contentDescription = "Clear", tint = SetupColors.TextSecondary)
                                }
                            } else {
                                Icon(Icons.Default.LocationOn, contentDescription = null, tint = SetupColors.TextSecondary)
                            }
                        }
                    )

                    // Dropdown menu - will automatically position above if no space below
                    ExposedDropdownMenu(
                        expanded = state.locationSearchResults.isNotEmpty(),
                        onDismissRequest = { viewModel.clearLocationSearch() },
                        modifier = Modifier.background(Color.White)
                    ) {
                        state.locationSearchResults.forEach { result ->
                            DropdownMenuItem(
                                text = {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Icon(
                                            Icons.Default.LocationOn,
                                            contentDescription = null,
                                            tint = Color(0xFF666666),
                                            modifier = Modifier.size(20.dp)
                                        )
                                        Spacer(modifier = Modifier.width(8.dp))
                                        Column {
                                            Text(
                                                text = result.displayName,
                                                fontSize = 14.sp,
                                                color = Color(0xFF1A1A1A)
                                            )
                                            if (result.population > 0) {
                                                Text(
                                                    text = localizedString("setup.prefs_location_pop", "pop", formatPopulation(result.population)),
                                                    fontSize = 11.sp,
                                                    color = Color(0xFF666666)
                                                )
                                            }
                                        }
                                    }
                                },
                                onClick = {
                                    viewModel.selectLocation(result)
                                    focusManager.clearFocus()
                                },
                                modifier = Modifier.background(Color.White).testableClickable("location_result_${result.displayName.lowercase().replace(" ", "_").replace(",", "").take(40)}") {
                                    viewModel.selectLocation(result)
                                    focusManager.clearFocus()
                                }
                            )
                        }
                    }
                }

                // Show selected location
                if (state.selectedLocation != null) {
                    Spacer(modifier = Modifier.height(12.dp))
                    Surface(
                        shape = RoundedCornerShape(8.dp),
                        color = SetupColors.SuccessLight,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Row(
                            modifier = Modifier.padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Icon(
                                Icons.Default.CheckCircle,
                                contentDescription = null,
                                tint = SetupColors.SuccessDark,
                                modifier = Modifier.size(20.dp)
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = state.selectedLocation!!.displayName,
                                fontSize = 14.sp,
                                fontWeight = FontWeight.Medium,
                                color = SetupColors.TextPrimary
                            )
                        }
                    }
                }
            }
        }

        // Privacy note
        Surface(
            shape = RoundedCornerShape(8.dp),
            color = SetupColors.InfoLight,
            modifier = Modifier.fillMaxWidth()
        ) {
            Row(
                modifier = Modifier.padding(12.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(text = "ℹ️", fontSize = 16.sp)
                Text(
                    text = localizedString("mobile.setup_location_note"),
                    fontSize = 12.sp,
                    color = SetupColors.InfoText
                )
            }
        }
    }
}
