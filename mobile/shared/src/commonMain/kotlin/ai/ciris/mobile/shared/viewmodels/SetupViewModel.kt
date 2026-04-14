package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.config.CIRISConfig
import ai.ciris.mobile.shared.models.*
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.CIRISApiClientProtocol
import ai.ciris.mobile.shared.api.LocationResultData

private const val TAG = "SetupViewModel"

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
 * - Survives configuration changes and app backgrounding (extends ViewModel)
 */
class SetupViewModel : ViewModel() {

    private val _state = MutableStateFlow(SetupFormState())
    val state: StateFlow<SetupFormState> = _state.asStateFlow()

    // OAuth poll job for adapter wizard
    private var adapterOAuthPollJob: Job? = null

    // Location search debounce job
    private var locationSearchJob: Job? = null

    // API client for location search (lazy - only needed during setup)
    private val apiClient: CIRISApiClientProtocol by lazy {
        CIRISApiClient()
    }

    // Available LLM providers for BYOK mode
    val availableProviders = listOf(
        "openai" to "OpenAI",
        "anthropic" to "Anthropic",
        "google" to "Google AI",
        "openrouter" to "OpenRouter",
        "groq" to "Groq",
        "together" to "Together AI",
        "mistral" to "Mistral",
        "cohere" to "Cohere",
        "deepseek" to "DeepSeek",
        "xai" to "xAI (Grok)",
        "azure" to "Azure OpenAI",
        "local_inference" to "Local Inference Server",
        "local" to "Local (Ollama)",
        "openai_compatible" to "OpenAI Compatible",
        "other" to "Other"
    )

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
        userId: String?,
        provider: String = "google"
    ) {
        _state.value = _state.value.copy(
            isGoogleAuth = isAuth,
            googleIdToken = idToken,
            googleEmail = email,
            googleUserId = userId,
            oauthProvider = provider,
            // Default mode: CIRIS_PROXY for Google auth, BYOK for local credentials
            setupMode = when {
                _state.value.setupMode != null -> _state.value.setupMode
                isAuth -> SetupMode.CIRIS_PROXY
                else -> SetupMode.BYOK
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

    /**
     * Select the on-device Gemma 4 provider inside BYOK mode.
     *
     * This is a convenience wrapper the wizard UI calls when the user
     * taps the "Mobile Local (On-Device)" option in the provider
     * dropdown. It sets the canonical backend provider id
     * [LOCAL_ON_DEVICE_PROVIDER_ID] in `llmProvider`, clears any
     * previously entered API key, and pre-populates the loopback base
     * URL the Python adapter serves on. Users can still come back and
     * choose a different provider (e.g. OpenAI as a backup) if they
     * want cloud fallback — the on-device adapter runs in parallel at
     * [Priority.HIGH] so the LLM bus routes local-first.
     */
    fun selectLocalOnDeviceProvider() {
        _state.value = _state.value.copy(
            setupMode = SetupMode.BYOK,
            llmProvider = LOCAL_ON_DEVICE_PROVIDER_ID,
            llmApiKey = "",
            llmBaseUrl = LOCAL_ON_DEVICE_BASE_URL,
            llmModel = LOCAL_ON_DEVICE_DEFAULT_MODEL,
        )
    }

    companion object {
        /** Canonical backend provider id for on-device Gemma 4 inference. */
        const val LOCAL_ON_DEVICE_PROVIDER_ID = "mobile_local"

        /** Display label shown in the BYOK provider dropdown. */
        const val LOCAL_ON_DEVICE_DISPLAY_NAME = "Mobile Local (On-Device)"

        /** Default model id used when the user picks on-device mode. */
        const val LOCAL_ON_DEVICE_DEFAULT_MODEL = "gemma-4-e2b"

        /**
         * Loopback base URL of the on-device OpenAI-compatible server
         * spawned by the Mobile Local LLM Python adapter. Kept in sync
         * with `MobileLocalLLMConfig.base_url()` in the Python side.
         */
        const val LOCAL_ON_DEVICE_BASE_URL = "http://127.0.0.1:8091/v1"

        /**
         * Map the current `llmProvider` state value to the canonical
         * backend provider id expected by `/v1/setup/complete` and
         * `/v1/setup/validate-llm`.
         *
         * The BYOK dropdown stores the canonical id (`anthropic`, `groq`,
         * `local_inference`, …) directly in state, so the pass-through
         * case is the common path. The explicit display-label cases
         * exist only as a back-compat shim for older state (e.g. saved
         * setup data from a previous build) that still carries raw
         * labels like `"Anthropic"`.
         *
         * Without this mapping, a user who picks any non-OpenAI
         * provider from the dropdown would silently have their
         * `llm_provider` serialised as `"openai"` because the old
         * when-block only matched display labels.
         */
        fun canonicalProviderId(value: String): String = when (value) {
            "" -> "openai"
            // Legacy display-label → canonical id mapping (pre-canonical
            // state, kept for back-compat).
            "OpenAI" -> "openai"
            "Anthropic" -> "anthropic"
            "Google AI" -> "google"
            "OpenRouter" -> "openrouter"
            "Groq" -> "groq"
            "Together AI" -> "together"
            "Azure OpenAI" -> "other"
            "LocalAI", "Local LLM" -> "local"
            "OpenAI Compatible" -> "openai_compatible"
            LOCAL_ON_DEVICE_DISPLAY_NAME -> LOCAL_ON_DEVICE_PROVIDER_ID
            // Canonical ids coming straight from `availableProviders`
            // pass through unchanged.
            else -> value
        }
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

    // ========== Language & Location Preferences ==========
    // Mirrors CLI wizard: ciris_engine/logic/setup/wizard.py:324-395

    /**
     * Set the preferred language (ISO 639-1 code).
     * Examples: "en", "am", "es", "ja", "zh"
     */
    fun setPreferredLanguage(language: String) {
        _state.value = _state.value.copy(preferredLanguage = language)
    }

    /**
     * Set the location sharing granularity.
     */
    fun setLocationGranularity(granularity: LocationGranularity) {
        _state.value = _state.value.copy(locationGranularity = granularity)
    }

    /**
     * Set the user's country.
     * Only used when locationGranularity >= COUNTRY.
     */
    fun setCountry(country: String) {
        _state.value = _state.value.copy(country = country)
    }

    /**
     * Set the user's region/state.
     * Only used when locationGranularity >= REGION.
     */
    fun setRegion(region: String) {
        _state.value = _state.value.copy(region = region)
    }

    /**
     * Set the user's city.
     * Only used when locationGranularity == CITY.
     */
    fun setCity(city: String) {
        _state.value = _state.value.copy(city = city)
    }

    /**
     * Set consent to share location data in telemetry traces.
     * When enabled, location info is included in anonymized telemetry
     * for contextual analysis (timezone patterns, regional usage, etc.).
     */
    fun setShareLocationInTraces(share: Boolean) {
        _state.value = _state.value.copy(shareLocationInTraces = share)
    }

    // ========== Location Search (Typeahead) ==========

    /**
     * Search for cities by name.
     * Uses debouncing to avoid excessive API calls during typing.
     * Results are sorted by population (largest cities first).
     *
     * @param query Search query (minimum 2 characters)
     */
    fun searchLocations(query: String) {
        // Update query immediately for responsive UI
        _state.value = _state.value.copy(locationSearchQuery = query)

        // Cancel any pending search
        locationSearchJob?.cancel()

        // Don't search for very short queries
        if (query.length < 2) {
            _state.value = _state.value.copy(
                locationSearchResults = emptyList(),
                locationSearchLoading = false
            )
            return
        }

        // Debounce: wait 300ms before searching
        locationSearchJob = viewModelScope.launch {
            _state.value = _state.value.copy(locationSearchLoading = true)

            delay(300)

            try {
                val response = apiClient.searchLocations(query = query, limit = 10)
                val results = response.results.map { result ->
                    LocationSearchResult(
                        city = result.city,
                        region = result.region,
                        country = result.country,
                        countryCode = result.countryCode,
                        latitude = result.latitude,
                        longitude = result.longitude,
                        population = result.population,
                        timezone = result.timezone,
                        displayName = result.displayName
                    )
                }
                _state.value = _state.value.copy(
                    locationSearchResults = results,
                    locationSearchLoading = false
                )
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "Location search failed: ${e.message}")
                _state.value = _state.value.copy(
                    locationSearchResults = emptyList(),
                    locationSearchLoading = false
                )
            }
        }
    }

    /**
     * Select a location from search results.
     * Auto-fills country, region, and city based on selection.
     * Sets location granularity to CITY.
     * Location is persisted after setup completes (in completeSetup).
     */
    fun selectLocation(location: LocationSearchResult) {
        _state.value = _state.value.copy(
            selectedLocation = location,
            country = location.country,
            region = location.region ?: "",
            city = location.city,
            locationGranularity = LocationGranularity.CITY,
            locationSearchQuery = location.displayName,
            locationSearchResults = emptyList()
        )
    }

    /**
     * Clear location search state.
     */
    fun clearLocationSearch() {
        locationSearchJob?.cancel()
        _state.value = _state.value.copy(
            locationSearchQuery = "",
            locationSearchResults = emptyList(),
            locationSearchLoading = false,
            selectedLocation = null
        )
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

        val nextStep = if (currentState.isNodeFlow) {
            // Node flow: WELCOME → NODE_AUTH → PREFERENCES → LLM → OPTIONAL_FEATURES → COMPLETE
            // (CIRISVerify is always bundled, no install step needed)
            when (currentState.currentStep) {
                SetupStep.WELCOME -> SetupStep.NODE_AUTH
                SetupStep.NODE_AUTH -> SetupStep.PREFERENCES
                SetupStep.PREFERENCES -> SetupStep.LLM_CONFIGURATION
                SetupStep.LLM_CONFIGURATION -> SetupStep.OPTIONAL_FEATURES
                SetupStep.OPTIONAL_FEATURES -> SetupStep.COMPLETE
                else -> SetupStep.COMPLETE
            }
        } else {
            // Normal flow: WELCOME → PREFERENCES → LLM → OPTIONAL_FEATURES → ACCOUNT → COMPLETE
            when (currentState.currentStep) {
                SetupStep.WELCOME -> SetupStep.PREFERENCES
                SetupStep.PREFERENCES -> SetupStep.LLM_CONFIGURATION
                SetupStep.LLM_CONFIGURATION -> SetupStep.OPTIONAL_FEATURES
                SetupStep.OPTIONAL_FEATURES -> SetupStep.ACCOUNT_AND_CONFIRMATION
                SetupStep.ACCOUNT_AND_CONFIRMATION -> SetupStep.COMPLETE
                else -> SetupStep.COMPLETE
            }
        }

        _state.value = currentState.copy(currentStep = nextStep)
        return true
    }

    /**
     * Move to the previous setup step.
     *
     * IMPORTANT: When going back from NODE_AUTH to WELCOME, we must reset isNodeFlow
     * so that the user can choose to NOT register this time.
     */
    fun previousStep() {
        val currentState = _state.value

        val prevStep = if (currentState.isNodeFlow) {
            // Node flow: COMPLETE → OPTIONAL_FEATURES → LLM → PREFERENCES → NODE_AUTH → WELCOME
            when (currentState.currentStep) {
                SetupStep.WELCOME -> SetupStep.WELCOME
                SetupStep.NODE_AUTH -> SetupStep.WELCOME
                SetupStep.PREFERENCES -> SetupStep.NODE_AUTH
                SetupStep.LLM_CONFIGURATION -> SetupStep.PREFERENCES
                SetupStep.OPTIONAL_FEATURES -> SetupStep.LLM_CONFIGURATION
                SetupStep.COMPLETE -> SetupStep.OPTIONAL_FEATURES
                else -> SetupStep.WELCOME
            }
        } else {
            // Normal flow: COMPLETE → ACCOUNT → OPTIONAL_FEATURES → LLM → PREFERENCES → WELCOME
            when (currentState.currentStep) {
                SetupStep.WELCOME -> SetupStep.WELCOME
                SetupStep.PREFERENCES -> SetupStep.WELCOME
                SetupStep.LLM_CONFIGURATION -> SetupStep.PREFERENCES
                SetupStep.OPTIONAL_FEATURES -> SetupStep.LLM_CONFIGURATION
                SetupStep.ACCOUNT_AND_CONFIRMATION -> SetupStep.OPTIONAL_FEATURES
                SetupStep.COMPLETE -> SetupStep.ACCOUNT_AND_CONFIRMATION
                else -> SetupStep.WELCOME
            }
        }

        // When going back from NODE_AUTH to WELCOME, reset isNodeFlow so user can
        // choose NOT to register this time (fixes bug where back->continue still went to NODE_AUTH)
        val shouldResetNodeFlow = currentState.isNodeFlow &&
            currentState.currentStep == SetupStep.NODE_AUTH &&
            prevStep == SetupStep.WELCOME

        _state.value = currentState.copy(
            currentStep = prevStep,
            isNodeFlow = if (shouldResetNodeFlow) false else currentState.isNodeFlow
        )

        // Also reset device auth state when backing out of NODE_AUTH to clear any
        // stale/error/timeout state. This ensures a clean slate for retry.
        if (shouldResetNodeFlow) {
            PlatformLogger.i(TAG, "previousStep: Backing out of NODE_AUTH, resetting device auth state")
            resetDeviceAuth()
        }
    }

    // ========== Accord Metrics Opt-In ==========

    /**
     * Set accord metrics consent for AI alignment research.
     * When enabled, anonymous metrics (reasoning scores, decision patterns,
     * LLM provider/API base URL) are shared with CIRIS L3C.
     * No message content or PII is ever sent.
     */
    fun setAccordMetricsConsent(consent: Boolean) {
        _state.value = _state.value.copy(accordMetricsConsent = consent)
    }

    // ========== Public API Services (Navigation & Weather) ==========

    /**
     * Set the email address for public API services (Navigation & Weather).
     * This email is included in User-Agent headers as required by
     * OpenStreetMap Nominatim and NOAA weather.gov usage policies.
     */
    fun setPublicApiEmail(email: String) {
        _state.value = _state.value.copy(publicApiEmail = email)
    }

    /**
     * Enable or disable public API services (Navigation & Weather).
     * When enabled, navigation:geocode can resolve location names to coordinates
     * for use with weather tools.
     */
    fun setPublicApiServicesEnabled(enabled: Boolean) {
        _state.value = _state.value.copy(publicApiServicesEnabled = enabled)
    }

    // ========== Template Selection (V1.9.7) ==========

    /**
     * Load available templates from the setup API.
     * Call this when entering the OPTIONAL_FEATURES step.
     */
    suspend fun loadAvailableTemplates(
        fetchFunc: suspend () -> List<AgentTemplateInfo>
    ) {
        _state.value = _state.value.copy(templatesLoading = true)
        try {
            val templates = fetchFunc()
            _state.value = _state.value.copy(
                availableTemplates = templates,
                templatesLoading = false
            )
        } catch (e: Exception) {
            _state.value = _state.value.copy(templatesLoading = false)
        }
    }

    /**
     * Set the selected template ID.
     */
    fun setSelectedTemplate(templateId: String) {
        _state.value = _state.value.copy(selectedTemplateId = templateId)
    }

    /**
     * Toggle advanced settings visibility.
     */
    fun setShowAdvancedSettings(show: Boolean) {
        _state.value = _state.value.copy(showAdvancedSettings = show)
    }

    /**
     * Get selected template name for display.
     */
    fun getSelectedTemplateName(): String {
        val templates = _state.value.availableTemplates
        val selectedId = _state.value.selectedTemplateId
        return templates.find { it.id == selectedId }?.name ?: "Default"
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

    // ========== Adapter Wizard (for adapters requiring configuration) ==========

    /**
     * Interface for adapter wizard API calls.
     * SetupScreen provides the implementation using apiClient.
     */
    interface AdapterWizardApi {
        suspend fun getLoadableAdapters(): LoadableAdaptersData
        suspend fun startAdapterConfiguration(adapterType: String): ConfigSessionData
        suspend fun executeConfigurationStep(sessionId: String, stepData: Map<String, String>): ConfigStepResultData
        suspend fun getConfigurationSessionStatus(sessionId: String): ConfigSessionData
        suspend fun completeAdapterConfiguration(sessionId: String): ConfigCompleteData
    }

    // Stored API instance for wizard operations
    private var wizardApi: AdapterWizardApi? = null

    /**
     * Set the API instance for wizard operations.
     * Call this before starting the wizard.
     */
    fun setWizardApi(api: AdapterWizardApi) {
        wizardApi = api
    }

    /**
     * Start the adapter wizard for a specific adapter type.
     * Called when user enables an adapter that requires configuration.
     */
    fun startAdapterWizard(adapterType: String) {
        val api = wizardApi
        if (api == null) {
            PlatformLogger.e(TAG, "startAdapterWizard: No API instance set")
            _state.value = _state.value.copy(
                adapterWizardError = "Configuration not available"
            )
            return
        }

        PlatformLogger.i(TAG, "startAdapterWizard: Starting wizard for adapter type: $adapterType")
        viewModelScope.launch {
            _state.value = _state.value.copy(
                showAdapterWizard = true,
                adapterWizardType = adapterType,
                adapterWizardLoading = true,
                adapterWizardError = null,
                adapterDiscoveredItems = emptyList(),
                adapterDiscoveryExecuted = false,
                adapterSelectOptions = emptyList()
            )
            try {
                val session = api.startAdapterConfiguration(adapterType)
                _state.value = _state.value.copy(
                    adapterWizardSession = session,
                    adapterWizardLoading = false
                )
                // Auto-execute discovery step if first step is discovery type
                if (session.currentStep?.stepType == "discovery") {
                    PlatformLogger.i(TAG, "First step is discovery, auto-executing...")
                    executeAdapterDiscoveryStepInternal(session)
                }
                // Auto-fetch options for select steps
                if (session.currentStep?.stepType == "select") {
                    PlatformLogger.i(TAG, "First step is select, auto-fetching options...")
                    fetchAdapterSelectOptionsInternal(session)
                }
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "startAdapterWizard: Failed - ${e.message}")
                _state.value = _state.value.copy(
                    adapterWizardError = "Failed to start wizard: ${e.message}",
                    adapterWizardLoading = false
                )
            }
        }
    }

    /**
     * Execute the discovery step for an adapter wizard.
     */
    fun executeAdapterDiscoveryStep() {
        val session = _state.value.adapterWizardSession ?: return
        val api = wizardApi ?: return
        PlatformLogger.i(TAG, "executeAdapterDiscoveryStep: Executing discovery for session: ${session.sessionId}")
        viewModelScope.launch {
            _state.value = _state.value.copy(
                adapterWizardLoading = true,
                adapterWizardError = null
            )
            try {
                executeAdapterDiscoveryStepInternal(session)
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "executeAdapterDiscoveryStep: Failed - ${e.message}")
                _state.value = _state.value.copy(
                    adapterWizardError = "Discovery failed: ${e.message}",
                    adapterWizardLoading = false
                )
            }
        }
    }

    private suspend fun executeAdapterDiscoveryStepInternal(session: ConfigSessionData) {
        val api = wizardApi ?: return
        val result = api.executeConfigurationStep(session.sessionId, emptyMap())
        _state.value = _state.value.copy(
            adapterDiscoveryExecuted = true,
            adapterDiscoveredItems = result.discoveredItems,
            adapterWizardLoading = false
        )
        if (result.nextStepIndex != null) {
            _state.value = _state.value.copy(
                adapterWizardSession = session.copy(currentStepIndex = result.nextStepIndex)
            )
        }
    }

    private suspend fun fetchAdapterSelectOptionsInternal(session: ConfigSessionData) {
        val api = wizardApi ?: return
        try {
            val result = api.executeConfigurationStep(session.sessionId, emptyMap())
            if (result.selectOptions.isNotEmpty()) {
                PlatformLogger.i(TAG, "Fetched ${result.selectOptions.size} select options")
                _state.value = _state.value.copy(adapterSelectOptions = result.selectOptions)
            }
        } catch (e: Exception) {
            PlatformLogger.e(TAG, "fetchAdapterSelectOptionsInternal: Failed - ${e.message}")
        }
    }

    /**
     * Select a discovered item in the wizard.
     */
    fun selectAdapterDiscoveredItem(item: DiscoveredItemData) {
        val session = _state.value.adapterWizardSession ?: return
        val api = wizardApi ?: return
        PlatformLogger.i(TAG, "selectAdapterDiscoveredItem: Selected ${item.label}")
        viewModelScope.launch {
            _state.value = _state.value.copy(adapterWizardLoading = true)
            try {
                val stepData = mapOf(
                    "selected_url" to item.value,
                    "selected_id" to item.id
                )
                val result = api.executeConfigurationStep(session.sessionId, stepData)
                handleAdapterWizardStepResult(session, result)
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "selectAdapterDiscoveredItem: Failed - ${e.message}")
                _state.value = _state.value.copy(
                    adapterWizardError = "Failed to select item: ${e.message}",
                    adapterWizardLoading = false
                )
            }
        }
    }

    /**
     * Submit a manual URL in the discovery step.
     */
    fun submitAdapterManualUrl(url: String) {
        val session = _state.value.adapterWizardSession ?: return
        val api = wizardApi ?: return
        PlatformLogger.i(TAG, "submitAdapterManualUrl: Submitting URL: $url")
        viewModelScope.launch {
            _state.value = _state.value.copy(adapterWizardLoading = true)
            try {
                val stepData = mapOf("manual_url" to url)
                val result = api.executeConfigurationStep(session.sessionId, stepData)
                handleAdapterWizardStepResult(session, result)
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "submitAdapterManualUrl: Failed - ${e.message}")
                _state.value = _state.value.copy(
                    adapterWizardError = "Failed to submit URL: ${e.message}",
                    adapterWizardLoading = false
                )
            }
        }
    }

    /**
     * Submit the current wizard step with field values.
     */
    fun submitAdapterWizardStep(stepData: Map<String, String>) {
        val session = _state.value.adapterWizardSession ?: return
        val api = wizardApi ?: return
        PlatformLogger.i(TAG, "submitAdapterWizardStep: Submitting step data: $stepData")
        viewModelScope.launch {
            _state.value = _state.value.copy(
                adapterWizardLoading = true,
                adapterWizardError = null
            )
            try {
                val result = api.executeConfigurationStep(session.sessionId, stepData)
                handleAdapterWizardStepResult(session, result)
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "submitAdapterWizardStep: Failed - ${e.message}")
                _state.value = _state.value.copy(
                    adapterWizardError = "Failed to submit step: ${e.message}",
                    adapterWizardLoading = false
                )
            }
        }
    }

    /**
     * Initiate OAuth step in the adapter wizard.
     */
    fun initiateAdapterOAuthStep() {
        val session = _state.value.adapterWizardSession ?: return
        val api = wizardApi ?: return
        PlatformLogger.i(TAG, "initiateAdapterOAuthStep: Starting OAuth for session: ${session.sessionId}")
        viewModelScope.launch {
            _state.value = _state.value.copy(
                adapterWizardLoading = true,
                adapterWizardError = null
            )
            try {
                val stepData = mapOf("callback_base_url" to "http://127.0.0.1:8080")
                val result = api.executeConfigurationStep(session.sessionId, stepData)
                if (result.oauthUrl != null) {
                    PlatformLogger.i(TAG, "OAuth URL received: ${result.oauthUrl.take(80)}...")
                    _state.value = _state.value.copy(
                        adapterOAuthUrl = result.oauthUrl,
                        adapterAwaitingOAuthCallback = true,
                        adapterWizardLoading = false
                    )
                    startAdapterOAuthPolling(session.sessionId)
                } else {
                    PlatformLogger.e(TAG, "No OAuth URL in response")
                    _state.value = _state.value.copy(
                        adapterWizardError = "Failed to get OAuth URL",
                        adapterWizardLoading = false
                    )
                }
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "initiateAdapterOAuthStep: Failed - ${e.message}")
                _state.value = _state.value.copy(
                    adapterWizardError = "OAuth initiation failed: ${e.message}",
                    adapterWizardLoading = false
                )
            }
        }
    }

    private fun startAdapterOAuthPolling(sessionId: String) {
        val api = wizardApi ?: return
        adapterOAuthPollJob?.cancel()
        adapterOAuthPollJob = viewModelScope.launch {
            PlatformLogger.i(TAG, "startAdapterOAuthPolling: Starting poll for session: $sessionId")
            var attempts = 0
            val maxAttempts = 120  // 2 minutes
            while (isActive && attempts < maxAttempts && _state.value.adapterAwaitingOAuthCallback) {
                delay(1000)
                attempts++
                try {
                    val updated = api.getConfigurationSessionStatus(sessionId)
                    val currentSession = _state.value.adapterWizardSession
                    if (currentSession != null && updated.currentStepIndex > currentSession.currentStepIndex) {
                        PlatformLogger.i(TAG, "OAuth callback received - step advanced")
                        _state.value = _state.value.copy(
                            adapterAwaitingOAuthCallback = false,
                            adapterOAuthUrl = null
                        )
                        onAdapterOAuthStepAdvanced(updated)
                        return@launch
                    }
                } catch (e: Exception) {
                    if (attempts % 10 == 0) {
                        PlatformLogger.e(TAG, "OAuth poll #$attempts failed: ${e.message}")
                    }
                }
            }
            if (_state.value.adapterAwaitingOAuthCallback) {
                PlatformLogger.e(TAG, "OAuth polling timed out")
                _state.value = _state.value.copy(
                    adapterAwaitingOAuthCallback = false,
                    adapterWizardError = "OAuth authentication timed out. Please try again."
                )
            }
        }
    }

    private suspend fun onAdapterOAuthStepAdvanced(updatedSession: ConfigSessionData) {
        _state.value = _state.value.copy(
            adapterWizardSession = updatedSession,
            adapterDiscoveredItems = emptyList(),
            adapterDiscoveryExecuted = false,
            adapterSelectOptions = emptyList()
        )

        // Check if wizard is complete
        if (updatedSession.currentStepIndex >= updatedSession.totalSteps) {
            completeAdapterWizardInternal(updatedSession)
            return
        }

        // Auto-execute discovery or fetch select options for next step
        if (updatedSession.currentStep?.stepType == "discovery") {
            executeAdapterDiscoveryStepInternal(updatedSession)
        }
        if (updatedSession.currentStep?.stepType == "select") {
            fetchAdapterSelectOptionsInternal(updatedSession)
        }
    }

    /**
     * Check OAuth status on app resume.
     */
    fun checkAdapterOAuthOnResume() {
        if (!_state.value.adapterAwaitingOAuthCallback) return
        val session = _state.value.adapterWizardSession ?: return
        val api = wizardApi ?: return
        PlatformLogger.i(TAG, "checkAdapterOAuthOnResume: Checking status...")
        viewModelScope.launch {
            try {
                val updated = api.getConfigurationSessionStatus(session.sessionId)
                if (updated.currentStepIndex > session.currentStepIndex) {
                    PlatformLogger.i(TAG, "OAuth completed while app was suspended")
                    _state.value = _state.value.copy(
                        adapterAwaitingOAuthCallback = false,
                        adapterOAuthUrl = null
                    )
                    adapterOAuthPollJob?.cancel()
                    onAdapterOAuthStepAdvanced(updated)
                }
            } catch (e: Exception) {
                PlatformLogger.e(TAG, "checkAdapterOAuthOnResume: Failed - ${e.message}")
            }
        }
    }

    private suspend fun handleAdapterWizardStepResult(session: ConfigSessionData, result: ConfigStepResultData) {
        val api = wizardApi ?: return
        try {
            val updatedSession = api.getConfigurationSessionStatus(session.sessionId)
            PlatformLogger.i(TAG, "handleAdapterWizardStepResult: Step ${updatedSession.currentStepIndex}/${updatedSession.totalSteps}")

            // Check if wizard is complete
            if (updatedSession.currentStepIndex >= updatedSession.totalSteps) {
                PlatformLogger.i(TAG, "Wizard completed!")
                completeAdapterWizardInternal(updatedSession)
                return
            }

            _state.value = _state.value.copy(
                adapterWizardSession = updatedSession,
                adapterDiscoveredItems = emptyList(),
                adapterDiscoveryExecuted = false,
                adapterSelectOptions = emptyList(),
                adapterWizardLoading = false
            )

            // Auto-execute next step if needed
            if (updatedSession.currentStep?.stepType == "discovery") {
                executeAdapterDiscoveryStepInternal(updatedSession)
            }
            if (updatedSession.currentStep?.stepType == "select") {
                fetchAdapterSelectOptionsInternal(updatedSession)
            }
        } catch (e: Exception) {
            PlatformLogger.e(TAG, "handleAdapterWizardStepResult: Failed to fetch session status - ${e.message}")
            _state.value = _state.value.copy(adapterWizardLoading = false)
            if (result.nextStepIndex != null && result.nextStepIndex >= session.totalSteps) {
                completeAdapterWizardInternal(session)
            }
        }
    }

    private suspend fun completeAdapterWizardInternal(session: ConfigSessionData) {
        val api = wizardApi ?: return
        val adapterType = _state.value.adapterWizardType
        try {
            val completeResult = api.completeAdapterConfiguration(session.sessionId)
            PlatformLogger.i(TAG, "completeAdapterWizardInternal: Completed - success=${completeResult.success}")

            // Store the collected config for this adapter
            val collectedConfig = session.collectedConfig
            val currentConfigured = _state.value.configuredAdapterData.toMutableMap()
            if (adapterType != null) {
                currentConfigured[adapterType] = collectedConfig
            }

            // Enable the adapter since it's now configured
            val currentEnabled = _state.value.enabledAdapterIds.toMutableSet()
            if (adapterType != null) {
                currentEnabled.add(adapterType)
            }

            _state.value = _state.value.copy(
                enabledAdapterIds = currentEnabled,
                configuredAdapterData = currentConfigured
            )
            closeAdapterWizard()
        } catch (e: Exception) {
            PlatformLogger.e(TAG, "completeAdapterWizardInternal: Failed - ${e.message}")
            _state.value = _state.value.copy(
                adapterWizardError = "Failed to apply configuration: ${e.message}",
                adapterWizardLoading = false
            )
        }
    }

    /**
     * Go back in the adapter wizard.
     */
    fun adapterWizardBack() {
        // For now, just close the session and clear state
        _state.value = _state.value.copy(
            adapterWizardSession = null,
            adapterWizardError = null
        )
    }

    /**
     * Close the adapter wizard dialog.
     */
    fun closeAdapterWizard() {
        PlatformLogger.i(TAG, "closeAdapterWizard: Closing wizard")
        adapterOAuthPollJob?.cancel()
        _state.value = _state.value.copy(
            showAdapterWizard = false,
            adapterWizardType = null,
            adapterWizardSession = null,
            loadableAdaptersData = null,
            adapterWizardError = null,
            adapterWizardLoading = false,
            adapterDiscoveredItems = emptyList(),
            adapterDiscoveryExecuted = false,
            adapterOAuthUrl = null,
            adapterAwaitingOAuthCallback = false,
            adapterSelectOptions = emptyList()
        )
    }

    /**
     * Reset to welcome step.
     */
    fun resetToWelcome() {
        _state.value = _state.value.copy(currentStep = SetupStep.WELCOME)
    }

    // ========== Connect to Node (Device Auth Flow) ==========

    /**
     * Update the node URL for the Connect to Node flow.
     */
    fun updateNodeUrl(url: String) {
        _state.value = _state.value.copy(
            deviceAuth = _state.value.deviceAuth.copy(nodeUrl = url)
        )
    }

    /**
     * Enter the node flow from the WELCOME step.
     * Sets isNodeFlow=true and transitions to NODE_AUTH step.
     */
    fun enterNodeFlow() {
        _state.value = _state.value.copy(
            isNodeFlow = true,
            currentStep = SetupStep.NODE_AUTH
        )
    }

    /**
     * Initiate device auth with the target CIRISNode.
     * Calls POST /v1/setup/connect-node which:
     * 1. Fetches node manifest
     * 2. Initiates device auth with Portal
     * 3. Returns verification URL for user
     *
     * @param connectFunc Platform-specific HTTP call to POST /v1/setup/connect-node
     */
    suspend fun startNodeConnection(
        connectFunc: suspend (nodeUrl: String) -> ConnectNodeResult
    ) {
        val nodeUrl = _state.value.deviceAuth.nodeUrl
        if (nodeUrl.isBlank()) return

        _state.value = _state.value.copy(
            deviceAuth = _state.value.deviceAuth.copy(
                status = DeviceAuthStatus.CONNECTING,
                error = null
            )
        )

        try {
            val result = connectFunc(nodeUrl)
            _state.value = _state.value.copy(
                deviceAuth = _state.value.deviceAuth.copy(
                    status = DeviceAuthStatus.WAITING,
                    verificationUri = result.verificationUriComplete,
                    deviceCode = result.deviceCode,
                    userCode = result.userCode,
                    portalUrl = result.portalUrl,
                    expiresIn = result.expiresIn,
                    interval = result.interval
                )
            )
        } catch (e: Exception) {
            _state.value = _state.value.copy(
                deviceAuth = _state.value.deviceAuth.copy(
                    status = DeviceAuthStatus.ERROR,
                    error = e.message ?: "Connection failed"
                )
            )
        }
    }

    /**
     * Poll for device auth completion.
     * Called periodically while status == WAITING.
     *
     * @param pollFunc Platform-specific HTTP call to GET /v1/setup/connect-node/status
     */
    suspend fun pollNodeAuthStatus(
        pollFunc: suspend (deviceCode: String, portalUrl: String) -> NodeAuthPollResult
    ) {
        PlatformLogger.i(TAG, "[pollNodeAuthStatus] ========== ENTRY ==========")
        val auth = _state.value.deviceAuth
        PlatformLogger.i(TAG, "[pollNodeAuthStatus] Current status: ${auth.status}")
        PlatformLogger.i(TAG, "[pollNodeAuthStatus] deviceCode: ${auth.deviceCode.take(16)}...")
        PlatformLogger.i(TAG, "[pollNodeAuthStatus] portalUrl: ${auth.portalUrl}")

        if (auth.status != DeviceAuthStatus.WAITING) {
            PlatformLogger.w(TAG, "[pollNodeAuthStatus] Status is ${auth.status}, not WAITING - returning early!")
            return
        }

        try {
            PlatformLogger.i(TAG, "[pollNodeAuthStatus] Invoking pollFunc...")
            val result = pollFunc(auth.deviceCode, auth.portalUrl)
            PlatformLogger.i(TAG, "[pollNodeAuthStatus] pollFunc returned: status=${result.status}, keyId=${result.keyId}, error=${result.error}")
            when (result.status) {
                "pending" -> {
                    PlatformLogger.i(TAG, "pollNodeAuthStatus: status=pending, keep polling")
                }
                "complete" -> {
                    PlatformLogger.i(TAG, "pollNodeAuthStatus: COMPLETE - keyId=${result.keyId}, signingKeyB64=${result.signingKeyB64?.take(20)}...")
                    PlatformLogger.i(TAG, "pollNodeAuthStatus: template=${result.template}, adapters=${result.adapters}")
                    _state.value = _state.value.copy(
                        deviceAuth = auth.copy(
                            status = DeviceAuthStatus.COMPLETE,
                            provisionedTemplate = result.template,
                            provisionedAdapters = result.adapters ?: emptyList(),
                            signingKeyB64 = result.signingKeyB64,
                            keyId = result.keyId,
                            orgId = result.orgId,
                            stewardshipTier = result.stewardshipTier
                        ),
                        // Lock template to provisioned value in node flow
                        selectedTemplateId = result.template ?: "default",
                        enabledAdapterIds = (result.adapters ?: emptyList()).toSet() + "api"
                    )
                }
                else -> {
                    PlatformLogger.w(TAG, "[pollNodeAuthStatus] Unknown/error status: ${result.status}, error: ${result.error}")
                    _state.value = _state.value.copy(
                        deviceAuth = auth.copy(
                            status = DeviceAuthStatus.ERROR,
                            error = result.error ?: "Authorization failed"
                        )
                    )
                }
            }
            PlatformLogger.i(TAG, "[pollNodeAuthStatus] ========== EXIT (success) ==========")
        } catch (e: Exception) {
            PlatformLogger.e(TAG, "[pollNodeAuthStatus] EXCEPTION: ${e.message}")
            PlatformLogger.e(TAG, "[pollNodeAuthStatus] Exception type: ${e::class.simpleName}")
            _state.value = _state.value.copy(
                deviceAuth = auth.copy(
                    status = DeviceAuthStatus.ERROR,
                    error = e.message ?: "Polling failed"
                )
            )
            PlatformLogger.i(TAG, "[pollNodeAuthStatus] ========== EXIT (exception) ==========")
        }
    }

    // ========== CIRISVerify Setup ==========

    /**
     * Toggle CIRISVerify installation.
     */
    fun setVerifyEnabled(enabled: Boolean) {
        _state.value = _state.value.copy(
            verifySetup = _state.value.verifySetup.copy(enabled = enabled)
        )
    }

    /**
     * Toggle hardware requirement for CIRISVerify.
     */
    fun setVerifyRequireHardware(require: Boolean) {
        _state.value = _state.value.copy(
            verifySetup = _state.value.verifySetup.copy(requireHardware = require)
        )
    }

    /**
     * Download and configure CIRISVerify binary.
     * TODO: Implement actual binary download from CIRIS CDN or GitHub releases.
     * MVP: Stub that sets downloaded=true for UI flow testing.
     *
     * @param downloadFunc Platform-specific download function
     */
    suspend fun downloadVerifyBinary(
        downloadFunc: suspend () -> VerifyDownloadResult
    ) {
        _state.value = _state.value.copy(
            verifySetup = _state.value.verifySetup.copy(
                downloading = true,
                error = null
            )
        )

        try {
            val result = downloadFunc()
            _state.value = _state.value.copy(
                verifySetup = _state.value.verifySetup.copy(
                    downloading = false,
                    downloaded = true,
                    binaryPath = result.binaryPath,
                    version = result.version
                )
            )
        } catch (e: Exception) {
            _state.value = _state.value.copy(
                verifySetup = _state.value.verifySetup.copy(
                    downloading = false,
                    error = e.message ?: "Download failed"
                )
            )
        }
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

        // On-device inference does not hit any external endpoint, so
        // there is nothing to validate here — the device capability
        // probe is the validation step for this provider. Return
        // success immediately so the wizard's "Test connection" action
        // does not appear broken.
        val providerLower = currentState.llmProvider.lowercase()
        if (providerLower == LOCAL_ON_DEVICE_PROVIDER_ID ||
            providerLower.startsWith("mobile local")) {
            val ok = LlmValidationResult(
                valid = true,
                message = "On-device inference — no remote endpoint to validate",
                error = null,
            )
            _state.value = _state.value.copy(isValidating = false, validationError = null)
            return ok
        }

        val request = ValidateLlmRequest(
            provider = canonicalProviderId(currentState.llmProvider),
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

        // Debug logging for node flow
        PlatformLogger.i(TAG, "buildSetupRequest: isNodeFlow=${currentState.isNodeFlow}, deviceAuth.status=${currentState.deviceAuth.status}")
        PlatformLogger.i(TAG, "buildSetupRequest: deviceAuth.keyId=${currentState.deviceAuth.keyId}, signingKeyB64=${currentState.deviceAuth.signingKeyB64?.take(20)}...")

        // Auto-generate admin password (32 chars)
        // Source: SetupViewModel.kt:141-146
        val adminPassword = generateAdminPassword()

        // Build enabled adapters list from user selections + consent-based adapters
        val enabledAdapters = buildList {
            // Add all user-selected adapters (api is always in the set)
            addAll(currentState.enabledAdapterIds)
            // Add accord metrics adapter if consented
            if (currentState.accordMetricsConsent) {
                add("ciris_accord_metrics")
            }
            // Add navigation & weather adapters if public API services enabled
            if (currentState.publicApiServicesEnabled && currentState.publicApiEmail.isNotBlank()) {
                add("navigation")
                add("weather")
            }
            // Add mobile_local_llm adapter if on-device inference is selected
            if (currentState.llmProvider == LOCAL_ON_DEVICE_PROVIDER_ID ||
                currentState.llmProvider == LOCAL_ON_DEVICE_DISPLAY_NAME) {
                add("mobile_local_llm")
            }
        }

        // Build adapter config with consent settings and adapter-specific config
        val adapterConfig = buildMap {
            // Accord metrics settings
            if (currentState.accordMetricsConsent) {
                put("CIRIS_ACCORD_METRICS_CONSENT", "true")
                put("CIRIS_ACCORD_METRICS_TRACE_LEVEL", "detailed")
            }
            // Public API services (Navigation & Weather)
            if (currentState.publicApiServicesEnabled && currentState.publicApiEmail.isNotBlank()) {
                put("PUBLIC_API_CONTACT_EMAIL", currentState.publicApiEmail)
            }
            // Include adapter-specific config from wizard (e.g., HA OAuth tokens)
            // configuredAdapterData is Map<String, Map<String, String>>
            for ((_, config) in currentState.configuredAdapterData) {
                putAll(config)
            }
        }

        // Node flow fields (if provisioned via Portal)
        val nodeFlowData = if (currentState.isNodeFlow && currentState.deviceAuth.status == DeviceAuthStatus.COMPLETE) {
            val da = currentState.deviceAuth
            PlatformLogger.i(TAG, "Node flow COMPLETE - extracting NodeFlowData: keyId=${da.keyId}, signingKeyB64=${da.signingKeyB64?.take(20)}...")
            NodeFlowData(
                nodeUrl = da.nodeUrl.takeIf { it.isNotEmpty() },
                identityTemplate = da.provisionedTemplate,
                stewardshipTier = da.stewardshipTier,
                approvedAdapters = da.provisionedAdapters.takeIf { it.isNotEmpty() },
                orgId = da.orgId,
                signingKeyProvisioned = da.signingKeyB64 != null,
                provisionedSigningKeyB64 = da.signingKeyB64,
                keyId = da.keyId
            )
        } else {
            PlatformLogger.w(TAG, "Node flow NOT complete or not in node flow - nodeFlowData will be null (isNodeFlow=${currentState.isNodeFlow}, status=${currentState.deviceAuth.status})")
            null
        }

        return if (useCirisProxy) {
            // CIRIS Proxy mode - use Google ID token with CIRIS hosted proxy
            CompleteSetupRequest(
                llm_provider = "other", // Use "other" so backend writes OPENAI_API_BASE to .env
                llm_api_key = currentState.googleIdToken ?: "",
                llm_base_url = CIRISConfig.CIRIS_LLM_PROXY_URL,  // US: llm01.ciris-services-1.ai
                llm_model = "default",

                // European backup
                backup_llm_api_key = currentState.googleIdToken,
                backup_llm_base_url = CIRISConfig.CIRIS_LLM_PROXY_URL_EU,  // EU: llm01.ciris-services-eu-1.com
                backup_llm_model = "default",

                // Agent configuration
                template_id = nodeFlowData?.identityTemplate ?: currentState.selectedTemplateId,
                enabled_adapters = enabledAdapters,
                adapter_config = adapterConfig,
                agent_port = 8080,

                // Admin account (auto-generated)
                system_admin_password = adminPassword,

                // OAuth user
                admin_username = "oauth_${currentState.oauthProvider}_user",
                admin_password = null,
                oauth_provider = currentState.oauthProvider,
                oauth_external_id = currentState.googleUserId,
                oauth_email = currentState.googleEmail,

                // Language and location preferences (extract from selectedLocation)
                preferred_language = currentState.preferredLanguage,
                location_country = currentState.selectedLocation?.country,
                location_region = currentState.selectedLocation?.region,
                location_city = currentState.selectedLocation?.city ?: currentState.city.takeIf { it.isNotEmpty() },
                location_latitude = currentState.selectedLocation?.latitude,
                location_longitude = currentState.selectedLocation?.longitude,
                timezone = currentState.selectedLocation?.timezone,
                share_location_in_traces = currentState.shareLocationInTraces,

                // Node flow fields
                node_url = nodeFlowData?.nodeUrl,
                identity_template = nodeFlowData?.identityTemplate,
                stewardship_tier = nodeFlowData?.stewardshipTier,
                approved_adapters = nodeFlowData?.approvedAdapters,
                org_id = nodeFlowData?.orgId,
                signing_key_provisioned = nodeFlowData?.signingKeyProvisioned ?: false,  // Must be boolean, not null
                provisioned_signing_key_b64 = nodeFlowData?.provisionedSigningKeyB64,
                signing_key_id = nodeFlowData?.keyId
            )
        } else {
            // BYOK mode — user-provided API key, or keyless providers
            // (LocalAI / Ollama, or on-device Gemma 4 via the
            // mobile_local adapter). `llmProvider` already holds the
            // canonical id (set by `setLlmProvider(key)` from the
            // dropdown); `canonicalProviderId()` also maps legacy
            // display labels for back-compat.
            val providerId = canonicalProviderId(currentState.llmProvider)

            var apiKey = currentState.llmApiKey
            if (apiKey.isEmpty() && providerId == "local") {
                apiKey = "local"
            }
            if (providerId == LOCAL_ON_DEVICE_PROVIDER_ID) {
                // No external credential is required: the Python adapter
                // runs its own OpenAI-compatible server on loopback.
                apiKey = ""
            }

            // For BYOK mode, we still need OAuth fields if user authenticated via OAuth
            // This allows OAuth users to use their own API keys while still using OAuth for login
            val isOAuthUser = currentState.isGoogleAuth && currentState.googleUserId != null

            CompleteSetupRequest(
                llm_provider = providerId,
                llm_api_key = apiKey,
                llm_base_url = currentState.llmBaseUrl.takeIf { it.isNotEmpty() },
                llm_model = currentState.llmModel.takeIf { it.isNotEmpty() },

                // Agent configuration
                template_id = nodeFlowData?.identityTemplate ?: currentState.selectedTemplateId,
                enabled_adapters = enabledAdapters,
                adapter_config = adapterConfig,
                agent_port = 8080,

                // Admin account (auto-generated)
                system_admin_password = adminPassword,

                // User account - OAuth users get auto-generated username, local users provide their own
                admin_username = if (isOAuthUser) {
                    "oauth_${currentState.oauthProvider}_user"
                } else {
                    currentState.username.ifEmpty { "admin" }
                },
                admin_password = if (isOAuthUser) null else currentState.userPassword,

                // OAuth fields - include if user authenticated via OAuth (even in BYOK mode)
                oauth_provider = if (isOAuthUser) currentState.oauthProvider else null,
                oauth_external_id = if (isOAuthUser) currentState.googleUserId else null,
                oauth_email = if (isOAuthUser) currentState.googleEmail else null,

                // Language and location preferences (extract from selectedLocation)
                preferred_language = currentState.preferredLanguage,
                location_country = currentState.selectedLocation?.country,
                location_region = currentState.selectedLocation?.region,
                location_city = currentState.selectedLocation?.city ?: currentState.city.takeIf { it.isNotEmpty() },
                location_latitude = currentState.selectedLocation?.latitude,
                location_longitude = currentState.selectedLocation?.longitude,
                timezone = currentState.selectedLocation?.timezone,
                share_location_in_traces = currentState.shareLocationInTraces,

                // Node flow fields
                node_url = nodeFlowData?.nodeUrl,
                identity_template = nodeFlowData?.identityTemplate,
                stewardship_tier = nodeFlowData?.stewardshipTier,
                approved_adapters = nodeFlowData?.approvedAdapters,
                org_id = nodeFlowData?.orgId,
                signing_key_provisioned = nodeFlowData?.signingKeyProvisioned ?: false,  // Must be boolean, not null
                provisioned_signing_key_b64 = nodeFlowData?.provisionedSigningKeyB64,
                signing_key_id = nodeFlowData?.keyId
            )
        }
    }

    /**
     * Helper data class for node flow fields.
     */
    private data class NodeFlowData(
        val nodeUrl: String?,
        val identityTemplate: String?,
        val stewardshipTier: Int?,
        val approvedAdapters: List<String>?,
        val orgId: String?,
        val signingKeyProvisioned: Boolean?,
        val provisionedSigningKeyB64: String?,
        val keyId: String?
    )

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
        PlatformLogger.i(TAG, "completeSetup: signing_key_id=${request.signing_key_id}, signing_key_provisioned=${request.signing_key_provisioned}")
        PlatformLogger.i(TAG, "completeSetup: provisioned_signing_key_b64=${request.provisioned_signing_key_b64?.take(20)}...")
        val result = submitFunc(request)

        // After setup completes (.env now exists), persist location if selected
        if (result.success) {
            val selectedLocation = _state.value.selectedLocation
            if (selectedLocation != null) {
                try {
                    val locationData = LocationResultData(
                        city = selectedLocation.city,
                        region = selectedLocation.region,
                        country = selectedLocation.country,
                        countryCode = selectedLocation.countryCode,
                        latitude = selectedLocation.latitude,
                        longitude = selectedLocation.longitude,
                        population = selectedLocation.population,
                        timezone = selectedLocation.timezone,
                        displayName = selectedLocation.displayName
                    )
                    val locResult = apiClient.updateUserLocation(locationData)
                    if (locResult.success) {
                        PlatformLogger.i(TAG, "completeSetup: Location persisted: ${locResult.locationDisplay}")
                    } else {
                        PlatformLogger.e(TAG, "completeSetup: Failed to persist location: ${locResult.message}")
                    }
                } catch (e: Exception) {
                    PlatformLogger.e(TAG, "completeSetup: Location persist error: ${e.message}")
                }
            }
        }

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

    /**
     * Reset device auth state only.
     * Called when user backs out of NODE_AUTH step to clear any stale/error state.
     * This allows the user to retry the node flow with a clean slate.
     */
    fun resetDeviceAuth() {
        PlatformLogger.i(TAG, "resetDeviceAuth: Clearing device auth state")
        _state.value = _state.value.copy(
            deviceAuth = DeviceAuthState()  // Reset to default empty state
        )
    }
}
