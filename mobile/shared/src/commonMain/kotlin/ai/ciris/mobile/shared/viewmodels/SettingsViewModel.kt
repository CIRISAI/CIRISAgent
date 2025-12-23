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
        viewModelScope.launch {
            try {
                // Load LLM provider
                secureStorage.get("llm_provider").onSuccess { provider ->
                    _llmProvider.value = provider ?: "openai"
                }

                // Load LLM model
                secureStorage.get("llm_model").onSuccess { model ->
                    _llmModel.value = model ?: "gpt-4"
                }

                // Load API key (masked)
                secureStorage.getApiKey(_llmProvider.value).onSuccess { key ->
                    if (key != null) {
                        _apiKeyMasked.value = maskApiKey(key)
                        _apiKey.value = key
                    }
                }
            } catch (e: Exception) {
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
        viewModelScope.launch {
            _isSaving.value = true
            _saveSuccess.value = false
            _errorMessage.value = null

            try {
                // Validate
                if (_apiKey.value.isEmpty()) {
                    throw Exception("API key is required")
                }

                // Save to secure storage
                secureStorage.save("llm_provider", _llmProvider.value).getOrThrow()
                secureStorage.save("llm_model", _llmModel.value).getOrThrow()
                secureStorage.saveApiKey(_llmProvider.value, _apiKey.value).getOrThrow()

                // Update masked version
                _apiKeyMasked.value = maskApiKey(_apiKey.value)

                _saveSuccess.value = true

                // TODO: Notify CIRIS runtime of config change via API
                // apiClient.updateConfig(...)

            } catch (e: Exception) {
                _errorMessage.value = "Failed to save settings: ${e.message}"
            } finally {
                _isSaving.value = false
            }
        }
    }

    /**
     * Logout
     */
    fun logout() {
        viewModelScope.launch {
            try {
                // Clear access token
                secureStorage.deleteAccessToken().getOrThrow()

                // Call logout API
                apiClient.logout()

                // TODO: Navigate to login screen
            } catch (e: Exception) {
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
