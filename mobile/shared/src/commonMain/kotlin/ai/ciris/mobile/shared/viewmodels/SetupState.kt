package ai.ciris.mobile.shared.viewmodels

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
     */
    WELCOME,

    /**
     * Step 2: LLM mode selection (CIRIS_PROXY vs BYOK) and configuration.
     */
    LLM_CONFIGURATION,

    /**
     * Step 3: Account creation (for non-Google users) and confirmation.
     */
    ACCOUNT_AND_CONFIRMATION,

    /**
     * Final step: Setup is complete.
     */
    COMPLETE
}

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

            SetupStep.ACCOUNT_AND_CONFIRMATION -> {
                if (isGoogleAuth) {
                    // Google user - no account creation needed
                    true
                } else {
                    // Local user - validate username/password
                    username.isNotEmpty() && userPassword.length >= 8
                }
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
