package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.DistributionStrategy
import ai.ciris.mobile.shared.models.LlmBusStatus
import ai.ciris.mobile.shared.models.LlmProviderStatus
import ai.ciris.mobile.shared.models.ProviderPriority
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * LLM Settings ViewModel
 *
 * Manages LLM Bus runtime configuration:
 * - Bus status and provider list
 * - Distribution strategy
 * - Circuit breaker management
 * - Provider priority management
 * - Local server discovery
 */
class LLMSettingsViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "LLMSettingsViewModel"
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

    // LLM Bus aggregate status
    private val _llmBusStatus = MutableStateFlow<LlmBusStatus?>(null)
    val llmBusStatus: StateFlow<LlmBusStatus?> = _llmBusStatus.asStateFlow()

    // LLM Providers with metrics and circuit breaker state
    private val _llmProviders = MutableStateFlow<List<LlmProviderStatus>>(emptyList())
    val llmProviders: StateFlow<List<LlmProviderStatus>> = _llmProviders.asStateFlow()

    // Loading state
    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    // Error message
    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage: StateFlow<String?> = _errorMessage.asStateFlow()

    // Success message
    private val _successMessage = MutableStateFlow<String?>(null)
    val successMessage: StateFlow<String?> = _successMessage.asStateFlow()

    // Discovered local servers
    private val _discoveredServers = MutableStateFlow<List<DiscoveredLlmServer>>(emptyList())
    val discoveredServers: StateFlow<List<DiscoveredLlmServer>> = _discoveredServers.asStateFlow()

    // Discovery in progress
    private val _isDiscovering = MutableStateFlow(false)
    val isDiscovering: StateFlow<Boolean> = _isDiscovering.asStateFlow()

    // Section expansion states
    private val _statusExpanded = MutableStateFlow(true)
    val statusExpanded: StateFlow<Boolean> = _statusExpanded.asStateFlow()

    private val _providersExpanded = MutableStateFlow(false)
    val providersExpanded: StateFlow<Boolean> = _providersExpanded.asStateFlow()

    private val _localServersExpanded = MutableStateFlow(false)
    val localServersExpanded: StateFlow<Boolean> = _localServersExpanded.asStateFlow()

    private val _advancedExpanded = MutableStateFlow(false)
    val advancedExpanded: StateFlow<Boolean> = _advancedExpanded.asStateFlow()

    // CIRIS Services enabled state (loaded from config)
    private val _cirisServicesEnabled = MutableStateFlow(true)
    val cirisServicesEnabled: StateFlow<Boolean> = _cirisServicesEnabled.asStateFlow()

    // ========== Initialization ==========

    init {
        loadStatus()
    }

    /**
     * Load LLM Bus status and provider list.
     */
    fun loadStatus() {
        val method = "loadStatus"
        logInfo(method, "Loading LLM Bus status...")

        viewModelScope.launch {
            _isLoading.value = true
            try {
                val busStatus = try {
                    apiClient.getLlmBusStatus()
                } catch (e: Exception) {
                    logWarn(method, "Failed to fetch LLM Bus status: ${e.message}")
                    null
                }

                val providers = try {
                    apiClient.getLlmProviders()
                } catch (e: Exception) {
                    logWarn(method, "Failed to fetch LLM providers: ${e.message}")
                    emptyList()
                }

                _llmBusStatus.value = busStatus
                _llmProviders.value = providers

                logInfo(method, "Loaded LLM Bus: strategy=${busStatus?.distributionStrategyLabel}, " +
                        "providers=${providers.size}")
            } catch (e: Exception) {
                logError(method, "Failed to load LLM Bus status: ${e.message}")
                _errorMessage.value = "Failed to load LLM status: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Refresh status (alias for loadStatus).
     */
    fun refresh() = loadStatus()

    // ========== Distribution Strategy ==========

    /**
     * Update the distribution strategy for the LLM Bus.
     */
    fun updateDistributionStrategy(strategy: DistributionStrategy) {
        val method = "updateDistributionStrategy"
        logInfo(method, "Updating distribution strategy to ${strategy.name}")

        viewModelScope.launch {
            try {
                val result = apiClient.updateLlmDistributionStrategy(strategy)
                if (result.success) {
                    logInfo(method, "Strategy updated: ${result.previousStrategy} -> ${result.newStrategy}")
                    _successMessage.value = "Distribution strategy updated"
                    loadStatus()
                } else {
                    logError(method, "Failed to update strategy: ${result.message}")
                    _errorMessage.value = result.message
                }
            } catch (e: Exception) {
                logError(method, "Error updating strategy: ${e.message}")
                _errorMessage.value = "Failed to update strategy: ${e.message}"
            }
        }
    }

    // ========== Circuit Breaker Management ==========

    /**
     * Reset a circuit breaker for a specific provider.
     */
    fun resetCircuitBreaker(providerName: String, force: Boolean = false) {
        val method = "resetCircuitBreaker"
        logInfo(method, "Resetting circuit breaker for $providerName (force=$force)")

        viewModelScope.launch {
            try {
                val result = apiClient.resetLlmCircuitBreaker(providerName, force)
                if (result.success) {
                    logInfo(method, "Circuit breaker reset: ${result.previousState} -> ${result.newState}")
                    _successMessage.value = "Protection reset for $providerName"
                    loadStatus()
                } else {
                    logError(method, "Failed to reset circuit breaker: ${result.message}")
                    _errorMessage.value = result.message
                }
            } catch (e: Exception) {
                logError(method, "Error resetting circuit breaker: ${e.message}")
                _errorMessage.value = "Failed to reset protection: ${e.message}"
            }
        }
    }

    /**
     * Update circuit breaker configuration for a provider.
     */
    fun updateCircuitBreakerConfig(
        providerName: String,
        failureThreshold: Int? = null,
        recoveryTimeoutSeconds: Float? = null,
        successThreshold: Int? = null,
        timeoutDurationSeconds: Float? = null
    ) {
        val method = "updateCircuitBreakerConfig"
        logInfo(method, "Updating CB config for $providerName")

        viewModelScope.launch {
            try {
                val result = apiClient.updateLlmCircuitBreakerConfig(
                    providerName = providerName,
                    failureThreshold = failureThreshold,
                    recoveryTimeoutSeconds = recoveryTimeoutSeconds,
                    successThreshold = successThreshold,
                    timeoutDurationSeconds = timeoutDurationSeconds
                )
                if (result.success) {
                    logInfo(method, "Circuit breaker config updated for $providerName")
                    _successMessage.value = "Protection settings updated"
                    loadStatus()
                } else {
                    logError(method, "Failed to update CB config: ${result.message}")
                    _errorMessage.value = result.message
                }
            } catch (e: Exception) {
                logError(method, "Error updating CB config: ${e.message}")
                _errorMessage.value = "Failed to update config: ${e.message}"
            }
        }
    }

    // ========== Provider Priority Management ==========

    /**
     * Update a provider's priority level.
     *
     * @param providerName Name of the provider to update
     * @param priority New priority level
     */
    fun updateProviderPriority(providerName: String, priority: ProviderPriority) {
        val method = "updateProviderPriority"
        logInfo(method, "Updating priority for $providerName to ${priority.name}")

        viewModelScope.launch {
            try {
                val result = apiClient.updateLlmProviderPriority(providerName, priority)
                if (result.success) {
                    logInfo(method, "Priority updated: ${result.previousPriority} -> ${result.newPriority}")
                    _successMessage.value = "Priority updated for $providerName"
                    loadStatus()
                } else {
                    logError(method, "Failed to update priority: ${result.message}")
                    _errorMessage.value = result.message
                }
            } catch (e: Exception) {
                logError(method, "Error updating priority: ${e.message}")
                _errorMessage.value = "Failed to update priority: ${e.message}"
            }
        }
    }

    /**
     * Delete/unregister a provider from the LLM Bus.
     *
     * @param providerName Name of the provider to delete
     */
    fun deleteProvider(providerName: String) {
        val method = "deleteProvider"
        logInfo(method, "Deleting provider $providerName")

        viewModelScope.launch {
            try {
                val result = apiClient.deleteLlmProvider(providerName)
                if (result.success) {
                    logInfo(method, "Provider deleted: ${result.message}")
                    _successMessage.value = "Provider removed"
                    loadStatus()
                } else {
                    logError(method, "Failed to delete provider: ${result.message}")
                    _errorMessage.value = result.message
                }
            } catch (e: Exception) {
                logError(method, "Error deleting provider: ${e.message}")
                _errorMessage.value = "Failed to delete provider: ${e.message}"
            }
        }
    }

    // ========== Local Server Discovery ==========

    /**
     * Discover local LLM inference servers on the network.
     */
    fun discoverLocalServers() {
        val method = "discoverLocalServers"
        logInfo(method, "Starting local LLM server discovery...")

        viewModelScope.launch {
            _isDiscovering.value = true
            try {
                val servers = apiClient.discoverLocalLlmServers(
                    timeoutSeconds = 5.0f,
                    includeLocalhost = true
                )
                _discoveredServers.value = servers
                logInfo(method, "Discovered ${servers.size} local LLM servers")
                if (servers.isNotEmpty()) {
                    _successMessage.value = "Found ${servers.size} local server${if (servers.size > 1) "s" else ""}"
                }
            } catch (e: Exception) {
                logError(method, "Discovery failed: ${e.message}")
                _errorMessage.value = "Discovery failed: ${e.message}"
            } finally {
                _isDiscovering.value = false
            }
        }
    }

    // ========== Add Provider ==========

    /**
     * Add a discovered local server as an LLM provider.
     *
     * @param server The discovered server to add
     * @param priority Priority level for the new provider
     */
    fun addDiscoveredServerAsProvider(
        server: DiscoveredLlmServer,
        priority: ProviderPriority = ProviderPriority.FALLBACK
    ) {
        val method = "addDiscoveredServerAsProvider"
        logInfo(method, "Adding ${server.label} as ${priority.name} provider")

        viewModelScope.launch {
            _isLoading.value = true
            try {
                // Map server type to provider ID
                val providerId = when (server.serverType.lowercase()) {
                    "ollama" -> "local"  // Ollama uses OpenAI-compatible API
                    "llama_cpp" -> "local"
                    "vllm" -> "local"
                    "lmstudio" -> "local"
                    "localai" -> "local"
                    else -> "local"  // Default to local (OpenAI-compatible)
                }

                // Use first model if available, or "default"
                val model = server.models.firstOrNull()

                val result = apiClient.addLlmProvider(
                    providerId = providerId,
                    providerBaseUrl = server.url,
                    name = server.label.replace(":", "_").replace(" ", "_"),
                    model = model,
                    apiKey = null,  // Local servers don't need API keys
                    priority = priority
                )

                if (result.success) {
                    logInfo(method, "Provider added: ${result.providerName}")
                    _successMessage.value = "Added ${server.label} as ${priority.name.lowercase()} provider"
                    // Refresh to show the new provider
                    loadStatus()
                } else {
                    logError(method, "Failed to add provider: ${result.message}")
                    _errorMessage.value = result.message
                }
            } catch (e: Exception) {
                logError(method, "Error adding provider: ${e.message}")
                _errorMessage.value = "Failed to add provider: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Add a cloud provider with API key.
     *
     * @param providerId Provider type (openai, anthropic, openrouter, etc.)
     * @param apiKey The API key for the provider
     * @param baseUrl Optional custom base URL (uses default for provider if not specified)
     * @param priority Priority level for the new provider
     */
    fun addCloudProvider(
        providerId: String,
        apiKey: String,
        baseUrl: String? = null,
        priority: ProviderPriority = ProviderPriority.FALLBACK
    ) {
        val method = "addCloudProvider"
        logInfo(method, "Adding $providerId as ${priority.name} provider")

        viewModelScope.launch {
            _isLoading.value = true
            try {
                // Default base URLs for known providers
                val providerBaseUrl = baseUrl ?: when (providerId.lowercase()) {
                    "openai" -> "https://api.openai.com/v1"
                    "anthropic" -> "https://api.anthropic.com/v1"
                    "openrouter" -> "https://openrouter.ai/api/v1"
                    "deepseek" -> "https://api.deepseek.com/v1"
                    "together" -> "https://api.together.xyz/v1"
                    "groq" -> "https://api.groq.com/openai/v1"
                    else -> ""
                }

                if (providerBaseUrl.isEmpty()) {
                    _errorMessage.value = "Unknown provider: $providerId"
                    return@launch
                }

                val result = apiClient.addLlmProvider(
                    providerId = providerId,
                    providerBaseUrl = providerBaseUrl,
                    name = "${providerId}_byok",
                    model = null,  // Will use provider's default
                    apiKey = apiKey,
                    priority = priority
                )

                if (result.success) {
                    logInfo(method, "Provider added: ${result.providerName}")
                    _successMessage.value = "Added $providerId as ${priority.name.lowercase()} provider"
                    loadStatus()
                } else {
                    logError(method, "Failed to add provider: ${result.message}")
                    _errorMessage.value = result.message
                }
            } catch (e: Exception) {
                logError(method, "Error adding provider: ${e.message}")
                _errorMessage.value = "Failed to add provider: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    // ========== Section Toggle Methods ==========

    fun toggleStatusExpanded() {
        _statusExpanded.value = !_statusExpanded.value
    }

    fun toggleProvidersExpanded() {
        _providersExpanded.value = !_providersExpanded.value
    }

    fun toggleLocalServersExpanded() {
        _localServersExpanded.value = !_localServersExpanded.value
    }

    fun toggleAdvancedExpanded() {
        _advancedExpanded.value = !_advancedExpanded.value
    }

    // ========== CIRIS Services ==========

    /**
     * Disable CIRIS services (switch to BYOK mode).
     * This persists the setting and updates the LLM config.
     */
    fun disableCirisServices() {
        val method = "disableCirisServices"
        logInfo(method, "Disabling CIRIS services")

        viewModelScope.launch {
            _isLoading.value = true
            try {
                // Call API to disable CIRIS services
                val result = apiClient.disableCirisServices()
                if (result.success) {
                    _cirisServicesEnabled.value = false
                    _successMessage.value = "CIRIS services disabled. Please restart the app for changes to take full effect."
                    logInfo(method, "CIRIS services disabled successfully")
                    // Refresh providers list to reflect changes
                    refresh()
                } else {
                    _errorMessage.value = result.message ?: "Failed to disable CIRIS services"
                    logError(method, "Failed to disable: ${result.message}")
                }
            } catch (e: Exception) {
                _errorMessage.value = "Failed to disable CIRIS services: ${e.message}"
                logError(method, "Error: ${e.message}")
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Show info about re-enabling CIRIS services (requires wizard).
     */
    fun showCirisServicesReenableInfo() {
        _errorMessage.value = "To re-enable CIRIS services, please re-run the setup wizard from Settings > Data Management > Reset Account"
    }

    // ========== Message Clearing ==========

    fun clearErrorMessage() {
        _errorMessage.value = null
    }

    fun clearSuccessMessage() {
        _successMessage.value = null
    }
}
