package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.CIRISBuild
import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.localization.localizedString
import androidx.compose.foundation.layout.imePadding
import ai.ciris.mobile.shared.models.ConsentDisclosure
import ai.ciris.mobile.shared.models.ConsentGrantDisclosure
import ai.ciris.mobile.shared.models.DecliningDisclosure
import ai.ciris.mobile.shared.models.DisclosureString
import ai.ciris.mobile.shared.models.Platform
import ai.ciris.mobile.shared.models.SetupMode
import ai.ciris.mobile.shared.models.safety.AgeBand
import ai.ciris.mobile.shared.models.filterAdaptersForPlatform
import ai.ciris.mobile.shared.models.forAdapter
import ai.ciris.mobile.shared.ui.components.setup.AdapterToolDisclosure
import ai.ciris.mobile.shared.ui.components.setup.ALWAYS_ON_DISCLOSURE_ID
import ai.ciris.mobile.shared.ui.components.setup.AlwaysOnToolDisclosure
import ai.ciris.mobile.shared.platform.DirectoryPickerDialog
import ai.ciris.mobile.shared.platform.LocalInferenceCapability
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
import ai.ciris.mobile.shared.ui.components.AnnounceDecisionCard
import ai.ciris.mobile.shared.ui.components.LocalLlmServerDiscovery
import ai.ciris.mobile.shared.ui.components.rememberLocalLlmDiscoveryState
import ai.ciris.mobile.shared.viewmodels.DeviceAuthStatus
import ai.ciris.mobile.shared.viewmodels.FederationIdentitySetupState
import ai.ciris.mobile.shared.viewmodels.LlmValidationResult
import ai.ciris.mobile.shared.viewmodels.ModelInfo
import ai.ciris.mobile.shared.viewmodels.SetupStep
import ai.ciris.mobile.shared.viewmodels.isFinalSetupStep
import ai.ciris.mobile.shared.viewmodels.SetupFormState
import ai.ciris.mobile.shared.viewmodels.SetupViewModel
import ai.ciris.mobile.shared.viewmodels.SUPPORTED_LANGUAGES
import ai.ciris.mobile.shared.viewmodels.LocationGranularity
import androidx.compose.animation.AnimatedVisibility
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
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
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Star
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
import androidx.compose.ui.platform.LocalUriHandler
import ai.ciris.mobile.shared.platform.openUrlInBrowser
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ai.ciris.mobile.shared.ui.theme.ColorTheme
import ai.ciris.mobile.shared.ui.theme.SemanticColors
import ai.ciris.mobile.shared.ui.components.setup.SetupCollapsibleSection
import ai.ciris.mobile.shared.ui.components.LanguageSelector
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.material.icons.filled.Settings
import ai.ciris.mobile.shared.ui.icons.*
import ai.ciris.mobile.shared.ui.components.CIRISIcons

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

    // Warning (amber) - derived from SemanticColors light mode. Used by the
    // under-18 stewardship panel (protective, attention-drawing, but kind).
    val WarningLight = semantic.surfaceWarning
    val WarningDark = semantic.onWarning
    val WarningText = semantic.warning

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
    onBackToLogin: (() -> Unit)? = null,  // Optional callback to return to login screen
    // The one-time ownership CLAIM PIN / NodeCode captured from the LOCAL node's
    // boot banner (PythonRuntime.localClaimPin / .localNodeCode). Used on setup
    // COMPLETE to self-claim ownership of the local node for the just-created user.
    // SUSPEND providers so the consumer can AWAIT the PIN (the banner can land
    // just after COMPLETE fires) instead of snapshotting a possibly-null value.
    // Default null providers → claim is skipped with an honest error (no local
    // node launched on this platform, so nothing to capture).
    claimPinProvider: suspend () -> String? = { null },
    nodeCodeProvider: suspend () -> String? = { null },
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
                "input_password_confirm" -> {
                    if (request.clearFirst) {
                        viewModel.setUserPasswordConfirm(request.text)
                    } else {
                        viewModel.setUserPasswordConfirm(state.userPasswordConfirm + request.text)
                    }
                    TestAutomation.clearTextInputRequest()
                }
                // REQUIRED federation-identity name (FEDERATION_IDENTITY_SETUP).
                "input_fedid_label" -> {
                    if (request.clearFirst) {
                        viewModel.setFederationLabel(request.text)
                    } else {
                        viewModel.setFederationLabel(state.federationIdentity.label + request.text)
                    }
                    TestAutomation.clearTextInputRequest()
                }
                // OPTIONAL friendly per-device name (e.g. "Mac mini") — distinct
                // from the fed-ID label. Empty is allowed.
                "input_device_name" -> {
                    if (request.clearFirst) {
                        viewModel.setDeviceName(request.text)
                    } else {
                        viewModel.setDeviceName(state.deviceName + request.text)
                    }
                    TestAutomation.clearTextInputRequest()
                }
                // Both the advanced-setup tags (input_*) and the Quick Setup
                // tags (quick_input_*) route here: Android text input is
                // dispatched by resourceId through this handler, so a field
                // whose tag is absent is silently dropped (the test server
                // still returns success). Keep these in sync with every LLM
                // input field rendered in either flow.
                "input_api_key", "quick_input_api_key" -> {
                    if (request.clearFirst) {
                        viewModel.setLlmApiKey(request.text)
                    } else {
                        viewModel.setLlmApiKey(state.llmApiKey + request.text)
                    }
                    TestAutomation.clearTextInputRequest()
                }
                "input_llm_model_text", "quick_input_llm_model_text" -> {
                    if (request.clearFirst) {
                        viewModel.setLlmModel(request.text)
                    } else {
                        viewModel.setLlmModel(state.llmModel + request.text)
                    }
                    TestAutomation.clearTextInputRequest()
                }
                "input_llm_base_url", "quick_input_llm_base_url" -> {
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
        Column(modifier = Modifier.fillMaxSize().imePadding()) {
            // Step indicators at top
            StepIndicators(
                currentStep = state.currentStep,
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(vertical = 16.dp, horizontal = 24.dp)
            )

            // Step content — shrinks when keyboard appears, buttons stay visible
            Box(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
            ) {
                when (state.currentStep) {
                    SetupStep.YOU -> YouStep(viewModel, state)
                    SetupStep.JOIN_FEDERATION -> JoinFederationStep(viewModel, state, apiClient)
                    SetupStep.AI -> AiStep(viewModel, state, apiClient)
                    SetupStep.COMPLETE -> CompleteStep(onSetupComplete, state.ownershipClaim)
                }
            }

            // Error display for submission failures
            state.submissionError?.let { error ->
                val isAlreadyConfigured = error.contains("already", ignoreCase = true) ||
                                          error.contains("configured", ignoreCase = true) ||
                                          error.contains("completed", ignoreCase = true)
                // Backend code for the "CIRISVerify FFI genuinely unusable on
                // this device" terminal state. (Renamed from
                // UNSUPPORTED_PLATFORM_CIRIS_VERIFY in release/2.9.5 — the old
                // name was misleading; the device's architecture is fine, the
                // signing capability is the thing that's broken.) We still
                // match the old token for backward compat with any agent that
                // hasn't shipped the rename yet.
                val isSigningUnavailable =
                    error.contains("CIRIS_VERIFY_SIGNING_UNAVAILABLE", ignoreCase = true) ||
                    error.contains("UNSUPPORTED_PLATFORM_CIRIS_VERIFY", ignoreCase = true)

                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .background(
                            when {
                                isAlreadyConfigured -> semantic.surfaceWarning
                                isSigningUnavailable -> SetupColors.ErrorLight
                                else -> SetupColors.ErrorLight
                            }
                        )
                        .padding(16.dp)
                ) {
                    Text(
                        text = when {
                            isAlreadyConfigured -> localizedString("mobile.setup_already_complete")
                            isSigningUnavailable -> localizedString("mobile.setup_error_signing_unavailable_title")
                            else -> localizedString("mobile.setup_error")
                        },
                        fontWeight = FontWeight.Bold,
                        color = if (isAlreadyConfigured) semantic.onWarning else SetupColors.ErrorDark
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = if (isSigningUnavailable) {
                            localizedString("mobile.setup_error_signing_unavailable_body")
                        } else {
                            error
                        },
                        fontSize = 14.sp,
                        color = if (isAlreadyConfigured) semantic.onWarning else SetupColors.ErrorDark
                    )
                    if (isSigningUnavailable) {
                        // Always render the raw backend message verbatim under
                        // a localized "Technical details" header — that's the
                        // only place engineers can read the underlying
                        // exception class + message that initialize() captured
                        // in _last_init_error. Critical for diagnosis.
                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = "${localizedString("mobile.setup_error_technical_details")}: $error",
                            fontSize = 12.sp,
                            color = SetupColors.ErrorDark.copy(alpha = 0.7f)
                        )
                    }
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
                onNext = {
                    PlatformLogger.i(TAG, " onNext clicked, currentStep=${state.currentStep}, canProceed=${state.canProceedFromCurrentStep()}")
                    // YOU → JOIN_FEDERATION → [AI] → COMPLETE. The final step is
                    // AI on the agent build and JOIN_FEDERATION on the node
                    // client; on COMPLETE we ALSO self-claim ownership of the
                    // local node for the just-created user.
                    val isFinalStep = isFinalSetupStep(state.currentStep, CIRISBuild.HAS_AGENT)

                    if (isFinalStep && !CIRISBuild.HAS_AGENT) {
                        // NODE CLIENT final step: there is NO agent /v1/setup/complete
                        // on ciris-server. The fed-ID was already minted (fed-ID step,
                        // first-run); the automated LAST step is the ownership
                        // self-claim. Then advance to COMPLETE, which renders the claim
                        // result (in-progress / owned / retry). Non-blocking — a
                        // missing PIN or failed claim surfaces in the UI, never traps.
                        PlatformLogger.i(TAG, " Final step (node client) - self-claiming local node ownership")
                        viewModel.claimLocalNodeOwnership(
                            claimPinProvider = claimPinProvider,
                            nodeCodeProvider = nodeCodeProvider,
                        )
                        viewModel.nextStep()
                    } else if (isFinalStep) {
                        // AGENT BUILD: CLAIM THEN COMPLETE. The self-claim
                        // (POST /v1/setup/claim-remote) needs a LIVE :4243 bearer
                        // session, and completeSetup restarts the runtime — which
                        // INVALIDATES that session. So we must claim FIRST (while
                        // the setup session is still valid) and only THEN write the
                        // config + reload. Doing complete-first left the claim to
                        // hit a dead session → 401 → node stays unclaimed → the
                        // first-run nav loop.
                        PlatformLogger.i(TAG, " Final step - CLAIM then COMPLETE")
                        coroutineScope.launch {
                            try {
                                // 1) Self-claim ownership on the still-valid session.
                                PlatformLogger.i(TAG, " Self-claiming local node ownership (pre-complete)")
                                viewModel.claimLocalNodeOwnership(
                                    claimPinProvider = claimPinProvider,
                                    nodeCodeProvider = nodeCodeProvider,
                                )
                                // Await the claim SETTLING (E9). Since the settle fix,
                                // inProgress stays true through the ENTIRE post-claim
                                // block (owner login → setAgeSelf → announce), so this
                                // await is the real E9 ≺ E10 gate: completeSetup's
                                // runtime restart cannot race those :4243 calls.
                                // Bounded so a stuck claim never traps the wizard.
                                val settled = kotlinx.coroutines.withTimeoutOrNull(90_000) {
                                    viewModel.state.first { !it.ownershipClaim.inProgress }
                                }
                                if (settled == null) {
                                    PlatformLogger.w(TAG, "[ORDER] settle_await TIMEOUT (90s) — proceeding; conformance will flag")
                                }
                                val claimed = viewModel.state.value.ownershipClaim.claimed
                                PlatformLogger.i(TAG, "[ORDER] settle_await released claimed=$claimed — advancing then completing")

                                // 2) Advance to COMPLETE NOW — the node is owned,
                                // so leave the Setup screen immediately (good UX,
                                // and keeps the wizard under the harness's
                                // COMPLETE-wait). completeSetup's config-write +
                                // runtime reload then runs while COMPLETE renders;
                                // the reload bounces to login, where — now that
                                // the node is CLAIMED — first-run is false and the
                                // owner signs in normally (no more nav loop).
                                viewModel.nextStep()

                                // 3) Complete setup (writes .env + reloads). Runs
                                // AFTER the claim (session was valid for the claim)
                                // and after advancing (so it never gates leaving
                                // Setup). Best-effort — the COMPLETE screen surfaces
                                // any error.
                                PlatformLogger.i(TAG, "[ORDER] complete_setup begin (post-settle)")
                                val result = withContext(Dispatchers.Default) {
                                    viewModel.completeSetup { request ->
                                        PlatformLogger.i(TAG, " Calling apiClient.completeSetup with provider=${request.llm_provider}")
                                        apiClient.completeSetup(request)
                                    }
                                }
                                PlatformLogger.i(TAG, " completeSetup returned: success=${result.success}, error=${result.error}")
                            } catch (e: Exception) {
                                PlatformLogger.i(TAG, " EXCEPTION in claim/completeSetup: ${e.message}")
                                e.printStackTrace()
                            }
                        }
                    } else {
                        // AUTO-MINT ON NEXT: leaving the fed-ID step without an
                        // identity? The proceed-gate allows advancing on a valid
                        // *typed* label alone (so "Create fed-ID" is optional to
                        // tap), but the later self-claim REQUIRES a minted fed-ID.
                        // So if the user typed a name and didn't tap Create, mint it
                        // now from that name as they advance. The mint runs async and
                        // surfaces on this step; the claim also mints-if-absent as a
                        // backstop. An association-in-progress is left alone.
                        val fed = state.federationIdentity
                        if (state.currentStep == SetupStep.YOU &&
                            !fed.minted && !fed.admitted && !fed.inProgress &&
                            fed.isLabelValid()
                        ) {
                            PlatformLogger.i(TAG, " fed-ID not minted but name is set — auto-minting on Next")
                            viewModel.runFederationIdentitySetup()
                        }
                        PlatformLogger.i(TAG, " Not final step - calling viewModel.nextStep()")
                        viewModel.nextStep()
                    }
                },
                onBack = { viewModel.previousStep() },
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
    modifier: Modifier = Modifier
) {
    // Three screens: You → Join the federation → AI. The node client has no
    // brain to configure, so it shows two.
    val steps = if (CIRISBuild.HAS_AGENT) {
        listOf(SetupStep.YOU to "1", SetupStep.JOIN_FEDERATION to "2", SetupStep.AI to "3")
    } else {
        listOf(SetupStep.YOU to "1", SetupStep.JOIN_FEDERATION to "2")
    }
    val currentFlowIndex = steps.indexOfFirst { it.first == currentStep }

    Row(
        modifier = modifier.testable("setup_step_indicators"),
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically
    ) {
        steps.forEachIndexed { index, (step, number) ->
            val isActive = if (currentFlowIndex >= 0) currentFlowIndex >= index else currentStep >= step
            val isComplete = if (currentFlowIndex >= 0) currentFlowIndex > index else currentStep > step
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
                            color = if (isComplete) SetupColors.Primary else SetupColors.GrayLight
                        )
                )
            }
        }
    }
}



/**
 * Localized string with an English fallback for keys not yet in the 29-locale
 * manifest. [localizedString] returns the KEY itself when a key is absent (not
 * ""), so treat "blank OR equal to the key" as missing and render [fallback].
 * Same pattern as `AnnounceDecisionCard.l10nOr` — it lets new UI ship before the
 * catalogue catches up, without machine-translating 29 locales badly.
 */
@Composable
private fun l10nOr(key: String, fallback: String): String {
    val v = localizedString(key)
    return if (v.isBlank() || v == key) fallback else v
}

// ========== Screen 1 — You ==========

/**
 * **Who are you?** One screen, one question.
 *
 * WELCOME, ACCOUNT_AND_CONFIRMATION, FEDERATION_IDENTITY_SETUP and AGE_RANGE all
 * asked it, in four vocabularies, on four consecutive screens. WELCOME collected
 * nothing at all — 169 lines with no interactive element — and its "what CIRIS
 * is" paragraph is this screen's header. The rest are sections of one form.
 *
 * The fed-ID mint keeps its OWN button inside its card: it is an apex act with a
 * hardware ceremony (TPM / Secure Enclave / StrongBox), and folding it into Next
 * would strand the user mid-screen with no legible cause when the ceremony
 * fails.
 */
@Composable
private fun YouStep(
    viewModel: SetupViewModel,
    state: SetupFormState,
    modifier: Modifier = Modifier
) {
    // ONE scroll for the whole screen — the sections below deliberately do not
    // scroll themselves (nesting two vertical scrolls is a Compose crash).
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(24.dp)
            .verticalScroll(rememberScrollState())
    ) {
        Text(
            text = localizedString("setup.welcome_title"),
            color = SetupColors.TextPrimary,
            fontSize = 24.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 8.dp)
        )
        Text(
            text = if (CIRISBuild.HAS_AGENT) {
                localizedString("setup.welcome_desc")
            } else {
                localizedString("mobile.setup_welcome_desc_node")
            },
            color = SetupColors.TextSecondary,
            fontSize = 14.sp,
            lineHeight = 20.sp,
            modifier = Modifier.padding(bottom = 20.dp)
        )

        FederationIdentitySection(viewModel = viewModel, state = state)
        Spacer(modifier = Modifier.height(24.dp))
        AccountSection(viewModel = viewModel, state = state)
        Spacer(modifier = Modifier.height(24.dp))
        AgeRangeSection(viewModel = viewModel, state = state)
    }
}

// ========== Screen 2 — Join the federation ==========

/**
 * **Do you join?** The consent decision, RENDERED from
 * `ciris_server.consent_disclosure()`.
 *
 * Not composed here, deliberately: the export exists so the wizard shows the
 * substrate's own words, because "a wizard that writes its own version of that
 * paragraph drifts from the substrate the moment either changes". Every string
 * arrives with a catalogue key, so [disclosureText] renders the user's locale
 * and falls back to the substrate's wording rather than to a raw key.
 *
 * Announce is stated as the FLOOR for service, not offered as a preference. The
 * two grants are separate toggles on opposite edges — sending traces and being
 * scored — and location leads with what it is FOR, because "presented first as a
 * restriction mechanism it reads as a pure cost, and an operator declines it".
 */
@Composable
private fun JoinFederationStep(
    viewModel: SetupViewModel,
    state: SetupFormState,
    apiClient: CIRISApiClient,
    modifier: Modifier = Modifier
) {
    var disclosure by remember { mutableStateOf<ConsentDisclosure?>(null) }
    var loadError by remember { mutableStateOf<String?>(null) }
    var expanded by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        try {
            disclosure = apiClient.getConsentDisclosure()
        } catch (e: Exception) {
            PlatformLogger.w(TAG, "consent disclosure unavailable: ${e.message}")
            loadError = e.message ?: "unavailable"
        }
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(24.dp)
            .verticalScroll(rememberScrollState())
    ) {
        val d = disclosure
        if (d == null) {
            // No hand-written substitute. Rendering our own version of this copy
            // is the exact drift the disclosure export prevents, so an
            // unreachable node shows why, not an invented paragraph.
            Text(
                text = l10nOr("setup.federation_title", "Join the federation"),
                color = SetupColors.TextPrimary,
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
                modifier = Modifier.padding(bottom = 12.dp)
            )
            Text(
                text = loadError ?: l10nOr("mobile.status_loading", "Loading…"),
                color = if (loadError != null) SetupColors.ErrorText else SetupColors.TextSecondary,
                fontSize = 14.sp,
            )
            return@Column
        }

        // ── The primary action ──────────────────────────────────────────────
        Text(
            text = disclosureText(d.primaryAction),
            color = SetupColors.TextPrimary,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 12.dp)
        )

        // ── Announce: a REQUIREMENT, stated as one ──────────────────────────
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = SetupColors.InfoLight,
            modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = disclosureText(d.announceRequirement),
                    color = SetupColors.InfoText,
                    fontSize = 13.sp,
                    lineHeight = 19.sp,
                )
                Spacer(modifier = Modifier.height(12.dp))
                ConsentToggleRow(
                    label = localizedString("mobile.announce_decision_toggle_label"),
                    checked = state.announceOwnership,
                    onCheckedChange = { viewModel.setAnnounceOwnership(it) },
                    testTag = "toggle_announce_ownership",
                )
            }
        }

        TextButton(
            onClick = { expanded = !expanded },
            modifier = Modifier.testableClickable("btn_consent_details") { expanded = !expanded }
        ) {
            Text(
                text = if (expanded) "▾ " + l10nOr("mobile.setup_hide_details", "Hide details")
                       else "▸ " + l10nOr("mobile.setup_show_details", "Show details"),
                color = SetupColors.Primary,
                fontSize = 14.sp,
            )
        }

        // ── The two grants: separate consents on opposite edges ─────────────
        d.grant("replication")?.let { g ->
            ConsentGrantRow(
                grant = g,
                checked = state.accordMetricsConsent,
                onCheckedChange = { viewModel.setAccordMetricsConsent(it) },
                testTag = "toggle_trace_opt_in",
                showDetail = expanded,
                declining = null,
            )
        }
        d.grant("analyze")?.let { g ->
            ConsentGrantRow(
                grant = g,
                checked = state.traceAnalyze,
                onCheckedChange = { viewModel.setTraceAnalyze(it) },
                testTag = "toggle_trace_analyze",
                showDetail = expanded,
                declining = d.decliningAnalyze,
            )
        }

        if (expanded) {
            Text(
                text = disclosureText(d.independent),
                color = SetupColors.TextSecondary,
                fontSize = 12.sp,
                lineHeight = 17.sp,
                modifier = Modifier.padding(top = 4.dp, bottom = 12.dp)
            )
        }

        // ── Location: purpose FIRST, then the bound ─────────────────────────
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = SetupColors.GrayLight,
            modifier = Modifier.fillMaxWidth().padding(top = 8.dp)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                ConsentToggleRow(
                    label = disclosureText(d.location.title),
                    checked = state.shareLocationInTraces,
                    onCheckedChange = { viewModel.setShareLocationInTraces(it) },
                    testTag = "toggle_share_location",
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = disclosureText(d.location.purpose),
                    color = SetupColors.TextSecondary,
                    fontSize = 13.sp,
                    lineHeight = 19.sp,
                )
                if (expanded) {
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = disclosureText(d.location.permits),
                        color = SetupColors.TextSecondary,
                        fontSize = 12.sp,
                        lineHeight = 17.sp,
                    )
                    d.location.declining.costs.forEach { cost ->
                        Text(
                            text = "• ${disclosureText(cost)}",
                            color = SetupColors.TextSecondary,
                            fontSize = 12.sp,
                            lineHeight = 17.sp,
                            modifier = Modifier.padding(top = 4.dp)
                        )
                    }
                }
            }
        }
    }
}

/**
 * Render a substrate string in the user's language.
 *
 * [DisclosureString.id] is a dot-notation key into the 29-locale catalogue and
 * [DisclosureString.text] is the substrate's own wording. `localizedString`
 * returns the KEY when it has no entry, so treat that as "missing" and fall back
 * to the substrate — a locale that has not caught up degrades to correct English
 * rather than to a raw identifier.
 */
@Composable
private fun disclosureText(s: DisclosureString): String {
    val localized = localizedString(s.id)
    return if (localized.isBlank() || localized == s.id) s.text else localized
}

@Composable
private fun ConsentToggleRow(
    label: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    testTag: String,
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = label,
            color = SetupColors.TextPrimary,
            fontSize = 15.sp,
            fontWeight = FontWeight.SemiBold,
            modifier = Modifier.weight(1f),
        )
        Switch(
            checked = checked,
            onCheckedChange = onCheckedChange,
            modifier = Modifier.testableClickable(testTag) { onCheckedChange(!checked) },
        )
    }
}

/**
 * One consent grant. [declining] is rendered when the substrate says the grant
 * may be declined and names what declining costs — the operator is entitled to
 * both halves before answering.
 */
@Composable
private fun ConsentGrantRow(
    grant: ConsentGrantDisclosure,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit,
    testTag: String,
    showDetail: Boolean,
    declining: DecliningDisclosure?,
) {
    Column(modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp)) {
        ConsentToggleRow(
            label = disclosureText(grant.title),
            checked = checked,
            onCheckedChange = onCheckedChange,
            testTag = testTag,
        )
        Text(
            text = disclosureText(grant.permits),
            color = SetupColors.TextSecondary,
            fontSize = 13.sp,
            lineHeight = 19.sp,
            modifier = Modifier.padding(top = 4.dp)
        )
        if (showDetail && declining?.allowed == true) {
            declining.summary?.let {
                Text(
                    text = disclosureText(it),
                    color = SetupColors.TextSecondary,
                    fontSize = 12.sp,
                    lineHeight = 17.sp,
                    modifier = Modifier.padding(top = 6.dp)
                )
            }
            declining.costs.forEach { cost ->
                Text(
                    text = "• ${disclosureText(cost)}",
                    color = SetupColors.TextSecondary,
                    fontSize = 12.sp,
                    lineHeight = 17.sp,
                    modifier = Modifier.padding(top = 4.dp)
                )
            }
        }
    }
}

// ========== Screen 3 — AI ==========
/**
 * **What powers it?** Arrives pre-answered for almost everyone.
 *
 * The old default was `OpenAI` with an empty key: Next disabled, "API key is
 * required", and nothing signposting the way out — while three keyless paths
 * existed, two of them buried at positions 12 and 13 of a 15-item dropdown. So
 * the platform picks the default it can actually run: the CIRIS proxy where an
 * OAuth token is the credential, on-device inference where the hardware allows
 * it, and otherwise the keyless-first provider list.
 *
 * "Run without AI" is offered LAST and is never a default — defaulting it would
 * disable a working agent on capable hardware. It is also not a no-op: it writes
 * `CIRIS_SERVICES_DISABLED=true`, without which the next boot makes
 * `llm_service` critical and initialization aborts instead of degrading.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AiStep(
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

    // Platform default, applied ONCE and only while the provider is still the
    // untouched `OpenAI` — never overwrite a choice the user has made.
    //
    // The CIRIS proxy is deliberately NOT offered on desktop: it is gated on
    // `isGoogleAuth`, which desktop first-run never sets, and the OAuth ID token
    // IS the credential. Showing the card there would offer a login that cannot
    // authenticate.
    LaunchedEffect(localInference.isReady) {
        val untouched = state.llmProvider.equals("OpenAI", ignoreCase = true) &&
            state.llmApiKey.isEmpty() && !state.runWithoutAi
        if (untouched && !state.isGoogleAuth && localInference.isReady) {
            PlatformLogger.i(TAG, "[AI] defaulting to on-device inference (device is capable)")
            viewModel.setLlmProvider(SetupViewModel.LOCAL_ON_DEVICE_PROVIDER_ID)
        }
    }

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

        // ── Run without AI ───────────────────────────────────────────────────
        // An option, never a default. Selected, it writes
        // CIRIS_SERVICES_DISABLED=true; picking any provider clears it.
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = if (state.runWithoutAi) SetupColors.InfoLight else SetupColors.GrayLight,
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 16.dp)
                .testableClickable("toggle_run_without_ai") {
                    viewModel.setRunWithoutAi(!state.runWithoutAi)
                }
        ) {
            Row(
                modifier = Modifier.padding(16.dp),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = l10nOr("setup.llm_run_without_ai_title", "Run without AI"),
                        color = SetupColors.TextPrimary,
                        fontSize = 15.sp,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Text(
                        text = l10nOr(
                            "setup.llm_run_without_ai_desc",
                            "The node runs on its own — federation, consent and your own data all " +
                                "work. You can add an AI provider later from Settings.",
                        ),
                        color = SetupColors.TextSecondary,
                        fontSize = 13.sp,
                        lineHeight = 18.sp,
                        modifier = Modifier.padding(top = 4.dp)
                    )
                }
                Switch(
                    checked = state.runWithoutAi,
                    onCheckedChange = { viewModel.setRunWithoutAi(it) },
                )
            }
        }

        if (state.runWithoutAi) {
            // The rest of the screen configures a provider that will not be used.
            return@Column
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

        // BYOK configuration (shown when in BYOK mode or for non-Google users)
        if (state.setupMode == SetupMode.BYOK || !state.isGoogleAuth) {
            // Provider selection
            Text(
                text = localizedString("mobile.setup_provider"),
                color = SetupColors.TextPrimary,
                fontSize = 14.sp,
                fontWeight = FontWeight.Medium,
                modifier = Modifier.padding(bottom = 8.dp)
            )

            var providerExpanded by remember { mutableStateOf(false) }

            // Dynamic provider list from ViewModel - includes:
            // - Cloud/hosted providers (OpenAI, Anthropic, etc.)
            // - Discovered local servers (Ollama, llama.cpp, etc.)
            // - On-device Gemma 4 (when localInference.isReady or .isComingSoon)
            val providers = viewModel.availableProviders

            // Add on-device option if capable (mobile or desktop with sufficient resources)
            val showOnDeviceProvider = localInference.isReady || localInference.isComingSoon
            val onDeviceEntry = SetupViewModel.LOCAL_ON_DEVICE_DISPLAY_NAME

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

                    // Show on-device option if capable (includes DESKTOP_CAPABLE)
                    if (showOnDeviceProvider) {
                        val isStub = localInference.isComingSoon
                        // iOS-stub devices still advertise the option so
                        // users know it exists, but the click is disabled
                        // until a model bundle is installed.
                        DropdownMenuItem(
                            text = {
                                Column {
                                    Text(
                                        text = if (isStub) {
                                            "$onDeviceEntry — Coming Soon"
                                        } else {
                                            onDeviceEntry
                                        },
                                        color = if (isStub) SetupColors.TextSecondary else SetupColors.TextPrimary,
                                    )
                                    Text(
                                        text = localInference.reason,
                                        color = SetupColors.TextSecondary,
                                        fontSize = 11.sp,
                                    )
                                }
                            },
                            enabled = !isStub,
                            onClick = {
                                viewModel.selectLocalOnDeviceProvider()
                                providerExpanded = false
                            },
                            modifier = Modifier.testableClickable("menu_provider_mobile_local") {
                                if (!isStub) {
                                    viewModel.selectLocalOnDeviceProvider()
                                    providerExpanded = false
                                }
                            }
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(16.dp))

            // Local providers that need endpoint URL
            val isLocalProvider = state.llmProvider in listOf("local", "local_inference", "openai_compatible", "other")

            // Performance warning for local inference providers
            val isMobileLocalProvider = state.llmProvider == SetupViewModel.LOCAL_ON_DEVICE_PROVIDER_ID ||
                state.llmProvider == SetupViewModel.LOCAL_ON_DEVICE_DISPLAY_NAME
            if (state.llmProvider == "local_inference" || isMobileLocalProvider) {
                Surface(
                    shape = RoundedCornerShape(8.dp),
                    color = SetupColors.InfoLight.copy(alpha = 0.5f),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Row(
                        modifier = Modifier.padding(12.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(
                            imageVector = CIRISIcons.info,
                            contentDescription = null,
                            tint = SetupColors.Primary,
                            modifier = Modifier.size(20.dp)
                        )
                        Text(
                            text = localizedString("mobile.llm_local_inference_performance_warning"),
                            style = MaterialTheme.typography.bodySmall,
                            color = SetupColors.TextSecondary,
                            fontSize = 12.sp
                        )
                    }
                }
                Spacer(modifier = Modifier.height(12.dp))
            }

            // Local Inference Server Discovery UI
            if (state.llmProvider == "local_inference") {
                LocalLlmServerDiscovery(
                    state = discoveryState,
                    apiClient = apiClient,
                    localInferenceCapability = localInference,
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

            // API Key input: skip for local/keyless providers
            // - LocalAI (uses Ollama with no key)
            // - local, local_inference (discovered local servers)
            // - mobile_local (on-device Gemma 4)
            // Note: isMobileLocalProvider already defined above for performance warning
            val isKeylessProvider = state.llmProvider in listOf("local", "local_inference", "LocalAI")
            if (!isKeylessProvider && !isMobileLocalProvider) {
                val apiKeyLabel = if (state.llmProvider == "OpenAI Compatible") {
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
                                Icon(CIRISIcons.star, contentDescription = "Recommended", tint = SetupColors.Primary, modifier = Modifier.size(16.dp))
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
                                                        "[*] Best",
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
                    text = "[*] =" + localizedString("mobile.setup_configured"), // Using "Configured" as best match for "Recommended"
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
                        coroutineScope.launch(Dispatchers.Default) {
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
                enabled = !isTesting && (isLocalProvider || isMobileLocalProvider || state.llmApiKey.isNotEmpty()),
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


// ========== Federation Identity Step (Create your federation ID) ==========
//
// MINTS the founder's hardware-rooted USER federation identity by DRIVING this
// device's local ciris-server: POST /v1/self/identity. The local node does ALL
// the crypto (keygen + sealing + genesis-object signing) in its substrate,
// custodied by a YubiKey / TPM·SE / software seed; the app holds NO keys and
// signs nothing — it only POSTs the mint and surfaces the public result (the
// CIRIS-V2-… fedcode + key_id + hardware tier).
@Composable
private fun FederationIdentitySection(
    viewModel: SetupViewModel,
    state: SetupFormState,
    modifier: Modifier = Modifier
) {
    val fed = state.federationIdentity
    val clipboardManager = LocalClipboardManager.current
    var copied by remember { mutableStateOf(false) }

    // Probe the local node first: if it already holds an identity we don't offer
    // to mint a duplicate, we just report it. The app holds NO keys.
    LaunchedEffect(Unit) {
        viewModel.probeFederationIdentity()
    }

    // Reset the "Copied" pill shortly after a copy.
    LaunchedEffect(copied) {
        if (copied) {
            delay(1800)
            copied = false
        }
    }

    Column(modifier = modifier.fillMaxWidth()) {
        Text(
            text = localizedString("mobile.federation_create_title"),
            color = SetupColors.TextPrimary,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 8.dp)
        )
        Text(
            text = localizedString("mobile.federation_create_explainer"),
            color = SetupColors.TextSecondary,
            fontSize = 14.sp,
            modifier = Modifier.padding(bottom = 16.dp)
        )

        // Plain-language explanation of the whole identity flow (middle-school
        // English): what a federation ID is, why the name must be unique, that
        // it's created once + can be restored elsewhere as the same you, and that
        // the app holds no keys.
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = SetupColors.GrayLight,
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 16.dp)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                listOf(
                    "mobile.setup_fedid_explain_what",
                    "mobile.setup_fedid_explain_name",
                    "mobile.setup_fedid_explain_once",
                    "mobile.setup_fedid_explain_keys",
                ).forEachIndexed { index, key ->
                    Text(
                        text = "• ${localizedString(key)}",
                        color = SetupColors.TextSecondary,
                        fontSize = 13.sp,
                        lineHeight = 18.sp,
                        modifier = Modifier.padding(top = if (index == 0) 0.dp else 8.dp)
                    )
                }
            }
        }

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
                    Text(text = "🔑", fontSize = 20.sp, modifier = Modifier.padding(end = 8.dp))
                    Text(
                        text = localizedString("mobile.federation_create_card_title"),
                        color = SetupColors.InfoDark,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold
                    )
                }

                when {
                    // Show the result ONLY after a real USER fed-ID was minted or
                    // associated THIS session. (Do NOT treat "node reachable + HW
                    // available" as "you already have a fed-ID" — that conflated the
                    // node's steward key with the user's identity and skipped the mint.)
                    fed.minted || fed.admitted -> {
                        Text(
                            text = if (fed.minted) {
                                localizedString("mobile.federation_create_minted")
                            } else {
                                localizedString("mobile.federation_create_exists")
                            },
                            color = SetupColors.InfoDark,
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Medium,
                            modifier = Modifier.padding(bottom = 10.dp),
                        )

                        // The shareable fedcode — prominent, monospace, copyable.
                        fed.fedcode?.let { code ->
                            Text(
                                text = localizedString("mobile.federation_create_fedcode_label"),
                                color = SetupColors.InfoText,
                                fontSize = 11.sp,
                                fontWeight = FontWeight.Medium,
                            )
                            Surface(
                                shape = RoundedCornerShape(8.dp),
                                color = Color.White.copy(alpha = 0.6f),
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(top = 4.dp, bottom = 8.dp)
                            ) {
                                Text(
                                    text = code,
                                    color = SetupColors.InfoDark,
                                    fontSize = 13.sp,
                                    fontFamily = FontFamily.Monospace,
                                    modifier = Modifier.padding(10.dp),
                                )
                            }
                            Button(
                                onClick = {
                                    clipboardManager.setText(AnnotatedString(code))
                                    copied = true
                                },
                                modifier = Modifier.testableClickable("btn_federation_copy_fedcode") {
                                    clipboardManager.setText(AnnotatedString(code))
                                    copied = true
                                }
                            ) {
                                Text(
                                    if (copied) {
                                        localizedString("mobile.federation_create_copied")
                                    } else {
                                        localizedString("mobile.federation_create_copy")
                                    }
                                )
                            }
                        }

                        fed.identityKeyId?.let {
                            Text(
                                text = localizedString("mobile.federation_create_keyid", "key_id", it),
                                color = SetupColors.InfoText,
                                fontSize = 12.sp,
                                fontFamily = FontFamily.Monospace,
                                modifier = Modifier.padding(top = 8.dp)
                            )
                        }
                        fed.hardwareLabel?.let {
                            Text(
                                text = localizedString("mobile.federation_create_hardware", "hardware", it),
                                color = SetupColors.InfoText,
                                fontSize = 12.sp,
                                modifier = Modifier.padding(top = 4.dp)
                            )
                        }
                    }

                    // Not minted yet → the mint UX: optional label + backend choice
                    // + the "Create my federation ID" button.
                    else -> {
                        Text(
                            text = localizedString("mobile.federation_create_prompt"),
                            color = SetupColors.InfoText,
                            fontSize = 13.sp,
                            lineHeight = 18.sp,
                            modifier = Modifier.padding(bottom = 12.dp)
                        )

                        // REQUIRED federation-identity name. This names + keys the
                        // ONE canonical "you" (via the node's derive_key_id) — so it
                        // must be present and must not be a generic default. The
                        // field is invalid (and Next is blocked) until the user
                        // enters a real, unique name like `firstname-lastname-v1`.
                        val labelTrimmed = fed.label.trim()
                        val labelIsGeneric = labelTrimmed.lowercase() in
                            FederationIdentitySetupState.REJECTED_GENERIC_LABELS
                        val labelHasError = labelTrimmed.isEmpty() || labelIsGeneric
                        OutlinedTextField(
                            value = fed.label,
                            onValueChange = { viewModel.setFederationLabel(it) },
                            label = { Text(localizedString("mobile.setup_fedid_label")) },
                            placeholder = { Text(localizedString("mobile.setup_fedid_label_hint")) },
                            singleLine = true,
                            isError = labelHasError,
                            enabled = !fed.inProgress,
                            modifier = Modifier
                                .fillMaxWidth()
                                .testable("input_fedid_label"),
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedTextColor = SetupColors.TextPrimary,
                                unfocusedTextColor = SetupColors.TextPrimary,
                                focusedBorderColor = SetupColors.Primary,
                                unfocusedBorderColor = SetupColors.TextSecondary.copy(alpha = 0.5f),
                                cursorColor = SetupColors.Primary,
                                errorBorderColor = SetupColors.ErrorText
                            )
                        )
                        // Inline requirement / rejection hint under the field.
                        Text(
                            text = when {
                                labelTrimmed.isEmpty() ->
                                    localizedString("mobile.setup_fedid_label_required")
                                labelIsGeneric ->
                                    localizedString("mobile.setup_fedid_label_generic")
                                else -> localizedString("mobile.setup_fedid_label_ok")
                            },
                            color = if (labelHasError) SetupColors.ErrorText else SetupColors.SuccessText,
                            fontSize = 12.sp,
                            modifier = Modifier.padding(top = 4.dp, bottom = 12.dp)
                        )

                        // OPTIONAL friendly per-device name (e.g. "Mac mini") —
                        // distinct from the fed-ID name above. Empty is allowed; it
                        // labels THIS device in the UI and is stored client-side
                        // (no server field on the wizard's mint/claim yet).
                        OutlinedTextField(
                            value = state.deviceName,
                            onValueChange = { viewModel.setDeviceName(it) },
                            label = {
                                Text(
                                    localizedString("mobile.setup_device_name_label")
                                        .ifEmpty { "Name this device (optional)" }
                                )
                            },
                            placeholder = {
                                Text(
                                    localizedString("mobile.setup_device_name_hint")
                                        .ifEmpty { "e.g. Mac mini" }
                                )
                            },
                            singleLine = true,
                            enabled = !fed.inProgress,
                            modifier = Modifier
                                .fillMaxWidth()
                                .testable("input_device_name"),
                            colors = OutlinedTextFieldDefaults.colors(
                                focusedTextColor = SetupColors.TextPrimary,
                                unfocusedTextColor = SetupColors.TextPrimary,
                                focusedBorderColor = SetupColors.Primary,
                                unfocusedBorderColor = SetupColors.TextSecondary.copy(alpha = 0.5f),
                                cursorColor = SetupColors.Primary,
                            )
                        )
                        Text(
                            text = localizedString("mobile.setup_device_name_helper")
                                .ifEmpty { "A friendly name for this device. You can leave this blank." },
                            color = SetupColors.TextSecondary,
                            fontSize = 12.sp,
                            modifier = Modifier.padding(top = 4.dp, bottom = 12.dp)
                        )

                        // No custody choice: the only option is the SECURE one.
                        // `backend = null` lets the substrate auto-pick the most
                        // secure custody available (YubiKey → TPM/Secure-Enclave →
                        // software), so the user never has to choose. Keep it easy.
                        Text(
                            text = localizedString("mobile.federation_create_secure_note"),
                            color = SetupColors.InfoText,
                            fontSize = 11.sp,
                            modifier = Modifier.padding(bottom = 12.dp)
                        )

                        // Secure with 2FA belongs to the FEDERATION IDENTITY (the
                        // hardware factor IS the fed-ID's custody), not the local
                        // login — so the toggle lives here.
                        SecureWith2FACard(state = state, viewModel = viewModel)
                        Spacer(modifier = Modifier.height(12.dp))

                        // Federation opt-in — now a FIRST-CLASS decision: announcing
                        // is upstream of everything the community touches (traces +
                        // joining communities). Privacy-first, default OFF. The trace
                        // opt-in (accordMetricsConsent) is GATED inside this card — it
                        // can only be enabled once the user announces (un-announced
                        // nodes never federate their traces). Turning announce OFF also
                        // clears the trace opt-in so state stays consistent.
                        AnnounceDecisionCard(
                            announce = state.announceOwnership,
                            onAnnounceChange = { on ->
                                viewModel.setAnnounceOwnership(on)
                                if (!on) viewModel.setAccordMetricsConsent(false)
                            },
                            traceOptIn = state.accordMetricsConsent,
                            onTraceOptInChange = { viewModel.setAccordMetricsConsent(it) },
                        )
                        Spacer(modifier = Modifier.height(12.dp))

                        Button(
                            // Block minting until the name is valid: minting with a
                            // blank/generic name is exactly what produced the
                            // colliding `ciris-client-user` identity.
                            onClick = { viewModel.runFederationIdentitySetup() },
                            enabled = !fed.inProgress && !labelHasError,
                            modifier = Modifier.testableClickable("btn_federation_identity") {
                                if (!labelHasError) viewModel.runFederationIdentitySetup()
                            }
                        ) {
                            if (fed.inProgress) {
                                CircularProgressIndicator(
                                    modifier = Modifier.size(16.dp),
                                    strokeWidth = 2.dp,
                                    color = Color.White
                                )
                                Spacer(modifier = Modifier.width(8.dp))
                            }
                            Text(
                                if (fed.inProgress) {
                                    localizedString("mobile.federation_create_minting")
                                } else {
                                    localizedString("mobile.federation_create_button")
                                }
                            )
                        }

                        // ASSOCIATE an EXISTING Fed ID instead of minting a new one
                        // (adopt prior crypto materials — same user, same auth). The
                        // choice is always offered; tapping reveals the key_id input.
                        Spacer(modifier = Modifier.height(10.dp))
                        TextButton(
                            onClick = { viewModel.toggleAssociateExisting() },
                            enabled = !fed.inProgress,
                            modifier = Modifier.testableClickable("btn_federation_associate_existing") {
                                viewModel.toggleAssociateExisting()
                            }
                        ) {
                            Text(localizedString("mobile.federation_create_associate"))
                        }
                        if (fed.associateExisting) {
                            OutlinedTextField(
                                value = fed.associateKeyId,
                                onValueChange = { viewModel.setAssociateKeyId(it) },
                                label = { Text(localizedString("mobile.federation_create_associate_hint")) },
                                singleLine = true,
                                enabled = !fed.inProgress,
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(top = 4.dp)
                                    .testable("input_federation_associate_keyid")
                            )
                            Button(
                                onClick = { viewModel.associateExistingFederationId() },
                                enabled = !fed.inProgress && fed.associateKeyId.isNotBlank(),
                                modifier = Modifier
                                    .padding(top = 8.dp)
                                    .testableClickable("btn_federation_associate_submit") {
                                        viewModel.associateExistingFederationId()
                                    }
                            ) {
                                Text(localizedString("mobile.federation_create_associate_button"))
                            }
                        }

                        // IMPORT an existing fed-ID from a USB / folder keyset — the
                        // "same person, new device" path. The node REPLACES this
                        // device's identity with the imported one and the self-claim
                        // re-owns the node under it (works at first-run). One device =
                        // one person; import replaces, it does not coexist.
                        Spacer(modifier = Modifier.height(6.dp))
                        var showImportPicker by remember { mutableStateOf(false) }
                        TextButton(
                            onClick = { showImportPicker = true },
                            enabled = !fed.inProgress,
                            modifier = Modifier.testableClickable("btn_federation_import_usb") {
                                showImportPicker = true
                            }
                        ) {
                            Text(localizedString("mobile.federation_import_usb"))
                        }
                        DirectoryPickerDialog(
                            show = showImportPicker,
                            onDirectoryPicked = { dir ->
                                showImportPicker = false
                                if (dir.isNotBlank()) viewModel.importPortableFromUsb(dir)
                            },
                            onDismiss = { showImportPicker = false },
                        )
                    }
                }

                fed.error?.let { err ->
                    Text(
                        text = err,
                        color = SetupColors.ErrorText,
                        fontSize = 12.sp,
                        modifier = Modifier.padding(top = 8.dp)
                    )
                }
            }
        }

        Text(
            text = localizedString("mobile.setup_fedid_required_note"),
            color = SetupColors.TextSecondary,
            fontSize = 12.sp,
        )
    }
}

/**
 * **AGE_RANGE step — the foundational protective gate.** You have a federation
 * ID; now STATE YOUR AGE RANGE, then you're on the fabric. Safety is built in
 * FIRST, ahead of content.
 *
 * A clear age-range selector (Under 18 / 18+ — matching `age.rs::AgeBand`'s
 * `minor` / `adult`) with a child-safe explainer. On select, the local node
 * records the subject-signed self-declared assurance
 * (`POST /v1/safety/age-assurance`). The app does NO crypto. Declining/erroring
 * never traps the user — the protective default is `minor`.
 */
@Composable
private fun AgeRangeSection(
    viewModel: SetupViewModel,
    state: SetupFormState,
    modifier: Modifier = Modifier
) {
    val age = state.ageRange

    Column(modifier = modifier.fillMaxWidth()) {
        Text(
            text = localizedString("mobile.age_range_title"),
            color = SetupColors.TextPrimary,
            fontSize = 20.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(bottom = 8.dp)
        )
        Text(
            text = localizedString("mobile.age_range_explainer"),
            color = SetupColors.TextSecondary,
            fontSize = 14.sp,
            modifier = Modifier.padding(bottom = 20.dp)
        )

        // The two protective bands. The server models exactly two: minor / adult
        // (age.rs::AgeBand). "Under 18" maps to `minor`; "18 or older" to `adult`.
        val options = listOf(
            AgeBand.MINOR to ("minor" to localizedString("mobile.age_range_minor")),
            AgeBand.ADULT to ("adult" to localizedString("mobile.age_range_adult")),
        )
        Column(modifier = Modifier.padding(bottom = 16.dp)) {
            options.forEach { (band, meta) ->
                val (token, label) = meta
                val selected = age.selectedBandToken == token
                Surface(
                    shape = RoundedCornerShape(12.dp),
                    color = if (selected) SetupColors.Primary.copy(alpha = 0.18f) else SetupColors.InfoLight,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 4.dp)
                        .testableClickable("age_band_$token") {
                            if (!age.inProgress) viewModel.setAgeRange(band)
                        }
                ) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.padding(horizontal = 14.dp, vertical = 14.dp)
                    ) {
                        RadioButton(
                            selected = selected,
                            onClick = { if (!age.inProgress) viewModel.setAgeRange(band) },
                            enabled = !age.inProgress,
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = label,
                            color = SetupColors.InfoDark,
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Medium,
                        )
                    }
                }
            }
        }

        // UNDER-18 STEWARDSHIP (CC 0.5.1 §2580). When the founder self-declares
        // the `minor` band they cannot self-claim ownership; a kind, plain-English
        // panel explains that an adult must accept responsibility (stewardship),
        // and lets the minor generate a stewardship request to hand over.
        if (age.selectedBandToken == "minor") {
            MinorStewardshipCard(viewModel, state)
        }

        // Child-safe explainer card — honest framing kept TRUE (matches the
        // age.rs honesty discipline: protective default; self-declared; the
        // subject controls their own band; misdeclaration is never punitive).
        Surface(
            shape = RoundedCornerShape(12.dp),
            color = SetupColors.InfoLight,
            modifier = Modifier
                .fillMaxWidth()
                .padding(bottom = 12.dp)
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.padding(bottom = 8.dp)
                ) {
                    Text(text = "🛡️", fontSize = 20.sp, modifier = Modifier.padding(end = 8.dp))
                    Text(
                        text = localizedString("mobile.age_range_card_title"),
                        color = SetupColors.InfoDark,
                        fontSize = 16.sp,
                        fontWeight = FontWeight.Bold
                    )
                }
                Text(
                    text = localizedString("mobile.age_range_card_body"),
                    color = SetupColors.InfoText,
                    fontSize = 13.sp,
                    lineHeight = 18.sp,
                )

                when {
                    age.inProgress -> {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.padding(top = 12.dp)
                        ) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(16.dp),
                                strokeWidth = 2.dp,
                                color = SetupColors.Primary
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = localizedString("mobile.age_range_saving"),
                                color = SetupColors.InfoText,
                                fontSize = 12.sp,
                            )
                        }
                    }
                    age.recorded -> {
                        Text(
                            text = localizedString("mobile.age_range_saved"),
                            color = SetupColors.InfoDark,
                            fontSize = 12.sp,
                            fontWeight = FontWeight.Medium,
                            modifier = Modifier.padding(top = 12.dp)
                        )
                    }
                }

                age.error?.let { err ->
                    Text(
                        text = err,
                        color = SetupColors.ErrorText,
                        fontSize = 12.sp,
                        modifier = Modifier.padding(top = 10.dp)
                    )
                }
            }
        }

        Text(
            text = localizedString("mobile.age_range_footnote"),
            color = SetupColors.TextSecondary,
            fontSize = 12.sp,
        )
    }
}

/**
 * UNDER-18 STEWARDSHIP panel (CIRIS Constitution 0.5.1 §2580 — minor-stewardship
 * rule). Shown inside [AgeRangeStep] when the founder selects the `minor` band.
 *
 * A minor MUST NOT self-claim ownership; instead an over-18 adult must accept
 * responsibility (stewardship) by signing a live `delegates_to(adult → minor)`.
 * This panel (a) explains that kindly and plainly, (b) lets the minor generate a
 * stewardship request — a code/URL + PIN they hand to their adult — and (c) makes
 * the fail-secure posture explicit: the account cannot operate until a live adult
 * steward accepts, and pauses again if the steward is ever removed.
 */
@Composable
private fun MinorStewardshipCard(
    viewModel: SetupViewModel,
    state: SetupFormState,
) {
    val steward = state.minorStewardship

    Surface(
        shape = RoundedCornerShape(12.dp),
        color = SetupColors.WarningLight,
        modifier = Modifier
            .fillMaxWidth()
            .padding(bottom = 12.dp)
            .testable("minor_stewardship_card")
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.padding(bottom = 8.dp)
            ) {
                Text(text = "🧡", fontSize = 20.sp, modifier = Modifier.padding(end = 8.dp))
                Text(
                    text = localizedString("mobile.setup_minor_title"),
                    color = SetupColors.WarningDark,
                    fontSize = 16.sp,
                    fontWeight = FontWeight.Bold
                )
            }

            // Kind, plain-English explanation of WHY and WHAT stewardship is.
            Text(
                text = localizedString("mobile.setup_minor_explainer"),
                color = SetupColors.WarningText,
                fontSize = 13.sp,
                lineHeight = 18.sp,
                modifier = Modifier.padding(bottom = 10.dp)
            )

            // Fail-secure note — the account cannot operate until an adult accepts.
            Text(
                text = localizedString("mobile.setup_minor_failsecure"),
                color = SetupColors.WarningText,
                fontSize = 12.sp,
                lineHeight = 17.sp,
                fontWeight = FontWeight.Medium,
                modifier = Modifier.padding(bottom = 14.dp)
            )

            when {
                // A request was generated — show the hand-off code/URL + PIN.
                steward.requested -> {
                    Text(
                        text = localizedString("mobile.setup_minor_handoff_title"),
                        color = SetupColors.WarningDark,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Bold,
                        modifier = Modifier.padding(bottom = 6.dp)
                    )
                    Text(
                        text = localizedString("mobile.setup_minor_handoff_body"),
                        color = SetupColors.WarningText,
                        fontSize = 12.sp,
                        lineHeight = 17.sp,
                        modifier = Modifier.padding(bottom = 10.dp)
                    )
                    // The PIN the adult enters to accept stewardship.
                    steward.requestPin?.let { pin ->
                        Surface(
                            shape = RoundedCornerShape(8.dp),
                            color = SetupColors.InfoLight,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(bottom = 8.dp)
                        ) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                Text(
                                    text = localizedString("mobile.setup_minor_pin_label"),
                                    color = SetupColors.TextSecondary,
                                    fontSize = 11.sp,
                                )
                                Text(
                                    text = pin,
                                    color = SetupColors.InfoDark,
                                    fontSize = 22.sp,
                                    fontWeight = FontWeight.Bold,
                                    modifier = Modifier
                                        .padding(top = 2.dp)
                                        .testable("minor_steward_pin", pin)
                                )
                            }
                        }
                    }
                    // The claim URL the adult opens on their own device to accept.
                    steward.requestUrl?.let { url ->
                        Surface(
                            shape = RoundedCornerShape(8.dp),
                            color = SetupColors.InfoLight,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(bottom = 8.dp)
                        ) {
                            Column(modifier = Modifier.padding(12.dp)) {
                                Text(
                                    text = localizedString("mobile.setup_minor_url_label"),
                                    color = SetupColors.TextSecondary,
                                    fontSize = 11.sp,
                                )
                                Text(
                                    text = url,
                                    color = SetupColors.InfoDark,
                                    fontSize = 13.sp,
                                    modifier = Modifier
                                        .padding(top = 2.dp)
                                        .testable("minor_steward_url", url)
                                )
                            }
                        }
                    }
                    Text(
                        text = localizedString("mobile.setup_minor_pending"),
                        color = SetupColors.WarningDark,
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Medium,
                        modifier = Modifier.padding(top = 2.dp)
                    )
                }

                // In flight.
                steward.inProgress -> {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(16.dp),
                            strokeWidth = 2.dp,
                            color = SetupColors.Primary
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = localizedString("mobile.setup_minor_requesting"),
                            color = SetupColors.WarningText,
                            fontSize = 12.sp,
                        )
                    }
                }

                // Initial state — offer the "ask an adult" button.
                else -> {
                    Surface(
                        shape = RoundedCornerShape(10.dp),
                        color = SetupColors.Primary,
                        modifier = Modifier
                            .fillMaxWidth()
                            .testableClickable("btn_request_steward") {
                                viewModel.requestMinorSteward()
                            }
                    ) {
                        Text(
                            text = localizedString("mobile.setup_minor_request_btn"),
                            color = Color.White,
                            fontSize = 15.sp,
                            fontWeight = FontWeight.Bold,
                            textAlign = TextAlign.Center,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(vertical = 14.dp)
                        )
                    }
                }
            }

            steward.error?.let { err ->
                Text(
                    text = err,
                    color = SetupColors.ErrorText,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(top = 10.dp)
                )
            }
        }
    }
}


// ========== Account & Confirmation Step ==========
@Composable
private fun AccountSection(
    viewModel: SetupViewModel,
    state: SetupFormState,
    modifier: Modifier = Modifier
) {
    // No "Confirm Setup — review your configuration and complete setup" title:
    // this is screen 1 of 3 and nothing has been configured yet.
    Column(modifier = modifier.fillMaxWidth()) {

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

            Spacer(modifier = Modifier.height(12.dp))

            OutlinedTextField(
                value = state.userPasswordConfirm,
                onValueChange = { viewModel.setUserPasswordConfirm(it) },
                modifier = Modifier.fillMaxWidth().testable("input_password_confirm"),
                label = { Text(localizedString("mobile.setup_password_confirm_label"), color = SetupColors.TextSecondary) },
                visualTransformation = if (showPassword) VisualTransformation.None else PasswordVisualTransformation(),
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

            if (state.userPasswordConfirm.isNotEmpty() && state.userPassword != state.userPasswordConfirm) {
                Text(
                    text = localizedString("mobile.setup_password_mismatch_hint"),
                    color = SetupColors.ErrorText,
                    fontSize = 12.sp,
                    modifier = Modifier.padding(start = 4.dp, top = 4.dp)
                )
            }
        }
    }
}

/**
 * The "Secure with 2FA" affordance — rendered on the FEDERATION-IDENTITY step
 * (the 2nd factor belongs to the federation identity, not the local login). The
 * factor is provided NATIVELY by CIRISVerify (the device's hardware authenticator:
 * YubiKey → TPM / Secure-Enclave) and enrolled as the `hardware_attestation` on
 * the self-login occurrence when the fed-ID is minted.
 */
@Composable
private fun SecureWith2FACard(
    state: SetupFormState,
    viewModel: SetupViewModel,
) {
    Surface(
        shape = RoundedCornerShape(12.dp),
        color = SetupColors.GrayLight,
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = localizedString("mobile.setup_2fa_title"),
                    color = SetupColors.TextPrimary,
                    fontSize = 15.sp,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.height(4.dp))
                Text(
                    text = localizedString("mobile.setup_2fa_desc"),
                    color = SetupColors.TextSecondary,
                    fontSize = 13.sp
                )
            }
            Spacer(modifier = Modifier.width(12.dp))
            Switch(
                checked = state.secureWith2FA,
                onCheckedChange = { viewModel.setSecureWith2FA(it) },
                modifier = Modifier.testableClickable("toggle_secure_2fa") {
                    viewModel.setSecureWith2FA(!state.secureWith2FA)
                }
            )
        }
    }
}





// ========== Complete Step ==========
@Composable
private fun CompleteStep(
    onSetupComplete: () -> Unit,
    ownershipClaim: ai.ciris.mobile.shared.viewmodels.NodeOwnershipClaimState =
        ai.ciris.mobile.shared.viewmodels.NodeOwnershipClaimState(),
    modifier: Modifier = Modifier
) {
    // Hold here until the LOCAL-node ownership self-claim settles (success or
    // error), then auto-complete. Bounded so a hung claim never traps the user.
    LaunchedEffect(ownershipClaim.inProgress) {
        if (!ownershipClaim.inProgress) {
            kotlinx.coroutines.delay(2000)
            onSetupComplete()
        }
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

        // LOCAL-node ownership self-claim status. Success → this node is now
        // OWNED by the just-created user. Failure → honest reason (e.g. the
        // console-only claim PIN was not captured); the node can still be claimed
        // later from the Network surface.
        when {
            ownershipClaim.inProgress -> {
                Text(
                    text = "Claiming ownership of this node…",
                    color = SetupColors.TextSecondary,
                    fontSize = 14.sp,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.testable("setup_ownership_claiming"),
                )
            }
            ownershipClaim.claimed -> {
                Text(
                    text = "You now own this node (${ownershipClaim.role ?: "owner"}).",
                    color = SetupColors.SuccessDark,
                    fontSize = 14.sp,
                    fontWeight = FontWeight.Medium,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.testable("setup_ownership_claimed"),
                )
            }
            ownershipClaim.error != null -> {
                Text(
                    text = "Couldn't claim this node yet: ${ownershipClaim.error}",
                    color = SetupColors.TextSecondary,
                    fontSize = 13.sp,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.testable("setup_ownership_error"),
                )
            }
        }

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
            // No back button on the first screen: this is first-run, there is
            // no prior login/account to return to (it is created right here).
            if (currentStep != SetupStep.YOU && currentStep != SetupStep.COMPLETE) {
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
                    // Equal weights when Back is visible; full width when it is not.
                    modifier = Modifier
                        .weight(if (currentStep == SetupStep.YOU) 2f else 1f)
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
                        Text(
                            if (isFinalSetupStep(currentStep, CIRISBuild.HAS_AGENT)) {
                                localizedString("setup.finish")
                            } else {
                                localizedString("setup.next")
                            }
                        )
                    }
                }
            }
        }
    }
}

