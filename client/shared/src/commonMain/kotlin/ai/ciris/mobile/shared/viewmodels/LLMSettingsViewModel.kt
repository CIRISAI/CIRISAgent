package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.DistributionStrategy
import ai.ciris.mobile.shared.models.LlmBusStatus
import ai.ciris.mobile.shared.models.LlmProviderStatus
import ai.ciris.mobile.shared.models.ProviderPriority
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Adapter item for display in the LLM Settings screen.
 * Shows adapters that provide LLM services.
 */
data class LlmAdapterItem(
    val adapterId: String,
    val adapterType: String,
    val isRunning: Boolean,
    val servicesRegistered: List<String>,
    val description: String
)

/**
 * LLM Settings ViewModel
 *
 * Manages LLM Bus runtime configuration:
 * - Bus status and provider list
 * - LLM-capable adapters with CRUD
 * - Distribution strategy
 * - Circuit breaker management
 * - Provider priority management
 * - Local server discovery
 *
 * Follows the Adapters page patterns:
 * - Operation coalescing (prevent concurrent ops)
 * - Transient status messages with auto-dismiss
 * - Lazy detail loading with caching
 */
class LLMSettingsViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "LLMSettingsViewModel"
        private const val MESSAGE_DISMISS_DELAY_MS = 3000L
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

    // LLM-capable adapters
    private val _llmAdapters = MutableStateFlow<List<LlmAdapterItem>>(emptyList())
    val llmAdapters: StateFlow<List<LlmAdapterItem>> = _llmAdapters.asStateFlow()

    // LLM Providers with metrics and circuit breaker state
    private val _llmProviders = MutableStateFlow<List<LlmProviderStatus>>(emptyList())
    val llmProviders: StateFlow<List<LlmProviderStatus>> = _llmProviders.asStateFlow()

    // Loading state
    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    // Operation in progress (prevents concurrent operations)
    private val _operationInProgress = MutableStateFlow(false)
    val operationInProgress: StateFlow<Boolean> = _operationInProgress.asStateFlow()

    // Error message
    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage: StateFlow<String?> = _errorMessage.asStateFlow()

    // Success/status message (transient, auto-dismisses)
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

    private val _adaptersExpanded = MutableStateFlow(false)
    val adaptersExpanded: StateFlow<Boolean> = _adaptersExpanded.asStateFlow()

    private val _providersExpanded = MutableStateFlow(false)
    val providersExpanded: StateFlow<Boolean> = _providersExpanded.asStateFlow()

    private val _addProviderExpanded = MutableStateFlow(false)
    val addProviderExpanded: StateFlow<Boolean> = _addProviderExpanded.asStateFlow()

    private val _localServersExpanded = MutableStateFlow(false)
    val localServersExpanded: StateFlow<Boolean> = _localServersExpanded.asStateFlow()

    private val _advancedExpanded = MutableStateFlow(false)
    val advancedExpanded: StateFlow<Boolean> = _advancedExpanded.asStateFlow()

    // CIRIS Services enabled state (loaded from config)
    private val _cirisServicesEnabled = MutableStateFlow(true)
    val cirisServicesEnabled: StateFlow<Boolean> = _cirisServicesEnabled.asStateFlow()

    // Provider pending delete confirmation (for system providers)
    private val _providerPendingDelete = MutableStateFlow<String?>(null)
    val providerPendingDelete: StateFlow<String?> = _providerPendingDelete.asStateFlow()

    // ========== Initialization ==========

    /**
     * Load LLM Bus status, adapters, and provider list.
     */
    fun loadStatus() {
        val method = "loadStatus"
        logInfo(method, "Loading LLM Bus status...")

        viewModelScope.launch {
            _isLoading.value = true
            try {
                // Load CIRIS services enabled state from backend
                val cirisEnabled = try {
                    apiClient.getCirisServicesStatus()
                } catch (e: Exception) {
                    logWarn(method, "Failed to fetch CIRIS services status: ${e.message}")
                    true // Default to enabled if we can't check
                }
                _cirisServicesEnabled.value = cirisEnabled
                logInfo(method, "CIRIS services enabled: $cirisEnabled")

                // Load adapters that provide LLM services
                // Filter by services_registered containing "LLM" (dynamic detection)
                val adapters = try {
                    val allAdapters = apiClient.listAdapters()
                    // Filter to adapters that have registered LLM service
                    allAdapters.adapters
                        .filter { adapter ->
                            adapter.servicesRegistered.any { service ->
                                service.equals("LLM", ignoreCase = true)
                            }
                        }
                        .map { adapter ->
                            LlmAdapterItem(
                                adapterId = adapter.adapterId,
                                adapterType = adapter.adapterType,
                                isRunning = adapter.isRunning,
                                servicesRegistered = adapter.servicesRegistered,
                                description = getAdapterDescription(adapter.adapterType)
                            )
                        }
                } catch (e: Exception) {
                    logWarn(method, "Failed to fetch adapters: ${e.message}")
                    emptyList()
                }
                _llmAdapters.value = adapters
                logInfo(method, "Loaded ${adapters.size} LLM adapters (filtered by LLM service)")

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
     * Get a human-readable description for an adapter type.
     */
    private fun getAdapterDescription(adapterType: String): String {
        return when (adapterType.lowercase()) {
            "mobile_local_llm" -> "On-device inference"
            "api" -> "CIRIS API endpoint"
            "discord" -> "Discord bot integration"
            "cli" -> "Command-line interface"
            else -> adapterType
        }
    }

    /**
     * Refresh status (alias for loadStatus).
     */
    fun refresh() = loadStatus()

    /**
     * Show a transient success message that auto-dismisses.
     */
    private fun showTransientMessage(message: String) {
        _successMessage.value = message
        viewModelScope.launch {
            delay(MESSAGE_DISMISS_DELAY_MS)
            if (_successMessage.value == message) {
                _successMessage.value = null
            }
        }
    }

    // ========== Adapter CRUD ==========

    /**
     * Reload an adapter with its current configuration.
     */
    fun reloadAdapter(adapterId: String) {
        val method = "reloadAdapter"
        if (_operationInProgress.value) {
            logWarn(method, "Operation already in progress")
            return
        }

        logInfo(method, "Reloading adapter: $adapterId")
        viewModelScope.launch {
            _operationInProgress.value = true
            try {
                val result = apiClient.reloadAdapter(adapterId)
                if (result.success) {
                    logInfo(method, "Adapter reloaded: $adapterId")
                    showTransientMessage("Adapter reloaded")
                    loadStatus()
                } else {
                    logError(method, "Failed to reload adapter: ${result.message}")
                    _errorMessage.value = result.message ?: "Failed to reload adapter"
                }
            } catch (e: Exception) {
                logError(method, "Error reloading adapter: ${e.message}")
                _errorMessage.value = "Failed to reload adapter: ${e.message}"
            } finally {
                _operationInProgress.value = false
            }
        }
    }

    /**
     * Remove/unload an adapter.
     */
    fun removeAdapter(adapterId: String) {
        val method = "removeAdapter"
        if (_operationInProgress.value) {
            logWarn(method, "Operation already in progress")
            return
        }

        logInfo(method, "Removing adapter: $adapterId")
        viewModelScope.launch {
            _operationInProgress.value = true
            try {
                val result = apiClient.removeAdapter(adapterId)
                if (result.success) {
                    logInfo(method, "Adapter removed: $adapterId")
                    showTransientMessage("Adapter removed")
                    loadStatus()
                } else {
                    logError(method, "Failed to remove adapter: ${result.message}")
                    _errorMessage.value = result.message ?: "Failed to remove adapter"
                }
            } catch (e: Exception) {
                logError(method, "Error removing adapter: ${e.message}")
                _errorMessage.value = "Failed to remove adapter: ${e.message}"
            } finally {
                _operationInProgress.value = false
            }
        }
    }

    // ========== Distribution Strategy ==========

    /**
     * Update the distribution strategy for the LLM Bus.
     */
    fun updateDistributionStrategy(strategy: DistributionStrategy) {
        val method = "updateDistributionStrategy"
        if (_operationInProgress.value) {
            logWarn(method, "Operation already in progress")
            return
        }

        logInfo(method, "Updating distribution strategy to ${strategy.name}")
        viewModelScope.launch {
            _operationInProgress.value = true
            try {
                val result = apiClient.updateLlmDistributionStrategy(strategy)
                if (result.success) {
                    logInfo(method, "Strategy updated: ${result.previousStrategy} -> ${result.newStrategy}")
                    showTransientMessage("Distribution strategy updated")
                    loadStatus()
                } else {
                    logError(method, "Failed to update strategy: ${result.message}")
                    _errorMessage.value = result.message
                }
            } catch (e: Exception) {
                logError(method, "Error updating strategy: ${e.message}")
                _errorMessage.value = "Failed to update strategy: ${e.message}"
            } finally {
                _operationInProgress.value = false
            }
        }
    }

    // ========== Circuit Breaker Management ==========

    /**
     * Reset a circuit breaker for a specific provider.
     */
    fun resetCircuitBreaker(providerName: String, force: Boolean = false) {
        val method = "resetCircuitBreaker"
        if (_operationInProgress.value) {
            logWarn(method, "Operation already in progress")
            return
        }

        logInfo(method, "Resetting circuit breaker for $providerName (force=$force)")
        viewModelScope.launch {
            _operationInProgress.value = true
            try {
                val result = apiClient.resetLlmCircuitBreaker(providerName, force)
                if (result.success) {
                    logInfo(method, "Circuit breaker reset: ${result.previousState} -> ${result.newState}")
                    showTransientMessage("Protection reset for $providerName")
                    loadStatus()
                } else {
                    logError(method, "Failed to reset circuit breaker: ${result.message}")
                    _errorMessage.value = result.message
                }
            } catch (e: Exception) {
                logError(method, "Error resetting circuit breaker: ${e.message}")
                _errorMessage.value = "Failed to reset protection: ${e.message}"
            } finally {
                _operationInProgress.value = false
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
        if (_operationInProgress.value) {
            logWarn(method, "Operation already in progress")
            return
        }

        logInfo(method, "Updating CB config for $providerName")
        viewModelScope.launch {
            _operationInProgress.value = true
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
                    showTransientMessage("Protection settings updated")
                    loadStatus()
                } else {
                    logError(method, "Failed to update CB config: ${result.message}")
                    _errorMessage.value = result.message
                }
            } catch (e: Exception) {
                logError(method, "Error updating CB config: ${e.message}")
                _errorMessage.value = "Failed to update config: ${e.message}"
            } finally {
                _operationInProgress.value = false
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
        if (_operationInProgress.value) {
            logWarn(method, "Operation already in progress")
            return
        }

        logInfo(method, "Updating priority for $providerName to ${priority.name}")
        viewModelScope.launch {
            _operationInProgress.value = true
            try {
                val result = apiClient.updateLlmProviderPriority(providerName, priority)
                if (result.success) {
                    logInfo(method, "Priority updated: ${result.previousPriority} -> ${result.newPriority}")
                    showTransientMessage("Priority updated")
                    loadStatus()
                } else {
                    logError(method, "Failed to update priority: ${result.message}")
                    _errorMessage.value = result.message
                }
            } catch (e: Exception) {
                logError(method, "Error updating priority: ${e.message}")
                _errorMessage.value = "Failed to update priority: ${e.message}"
            } finally {
                _operationInProgress.value = false
            }
        }
    }

    /**
     * Check if a provider is a system provider that requires confirmation to delete.
     */
    fun isSystemProvider(providerName: String): Boolean {
        return providerName in listOf("ciris_primary", "local_primary")
    }

    /**
     * Request deletion of a provider. For system providers, this sets the pending
     * delete state to show a confirmation dialog.
     */
    fun requestDeleteProvider(providerName: String) {
        if (isSystemProvider(providerName)) {
            _providerPendingDelete.value = providerName
        } else {
            deleteProvider(providerName)
        }
    }

    /**
     * Cancel the pending provider deletion.
     */
    fun cancelDeleteProvider() {
        _providerPendingDelete.value = null
    }

    /**
     * Confirm deletion of a system provider.
     */
    fun confirmDeleteProvider() {
        val providerName = _providerPendingDelete.value ?: return
        _providerPendingDelete.value = null
        deleteProvider(providerName)
    }

    /**
     * Delete/unregister a provider from the LLM Bus.
     *
     * @param providerName Name of the provider to delete
     */
    fun deleteProvider(providerName: String) {
        val method = "deleteProvider"
        if (_operationInProgress.value) {
            logWarn(method, "Operation already in progress")
            return
        }

        logInfo(method, "Deleting provider $providerName")
        viewModelScope.launch {
            _operationInProgress.value = true
            try {
                val result = apiClient.deleteLlmProvider(providerName)
                if (result.success) {
                    logInfo(method, "Provider deleted: ${result.message}")
                    showTransientMessage("Provider removed")
                    loadStatus()
                } else {
                    logError(method, "Failed to delete provider: ${result.message}")
                    _errorMessage.value = result.message
                }
            } catch (e: Exception) {
                logError(method, "Error deleting provider: ${e.message}")
                _errorMessage.value = "Failed to delete provider: ${e.message}"
            } finally {
                _operationInProgress.value = false
            }
        }
    }

    // ========== Local Server Discovery ==========

    /**
     * Discover local LLM inference servers on the network.
     */
    fun discoverLocalServers() {
        val method = "discoverLocalServers"
        if (_isDiscovering.value) {
            logWarn(method, "Discovery already in progress")
            return
        }

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
                    showTransientMessage("Found ${servers.size} server${if (servers.size > 1) "s" else ""}")
                } else {
                    showTransientMessage("No local servers found")
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
        priority: ProviderPriority = ProviderPriority.FALLBACK,
        selectedModel: String? = null
    ) {
        val method = "addDiscoveredServerAsProvider"
        if (_operationInProgress.value) {
            logWarn(method, "Operation already in progress")
            return
        }

        logInfo(method, "Adding ${server.label} as ${priority.name} provider with model: ${selectedModel ?: "auto"}")
        viewModelScope.launch {
            _operationInProgress.value = true
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

                // Use selected model, or fall back to first available model
                val model = selectedModel ?: server.models.firstOrNull()

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
                    showTransientMessage("Added ${server.label}")
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
                _operationInProgress.value = false
            }
        }
    }

    /**
     * Add a cloud provider with API key.
     *
     * @param providerId Provider type (openai, anthropic, openrouter, etc.)
     * @param apiKey The API key for the provider
     * @param baseUrl Optional custom base URL (uses default for provider if not specified)
     * @param model Optional specific model to use (fetched via listModels API)
     * @param priority Priority level for the new provider
     */
    fun addCloudProvider(
        providerId: String,
        apiKey: String,
        baseUrl: String? = null,
        model: String? = null,
        priority: ProviderPriority = ProviderPriority.FALLBACK
    ) {
        val method = "addCloudProvider"
        if (_operationInProgress.value) {
            logWarn(method, "Operation already in progress")
            return
        }

        logInfo(method, "Adding $providerId as ${priority.name} provider${model?.let { " with model $it" } ?: ""}")
        viewModelScope.launch {
            _operationInProgress.value = true
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
                    model = model,  // Use selected model or provider's default
                    apiKey = apiKey,
                    priority = priority
                )

                if (result.success) {
                    logInfo(method, "Provider added: ${result.providerName}")
                    showTransientMessage("Added $providerId provider")
                    loadStatus()
                } else {
                    logError(method, "Failed to add provider: ${result.message}")
                    _errorMessage.value = result.message
                }
            } catch (e: Exception) {
                logError(method, "Error adding provider: ${e.message}")
                _errorMessage.value = "Failed to add provider: ${e.message}"
            } finally {
                _operationInProgress.value = false
            }
        }
    }

    // ========== Section Toggle Methods ==========

    fun toggleStatusExpanded() {
        _statusExpanded.value = !_statusExpanded.value
    }

    fun toggleAdaptersExpanded() {
        _adaptersExpanded.value = !_adaptersExpanded.value
    }

    fun toggleProvidersExpanded() {
        _providersExpanded.value = !_providersExpanded.value
    }

    fun toggleAddProviderExpanded() {
        _addProviderExpanded.value = !_addProviderExpanded.value
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
     *
     * This uses standard provider CRUD to delete CIRIS providers:
     * 1. Delete ciris_primary provider (if exists)
     * 2. Delete local_primary provider (if exists)
     * 3. Persist disabled state for restart
     */
    fun disableCirisServices() {
        val method = "disableCirisServices"
        if (_operationInProgress.value) {
            logWarn(method, "Operation already in progress")
            return
        }

        logInfo(method, "Disabling CIRIS services via provider CRUD")
        viewModelScope.launch {
            _operationInProgress.value = true
            try {
                val providers = _llmProviders.value
                var deletedCount = 0

                // 1. Delete ciris_primary provider via standard CRUD
                val cirisProvider = providers.find { it.name == "ciris_primary" }
                if (cirisProvider != null) {
                    logInfo(method, "Deleting ciris_primary provider")
                    try {
                        val result = apiClient.deleteLlmProvider("ciris_primary")
                        if (result.success) {
                            deletedCount++
                            logInfo(method, "Deleted ciris_primary")
                        } else {
                            logWarn(method, "Failed to delete ciris_primary: ${result.message}")
                        }
                    } catch (e: Exception) {
                        logWarn(method, "Error deleting ciris_primary: ${e.message}")
                    }
                }

                // 2. Delete local_primary provider via standard CRUD
                val localProvider = providers.find { it.name == "local_primary" }
                if (localProvider != null) {
                    logInfo(method, "Deleting local_primary provider")
                    try {
                        val result = apiClient.deleteLlmProvider("local_primary")
                        if (result.success) {
                            deletedCount++
                            logInfo(method, "Deleted local_primary")
                        } else {
                            logWarn(method, "Failed to delete local_primary: ${result.message}")
                        }
                    } catch (e: Exception) {
                        logWarn(method, "Error deleting local_primary: ${e.message}")
                    }
                }

                // 3. Persist disabled state for restart
                logInfo(method, "Persisting CIRIS services disabled state")
                val result = apiClient.disableCirisServices()
                if (result.success) {
                    _cirisServicesEnabled.value = false
                    showTransientMessage("CIRIS services disabled ($deletedCount providers removed)")
                    logInfo(method, "CIRIS services disabled successfully")
                    // Refresh to reflect changes
                    loadStatus()
                } else {
                    _errorMessage.value = result.message ?: "Failed to persist disabled state"
                    logError(method, "Failed to persist: ${result.message}")
                }
            } catch (e: Exception) {
                _errorMessage.value = "Failed to disable CIRIS services: ${e.message}"
                logError(method, "Error: ${e.message}")
            } finally {
                _operationInProgress.value = false
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
