package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.platform.SecureStorage
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Settings ViewModel
 * Manages app settings, API keys, and user preferences
 *
 * Based on android/app/.../SettingsActivity.kt
 */
class SettingsViewModel(
    private val secureStorage: SecureStorage,
    private val apiClient: CIRISApiClient
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

    // Logout completion callback
    private var _onLogoutComplete: (() -> Unit)? = null

    private val _llmProvider = MutableStateFlow("openai")
    val llmProvider: StateFlow<String> = _llmProvider.asStateFlow()

    private val _llmModel = MutableStateFlow("gpt-4")
    val llmModel: StateFlow<String> = _llmModel.asStateFlow()

    private val _apiKey = MutableStateFlow("")
    val apiKey: StateFlow<String> = _apiKey.asStateFlow()

    private val _apiKeyMasked = MutableStateFlow("")
    val apiKeyMasked: StateFlow<String> = _apiKeyMasked.asStateFlow()

    private val _isSaving = MutableStateFlow(false)
    val isSaving: StateFlow<Boolean> = _isSaving.asStateFlow()

    private val _saveSuccess = MutableStateFlow(false)
    val saveSuccess: StateFlow<Boolean> = _saveSuccess.asStateFlow()

    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage: StateFlow<String?> = _errorMessage.asStateFlow()

    // Available LLM providers
    val availableProviders = listOf(
        "openai" to "OpenAI",
        "anthropic" to "Anthropic",
        "local" to "Local (Ollama)"
    )

    // Available models per provider
    private val modelsByProvider = mapOf(
        "openai" to listOf("gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"),
        "anthropic" to listOf("claude-3-opus", "claude-3-sonnet", "claude-3-haiku"),
        "local" to listOf("llama2", "mistral", "codellama")
    )

    val availableModels: StateFlow<List<String>> = MutableStateFlow(
        modelsByProvider[_llmProvider.value] ?: emptyList()
    )

    init {
        loadSettings()
    }

    /**
     * Load settings from secure storage
     */
    private fun loadSettings() {
        val method = "loadSettings"
        logInfo(method, "Loading settings from secure storage")

        viewModelScope.launch {
            try {
                // Load LLM provider
                secureStorage.get("llm_provider").onSuccess { provider ->
                    _llmProvider.value = provider ?: "openai"
                    logDebug(method, "Loaded LLM provider: ${_llmProvider.value}")
                }

                // Load LLM model
                secureStorage.get("llm_model").onSuccess { model ->
                    _llmModel.value = model ?: "gpt-4"
                    logDebug(method, "Loaded LLM model: ${_llmModel.value}")
                }

                // Load API key (masked)
                secureStorage.getApiKey(_llmProvider.value).onSuccess { key ->
                    if (key != null) {
                        _apiKeyMasked.value = maskApiKey(key)
                        _apiKey.value = key
                        logDebug(method, "Loaded API key for ${_llmProvider.value} (masked)")
                    } else {
                        logDebug(method, "No API key found for ${_llmProvider.value}")
                    }
                }

                logInfo(method, "Settings loaded successfully")
            } catch (e: Exception) {
                logError(method, "Failed to load settings: ${e::class.simpleName}: ${e.message}")
                _errorMessage.value = "Failed to load settings: ${e.message}"
            }
        }
    }

    /**
     * Update LLM provider
     */
    fun onProviderChanged(provider: String) {
        _llmProvider.value = provider

        // Update available models
        (availableModels as MutableStateFlow).value = modelsByProvider[provider] ?: emptyList()

        // Reset model to first available
        _llmModel.value = modelsByProvider[provider]?.firstOrNull() ?: ""

        // Load API key for new provider
        viewModelScope.launch {
            secureStorage.getApiKey(provider).onSuccess { key ->
                if (key != null) {
                    _apiKeyMasked.value = maskApiKey(key)
                    _apiKey.value = key
                } else {
                    _apiKeyMasked.value = ""
                    _apiKey.value = ""
                }
            }
        }
    }

    /**
     * Update LLM model
     */
    fun onModelChanged(model: String) {
        _llmModel.value = model
    }

    /**
     * Update API key
     */
    fun onApiKeyChanged(key: String) {
        _apiKey.value = key
        // Don't mask while typing
        if (key.isNotEmpty()) {
            _apiKeyMasked.value = key
        }
    }

    /**
     * Save settings
     */
    fun saveSettings() {
        val method = "saveSettings"
        logInfo(method, "Saving settings: provider=${_llmProvider.value}, model=${_llmModel.value}")

        viewModelScope.launch {
            _isSaving.value = true
            _saveSuccess.value = false
            _errorMessage.value = null

            try {
                // Validate
                if (_apiKey.value.isEmpty()) {
                    logWarn(method, "Validation failed: API key is required")
                    throw Exception("API key is required")
                }
                logDebug(method, "Validation passed")

                // Save to secure storage
                logDebug(method, "Saving LLM provider: ${_llmProvider.value}")
                secureStorage.save("llm_provider", _llmProvider.value).getOrThrow()

                logDebug(method, "Saving LLM model: ${_llmModel.value}")
                secureStorage.save("llm_model", _llmModel.value).getOrThrow()

                logDebug(method, "Saving API key for provider: ${_llmProvider.value}")
                secureStorage.saveApiKey(_llmProvider.value, _apiKey.value).getOrThrow()

                // Update masked version
                _apiKeyMasked.value = maskApiKey(_apiKey.value)

                _saveSuccess.value = true
                logInfo(method, "Settings saved successfully")

                // Notify CIRIS runtime of config change
                // The runtime will pick up changes on next request via the stored config
                logDebug(method, "Runtime will use updated config on next API call")

            } catch (e: Exception) {
                logError(method, "Failed to save settings: ${e::class.simpleName}: ${e.message}")
                _errorMessage.value = "Failed to save settings: ${e.message}"
            } finally {
                _isSaving.value = false
            }
        }
    }

    /**
     * Logout - clears all tokens and notifies for navigation
     * @param onComplete Callback invoked after successful logout to trigger navigation
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
                    // Continue with local logout even if API fails
                }

                logInfo(method, "Logout complete - invoking navigation callback")
                onComplete()

            } catch (e: Exception) {
                logError(method, "Logout failed: ${e::class.simpleName}: ${e.message}")
                _errorMessage.value = "Logout failed: ${e.message}"
            }
        }
    }

    /**
     * Mask API key for display
     * Shows first 4 and last 4 characters
     */
    private fun maskApiKey(key: String): String {
        return when {
            key.length <= 8 -> "****"
            else -> "${key.take(4)}${"*".repeat(key.length - 8)}${key.takeLast(4)}"
        }
    }

    /**
     * Clear error message
     */
    fun clearError() {
        _errorMessage.value = null
    }

    /**
     * Clear success message
     */
    fun clearSuccess() {
        _saveSuccess.value = false
    }
}
