package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.Platform
import ai.ciris.mobile.shared.models.SetupMode
import ai.ciris.mobile.shared.models.filterAdaptersForPlatform
import ai.ciris.mobile.shared.platform.getOAuthProviderName
import ai.ciris.mobile.shared.viewmodels.DeviceAuthStatus
import ai.ciris.mobile.shared.viewmodels.SetupStep
import ai.ciris.mobile.shared.viewmodels.SetupFormState
import ai.ciris.mobile.shared.viewmodels.SetupViewModel
import ai.ciris.mobile.shared.viewmodels.VerifyStatusResponse
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
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Setup Wizard Screen - EXACTLY matches android/app/.../setup/ fragments
 *
 * Uses LIGHT THEME with colors from android/app/src/main/res/values/colors.xml:
 * - text_primary: #1F2937 (dark gray)
 * - text_secondary: #6B7280 (medium gray)
 * - success_light: #D1FAE5, success_dark: #065F46, success_text: #047857
 * - info_light: #DBEAFE, info_dark: #1E40AF, info_text: #1D4ED8
 */

// Colors from android/app/src/main/res/values/colors.xml
private object SetupColors {
    val Background = Color.White
    val TextPrimary = Color(0xFF1F2937)
    val TextSecondary = Color(0xFF6B7280)

    // Success (green) - for Google ready card
    val SuccessLight = Color(0xFFD1FAE5)
    val SuccessBorder = Color(0xFF6EE7B7)
    val SuccessDark = Color(0xFF065F46)
    val SuccessText = Color(0xFF047857)

    // Info (blue) - for setup required card
    val InfoLight = Color(0xFFDBEAFE)
    val InfoBorder = Color(0xFF93C5FD)
    val InfoDark = Color(0xFF1E40AF)
    val InfoText = Color(0xFF1D4ED8)

    // Gray for cards
    val GrayLight = Color(0xFFF3F4F6)

    // Primary accent
    val Primary = Color(0xFF667eea)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SetupScreen(
    viewModel: SetupViewModel,
    apiClient: CIRISApiClient,
    onSetupComplete: () -> Unit,
    modifier: Modifier = Modifier
) {
    val state by viewModel.state.collectAsState()
    val coroutineScope = rememberCoroutineScope()

    // Load adapters and templates when entering OPTIONAL_FEATURES step
    LaunchedEffect(state.currentStep) {
        if (state.currentStep == SetupStep.OPTIONAL_FEATURES) {
            // Load adapters if not already loaded
            if (state.availableAdapters.isEmpty()) {
                // Fetch all adapters from server, then filter client-side based on platform
                // This approach works for both iOS and Android (KMP)
                viewModel.loadAvailableAdapters {
                    val allAdapters = apiClient.getSetupAdapters()
                    filterAdaptersForPlatform(
                        adapters = allAdapters,
                        platform = Platform.ANDROID,  // TODO: Use expect/actual for platform detection
                        useCirisServices = state.isGoogleAuth
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
                    SetupStep.LLM_CONFIGURATION -> LlmConfigurationStep(viewModel, state)
                    SetupStep.OPTIONAL_FEATURES -> OptionalFeaturesStep(viewModel, state)
                    SetupStep.ACCOUNT_AND_CONFIRMATION -> AccountConfirmationStep(viewModel, state)
                    SetupStep.VERIFY_SETUP -> VerifySetupStep(viewModel, state)
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
                        .background(if (isAlreadyConfigured) Color(0xFFFFF3CD) else Color(0xFFF8D7DA))
                        .padding(16.dp)
                ) {
                    Text(
                        text = if (isAlreadyConfigured) "Setup Already Complete" else "Setup Error",
                        fontWeight = FontWeight.Bold,
                        color = if (isAlreadyConfigured) Color(0xFF856404) else Color(0xFF721C24)
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = error,
                        fontSize = 14.sp,
                        color = if (isAlreadyConfigured) Color(0xFF856404) else Color(0xFF721C24)
                    )
                    if (isAlreadyConfigured) {
                        Spacer(modifier = Modifier.height(12.dp))
                        Button(
                            onClick = {
                                println("[SetupScreen] User chose to skip setup (already configured)")
                                onSetupComplete()
                            },
                            colors = ButtonDefaults.buttonColors(
                                containerColor = SetupColors.Primary
                            )
                        ) {
                            Text("Continue to App")
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
                onNext = {
                    println("[SetupScreen] onNext clicked, currentStep=${state.currentStep}, canProceed=${state.canProceedFromCurrentStep()}")
                    if (state.currentStep == SetupStep.ACCOUNT_AND_CONFIRMATION) {
                        // On final step, submit setup to API then advance
                        println("[SetupScreen] Final step - launching coroutine to submit setup")
                        coroutineScope.launch {
                            println("[SetupScreen] Coroutine started - calling viewModel.completeSetup")
                            try {
                                // Run API call on IO dispatcher to avoid blocking main thread
                                // Setup can take 20+ seconds as Python initializes services
                                val result = withContext(Dispatchers.IO) {
                                    viewModel.completeSetup { request ->
                                        // Make API call to /v1/setup/complete
                                        println("[SetupScreen] Calling apiClient.completeSetup with provider=${request.llm_provider}")
                                        apiClient.completeSetup(request)
                                    }
                                }
                                println("[SetupScreen] completeSetup returned: success=${result.success}, error=${result.error}")
                                if (result.success) {
                                    println("[SetupScreen] Setup successful - advancing to next step")
                                    viewModel.nextStep()
                                } else {
                                    println("[SetupScreen] ERROR: Setup failed: ${result.error}")
                                    // Error is now shown in UI via state.submissionError
                                }
                            } catch (e: Exception) {
                                println("[SetupScreen] EXCEPTION in completeSetup: ${e.message}")
                                e.printStackTrace()
                            }
                        }
                    } else {
                        println("[SetupScreen] Not final step - calling viewModel.nextStep()")
                        viewModel.nextStep()
                    }
                },
                onBack = { viewModel.previousStep() },
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
            SetupStep.VERIFY_SETUP to "4"
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
        modifier = modifier,
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically
    ) {
        steps.forEachIndexed { index, (step, number) ->
            val isActive = currentStep >= step
            val isComplete = currentStep > step

            Box(
                modifier = Modifier
                    .size(32.dp)
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
                text = "✓ 100% Free & Open Source",
                color = SetupColors.SuccessText,
                fontSize = 14.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
            )
        }

        // Register Your Agent card — always visible, above the fold
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = Color(0xFFF0FDF4), // Light green
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 16.dp)
                .border(1.dp, Color(0xFF86EFAC), RoundedCornerShape(12.dp))
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = "Register Your Agent Identity",
                    color = SetupColors.SuccessDark,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = "Join the CIRIS community and enable cryptographic verification of your agent's behavior.",
                    color = SetupColors.SuccessText,
                    fontSize = 13.sp,
                    lineHeight = 18.sp,
                    modifier = Modifier.padding(top = 4.dp, bottom = 8.dp)
                )

                // Benefits list
                Column(modifier = Modifier.padding(bottom = 12.dp)) {
                    BenefitRow("Audit trail — cryptographically-signed traces begin")
                    BenefitRow("Coherence Ratchet — coordinated deception becomes mathematically harder over time")
                    BenefitRow("CIRIS Scoring — measures integrity across interactions")
                    BenefitRow("Community template (Ally) included")
                }

                Text(
                    text = "\$1.00 refundable bond + \$0.50 processing fee",
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
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text("Connect to CIRIS Portal", fontWeight = FontWeight.Bold)
                }

                Text(
                    text = "Identity keys are bound to your agent — transfers not yet supported",
                    color = SetupColors.TextSecondary,
                    fontSize = 11.sp,
                    textAlign = TextAlign.Center,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 8.dp)
                )

                Text(
                    text = "For licensed deployment, contact sales@ciris.ai",
                    color = SetupColors.TextSecondary,
                    fontSize = 11.sp,
                    textAlign = TextAlign.Center,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(top = 4.dp)
                )
            }
        }

        // Main description
        Text(
            text = "CIRIS is an ethical AI assistant that runs on your device. Your conversations and data stay private.",
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
                    text = "ℹ️ What CIRIS Is",
                    color = SetupColors.InfoDark,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(bottom = 8.dp)
                )
                Text(
                    text = "CIRIS is an AI tool, not a friend, therapist, or human substitute. For emotional support, please reach out to real people in your life or professional services.",
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
                            text = "You're ready to go!",
                            color = SetupColors.SuccessDark,
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                    Text(
                        text = "Since you signed in with ${getOAuthProviderName()}, CIRIS can start working right away. Free access is limited and includes web search via privacy-protecting providers (Exa, Brave).",
                        color = SetupColors.SuccessText,
                        fontSize = 14.sp,
                        lineHeight = 20.sp
                    )

                    // Expandable details
                    Text(
                        text = if (detailsExpanded) "▼ Details" else "▶ Details",
                        color = SetupColors.SuccessDark,
                        fontSize = 13.sp,
                        modifier = Modifier
                            .padding(top = 12.dp)
                            .clickable { detailsExpanded = !detailsExpanded }
                    )

                    AnimatedVisibility(visible = detailsExpanded) {
                        Text(
                            text = "• Your conversations are never sent for external AI training\n• With your consent, CIRIS can learn locally on your device to better assist you\n• All data stays on your device unless you explicitly share it\n• You control what CIRIS remembers about you",
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
                        text = "Quick Setup Required",
                        color = SetupColors.InfoDark,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(bottom = 8.dp)
                    )
                    Text(
                        text = "To power AI conversations, you'll need to connect an AI provider (like OpenAI or Anthropic). This takes about 2 minutes.",
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
                    text = "How it works",
                    color = SetupColors.TextPrimary,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.padding(bottom = 8.dp)
                )
                Text(
                    text = "CIRIS runs entirely on your device. However, AI reasoning requires powerful servers. CIRIS connects to privacy-respecting AI providers that never train on your data and never store your conversations.",
                    color = SetupColors.TextSecondary,
                    fontSize = 14.sp,
                    lineHeight = 20.sp
                )
            }
        }

        // Trust and Security card - shows CIRISVerify status (REQUIRED for 2.0)
        Spacer(modifier = Modifier.height(16.dp))
        TrustSecurityCard(
            apiClient = apiClient,
            modifier = Modifier.fillMaxWidth()
        )

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
    val uriHandler = LocalUriHandler.current
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

    // Poll for completion while waiting
    LaunchedEffect(deviceAuth.status) {
        if (deviceAuth.status == DeviceAuthStatus.WAITING) {
            while (true) {
                kotlinx.coroutines.delay(deviceAuth.interval.toLong() * 1000)
                viewModel.pollNodeAuthStatus { deviceCode, portalUrl ->
                    apiClient.pollNodeAuthStatus(deviceCode, portalUrl)
                }
                // Break if no longer waiting
                if (viewModel.state.value.deviceAuth.status != DeviceAuthStatus.WAITING) break
            }
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(24.dp)
            .verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = "Register Agent",
            color = SetupColors.TextPrimary,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 8.dp)
        )

        Text(
            text = "Registering via ${deviceAuth.nodeUrl}",
            color = SetupColors.TextSecondary,
            fontSize = 14.sp,
            modifier = Modifier.padding(bottom = 24.dp)
        )

        when (deviceAuth.status) {
            DeviceAuthStatus.IDLE, DeviceAuthStatus.CONNECTING -> {
                CircularProgressIndicator(
                    color = SetupColors.Primary,
                    modifier = Modifier.padding(16.dp)
                )
                Text(
                    text = "Connecting to portal...",
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
                            text = "Click to open in browser, or copy to open in another app:",
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
                                    uriHandler.openUri(fullVerificationUrl)
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
                                onClick = { uriHandler.openUri(fullVerificationUrl) },
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = SetupColors.Primary
                                ),
                                modifier = Modifier.weight(1f)
                            ) {
                                Text("Open in Browser", fontSize = 13.sp)
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
                                modifier = Modifier.weight(1f)
                            ) {
                                Text(
                                    if (showCopiedToast) "Copied!" else "Copy URL",
                                    fontSize = 13.sp
                                )
                            }
                        }

                        if (deviceAuth.userCode.isNotBlank()) {
                            Spacer(modifier = Modifier.height(12.dp))
                            Text(
                                text = "Code: ${deviceAuth.userCode}",
                                color = SetupColors.InfoDark,
                                fontSize = 18.sp,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.height(24.dp))

                // Polling spinner
                CircularProgressIndicator(
                    color = SetupColors.Primary,
                    modifier = Modifier.size(24.dp),
                    strokeWidth = 2.dp
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "Waiting for authorization...",
                    color = SetupColors.TextSecondary,
                    fontSize = 14.sp
                )
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
                            text = "✓ Agent Authorized",
                            color = SetupColors.SuccessDark,
                            fontSize = 18.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(bottom = 12.dp)
                        )
                        deviceAuth.provisionedTemplate?.let {
                            Text(
                                text = "Template: $it",
                                color = SetupColors.SuccessText,
                                fontSize = 14.sp
                            )
                        }
                        if (deviceAuth.provisionedAdapters.isNotEmpty()) {
                            Text(
                                text = "Adapters: ${deviceAuth.provisionedAdapters.joinToString(", ")}",
                                color = SetupColors.SuccessText,
                                fontSize = 14.sp
                            )
                        }
                        deviceAuth.orgId?.let {
                            Text(
                                text = "Organization: $it",
                                color = SetupColors.SuccessText,
                                fontSize = 14.sp
                            )
                        }
                    }
                }

                Spacer(modifier = Modifier.height(16.dp))
                Text(
                    text = "Tap Continue to configure your LLM provider.",
                    color = SetupColors.TextSecondary,
                    fontSize = 14.sp,
                    textAlign = TextAlign.Center
                )
            }

            DeviceAuthStatus.ERROR -> {
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = Color(0xFFFEE2E2),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(20.dp)) {
                        Text(
                            text = "Connection Failed",
                            color = Color(0xFF991B1B),
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold,
                            modifier = Modifier.padding(bottom = 8.dp)
                        )
                        Text(
                            text = deviceAuth.error ?: "Unknown error",
                            color = Color(0xFFDC2626),
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
                    colors = ButtonDefaults.buttonColors(containerColor = SetupColors.Primary)
                ) {
                    Text("Retry")
                }
            }
        }
    }
}

// ========== CIRISVerify Setup Step ==========
@Composable
private fun VerifySetupStep(
    viewModel: SetupViewModel,
    state: SetupFormState,
    modifier: Modifier = Modifier
) {
    val verifyState = state.verifySetup

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(24.dp)
            .verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text(
            text = "CIRISVerify",
            color = SetupColors.TextPrimary,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 8.dp)
        )

        Text(
            text = "CIRISVerify provides hardware-rooted license verification for your agent.",
            color = SetupColors.TextSecondary,
            fontSize = 14.sp,
            textAlign = TextAlign.Center,
            modifier = Modifier.padding(bottom = 24.dp)
        )

        // Enable toggle
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = if (verifyState.enabled) SetupColors.SuccessLight else SetupColors.GrayLight,
            modifier = Modifier
                .fillMaxWidth()
                .clickable { viewModel.setVerifyEnabled(!verifyState.enabled) }
        ) {
            Row(
                modifier = Modifier.padding(16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Install CIRISVerify",
                        color = SetupColors.TextPrimary,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "Enables hardware attestation and license verification",
                        color = SetupColors.TextSecondary,
                        fontSize = 13.sp
                    )
                }
                Switch(
                    checked = verifyState.enabled,
                    onCheckedChange = { viewModel.setVerifyEnabled(it) },
                    colors = SwitchDefaults.colors(
                        checkedTrackColor = SetupColors.SuccessDark
                    )
                )
            }
        }

        if (verifyState.enabled) {
            Spacer(modifier = Modifier.height(16.dp))

            // Download status
            if (verifyState.downloaded) {
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = SetupColors.SuccessLight,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Text(
                            text = "✓ CIRISVerify Installed",
                            color = SetupColors.SuccessDark,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold
                        )
                        verifyState.version?.let {
                            Text(
                                text = "Version: $it",
                                color = SetupColors.SuccessText,
                                fontSize = 13.sp
                            )
                        }
                    }
                }
            } else if (verifyState.downloading) {
                CircularProgressIndicator(
                    color = SetupColors.Primary,
                    modifier = Modifier.padding(16.dp)
                )
                Text(
                    text = "Downloading CIRISVerify...",
                    color = SetupColors.TextSecondary,
                    fontSize = 14.sp
                )
            } else {
                // TODO: Wire download button to actual POST /v1/setup/verify/download.
                // MVP: Placeholder button (download func not yet implemented).
                Button(
                    onClick = { /* TODO: Implement download */ },
                    colors = ButtonDefaults.buttonColors(containerColor = SetupColors.Primary),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text("Download CIRISVerify", fontWeight = FontWeight.Bold)
                }
            }

            // Hardware requirement toggle
            Spacer(modifier = Modifier.height(16.dp))
            Surface(
                shape = RoundedCornerShape(12.dp),
                color = SetupColors.GrayLight,
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { viewModel.setVerifyRequireHardware(!verifyState.requireHardware) }
            ) {
                Row(
                    modifier = Modifier.padding(16.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Require Hardware Attestation",
                            color = SetupColors.TextPrimary,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Bold
                        )
                        Text(
                            text = "Requires TPM or Secure Enclave for verification",
                            color = SetupColors.TextSecondary,
                            fontSize = 12.sp
                        )
                    }
                    Switch(
                        checked = verifyState.requireHardware,
                        onCheckedChange = { viewModel.setVerifyRequireHardware(it) }
                    )
                }
            }

            verifyState.error?.let { error ->
                Spacer(modifier = Modifier.height(12.dp))
                Text(
                    text = error,
                    color = Color(0xFFDC2626),
                    fontSize = 13.sp
                )
            }
        }

        Spacer(modifier = Modifier.height(24.dp))
        Text(
            text = "You can skip this step and configure CIRISVerify later.",
            color = SetupColors.TextSecondary,
            fontSize = 13.sp,
            textAlign = TextAlign.Center
        )
    }
}

// ========== LLM Configuration Step (fragment_setup_llm.xml) ==========
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun LlmConfigurationStep(
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
            text = "AI Configuration",
            color = SetupColors.TextPrimary,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 8.dp)
        )

        Text(
            text = "Configure how CIRIS connects to AI services.",
            color = SetupColors.TextSecondary,
            fontSize = 14.sp,
            modifier = Modifier.padding(bottom = 24.dp)
        )

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
                            text = "Free AI Access Ready",
                            color = SetupColors.SuccessDark,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold
                        )
                    }
                    Text(
                        text = "Your ${getOAuthProviderName()} account includes limited free AI access with web search (Exa, Brave). Privacy-protected and never used for training.",
                        color = SetupColors.SuccessText,
                        fontSize = 14.sp,
                        lineHeight = 20.sp
                    )
                }
            }

            // Advanced option link
            TextButton(
                onClick = { viewModel.setSetupMode(SetupMode.BYOK) },
                modifier = Modifier.padding(bottom = 16.dp)
            ) {
                Text(
                    text = "I have my own AI provider (Advanced)",
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
                            text = "Using your own AI provider",
                            color = SetupColors.InfoDark,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Bold
                        )
                        Text(
                            text = "You can switch back to free AI anytime",
                            color = SetupColors.InfoText,
                            fontSize = 12.sp
                        )
                    }
                    TextButton(onClick = { viewModel.setSetupMode(SetupMode.CIRIS_PROXY) }) {
                        Text("Use Free AI", color = SetupColors.InfoDark)
                    }
                }
            }
        }

        // BYOK configuration (shown when in BYOK mode or for non-Google users)
        if (state.setupMode == SetupMode.BYOK || !state.isGoogleAuth) {
            // Provider selection
            Text(
                text = "Provider",
                color = SetupColors.TextPrimary,
                fontSize = 14.sp,
                fontWeight = FontWeight.Medium,
                modifier = Modifier.padding(bottom = 8.dp)
            )

            var providerExpanded by remember { mutableStateOf(false) }
            val providers = listOf("OpenAI", "Anthropic", "Google AI", "OpenRouter", "Groq", "Together AI", "LocalAI")

            ExposedDropdownMenuBox(
                expanded = providerExpanded,
                onExpandedChange = { providerExpanded = it }
            ) {
                OutlinedTextField(
                    value = state.llmProvider,
                    onValueChange = {},
                    readOnly = true,
                    modifier = Modifier
                        .fillMaxWidth()
                        .menuAnchor(),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = SetupColors.Primary,
                        unfocusedBorderColor = SetupColors.GrayLight
                    )
                )

                ExposedDropdownMenu(
                    expanded = providerExpanded,
                    onDismissRequest = { providerExpanded = false }
                ) {
                    providers.forEach { provider ->
                        DropdownMenuItem(
                            text = { Text(provider) },
                            onClick = {
                                viewModel.setLlmProvider(provider)
                                providerExpanded = false
                            }
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // API Key input (except for LocalAI)
            if (state.llmProvider != "LocalAI") {
                Text(
                    text = "API Key",
                    color = SetupColors.TextPrimary,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium,
                    modifier = Modifier.padding(bottom = 8.dp)
                )

                var showApiKey by remember { mutableStateOf(false) }

                OutlinedTextField(
                    value = state.llmApiKey,
                    onValueChange = { viewModel.setLlmApiKey(it) },
                    modifier = Modifier.fillMaxWidth(),
                    placeholder = { Text("sk-...", color = SetupColors.TextSecondary) },
                    visualTransformation = if (showApiKey) VisualTransformation.None else PasswordVisualTransformation(),
                    trailingIcon = {
                        TextButton(onClick = { showApiKey = !showApiKey }) {
                            Text(
                                text = if (showApiKey) "Hide" else "Show",
                                color = SetupColors.Primary,
                                fontSize = 12.sp
                            )
                        }
                    },
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = SetupColors.Primary,
                        unfocusedBorderColor = SetupColors.GrayLight
                    ),
                    singleLine = true
                )

                Spacer(modifier = Modifier.height(16.dp))
            }

            // Test Connection button
            OutlinedButton(
                onClick = { /* TODO: Test connection */ },
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.outlinedButtonColors(
                    contentColor = SetupColors.Primary
                )
            ) {
                Text("Test Connection")
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
            text = "Optional Features",
            color = SetupColors.TextPrimary,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 8.dp)
        )

        Text(
            text = "Customize your CIRIS experience with these optional settings.",
            color = SetupColors.TextSecondary,
            fontSize = 14.sp,
            modifier = Modifier.padding(bottom = 24.dp)
        )

        // Covenant Metrics Consent Card
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
                        text = "Help Improve AI Alignment",
                        color = SetupColors.InfoDark,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold
                    )
                }

                Text(
                    text = "Share anonymous metrics with CIRIS L3C to advance AI alignment research. This includes your LLM provider and API base URL to help study alignment patterns across different providers and models.",
                    color = SetupColors.InfoText,
                    fontSize = 14.sp,
                    lineHeight = 20.sp,
                    modifier = Modifier.padding(bottom = 12.dp)
                )

                Text(
                    text = "Data shared:",
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
                    modifier = Modifier.clickable {
                        viewModel.setCovenantMetricsConsent(!state.covenantMetricsConsent)
                    }
                ) {
                    Checkbox(
                        checked = state.covenantMetricsConsent,
                        onCheckedChange = { viewModel.setCovenantMetricsConsent(it) },
                        colors = CheckboxDefaults.colors(
                            checkedColor = SetupColors.Primary,
                            uncheckedColor = SetupColors.TextSecondary
                        )
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "I agree to share anonymous alignment metrics",
                        color = SetupColors.InfoDark,
                        fontSize = 14.sp
                    )
                }
            }
        }

        // Adapters Section
        Text(
            text = "Communication Adapters",
            color = SetupColors.TextPrimary,
            fontSize = 16.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 8.dp, top = 8.dp)
        )

        Text(
            text = "Select which adapters to enable. You can configure additional adapters later in Settings.",
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
                onToggle = {}
            )
        } else {
            state.availableAdapters.forEach { adapter ->
                val isEnabled = state.enabledAdapterIds.contains(adapter.id)
                val isRequired = adapter.id == "api"

                AdapterToggleItem(
                    name = adapter.name,
                    description = adapter.description,
                    isEnabled = isEnabled,
                    isRequired = isRequired,
                    requiresConfig = adapter.requires_config,
                    configFields = adapter.config_fields,
                    onToggle = { enabled ->
                        if (!isRequired) {
                            viewModel.toggleAdapter(adapter.id, enabled)
                        }
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
                .clickable { viewModel.setShowAdvancedSettings(!state.showAdvancedSettings) }
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
                    text = "Advanced Settings",
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
                        text = "Agent Template",
                        color = SetupColors.TextPrimary,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium,
                        modifier = Modifier.padding(bottom = 4.dp)
                    )
                    Text(
                        text = "Choose a personality template. Most users should use Default.",
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
                            text = "Default template will be used",
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
                                                text = "(Recommended)",
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

// ========== Trust and Security Card ==========
// Additional colors for Trust and Security card
private object TrustColors {
    val EmeraldLight = Color(0xFFD1FAE5)
    val EmeraldBorder = Color(0xFF6EE7B7)
    val EmeraldDark = Color(0xFF065F46)
    val EmeraldText = Color(0xFF047857)
    val EmeraldMuted = Color(0xFFA7F3D0)

    val WarningLight = Color(0xFFFEF3C7)
    val WarningBorder = Color(0xFFFCD34D)
    val WarningDark = Color(0xFF92400E)
    val WarningText = Color(0xFFD97706)

    val ErrorLight = Color(0xFFFEE2E2)
    val ErrorBorder = Color(0xFFFCA5A5)
    val ErrorDark = Color(0xFF991B1B)
    val ErrorText = Color(0xFFDC2626)
}

/**
 * Trust and Security Card
 *
 * Displays CIRISVerify status including:
 * - Library loaded status (REQUIRED for CIRIS 2.0+)
 * - Hardware security type
 * - Key status (Portal key activation)
 * - Attestation status
 * - Disclaimer about cryptographic verification
 */
@Composable
private fun TrustSecurityCard(
    apiClient: CIRISApiClient,
    modifier: Modifier = Modifier
) {
    var verifyStatus by remember { mutableStateOf<VerifyStatusResponse?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    val coroutineScope = rememberCoroutineScope()
    val uriHandler = LocalUriHandler.current

    // Fetch verify status on mount and refresh every 30 seconds
    LaunchedEffect(Unit) {
        while (true) {
            try {
                verifyStatus = withContext(Dispatchers.IO) {
                    apiClient.getVerifyStatus()
                }
                error = null
            } catch (e: Exception) {
                error = e.message ?: "Failed to fetch verify status"
            } finally {
                loading = false
            }
            delay(30000) // Refresh every 30 seconds
        }
    }

    // Loading state
    if (loading) {
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = SetupColors.GrayLight,
            modifier = modifier.fillMaxWidth()
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Box(
                    modifier = Modifier
                        .fillMaxWidth(0.33f)
                        .height(16.dp)
                        .background(Color(0xFFE5E7EB), RoundedCornerShape(4.dp))
                )
                Spacer(modifier = Modifier.height(12.dp))
                Box(
                    modifier = Modifier
                        .fillMaxWidth(0.66f)
                        .height(12.dp)
                        .background(Color(0xFFE5E7EB), RoundedCornerShape(4.dp))
                )
                Spacer(modifier = Modifier.height(8.dp))
                Box(
                    modifier = Modifier
                        .fillMaxWidth(0.5f)
                        .height(12.dp)
                        .background(Color(0xFFE5E7EB), RoundedCornerShape(4.dp))
                )
            }
        }
        return
    }

    // CIRISVerify not loaded - CRITICAL ERROR for 2.0
    if (verifyStatus?.loaded != true) {
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = TrustColors.ErrorLight,
            modifier = modifier
                .fillMaxWidth()
                .border(1.dp, TrustColors.ErrorBorder, RoundedCornerShape(12.dp))
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.padding(bottom = 8.dp)
                ) {
                    Text(
                        text = "⚠",
                        color = TrustColors.ErrorDark,
                        fontSize = 18.sp
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "CIRISVerify Required",
                        color = TrustColors.ErrorDark,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold
                    )
                }

                Text(
                    text = "CIRISVerify is required for CIRIS 2.0 agents. The agent cannot operate without cryptographic identity verification.",
                    color = TrustColors.ErrorText,
                    fontSize = 13.sp,
                    lineHeight = 18.sp
                )

                (error ?: verifyStatus?.error)?.let { errMsg ->
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = TrustColors.ErrorLight.copy(alpha = 0.5f),
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(top = 8.dp)
                    ) {
                        Text(
                            text = errMsg,
                            color = TrustColors.ErrorDark,
                            fontSize = 11.sp,
                            fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace,
                            modifier = Modifier.padding(8.dp)
                        )
                    }
                }

                Spacer(modifier = Modifier.height(12.dp))
                HorizontalDivider(color = TrustColors.ErrorBorder.copy(alpha = 0.5f))
                Spacer(modifier = Modifier.height(8.dp))

                Text(
                    text = "Install CIRISVerify →",
                    color = TrustColors.ErrorDark,
                    fontSize = 12.sp,
                    textDecoration = TextDecoration.Underline,
                    modifier = Modifier.clickable {
                        uriHandler.openUri("https://github.com/CIRISAI/CIRISVerify")
                    }
                )
            }
        }
        return
    }

    // CIRISVerify loaded - show status
    val status = verifyStatus!!

    Surface(
        shape = RoundedCornerShape(12.dp),
        color = TrustColors.EmeraldLight,
        modifier = modifier
            .fillMaxWidth()
            .border(1.dp, TrustColors.EmeraldBorder, RoundedCornerShape(12.dp))
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            // Header row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = "🛡",
                        fontSize = 18.sp
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(
                        text = "Trust & Security",
                        color = TrustColors.EmeraldDark,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
                status.version?.let { version ->
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = TrustColors.EmeraldMuted
                    ) {
                        Text(
                            text = "v$version",
                            color = TrustColors.EmeraldDark,
                            fontSize = 11.sp,
                            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Status grid
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Hardware column
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Hardware",
                        color = TrustColors.EmeraldText,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Medium
                    )
                    Text(
                        text = status.hardwareType?.replace("_", " ") ?: "Unknown",
                        color = TrustColors.EmeraldDark,
                        fontSize = 13.sp
                    )
                }

                // Key status column
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Key Status",
                        color = TrustColors.EmeraldText,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Medium
                    )
                    val (keyLabel, keyColor) = getKeyStatusLabel(status.keyStatus)
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = keyColor.copy(alpha = 0.2f)
                    ) {
                        Text(
                            text = keyLabel,
                            color = keyColor,
                            fontSize = 11.sp,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                // Attestation column
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Attestation",
                        color = TrustColors.EmeraldText,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Medium
                    )
                    val (attestLabel, attestColor) = getAttestationLabel(status.attestationStatus)
                    Surface(
                        shape = RoundedCornerShape(4.dp),
                        color = attestColor.copy(alpha = 0.2f)
                    ) {
                        Text(
                            text = attestLabel,
                            color = attestColor,
                            fontSize = 11.sp,
                            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                        )
                    }
                }

                // Key ID column (if present)
                status.keyId?.let { keyId ->
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Key ID",
                            color = TrustColors.EmeraldText,
                            fontSize = 11.sp,
                            fontWeight = FontWeight.Medium
                        )
                        Text(
                            text = if (keyId.length > 12) "${keyId.take(6)}...${keyId.takeLast(4)}" else keyId,
                            color = TrustColors.EmeraldDark,
                            fontSize = 11.sp,
                            fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace
                        )
                    }
                }
            }

            // Disclaimer
            Spacer(modifier = Modifier.height(12.dp))
            Surface(
                shape = RoundedCornerShape(4.dp),
                color = TrustColors.EmeraldMuted.copy(alpha = 0.5f),
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(
                    text = "CIRISVerify provides cryptographic attestation of agent identity. This enables participation in the Coherence Ratchet and CIRIS Scoring.",
                    color = TrustColors.EmeraldText,
                    fontSize = 11.sp,
                    lineHeight = 15.sp,
                    modifier = Modifier.padding(8.dp)
                )
            }

            // Links
            Spacer(modifier = Modifier.height(12.dp))
            HorizontalDivider(color = TrustColors.EmeraldBorder.copy(alpha = 0.5f))
            Spacer(modifier = Modifier.height(8.dp))

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(
                    text = "Coherence Ratchet",
                    color = TrustColors.EmeraldText,
                    fontSize = 11.sp,
                    modifier = Modifier.clickable {
                        uriHandler.openUri("https://ciris.ai/coherence-ratchet")
                    }
                )
                Text("·", color = TrustColors.EmeraldText, fontSize = 11.sp)
                Text(
                    text = "CIRIS Scoring",
                    color = TrustColors.EmeraldText,
                    fontSize = 11.sp,
                    modifier = Modifier.clickable {
                        uriHandler.openUri("https://ciris.ai/ciris-scoring")
                    }
                )
                Text("·", color = TrustColors.EmeraldText, fontSize = 11.sp)
                Text(
                    text = "CIRISVerify",
                    color = TrustColors.EmeraldText,
                    fontSize = 11.sp,
                    modifier = Modifier.clickable {
                        uriHandler.openUri("https://github.com/CIRISAI/CIRISVerify")
                    }
                )
            }
        }
    }
}

private fun getKeyStatusLabel(keyStatus: String): Pair<String, Color> {
    return when (keyStatus) {
        "portal_active" -> "Portal Key Active" to Color(0xFF047857)
        "portal_pending" -> "Portal Key Pending" to Color(0xFFD97706)
        "ephemeral" -> "Ephemeral Key" to Color(0xFF1D4ED8)
        else -> "No Key" to Color(0xFF6B7280)
    }
}

private fun getAttestationLabel(attestation: String): Pair<String, Color> {
    return when (attestation) {
        "verified" -> "Verified" to Color(0xFF047857)
        "pending" -> "Pending" to Color(0xFFD97706)
        "failed" -> "Failed" to Color(0xFFDC2626)
        else -> "Not Attempted" to Color(0xFF6B7280)
    }
}

@Composable
private fun AdapterToggleItem(
    name: String,
    description: String,
    isEnabled: Boolean,
    isRequired: Boolean,
    requiresConfig: Boolean,
    configFields: List<String> = emptyList(),
    onToggle: (Boolean) -> Unit
) {
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = if (isEnabled) SetupColors.SuccessLight else SetupColors.GrayLight,
        modifier = Modifier.fillMaxWidth()
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
                                text = "Required",
                                color = SetupColors.Primary,
                                fontSize = 10.sp,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                            )
                        }
                    }
                    if (requiresConfig && isEnabled) {
                        Spacer(modifier = Modifier.width(8.dp))
                        Surface(
                            shape = RoundedCornerShape(4.dp),
                            color = Color(0xFFFFF3CD)
                        ) {
                            Text(
                                text = "Needs Config",
                                color = Color(0xFF856404),
                                fontSize = 10.sp,
                                modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                            )
                        }
                    }
                }
                Text(
                    text = description,
                    color = SetupColors.TextSecondary,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(top = 2.dp)
                )
                if (requiresConfig && configFields.isNotEmpty() && isEnabled) {
                    Text(
                        text = "Required: ${configFields.joinToString(", ")}",
                        color = Color(0xFF856404),
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
            text = "Confirm Setup",
            color = SetupColors.TextPrimary,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 8.dp)
        )

        Text(
            text = "Review your configuration and complete setup.",
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
                        text = "${getOAuthProviderName()} Account Connected",
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
                        text = "You'll sign in to CIRIS using your ${getOAuthProviderName()} account. A secure random password will be generated for the admin account (you won't need to use it).",
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
                    text = "Setup Summary",
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
                text = "Your Account",
                color = SetupColors.TextPrimary,
                fontSize = 16.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(bottom = 8.dp)
            )

            Text(
                text = "Create your personal account to access CIRIS.",
                color = SetupColors.TextSecondary,
                fontSize = 14.sp,
                modifier = Modifier.padding(bottom = 16.dp)
            )

            OutlinedTextField(
                value = state.username,
                onValueChange = { viewModel.setUsername(it) },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("Username") },
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = SetupColors.Primary,
                    unfocusedBorderColor = SetupColors.GrayLight
                ),
                singleLine = true
            )

            Spacer(modifier = Modifier.height(12.dp))

            var showPassword by remember { mutableStateOf(false) }

            OutlinedTextField(
                value = state.userPassword,
                onValueChange = { viewModel.setUserPassword(it) },
                modifier = Modifier.fillMaxWidth(),
                label = { Text("Password") },
                visualTransformation = if (showPassword) VisualTransformation.None else PasswordVisualTransformation(),
                trailingIcon = {
                    TextButton(onClick = { showPassword = !showPassword }) {
                        Text(if (showPassword) "Hide" else "Show", color = SetupColors.Primary)
                    }
                },
                colors = OutlinedTextFieldDefaults.colors(
                    focusedBorderColor = SetupColors.Primary,
                    unfocusedBorderColor = SetupColors.GrayLight
                ),
                singleLine = true
            )

            if (state.userPassword.isNotEmpty() && state.userPassword.length < 8) {
                Text(
                    text = "Password must be at least 8 characters",
                    color = Color(0xFFDC2626),
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
            text = "Setup Complete!",
            color = SetupColors.TextPrimary,
            fontSize = 24.sp,
            fontWeight = FontWeight.Bold,
            textAlign = TextAlign.Center
        )

        Spacer(modifier = Modifier.height(16.dp))

        Text(
            text = "Your CIRIS agent is ready to go.",
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
    onNext: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    Column(modifier = modifier) {
        // Show validation error if present
        if (validationError != null && !canProceed) {
            Surface(
                color = Color(0xFFFEE2E2),
                shape = RoundedCornerShape(8.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(bottom = 12.dp)
            ) {
                Text(
                    text = validationError,
                    color = Color(0xFFDC2626),
                    fontSize = 14.sp,
                    modifier = Modifier.padding(12.dp)
                )
            }
        }

        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Back button
            if (currentStep != SetupStep.WELCOME && currentStep != SetupStep.COMPLETE) {
                OutlinedButton(
                    onClick = onBack,
                    enabled = !isSubmitting,
                    modifier = Modifier.weight(1f),
                    colors = ButtonDefaults.outlinedButtonColors(
                        contentColor = SetupColors.TextSecondary
                    )
                ) {
                    Text("Back")
                }
            }

            // Next/Finish button
            if (currentStep != SetupStep.COMPLETE) {
                Button(
                    onClick = onNext,
                    enabled = canProceed && !isSubmitting,
                    modifier = Modifier.weight(if (currentStep == SetupStep.WELCOME) 2f else 1f),
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
                        Text(
                            when (currentStep) {
                                SetupStep.WELCOME -> "Continue →"
                                SetupStep.ACCOUNT_AND_CONFIRMATION -> "Finish Setup"
                                else -> "Next"
                            }
                        )
                    }
                }
            }
        }
    }
}
