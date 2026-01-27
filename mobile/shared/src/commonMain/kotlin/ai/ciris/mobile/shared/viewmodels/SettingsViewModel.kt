package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.LlmConfigData
import ai.ciris.mobile.shared.platform.AppRestarter
import ai.ciris.mobile.shared.platform.EnvFileUpdater
import ai.ciris.mobile.shared.platform.SecureStorage
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
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
        println("[$TAG][$level][$method] $message")
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

    // Available LLM providers for BYOK mode
    val availableProviders = listOf(
        "openai" to "OpenAI",
        "anthropic" to "Anthropic",
        "other" to "Other (OpenAI-compatible)",
        "local" to "Local (Ollama)"
    )

    // Available models per provider
    private val modelsByProvider = mapOf(
        "openai" to listOf("gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-4", "gpt-3.5-turbo"),
        "anthropic" to listOf("claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"),
        "other" to listOf("default"),
        "local" to listOf("llama3.2", "llama3.1", "mistral", "codellama", "qwen2.5")
    )

    private val _availableModels = MutableStateFlow<List<String>>(emptyList())
    val availableModels: StateFlow<List<String>> = _availableModels.asStateFlow()

    // Track if we've loaded config
    private var hasLoadedConfig = false

    init {
        // Don't auto-load here - wait for refresh() to be called when screen is shown
        // This avoids making API calls before authentication is complete
        logDebug("init", "SettingsViewModel created, waiting for refresh() call")
    }

    /**
     * Load LLM configuration by reading .env file directly.
     * This determines whether we're in CIRIS Proxy or BYOK mode.
     *
     * We read .env directly instead of using API because:
     * 1. No authentication required
     * 2. More reliable for mobile (doesn't depend on Python server state)
     * 3. Faster (no network call)
     */
    private fun loadLlmConfig() {
        val method = "loadLlmConfig"
        logInfo(method, "Loading LLM configuration from .env file")

        viewModelScope.launch {
            _isLoading.value = true
            _errorMessage.value = null

            try {
                val envConfig = envFileUpdater.readLlmConfig()

                if (envConfig != null) {
                    // Convert EnvLlmConfig to LlmConfigData
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

                    _llmConfig.value = config
                    _isCirisProxy.value = config.isCirisProxy
                    hasLoadedConfig = true

                    logInfo(method, "LLM config loaded from .env: provider=${config.provider}, " +
                            "isCirisProxy=${config.isCirisProxy}, model=${config.model}")

                    if (!config.isCirisProxy) {
                        // BYOK mode - populate form fields
                        _llmProvider.value = config.provider
                        _llmModel.value = config.model
                        _llmBaseUrl.value = config.baseUrl ?: ""
                        _availableModels.value = modelsByProvider[config.provider] ?: listOf(config.model)

                        // Load API key from secure storage (we don't get it from .env for security)
                        loadApiKeyFromStorage(config.provider)
                    }

                    logInfo(method, "Configuration loaded successfully from .env")
                } else {
                    logWarn(method, ".env file not found or unreadable, using fallback")
                    loadFallbackConfig()
                }
            } catch (e: Exception) {
                logError(method, "Failed to load LLM config: ${e::class.simpleName}: ${e.message}")
                _errorMessage.value = "Failed to load configuration: ${e.message}"

                // Fall back to checking secure storage for any previously saved BYOK config
                loadFallbackConfig()
            } finally {
                _isLoading.value = false
            }
        }
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

    /**
     * Update LLM provider (BYOK mode only).
     */
    fun onProviderChanged(provider: String) {
        if (_isCirisProxy.value) {
            logWarn("onProviderChanged", "Cannot change provider in CIRIS Proxy mode")
            return
        }

        _llmProvider.value = provider
        _availableModels.value = modelsByProvider[provider] ?: emptyList()

        // Reset model to first available
        _llmModel.value = modelsByProvider[provider]?.firstOrNull() ?: ""

        // Load API key for new provider
        viewModelScope.launch {
            loadApiKeyFromStorage(provider)
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
     * Note: This currently only saves to secure storage.
     * Full .env update would require backend API call.
     */
    fun saveSettings() {
        val method = "saveSettings"

        if (_isCirisProxy.value) {
            logWarn(method, "Cannot save settings in CIRIS Proxy mode")
            _errorMessage.value = "Settings are managed by CIRIS in proxy mode"
            return
        }

        logInfo(method, "Saving BYOK settings: provider=${_llmProvider.value}, model=${_llmModel.value}")

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

                // Save to secure storage
                secureStorage.save("llm_provider", _llmProvider.value).getOrThrow()
                secureStorage.save("llm_model", _llmModel.value).getOrThrow()
                secureStorage.save("llm_base_url", _llmBaseUrl.value).getOrThrow()
                secureStorage.saveApiKey(_llmProvider.value, _apiKey.value).getOrThrow()

                // Update masked version
                _apiKeyMasked.value = maskApiKey(_apiKey.value)

                _saveSuccess.value = true
                logInfo(method, "Settings saved successfully")

                // Note: To fully update the running agent, we'd need a backend API call
                // to update the .env file. For now, changes take effect on restart.

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

                // Call logout API
                logDebug(method, "Calling API logout")
                try {
                    apiClient.logout()
                    logInfo(method, "API logout successful")
                } catch (e: Exception) {
                    logWarn(method, "API logout failed (may already be logged out): ${e.message}")
                }

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
     * Reset setup to re-run the setup wizard.
     * Deletes .env file and restarts the app.
     *
     * @param onSuccess Callback before app restart (for any cleanup)
     */
    fun resetSetup(onSuccess: () -> Unit = {}) {
        val method = "resetSetup"
        logInfo(method, "Starting setup reset - will delete .env file and restart app")

        viewModelScope.launch {
            _isResetting.value = true
            _errorMessage.value = null

            try {
                // Delete the .env file
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
                logError(method, "Failed to reset setup: ${e::class.simpleName}: ${e.message}")
                _errorMessage.value = "Failed to reset setup: ${e.message}"
                _isResetting.value = false
            }
            // Note: We don't reset _isResetting in finally block because the app will restart
        }
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
}
