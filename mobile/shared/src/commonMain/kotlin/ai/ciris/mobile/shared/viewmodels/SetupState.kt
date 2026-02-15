package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.models.CommunicationAdapter
import ai.ciris.mobile.shared.models.SetupMode
import kotlinx.serialization.Serializable

/**
 * Setup wizard state management.
 *
 * Source: android/app/src/main/java/ai/ciris/mobile/setup/SetupWizardActivity.kt
 * and android/app/src/main/java/ai/ciris/mobile/setup/SetupViewModel.kt
 */

/**
 * Setup wizard steps.
 *
 * Source: SetupWizardActivity.kt:29-32
 * The Android app uses a 3-step wizard:
 * 1. Welcome - Introduction
 * 2. LLM Configuration - Choose CIRIS_PROXY or BYOK mode
 * 3. Confirmation - Summary + account creation (if needed)
 */
enum class SetupStep {
    /**
     * Step 1: Welcome screen with introduction.
     * In node flow, includes "Connect to Node" option.
     */
    WELCOME,

    /**
     * Step 1b (Node flow only): Device auth with CIRISPortal.
     * Agent polls while user authenticates in browser and selects template.
     */
    NODE_AUTH,

    /**
     * Step 2: LLM mode selection (CIRIS_PROXY vs BYOK) and configuration.
     */
    LLM_CONFIGURATION,

    /**
     * Step 3: Optional features - Covenant Metrics opt-in for AI alignment research.
     */
    OPTIONAL_FEATURES,

    /**
     * Step 4: Account creation (for non-Google users) and confirmation.
     */
    ACCOUNT_AND_CONFIRMATION,

    /**
     * Step 4b (Node flow only): Optional CIRISVerify download and configuration.
     */
    VERIFY_SETUP,

    /**
     * Final step: Setup is complete.
     */
    COMPLETE
}

/**
 * Device auth state for the "Connect to Node" flow.
 * Tracks the RFC 8628 device authorization session.
 */
@Serializable
data class DeviceAuthState(
    val nodeUrl: String = "",
    val verificationUri: String = "",
    val deviceCode: String = "",
    val userCode: String = "",
    val portalUrl: String = "",
    val status: DeviceAuthStatus = DeviceAuthStatus.IDLE,
    val expiresIn: Int = 900,
    val interval: Int = 5,
    // Provisioned data (set after user completes in Portal)
    val provisionedTemplate: String? = null,
    val provisionedAdapters: List<String> = emptyList(),
    val signingKeyB64: String? = null,
    val keyId: String? = null,
    val orgId: String? = null,
    val stewardshipTier: Int? = null,
    val error: String? = null,
    // Node manifest for display
    val nodeManifest: Map<String, String> = emptyMap()
)

/**
 * Device auth flow status.
 */
@Serializable
enum class DeviceAuthStatus {
    IDLE,           // Not started
    CONNECTING,     // Fetching node manifest + initiating device auth
    WAITING,        // Waiting for user to complete in browser
    COMPLETE,       // User completed, key provisioned
    ERROR           // Something went wrong
}

/**
 * CIRISVerify setup state for the optional verification step.
 */
@Serializable
data class VerifySetupState(
    val enabled: Boolean = false,
    val downloading: Boolean = false,
    val downloaded: Boolean = false,
    val binaryPath: String? = null,
    val version: String? = null,
    val requireHardware: Boolean = false,
    val error: String? = null
)

/**
 * Form state for the setup wizard.
 *
 * Source: SetupViewModel.kt:15-167
 * Tracks all user inputs and Google OAuth state.
 */
@Serializable
data class SetupFormState(
    // Current step in the wizard
    val currentStep: SetupStep = SetupStep.WELCOME,

    // Node flow flag: when true, step sequence is modified
    // WELCOME → NODE_AUTH → LLM_CONFIGURATION → VERIFY_SETUP → COMPLETE
    val isNodeFlow: Boolean = false,

    // Device auth state (Connect to Node flow)
    val deviceAuth: DeviceAuthState = DeviceAuthState(),

    // CIRISVerify setup state (node flow only)
    val verifySetup: VerifySetupState = VerifySetupState(),

    // Google OAuth state
    val isGoogleAuth: Boolean = false,
    val googleIdToken: String? = null,
    val googleEmail: String? = null,
    val googleUserId: String? = null,

    // LLM mode selection (CIRIS_PROXY or BYOK)
    val setupMode: SetupMode? = null,

    // LLM configuration (for BYOK mode)
    val llmProvider: String = "OpenAI",      // "OpenAI", "Anthropic", "LocalAI", "Azure OpenAI"
    val llmApiKey: String = "",
    val llmBaseUrl: String = "",
    val llmModel: String = "",

    // User account (for non-Google users only)
    val username: String = "",
    val email: String = "",
    val userPassword: String = "",

    // Covenant Metrics opt-in (for AI alignment research)
    // Data shared: reasoning scores, decision patterns, LLM provider/API base URL
    // No message content or PII is ever sent
    val covenantMetricsConsent: Boolean = false,

    // V1.9.7: Template selection (Advanced Settings)
    val availableTemplates: List<AgentTemplateInfo> = emptyList(),
    val selectedTemplateId: String = "default",
    val showAdvancedSettings: Boolean = false,
    val templatesLoading: Boolean = false,

    // Adapter configuration
    // Available adapters from /v1/setup/adapters
    val availableAdapters: List<CommunicationAdapter> = emptyList(),
    // IDs of adapters that will be enabled (api is always included)
    val enabledAdapterIds: Set<String> = setOf("api"),
    // Loading state for adapter list
    val adaptersLoading: Boolean = false,

    // Validation state
    val isValidating: Boolean = false,
    val validationError: String? = null,

    // Submission state
    val isSubmitting: Boolean = false,
    val submissionError: String? = null
) {
    /**
     * Check if using CIRIS proxy mode.
     * Source: SetupViewModel.kt:125-127
     */
    fun useCirisProxy(): Boolean {
        return setupMode == SetupMode.CIRIS_PROXY
    }

    /**
     * Check if local user account fields should be shown.
     * Source: SetupViewModel.kt:133-135
     */
    fun showLocalUserFields(): Boolean {
        return !isGoogleAuth
    }

    /**
     * Check if current step is valid and can proceed to next.
     * Source: SetupWizardActivity.kt:209-286
     */
    fun canProceedFromCurrentStep(): Boolean {
        return when (currentStep) {
            SetupStep.WELCOME -> true

            SetupStep.NODE_AUTH -> {
                // Can proceed when device auth is complete
                deviceAuth.status == DeviceAuthStatus.COMPLETE
            }

            SetupStep.LLM_CONFIGURATION -> {
                if (setupMode == SetupMode.CIRIS_PROXY) {
                    // CIRIS proxy mode - need Google auth token
                    googleIdToken != null
                } else if (setupMode == SetupMode.BYOK) {
                    // BYOK mode - need provider and API key (unless LocalAI)
                    if (llmProvider == "LocalAI") {
                        true
                    } else {
                        llmApiKey.isNotEmpty()
                    }
                } else {
                    false // No mode selected
                }
            }

            SetupStep.OPTIONAL_FEATURES -> {
                // Optional features step - always valid (consent is optional)
                true
            }

            SetupStep.ACCOUNT_AND_CONFIRMATION -> {
                if (isGoogleAuth) {
                    // Google user - no account creation needed
                    true
                } else {
                    // Local user - validate username/password
                    username.isNotEmpty() && userPassword.length >= 8
                }
            }

            SetupStep.VERIFY_SETUP -> {
                // CIRISVerify setup is optional — always can proceed
                true
            }

            SetupStep.COMPLETE -> true
        }
    }

    /**
     * Get validation error for current step.
     * Source: SetupWizardActivity.kt:209-286
     */
    fun getStepValidationError(): String? {
        return when (currentStep) {
            SetupStep.WELCOME -> null

            SetupStep.NODE_AUTH -> {
                when (deviceAuth.status) {
                    DeviceAuthStatus.ERROR -> deviceAuth.error ?: "Device authorization failed"
                    DeviceAuthStatus.IDLE -> "Enter a node URL to connect"
                    DeviceAuthStatus.CONNECTING -> "Connecting to node..."
                    DeviceAuthStatus.WAITING -> "Waiting for authorization in browser..."
                    DeviceAuthStatus.COMPLETE -> null
                }
            }

            SetupStep.LLM_CONFIGURATION -> {
                when {
                    setupMode == null -> "Please select an AI mode"
                    setupMode == SetupMode.CIRIS_PROXY && googleIdToken == null ->
                        "Google sign-in required for free AI"
                    setupMode == SetupMode.BYOK && llmProvider != "LocalAI" && llmApiKey.isEmpty() ->
                        "API Key is required"
                    else -> null
                }
            }

            SetupStep.OPTIONAL_FEATURES -> {
                // Optional features - no validation required (consent is optional)
                null
            }

            SetupStep.ACCOUNT_AND_CONFIRMATION -> {
                if (!isGoogleAuth) {
                    when {
                        username.isEmpty() -> "Username is required"
                        userPassword.isEmpty() -> "Password is required"
                        userPassword.length < 8 -> "Password must be at least 8 characters"
                        else -> null
                    }
                } else {
                    null
                }
            }

            SetupStep.VERIFY_SETUP -> null

            SetupStep.COMPLETE -> null
        }
    }
}

/**
 * Result of LLM validation test.
 * Source: POST /v1/setup/validate-llm
 */
@Serializable
data class LlmValidationResult(
    val valid: Boolean,
    val error: String? = null,
    val modelUsed: String? = null
)

/**
 * Result of setup completion.
 * Source: POST /v1/setup/complete
 */
@Serializable
data class SetupCompletionResult(
    val success: Boolean,
    val message: String,
    val agentId: String? = null,
    val adminUserId: String? = null,
    val error: String? = null
)

/**
 * Agent template info for display in setup wizard.
 * Source: GET /v1/setup/templates
 */
@Serializable
data class AgentTemplateInfo(
    val id: String,
    val name: String,
    val description: String
)
