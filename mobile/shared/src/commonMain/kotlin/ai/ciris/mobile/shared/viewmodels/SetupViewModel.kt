package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.models.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * ViewModel for Setup Wizard state management.
 *
 * Source: android/app/src/main/java/ai/ciris/mobile/setup/SetupViewModel.kt
 * and android/app/src/main/java/ai/ciris/mobile/setup/SetupWizardActivity.kt
 *
 * Supports two LLM modes:
 * - CIRIS Proxy (free for Google OAuth users): Uses Google ID token with CIRIS hosted proxy
 * - BYOK (Bring Your Own Key): User provides their own API key from OpenAI/Anthropic/etc
 *
 * Key features:
 * - StateFlow for reactive UI updates
 * - Form validation with detailed error messages
 * - LLM validation (test call before setup completion)
 * - Auto-generated admin password (users don't set this)
 * - Google OAuth support for CIRIS proxy mode
 */
class SetupViewModel {

    private val _state = MutableStateFlow(SetupFormState())
    val state: StateFlow<SetupFormState> = _state.asStateFlow()

    // ========== Google OAuth State ==========
    // Source: SetupViewModel.kt:68-80, SetupWizardActivity.kt:110-174

    /**
     * Set Google OAuth state from successful sign-in.
     *
     * If Google auth is available, defaults to CIRIS_PROXY mode.
     *
     * Source: SetupViewModel.kt:68-80
     */
    fun setGoogleAuthState(
        isAuth: Boolean,
        idToken: String?,
        email: String?,
        userId: String?
    ) {
        _state.value = _state.value.copy(
            isGoogleAuth = isAuth,
            googleIdToken = idToken,
            googleEmail = email,
            googleUserId = userId,
            // Default to CIRIS proxy if Google auth available and no mode selected yet
            setupMode = if (isAuth && _state.value.setupMode == null) {
                SetupMode.CIRIS_PROXY
            } else {
                _state.value.setupMode
            }
        )
    }

    // ========== Setup Mode ==========
    // Source: SetupViewModel.kt:82-85

    /**
     * Set the LLM setup mode (CIRIS_PROXY or BYOK).
     */
    fun setSetupMode(mode: SetupMode) {
        _state.value = _state.value.copy(setupMode = mode)
    }

    // ========== LLM Configuration (BYOK mode) ==========
    // Source: SetupViewModel.kt:87-105

    /**
     * Set the LLM provider for BYOK mode.
     * Examples: "OpenAI", "Anthropic", "Azure OpenAI", "LocalAI"
     */
    fun setLlmProvider(provider: String) {
        _state.value = _state.value.copy(llmProvider = provider)
    }

    /**
     * Set the LLM API key for BYOK mode.
     */
    fun setLlmApiKey(key: String) {
        _state.value = _state.value.copy(llmApiKey = key)
    }

    /**
     * Set the LLM base URL (optional, for custom providers).
     */
    fun setLlmBaseUrl(url: String) {
        _state.value = _state.value.copy(llmBaseUrl = url)
    }

    /**
     * Set the LLM model (optional, provider default used if empty).
     */
    fun setLlmModel(model: String) {
        _state.value = _state.value.copy(llmModel = model)
    }

    // ========== User Account (non-Google users) ==========
    // Source: SetupViewModel.kt:107-120

    /**
     * Set the username for local user account.
     */
    fun setUsername(username: String) {
        _state.value = _state.value.copy(username = username)
    }

    /**
     * Set the email for local user account.
     */
    fun setEmail(email: String) {
        _state.value = _state.value.copy(email = email)
    }

    /**
     * Set the password for local user account.
     */
    fun setUserPassword(password: String) {
        _state.value = _state.value.copy(userPassword = password)
    }

    // ========== Step Navigation ==========
    // Source: SetupWizardActivity.kt:77-97

    /**
     * Move to the next setup step.
     * Only proceeds if current step is valid.
     *
     * Returns true if navigation succeeded, false if validation failed.
     */
    fun nextStep(): Boolean {
        val currentState = _state.value

        if (!currentState.canProceedFromCurrentStep()) {
            return false
        }

        val nextStep = when (currentState.currentStep) {
            SetupStep.WELCOME -> SetupStep.LLM_CONFIGURATION
            SetupStep.LLM_CONFIGURATION -> SetupStep.OPTIONAL_FEATURES
            SetupStep.OPTIONAL_FEATURES -> SetupStep.ACCOUNT_AND_CONFIRMATION
            SetupStep.ACCOUNT_AND_CONFIRMATION -> SetupStep.COMPLETE
            SetupStep.COMPLETE -> SetupStep.COMPLETE // Stay at complete
        }

        _state.value = currentState.copy(currentStep = nextStep)
        return true
    }

    /**
     * Move to the previous setup step.
     */
    fun previousStep() {
        val currentState = _state.value

        val prevStep = when (currentState.currentStep) {
            SetupStep.WELCOME -> SetupStep.WELCOME // Stay at welcome
            SetupStep.LLM_CONFIGURATION -> SetupStep.WELCOME
            SetupStep.OPTIONAL_FEATURES -> SetupStep.LLM_CONFIGURATION
            SetupStep.ACCOUNT_AND_CONFIRMATION -> SetupStep.OPTIONAL_FEATURES
            SetupStep.COMPLETE -> SetupStep.ACCOUNT_AND_CONFIRMATION
        }

        _state.value = currentState.copy(currentStep = prevStep)
    }

    // ========== Covenant Metrics Opt-In ==========

    /**
     * Set covenant metrics consent for AI alignment research.
     * When enabled, anonymous metrics (reasoning scores, decision patterns,
     * LLM provider/API base URL) are shared with CIRIS L3C.
     * No message content or PII is ever sent.
     */
    fun setCovenantMetricsConsent(consent: Boolean) {
        _state.value = _state.value.copy(covenantMetricsConsent = consent)
    }

    // ========== Adapter Configuration ==========

    /**
     * Load available adapters from the setup API.
     * Call this when entering the OPTIONAL_FEATURES step.
     *
     * Adapters with enabled_by_default=true are automatically selected.
     * This includes ciris_hosted_tools when user has CIRIS AI services.
     */
    suspend fun loadAvailableAdapters(
        fetchFunc: suspend () -> List<ai.ciris.mobile.shared.models.CommunicationAdapter>
    ) {
        _state.value = _state.value.copy(adaptersLoading = true)
        try {
            val adapters = fetchFunc()

            // Auto-select adapters that have enabled_by_default=true
            // This includes ciris_hosted_tools for CIRIS AI services users
            val autoEnabled = adapters
                .filter { it.enabled_by_default }
                .map { it.id }
                .toSet()

            // Merge with existing enabled adapters (api is always in the set)
            val newEnabled = _state.value.enabledAdapterIds + autoEnabled

            _state.value = _state.value.copy(
                availableAdapters = adapters,
                enabledAdapterIds = newEnabled,
                adaptersLoading = false
            )
        } catch (e: Exception) {
            _state.value = _state.value.copy(adaptersLoading = false)
        }
    }

    /**
     * Toggle an adapter's enabled state.
     * Note: "api" adapter cannot be disabled.
     */
    fun toggleAdapter(adapterId: String, enabled: Boolean) {
        if (adapterId == "api") return // API adapter is always enabled

        val currentEnabled = _state.value.enabledAdapterIds.toMutableSet()
        if (enabled) {
            currentEnabled.add(adapterId)
        } else {
            currentEnabled.remove(adapterId)
        }
        _state.value = _state.value.copy(enabledAdapterIds = currentEnabled)
    }

    /**
     * Check if an adapter is enabled.
     */
    fun isAdapterEnabled(adapterId: String): Boolean {
        return _state.value.enabledAdapterIds.contains(adapterId)
    }

    /**
     * Reset to welcome step.
     */
    fun resetToWelcome() {
        _state.value = _state.value.copy(currentStep = SetupStep.WELCOME)
    }

    // ========== Validation ==========
    // Source: SetupWizardActivity.kt:209-286

    /**
     * Get validation error message for current step, or null if valid.
     */
    fun getValidationError(): String? {
        return _state.value.getStepValidationError()
    }

    /**
     * Validate LLM configuration by making a test call.
     *
     * This should be implemented per-platform using expect/actual:
     * - Android: Use HttpURLConnection
     * - iOS: Use URLSession
     *
     * Source: POST /v1/setup/validate-llm
     */
    suspend fun validateLlmConfiguration(
        validateFunc: suspend (ValidateLlmRequest) -> LlmValidationResult
    ): LlmValidationResult {
        _state.value = _state.value.copy(isValidating = true, validationError = null)

        val currentState = _state.value
        val request = ValidateLlmRequest(
            provider = when (currentState.llmProvider) {
                "OpenAI" -> "openai"
                "Anthropic" -> "anthropic"
                "Azure OpenAI" -> "other"
                "LocalAI" -> "local"
                else -> "openai"
            },
            api_key = currentState.llmApiKey,
            base_url = currentState.llmBaseUrl.takeIf { it.isNotEmpty() },
            model = currentState.llmModel.takeIf { it.isNotEmpty() }
        )

        val result = validateFunc(request)

        _state.value = _state.value.copy(
            isValidating = false,
            validationError = result.error
        )

        return result
    }

    // ========== Setup Completion ==========
    // Source: SetupWizardActivity.kt:288-389

    /**
     * Build setup completion request.
     *
     * This generates the JSON payload for POST /v1/setup/complete.
     * Handles both CIRIS proxy and BYOK modes.
     *
     * Source: SetupWizardActivity.kt:395-500
     */
    fun buildSetupRequest(): CompleteSetupRequest {
        val currentState = _state.value
        val useCirisProxy = currentState.useCirisProxy()

        // Auto-generate admin password (32 chars)
        // Source: SetupViewModel.kt:141-146
        val adminPassword = generateAdminPassword()

        // Build enabled adapters list from user selections + covenant metrics
        val enabledAdapters = buildList {
            // Add all user-selected adapters (api is always in the set)
            addAll(currentState.enabledAdapterIds)
            // Add covenant metrics adapter if consented
            if (currentState.covenantMetricsConsent) {
                add("ciris_covenant_metrics")
            }
        }

        // Build adapter config with covenant metrics settings if consented
        val adapterConfig = if (currentState.covenantMetricsConsent) {
            mapOf(
                "CIRIS_COVENANT_METRICS_CONSENT" to "true",
                "CIRIS_COVENANT_METRICS_TRACE_LEVEL" to "detailed"
            )
        } else {
            emptyMap()
        }

        return if (useCirisProxy) {
            // CIRIS Proxy mode - use Google ID token with CIRIS hosted proxy
            CompleteSetupRequest(
                llm_provider = "other", // Use "other" so backend writes OPENAI_API_BASE to .env
                llm_api_key = currentState.googleIdToken ?: "",
                llm_base_url = "https://llm.ciris.ai",  // CIRIS_LLM_PROXY_URL
                llm_model = "default",

                // European backup
                backup_llm_api_key = currentState.googleIdToken,
                backup_llm_base_url = "https://llm-eu.ciris.ai",  // CIRIS_LLM_PROXY_URL_EU
                backup_llm_model = "default",

                // Agent configuration
                template_id = "ally",  // Force Ally template for mobile
                enabled_adapters = enabledAdapters,
                adapter_config = adapterConfig,
                agent_port = 8080,

                // Admin account (auto-generated)
                system_admin_password = adminPassword,

                // Google OAuth user
                admin_username = "oauth_google_user",
                admin_password = null,
                oauth_provider = "google",
                oauth_external_id = currentState.googleUserId,
                oauth_email = currentState.googleEmail
            )
        } else {
            // BYOK mode - use user-provided API key
            val providerId = when (currentState.llmProvider) {
                "OpenAI" -> "openai"
                "Anthropic" -> "anthropic"
                "Azure OpenAI" -> "other"
                "LocalAI" -> "local"
                else -> "openai"
            }

            var apiKey = currentState.llmApiKey
            if (apiKey.isEmpty() && providerId == "local") {
                apiKey = "local"
            }

            CompleteSetupRequest(
                llm_provider = providerId,
                llm_api_key = apiKey,
                llm_base_url = currentState.llmBaseUrl.takeIf { it.isNotEmpty() },
                llm_model = currentState.llmModel.takeIf { it.isNotEmpty() },

                // Agent configuration
                template_id = "ally",  // Force Ally template for mobile
                enabled_adapters = enabledAdapters,
                adapter_config = adapterConfig,
                agent_port = 8080,

                // Admin account (auto-generated)
                system_admin_password = adminPassword,

                // Local user account
                admin_username = currentState.username.ifEmpty { "admin" },
                admin_password = currentState.userPassword
            )
        }
    }

    /**
     * Submit setup completion request.
     *
     * This should be implemented per-platform using expect/actual.
     *
     * Source: SetupWizardActivity.kt:288-389
     */
    suspend fun completeSetup(
        submitFunc: suspend (CompleteSetupRequest) -> SetupCompletionResult
    ): SetupCompletionResult {
        _state.value = _state.value.copy(isSubmitting = true, submissionError = null)

        val request = buildSetupRequest()
        val result = submitFunc(request)

        _state.value = _state.value.copy(
            isSubmitting = false,
            submissionError = result.error,
            currentStep = if (result.success) SetupStep.COMPLETE else _state.value.currentStep
        )

        return result
    }

    // ========== Utilities ==========

    /**
     * Generate a random admin password (32 chars).
     * Admin password is always auto-generated - users don't need to enter it.
     *
     * Source: SetupViewModel.kt:141-146
     */
    private fun generateAdminPassword(): String {
        val chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#\$%^&*"
        return (1..32).map { chars.random() }.joinToString("")
    }

    /**
     * Reset all setup state (useful for testing or retry).
     */
    fun resetState() {
        _state.value = SetupFormState()
    }
}
