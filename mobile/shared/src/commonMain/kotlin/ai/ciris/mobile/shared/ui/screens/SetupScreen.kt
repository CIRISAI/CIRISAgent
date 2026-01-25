package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.SetupMode
import ai.ciris.mobile.shared.viewmodels.SetupStep
import ai.ciris.mobile.shared.viewmodels.SetupFormState
import ai.ciris.mobile.shared.viewmodels.SetupViewModel
import androidx.compose.animation.AnimatedVisibility
import kotlinx.coroutines.launch
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextAlign
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

    Surface(
        modifier = modifier.fillMaxSize(),
        color = SetupColors.Background
    ) {
        Column(modifier = Modifier.fillMaxSize()) {
            // Step indicators at top
            StepIndicators(
                currentStep = state.currentStep,
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
                        isGoogleAuth = state.isGoogleAuth
                    )
                    SetupStep.LLM_CONFIGURATION -> LlmConfigurationStep(viewModel, state)
                    SetupStep.ACCOUNT_AND_CONFIRMATION -> AccountConfirmationStep(viewModel, state)
                    SetupStep.COMPLETE -> CompleteStep(onSetupComplete)
                }
            }

            // Navigation buttons
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
                                val result = viewModel.completeSetup { request ->
                                    // Make API call to /v1/setup/complete
                                    println("[SetupScreen] Calling apiClient.completeSetup with provider=${request.llm_provider}")
                                    apiClient.completeSetup(request)
                                }
                                println("[SetupScreen] completeSetup returned: success=${result.success}, error=${result.error}")
                                if (result.success) {
                                    println("[SetupScreen] Setup successful - advancing to next step")
                                    viewModel.nextStep()
                                } else {
                                    println("[SetupScreen] ERROR: Setup failed: ${result.error}")
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
                    .padding(24.dp)
            )
        }
    }
}

// ========== Step Indicators ==========
@Composable
private fun StepIndicators(
    currentStep: SetupStep,
    modifier: Modifier = Modifier
) {
    val steps = listOf(
        SetupStep.WELCOME to "1",
        SetupStep.LLM_CONFIGURATION to "2",
        SetupStep.ACCOUNT_AND_CONFIRMATION to "3"
    )

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
    isGoogleAuth: Boolean,
    modifier: Modifier = Modifier
) {
    var detailsExpanded by remember { mutableStateOf(false) }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(24.dp)
            .verticalScroll(rememberScrollState()),
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
                        text = "Since you signed in with Google, CIRIS can start working right away. Free access is limited and includes web search via privacy-protecting providers (Exa, Brave).",
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
                        text = "Your Google account includes limited free AI access with web search (Exa, Brave). Privacy-protected and never used for training.",
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
            val providers = listOf("OpenAI", "Anthropic", "Azure OpenAI", "LocalAI")

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
                        text = "Google Account Connected",
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
                        text = "You'll sign in to CIRIS using your Google account. A secure random password will be generated for the admin account (you won't need to use it).",
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
                    value = if (state.useCirisProxy()) "Free AI Access (via Google)" else state.llmProvider
                )
                SummaryRow(label = "Assistant", value = "Ally")
                if (state.isGoogleAuth) {
                    SummaryRow(label = "Sign-in", value = "Google Account")
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
