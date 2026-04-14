package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.LocationResultData
import ai.ciris.mobile.shared.ui.theme.BrightnessPreference
import ai.ciris.mobile.shared.ui.theme.ColorTheme
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.api.LlmConfigData
import ai.ciris.mobile.shared.platform.AppRestarter
import ai.ciris.mobile.shared.platform.EnvFileUpdater
import ai.ciris.mobile.shared.platform.SecureStorage
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Settings ViewModel
 * Manages app settings with context-awareness for CIRIS Proxy vs BYOK mode.
 *
 * Mode detection is done by reading the .env file directly (not via API),
 * which is more reliable for mobile since the API requires authentication.
 *
 * - CIRIS Proxy: llmBaseUrl contains CIRIS proxy hostnames
 * - BYOK: User's own API key with custom provider
 */
class SettingsViewModel(
    private val secureStorage: SecureStorage,
    private val apiClient: CIRISApiClient,
    private val envFileUpdater: EnvFileUpdater
) : ViewModel() {

    companion object {
        private const val TAG = "SettingsViewModel"
    }

    private fun log(level: String, method: String, message: String) {
        val fullMessage = "[$method] $message"
        when (level) {
            "DEBUG" -> PlatformLogger.d(TAG, fullMessage)
            "INFO" -> PlatformLogger.i(TAG, fullMessage)
            "WARN" -> PlatformLogger.w(TAG, fullMessage)
            "ERROR" -> PlatformLogger.e(TAG, fullMessage)
            else -> PlatformLogger.i(TAG, fullMessage)
        }
    }

    private fun logDebug(method: String, message: String) = log("DEBUG", method, message)
    private fun logInfo(method: String, message: String) = log("INFO", method, message)
    private fun logWarn(method: String, message: String) = log("WARN", method, message)
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    // ========== State Flows ==========

    // Loading state
    private val _isLoading = MutableStateFlow(true)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    // LLM configuration from backend
    private val _llmConfig = MutableStateFlow<LlmConfigData?>(null)
    val llmConfig: StateFlow<LlmConfigData?> = _llmConfig.asStateFlow()

    // Is using CIRIS Proxy (vs BYOK)
    private val _isCirisProxy = MutableStateFlow(false)
    val isCirisProxy: StateFlow<Boolean> = _isCirisProxy.asStateFlow()

    // BYOK fields (only used in BYOK mode)
    private val _llmProvider = MutableStateFlow("openai")
    val llmProvider: StateFlow<String> = _llmProvider.asStateFlow()

    private val _llmModel = MutableStateFlow("")
    val llmModel: StateFlow<String> = _llmModel.asStateFlow()

    private val _llmBaseUrl = MutableStateFlow("")
    val llmBaseUrl: StateFlow<String> = _llmBaseUrl.asStateFlow()

    private val _apiKey = MutableStateFlow("")
    val apiKey: StateFlow<String> = _apiKey.asStateFlow()

    private val _apiKeyMasked = MutableStateFlow("")
    val apiKeyMasked: StateFlow<String> = _apiKeyMasked.asStateFlow()

    // Operation states
    private val _isSaving = MutableStateFlow(false)
    val isSaving: StateFlow<Boolean> = _isSaving.asStateFlow()

    private val _saveSuccess = MutableStateFlow(false)
    val saveSuccess: StateFlow<Boolean> = _saveSuccess.asStateFlow()

    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage: StateFlow<String?> = _errorMessage.asStateFlow()

    // Live background setting (persisted)
    private val _liveBackgroundEnabled = MutableStateFlow(true)  // Default enabled
    val liveBackgroundEnabled: StateFlow<Boolean> = _liveBackgroundEnabled.asStateFlow()

    // Color theme setting (persisted) - Vapor (pink/cyan/plum) is default
    private val _colorTheme = MutableStateFlow(ColorTheme.DEFAULT)
    val colorTheme: StateFlow<ColorTheme> = _colorTheme.asStateFlow()

    // Brightness preference (persisted) - System is default
    private val _brightnessPreference = MutableStateFlow(BrightnessPreference.SYSTEM)
    val brightnessPreference: StateFlow<BrightnessPreference> = _brightnessPreference.asStateFlow()

    // ========== Location Settings ==========

    // Location search state
    private val _locationSearchQuery = MutableStateFlow("")
    val locationSearchQuery: StateFlow<String> = _locationSearchQuery.asStateFlow()

    private val _locationSearchResults = MutableStateFlow<List<LocationResultData>>(emptyList())
    val locationSearchResults: StateFlow<List<LocationResultData>> = _locationSearchResults.asStateFlow()

    private val _locationSearchLoading = MutableStateFlow(false)
    val locationSearchLoading: StateFlow<Boolean> = _locationSearchLoading.asStateFlow()

    private val _selectedLocation = MutableStateFlow<LocationResultData?>(null)
    val selectedLocation: StateFlow<LocationResultData?> = _selectedLocation.asStateFlow()

    private val _currentLocationDisplay = MutableStateFlow<String?>(null)
    val currentLocationDisplay: StateFlow<String?> = _currentLocationDisplay.asStateFlow()

    private var locationSearchJob: Job? = null

    // Available LLM providers for BYOK mode.
    //
    // The "mobile_local" entry is the on-device Gemma 4 provider backed by
    // the `mobile_local_llm` Python adapter. The first-start wizard only
    // surfaces it when `probeLocalInferenceCapability()` returns a capable
    // or stub tier — this list exposes it for settings too so a user who
    // sideloads a model on iOS can flip to on-device inference later.
    val availableProviders = listOf(
        "mobile_local" to "On-Device (Local Gemma 4)",
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

    // Available models per provider (static fallbacks for cloud providers only)
    // Local providers should ALWAYS query - no hardcoded defaults
    private val modelsByProvider = mapOf(
        "openai" to listOf("gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"),
        "anthropic" to listOf("claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"),
        "other" to listOf("default")
        // NOTE: "local" and "openai_compatible" intentionally omitted - always query the endpoint
    )

    private val _availableModels = MutableStateFlow<List<String>>(emptyList())
    val availableModels: StateFlow<List<String>> = _availableModels.asStateFlow()

    // ========== Local Inference Server Discovery ==========

    // Discovered servers from network scan
    private val _discoveredServers = MutableStateFlow<List<DiscoveredLlmServer>>(emptyList())
    val discoveredServers: StateFlow<List<DiscoveredLlmServer>> = _discoveredServers.asStateFlow()

    // Currently selected server (for local_inference provider)
    private val _selectedServer = MutableStateFlow<DiscoveredLlmServer?>(null)
    val selectedServer: StateFlow<DiscoveredLlmServer?> = _selectedServer.asStateFlow()

    // Discovery in progress flag
    private val _isDiscovering = MutableStateFlow(false)
    val isDiscovering: StateFlow<Boolean> = _isDiscovering.asStateFlow()

    // Track if we've loaded config
    private var hasLoadedConfig = false

    init {
        // Don't auto-load here - wait for refresh() to be called when screen is shown
        // This avoids making API calls before authentication is complete
        logDebug("init", "SettingsViewModel created, waiting for refresh() call")

        // Load persisted display settings immediately (no auth needed)
        loadDisplaySettings()
    }

    /**
     * Load display-related settings that don't require authentication.
     */
    private fun loadDisplaySettings() {
        viewModelScope.launch {
            try {
                logInfo("loadDisplaySettings", ">>> Loading live_background_enabled from secure storage...")
                secureStorage.get("live_background_enabled").onSuccess { value ->
                    // Default to true if not set
                    val newValue = value?.toBooleanStrictOrNull() ?: true
                    logInfo("loadDisplaySettings", ">>> Raw value='$value', parsed=$newValue")
                    _liveBackgroundEnabled.value = newValue
                    logInfo("loadDisplaySettings", ">>> Live background state set to: ${_liveBackgroundEnabled.value}")
                }.onFailure { error ->
                    logWarn("loadDisplaySettings", ">>> Storage get failed: ${error.message}, defaulting to true")
                    _liveBackgroundEnabled.value = true
                }

                // Load color theme
                secureStorage.get("color_theme").onSuccess { value ->
                    _colorTheme.value = ColorTheme.fromString(value)
                    logInfo("loadDisplaySettings", ">>> Color theme loaded: ${_colorTheme.value}")
                }.onFailure {
                    _colorTheme.value = ColorTheme.DEFAULT
                }

                // Load brightness preference
                secureStorage.get("brightness_preference").onSuccess { value ->
                    _brightnessPreference.value = BrightnessPreference.fromString(value)
                    logInfo("loadDisplaySettings", ">>> Brightness preference loaded: ${_brightnessPreference.value}")
                }.onFailure {
                    _brightnessPreference.value = BrightnessPreference.SYSTEM
                }
            } catch (e: Exception) {
                logWarn("loadDisplaySettings", ">>> Exception loading display settings: ${e.message}, defaulting to true")
                _liveBackgroundEnabled.value = true
            }
        }
    }

    /**
     * Load LLM configuration from the API (same endpoint as InteractScreen badge).
     * Falls back to .env file if the API call fails.
     *
     * Uses apiClient.getLlmConfig() to ensure the badge and settings page
     * always show the same provider, model, and proxy status.
     */
    private fun loadLlmConfig() {
        val method = "loadLlmConfig"
        logInfo(method, "Loading LLM configuration")

        viewModelScope.launch {
            _isLoading.value = true
            _errorMessage.value = null

            try {
                // Primary: use the same API endpoint as the InteractScreen badge
                val config = apiClient.getLlmConfig()
                applyConfig(config, method, "API")
            } catch (e: Exception) {
                logWarn(method, "API config fetch failed: ${e.message}, falling back to .env")

                // Fallback: read .env file directly
                try {
                    val envConfig = envFileUpdater.readLlmConfig()
                    if (envConfig != null) {
                        val config = LlmConfigData(
                            provider = envConfig.provider,
                            baseUrl = envConfig.baseUrl,
                            model = envConfig.model ?: "default",
                            apiKeySet = envConfig.apiKeySet,
                            isCirisProxy = envConfig.isCirisProxy,
                            backupBaseUrl = null,
                            backupModel = null,
                            backupApiKeySet = false
                        )
                        applyConfig(config, method, ".env")
                    } else {
                        logWarn(method, ".env file not found, using secure storage fallback")
                        loadFallbackConfig()
                    }
                } catch (envErr: Exception) {
                    logError(method, "All config sources failed: ${envErr.message}")
                    _errorMessage.value = "Failed to load configuration: ${e.message}"
                    loadFallbackConfig()
                }
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Apply a loaded LlmConfigData to the view model state.
     * Shared by both API and .env loading paths.
     */
    private suspend fun applyConfig(config: LlmConfigData, method: String, source: String) {
        _llmConfig.value = config
        _isCirisProxy.value = config.isCirisProxy
        hasLoadedConfig = true

        logInfo(method, "LLM config loaded from $source: provider=${config.provider}, " +
                "isCirisProxy=${config.isCirisProxy}, model=${config.model}")

        if (!config.isCirisProxy) {
            // BYOK mode - populate form fields
            _llmProvider.value = config.provider
            _llmModel.value = config.model
            _llmBaseUrl.value = config.baseUrl ?: ""
            // Start with current model as fallback while fetching
            _availableModels.value = if (config.model.isNotEmpty()) listOf(config.model) else emptyList()

            // Load API key FIRST, then fetch models (must be sequential)
            loadApiKeyFromStorage(config.provider)
            // Now fetch models with the loaded API key
            logInfo(method, "API key loaded, now fetching models for provider: ${config.provider}")
            fetchModelsForProvider(config.provider)
        }

        logInfo(method, "Configuration loaded successfully from $source")
    }

    /**
     * Load API key from secure storage for BYOK mode.
     */
    private suspend fun loadApiKeyFromStorage(provider: String) {
        val method = "loadApiKeyFromStorage"
        logDebug(method, "Loading API key for provider: $provider")

        try {
            secureStorage.getApiKey(provider).onSuccess { key ->
                if (key != null) {
                    _apiKeyMasked.value = maskApiKey(key)
                    _apiKey.value = key
                    logDebug(method, "Loaded API key for $provider (masked)")
                } else {
                    logDebug(method, "No API key found for $provider")
                }
            }
        } catch (e: Exception) {
            logWarn(method, "Failed to load API key: ${e.message}")
        }
    }

    /**
     * Fallback config loading if backend call fails.
     */
    private suspend fun loadFallbackConfig() {
        val method = "loadFallbackConfig"
        logInfo(method, "Loading fallback config from secure storage")

        try {
            secureStorage.get("llm_provider").onSuccess { provider ->
                if (provider != null) {
                    _llmProvider.value = provider
                    _availableModels.value = modelsByProvider[provider] ?: emptyList()
                    _isCirisProxy.value = false // Assume BYOK if we have stored provider
                    logDebug(method, "Fallback provider: $provider")
                }
            }

            secureStorage.get("llm_model").onSuccess { model ->
                _llmModel.value = model ?: ""
            }

            secureStorage.get("llm_base_url").onSuccess { url ->
                _llmBaseUrl.value = url ?: ""
            }
        } catch (e: Exception) {
            logError(method, "Fallback config load failed: ${e.message}")
        }
    }

    /**
     * Refresh configuration from backend.
     */
    fun refresh() {
        loadLlmConfig()
    }

    // ========== BYOK Mode: Form Updates ==========

    // Default base URLs for providers that need them
    private val defaultBaseUrlsByProvider = mapOf(
        "local" to "http://127.0.0.1:11434/v1",  // Ollama default with OpenAI-compatible endpoint
        "openai_compatible" to "http://127.0.0.1:8080/v1"  // Generic local server
    )

    /**
     * Update LLM provider (BYOK mode only).
     * Resets base URL and API key to provider defaults, then fetches available models.
     */
    fun onProviderChanged(provider: String) {
        if (_isCirisProxy.value) {
            logWarn("onProviderChanged", "Cannot change provider in CIRIS Proxy mode")
            return
        }

        val method = "onProviderChanged"
        logInfo(method, "Provider changed to: $provider")

        _llmProvider.value = provider

        // Reset base URL to provider's default (clear for cloud providers, set localhost for local)
        val defaultBaseUrl = defaultBaseUrlsByProvider[provider] ?: ""
        _llmBaseUrl.value = defaultBaseUrl
        logInfo(method, "Reset base URL to: ${defaultBaseUrl.ifEmpty { "(empty - use provider default)" }}")

        // Clear API key for local providers (they don't need one)
        // For cloud providers, load from storage
        if (provider == "local" || provider == "openai_compatible" || provider == "local_inference") {
            _apiKey.value = ""
            _apiKeyMasked.value = ""
            logInfo(method, "Cleared API key for local provider")
        }

        // For local_inference, trigger discovery instead of using static list
        if (provider == "local_inference") {
            _availableModels.value = emptyList()
            _llmModel.value = ""
            _selectedServer.value = null
            _discoveredServers.value = emptyList()
            discoverLocalServers()
            return
        }

        // Use static fallback first while fetching
        _availableModels.value = modelsByProvider[provider] ?: emptyList()

        // Reset model to first available
        _llmModel.value = modelsByProvider[provider]?.firstOrNull() ?: ""

        // Load API key for cloud providers and fetch live models
        viewModelScope.launch {
            if (provider != "local" && provider != "openai_compatible") {
                loadApiKeyFromStorage(provider)
            }
            fetchModelsForProvider(provider)
        }
    }

    // ========== Local Inference Server Discovery ==========

    /**
     * Discover local LLM inference servers on the network.
     * Probes hostnames like jetson.local, ollama.local, etc.
     * Also scans localhost ports for common LLM servers.
     */
    fun discoverLocalServers() {
        val method = "discoverLocalServers"
        logInfo(method, "Starting local LLM server discovery...")

        viewModelScope.launch {
            _isDiscovering.value = true
            _discoveredServers.value = emptyList()

            try {
                val servers = apiClient.discoverLocalLlmServers(
                    timeoutSeconds = 5.0f,
                    includeLocalhost = true
                )

                _discoveredServers.value = servers
                logInfo(method, "Discovered ${servers.size} local LLM servers")

                // Auto-select first server if only one found
                if (servers.size == 1) {
                    selectServer(servers.first())
                }
            } catch (e: Exception) {
                logError(method, "Discovery failed: ${e.message}")
                _discoveredServers.value = emptyList()
            } finally {
                _isDiscovering.value = false
            }
        }
    }

    /**
     * Select a discovered server as the LLM endpoint.
     * Sets the base URL and fetches available models from the server.
     */
    fun selectServer(server: DiscoveredLlmServer) {
        val method = "selectServer"
        logInfo(method, "Selected server: ${server.label} (${server.url})")

        _selectedServer.value = server

        // Set base URL to server's URL with /v1 suffix for OpenAI-compatible endpoint
        val baseUrl = when (server.serverType) {
            "ollama" -> "${server.url}/v1"  // Ollama needs /v1 for OpenAI-compat
            else -> "${server.url}/v1"      // Most servers use /v1
        }
        _llmBaseUrl.value = baseUrl
        logInfo(method, "Set base URL to: $baseUrl")

        // If server reported models, use them directly
        if (server.models.isNotEmpty()) {
            _availableModels.value = server.models
            _llmModel.value = server.models.first()
            logInfo(method, "Using ${server.models.size} models from discovery: ${server.models}")
        } else {
            // Otherwise fetch from the server's API
            viewModelScope.launch {
                fetchModelsForProvider("local")
            }
        }
    }

    /**
     * Fetch available models from API for a provider.
     * Falls back to static list if API call fails.
     */
    private suspend fun fetchModelsForProvider(provider: String) {
        val method = "fetchModelsForProvider"
        logInfo(method, "Fetching models for provider: $provider")

        try {
            // Map display name to provider ID for API
            val providerId = when (provider.lowercase()) {
                "openai" -> "openai"
                "openrouter" -> "openrouter"
                "anthropic" -> "anthropic"
                "google ai", "google" -> "google"
                "groq" -> "groq"
                "together ai", "together" -> "together"
                "local", "localai" -> "local"
                else -> provider.lowercase()
            }

            // Only fetch if we have an API key
            val apiKey = _apiKey.value
            if (apiKey.isEmpty() && provider != "local") {
                logWarn(method, "No API key available, using static model list")
                return
            }

            val models = apiClient.listModels(
                provider = providerId,
                apiKey = apiKey,
                baseUrl = _llmBaseUrl.value.takeIf { it.isNotEmpty() }
            )

            if (models.isNotEmpty()) {
                _availableModels.value = models.map { it.id }
                logInfo(method, "Fetched ${models.size} models from API")

                // If current model is not in list, select first available
                if (_llmModel.value !in _availableModels.value && _availableModels.value.isNotEmpty()) {
                    _llmModel.value = _availableModels.value.first()
                }
            } else {
                logWarn(method, "API returned no models, keeping static list")
            }
        } catch (e: Exception) {
            logError(method, "Failed to fetch models: ${e.message}")
            // Keep static fallback
        }
    }

    /**
     * Update LLM model (BYOK mode only).
     */
    fun onModelChanged(model: String) {
        if (_isCirisProxy.value) {
            logWarn("onModelChanged", "Cannot change model in CIRIS Proxy mode")
            return
        }
        _llmModel.value = model
    }

    /**
     * Update base URL (BYOK mode only).
     */
    fun onBaseUrlChanged(url: String) {
        if (_isCirisProxy.value) {
            logWarn("onBaseUrlChanged", "Cannot change base URL in CIRIS Proxy mode")
            return
        }
        _llmBaseUrl.value = url
    }

    /**
     * Update API key (BYOK mode only).
     */
    fun onApiKeyChanged(key: String) {
        if (_isCirisProxy.value) {
            logWarn("onApiKeyChanged", "Cannot change API key in CIRIS Proxy mode")
            return
        }
        _apiKey.value = key
        if (key.isNotEmpty()) {
            _apiKeyMasked.value = key // Don't mask while typing
        }
    }

    /**
     * Save settings (BYOK mode only).
     * Saves to both secure storage and backend .env file.
     */
    fun saveSettings() {
        val method = "saveSettings"

        if (_isCirisProxy.value) {
            logWarn(method, "Cannot save settings in CIRIS Proxy mode")
            _errorMessage.value = "Settings are managed by CIRIS in proxy mode"
            return
        }

        logInfo(method, "Saving BYOK settings: provider=${_llmProvider.value}, model=${_llmModel.value}, baseUrl=${_llmBaseUrl.value}")

        viewModelScope.launch {
            _isSaving.value = true
            _saveSuccess.value = false
            _errorMessage.value = null

            try {
                // Validate
                if (_apiKey.value.isEmpty() && _llmProvider.value != "local") {
                    logWarn(method, "Validation failed: API key is required")
                    throw Exception("API key is required")
                }

                // Map provider display name to ID for API
                val providerId = when (_llmProvider.value.lowercase()) {
                    "openai" -> "openai"
                    "openrouter" -> "openrouter"
                    "anthropic" -> "anthropic"
                    "google ai", "google" -> "google"
                    "groq" -> "groq"
                    "together ai", "together" -> "together"
                    "local", "localai" -> "local"
                    else -> _llmProvider.value.lowercase()
                }

                // Save to backend .env file first - this is the source of truth
                logInfo(method, "Calling API to update .env: provider=$providerId")
                val result = apiClient.updateLlmConfig(
                    provider = providerId,
                    apiKey = _apiKey.value.takeIf { it.isNotEmpty() },
                    baseUrl = _llmBaseUrl.value.takeIf { it.isNotEmpty() },
                    model = _llmModel.value.takeIf { it.isNotEmpty() }
                )

                // Fail the save if backend update fails - the agent reads from .env, not local storage
                result.onFailure { e ->
                    logError(method, "API update failed: ${e.message}")
                    throw Exception("Failed to update agent configuration: ${e.message}")
                }

                logInfo(method, "API update successful")

                // Only save to local storage AFTER backend succeeds (for quick UI access)
                secureStorage.save("llm_provider", _llmProvider.value).getOrThrow()
                secureStorage.save("llm_model", _llmModel.value).getOrThrow()
                secureStorage.save("llm_base_url", _llmBaseUrl.value).getOrThrow()
                secureStorage.saveApiKey(_llmProvider.value, _apiKey.value).getOrThrow()

                // Update masked version
                _apiKeyMasked.value = maskApiKey(_apiKey.value)

                _saveSuccess.value = true
                logInfo(method, "Settings saved successfully")

            } catch (e: Exception) {
                logError(method, "Failed to save settings: ${e::class.simpleName}: ${e.message}")
                _errorMessage.value = "Failed to save settings: ${e.message}"
            } finally {
                _isSaving.value = false
            }
        }
    }

    // ========== Logout ==========

    /**
     * Logout - clears all tokens and notifies for navigation.
     */
    fun logout(onComplete: () -> Unit = {}) {
        val method = "logout"
        logInfo(method, "Starting logout process")

        viewModelScope.launch {
            try {
                // Clear access token
                logDebug(method, "Clearing access token from secure storage")
                secureStorage.deleteAccessToken().getOrThrow()
                logInfo(method, "Access token cleared")

                // Clear refresh token if exists
                logDebug(method, "Clearing refresh token")
                secureStorage.delete("refresh_token")

                // Clear user info
                logDebug(method, "Clearing user info")
                secureStorage.delete("user_id")
                secureStorage.delete("user_email")

                // Call logout API (revokes token server-side)
                logDebug(method, "Calling API logout")
                try {
                    apiClient.logout()
                    logInfo(method, "API logout successful")
                } catch (e: Exception) {
                    logWarn(method, "API logout failed (may already be logged out): ${e.message}")
                }

                // Clear in-memory token to stop background polling with revoked token
                logDebug(method, "Clearing in-memory access token")
                (apiClient as? ai.ciris.mobile.shared.api.CIRISApiClient)?.clearAccessToken()

                logInfo(method, "Logout complete - invoking navigation callback")
                onComplete()

            } catch (e: Exception) {
                logError(method, "Logout failed: ${e::class.simpleName}: ${e.message}")
                _errorMessage.value = "Logout failed: ${e.message}"
            }
        }
    }

    // ========== Reset Setup ==========

    // State for reset operation
    private val _isResetting = MutableStateFlow(false)
    val isResetting: StateFlow<Boolean> = _isResetting.asStateFlow()

    private val _resetSuccess = MutableStateFlow(false)
    val resetSuccess: StateFlow<Boolean> = _resetSuccess.asStateFlow()

    /**
     * Re-run setup wizard without wiping data.
     * Only deletes .env file - keeps databases, audit logs, signing keys, etc.
     * Use this to reconfigure LLM settings or fix auth issues.
     *
     * @param onSuccess Callback before app restart (for any cleanup)
     */
    fun rerunSetupWizard(onSuccess: () -> Unit = {}) {
        val method = "rerunSetupWizard"
        logInfo(method, "Re-running setup wizard - deleting .env only, keeping data")

        viewModelScope.launch {
            _isResetting.value = true
            _errorMessage.value = null

            try {
                // Only delete the .env file - keep everything else
                envFileUpdater.deleteEnvFile().getOrThrow()

                logInfo(method, ".env deleted successfully - restarting app for setup wizard")
                _resetSuccess.value = true

                // Invoke callback for any cleanup before restart
                onSuccess()

                // Small delay to let UI update
                kotlinx.coroutines.delay(100)

                // Restart the app completely - this kills the process and relaunches
                // The Python runtime will start fresh without CIRIS_CONFIGURED
                logInfo(method, "Triggering app restart...")
                AppRestarter.restartApp()

            } catch (e: Exception) {
                logError(method, "Failed to re-run setup: ${e::class.simpleName}: ${e.message}")
                _errorMessage.value = "Failed to re-run setup: ${e.message}"
                _isResetting.value = false
            }
        }
    }

    /**
     * Factory reset - wipe ALL data and start fresh.
     * Deletes .env file, signing keys, databases, audit logs, etc.
     * Use this to completely reset the agent to first-run state.
     *
     * @param onSuccess Callback before app restart (for any cleanup)
     */
    fun factoryReset(onSuccess: () -> Unit = {}) {
        val method = "factoryReset"
        logInfo(method, "Factory reset - wiping ALL data including databases and signing keys")

        viewModelScope.launch {
            _isResetting.value = true
            _errorMessage.value = null

            try {
                // Clear the signing key and data directory (databases, audit logs, etc.)
                logInfo(method, "Clearing signing key and data directory...")
                envFileUpdater.clearSigningKey().getOrThrow()
                logInfo(method, "Signing key and data cleared")

                // Delete the .env file
                envFileUpdater.deleteEnvFile().getOrThrow()

                logInfo(method, "Factory reset complete - restarting app for setup wizard")
                _resetSuccess.value = true

                // Invoke callback for any cleanup before restart
                onSuccess()

                // Small delay to let UI update
                kotlinx.coroutines.delay(100)

                // Restart the app completely
                logInfo(method, "Triggering app restart...")
                AppRestarter.restartApp()

            } catch (e: Exception) {
                logError(method, "Failed to factory reset: ${e::class.simpleName}: ${e.message}")
                _errorMessage.value = "Failed to factory reset: ${e.message}"
                _isResetting.value = false
            }
        }
    }

    /**
     * Legacy method for backwards compatibility.
     * Now calls factoryReset() for full wipe behavior.
     */
    @Deprecated("Use rerunSetupWizard() or factoryReset() instead", ReplaceWith("factoryReset(onSuccess)"))
    fun resetSetup(onSuccess: () -> Unit = {}) {
        factoryReset(onSuccess)
    }

    /**
     * Clear reset success state.
     */
    fun clearResetSuccess() {
        _resetSuccess.value = false
    }

    // ========== Utilities ==========

    /**
     * Mask API key for display.
     */
    private fun maskApiKey(key: String): String {
        return when {
            key.length <= 8 -> "****"
            else -> "${key.take(4)}${"*".repeat(key.length - 8)}${key.takeLast(4)}"
        }
    }

    /**
     * Clear error message.
     */
    fun clearError() {
        _errorMessage.value = null
    }

    /**
     * Clear success message.
     */
    fun clearSuccess() {
        _saveSuccess.value = false
    }

    /**
     * Get display name for provider.
     */
    fun getProviderDisplayName(provider: String): String {
        return availableProviders.find { it.first == provider }?.second ?: provider
    }

    // ========== Display Settings ==========

    /**
     * Toggle live background on/off.
     * Persists to secure storage immediately.
     */
    fun toggleLiveBackground(enabled: Boolean) {
        val method = "toggleLiveBackground"
        logInfo(method, "Setting live background to: $enabled")

        _liveBackgroundEnabled.value = enabled

        viewModelScope.launch {
            try {
                secureStorage.save("live_background_enabled", enabled.toString()).getOrThrow()
                logDebug(method, "Live background setting persisted")
            } catch (e: Exception) {
                logWarn(method, "Failed to persist live background setting: ${e.message}")
            }
        }
    }

    /**
     * Set color theme.
     * Persists to secure storage immediately.
     */
    fun setColorTheme(theme: ColorTheme) {
        val method = "setColorTheme"
        logInfo(method, "Setting color theme to: $theme")

        _colorTheme.value = theme

        viewModelScope.launch {
            try {
                secureStorage.save("color_theme", theme.name).getOrThrow()
                logDebug(method, "Color theme setting persisted")
            } catch (e: Exception) {
                logWarn(method, "Failed to persist color theme setting: ${e.message}")
            }
        }
    }

    /**
     * Set brightness preference (Dark, Light, or System).
     * Persists to secure storage immediately.
     */
    fun setBrightnessPreference(brightness: BrightnessPreference) {
        val method = "setBrightnessPreference"
        logInfo(method, "Setting brightness preference to: $brightness")

        _brightnessPreference.value = brightness

        viewModelScope.launch {
            try {
                secureStorage.save("brightness_preference", brightness.name).getOrThrow()
                logDebug(method, "Brightness preference setting persisted")
            } catch (e: Exception) {
                logWarn(method, "Failed to persist brightness preference: ${e.message}")
            }
        }
    }

    // ========== Location Settings ==========

    /**
     * Search for locations matching the query.
     * Debounces input with 300ms delay.
     */
    fun searchLocations(query: String) {
        val method = "searchLocations"
        _locationSearchQuery.value = query

        // Cancel previous search
        locationSearchJob?.cancel()

        // Clear results if query is too short
        if (query.length < 2) {
            _locationSearchResults.value = emptyList()
            _locationSearchLoading.value = false
            return
        }

        locationSearchJob = viewModelScope.launch {
            _locationSearchLoading.value = true
            delay(300) // Debounce

            try {
                val response = apiClient.searchLocations(query = query, limit = 10)
                _locationSearchResults.value = response.results
                logDebug(method, "Found ${response.results.size} locations for query: $query")
            } catch (e: Exception) {
                logError(method, "Location search failed: ${e.message}")
                _locationSearchResults.value = emptyList()
            } finally {
                _locationSearchLoading.value = false
            }
        }
    }

    /**
     * Select a location and save it to the backend.
     */
    fun selectLocation(location: LocationResultData) {
        val method = "selectLocation"
        logInfo(method, "Selecting location: ${location.displayName}")

        _selectedLocation.value = location
        _locationSearchQuery.value = location.displayName
        _locationSearchResults.value = emptyList()

        viewModelScope.launch {
            try {
                val result = apiClient.updateUserLocation(location)
                if (result.success) {
                    _currentLocationDisplay.value = result.locationDisplay
                    logInfo(method, "Location saved successfully: ${result.locationDisplay}")
                } else {
                    logError(method, "Failed to save location: ${result.message}")
                    _errorMessage.value = "Failed to save location: ${result.message}"
                }
            } catch (e: Exception) {
                logError(method, "Location update failed: ${e.message}")
                _errorMessage.value = "Failed to update location: ${e.message}"
            }
        }
    }

    /**
     * Clear the location search results.
     */
    fun clearLocationSearch() {
        locationSearchJob?.cancel()
        _locationSearchQuery.value = ""
        _locationSearchResults.value = emptyList()
        _locationSearchLoading.value = false
    }

    /**
     * Load the current location display from backend API (.env file).
     */
    fun loadCurrentLocation() {
        val method = "loadCurrentLocation"
        viewModelScope.launch {
            try {
                val location = apiClient.getCurrentLocation()
                if (location.configured && location.displayName != null) {
                    _currentLocationDisplay.value = location.displayName
                    logDebug(method, "Loaded current location: ${location.displayName}")
                } else {
                    _currentLocationDisplay.value = null
                    logDebug(method, "No location configured")
                }
            } catch (e: Exception) {
                logWarn(method, "Failed to load current location: ${e.message}")
                _currentLocationDisplay.value = null
            }
        }
    }
}
