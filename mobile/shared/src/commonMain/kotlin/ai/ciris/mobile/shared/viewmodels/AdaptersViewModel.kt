package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.models.ConfigSessionData
import ai.ciris.mobile.shared.models.ConfigStepResultData
import ai.ciris.mobile.shared.models.DiscoveredItemData
import ai.ciris.mobile.shared.models.LoadableAdaptersData
import ai.ciris.mobile.shared.ui.screens.AdapterItem
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Shared ViewModel for Adapters management
 * Uses CIRISApiClient for all API calls (centralized auth handling)
 *
 * Features:
 * - List all active adapters with status
 * - Reload adapters with new configuration
 * - Remove adapters from runtime
 * - Poll for adapter status updates
 * - Connection status monitoring
 */
class AdaptersViewModel(
    private val apiClient: CIRISApiClient,
    baseUrl: String = "http://localhost:8080"
) : ViewModel() {

    companion object {
        private const val TAG = "AdaptersViewModel"
        private const val POLL_INTERVAL_MS = 10000L
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

    private fun logException(method: String, e: Exception, context: String = "") {
        val contextStr = if (context.isNotEmpty()) " | Context: $context" else ""
        logError(method, "Exception: ${e::class.simpleName}: ${e.message}$contextStr")
        logError(method, "Stack trace: ${e.stackTraceToString().take(500)}")
    }

    // State flows
    private val _adapters = MutableStateFlow<List<AdapterItem>>(emptyList())
    val adapters: StateFlow<List<AdapterItem>> = _adapters.asStateFlow()

    private val _isConnected = MutableStateFlow(false)
    val isConnected: StateFlow<Boolean> = _isConnected.asStateFlow()

    private val _isLoading = MutableStateFlow(true)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _statusMessage = MutableStateFlow<String?>(null)
    val statusMessage: StateFlow<String?> = _statusMessage.asStateFlow()

    private val _operationInProgress = MutableStateFlow(false)
    val operationInProgress: StateFlow<Boolean> = _operationInProgress.asStateFlow()

    // Wizard state flows
    private val _showWizardDialog = MutableStateFlow(false)
    val showWizardDialog: StateFlow<Boolean> = _showWizardDialog.asStateFlow()

    private val _loadableAdapters = MutableStateFlow<LoadableAdaptersData?>(null)
    val loadableAdapters: StateFlow<LoadableAdaptersData?> = _loadableAdapters.asStateFlow()

    private val _wizardSession = MutableStateFlow<ConfigSessionData?>(null)
    val wizardSession: StateFlow<ConfigSessionData?> = _wizardSession.asStateFlow()

    private val _wizardError = MutableStateFlow<String?>(null)
    val wizardError: StateFlow<String?> = _wizardError.asStateFlow()

    private val _wizardLoading = MutableStateFlow(false)
    val wizardLoading: StateFlow<Boolean> = _wizardLoading.asStateFlow()

    private val _discoveredItems = MutableStateFlow<List<DiscoveredItemData>>(emptyList())
    val discoveredItems: StateFlow<List<DiscoveredItemData>> = _discoveredItems.asStateFlow()

    private val _discoveryExecuted = MutableStateFlow(false)
    val discoveryExecuted: StateFlow<Boolean> = _discoveryExecuted.asStateFlow()

    // Polling job
    private var pollingJob: Job? = null
    private var isFirstLoad = true

    init {
        logInfo("init", "AdaptersViewModel initialized")
        // Don't auto-fetch in init - wait for token to be set via CIRISApp
    }

    /**
     * Start polling for adapter updates
     */
    fun startPolling() {
        val method = "startPolling"
        if (pollingJob?.isActive == true) {
            logDebug(method, "Polling already active, skipping")
            return
        }

        logInfo(method, "Starting adapter polling (interval=${POLL_INTERVAL_MS}ms)")
        pollingJob = viewModelScope.launch {
            var pollCount = 0
            while (isActive) {
                pollCount++
                delay(POLL_INTERVAL_MS)
                try {
                    fetchAdaptersInternal()
                    if (pollCount % 6 == 0) {
                        logDebug(method, "Poll #$pollCount: ${_adapters.value.size} adapters")
                    }
                } catch (e: Exception) {
                    logError(method, "Polling failed: ${e.message}")
                }
            }
        }
    }

    /**
     * Stop polling for adapter updates
     */
    fun stopPolling() {
        val method = "stopPolling"
        logInfo(method, "Stopping adapter polling")
        pollingJob?.cancel()
        pollingJob = null
    }

    /**
     * Refresh adapters list (manual trigger)
     */
    fun refresh() {
        val method = "refresh"
        logInfo(method, "Manual refresh triggered")
        fetchAdapters()
    }

    /**
     * Fetch adapters with loading indicator
     */
    fun fetchAdapters() {
        val method = "fetchAdapters"
        logDebug(method, "Fetching adapters with loading indicator")
        _isLoading.value = true
        viewModelScope.launch {
            try {
                fetchAdaptersInternal()
            } catch (e: Exception) {
                logException(method, e)
            } finally {
                if (isFirstLoad) {
                    logInfo(method, "First load complete")
                    isFirstLoad = false
                }
                _isLoading.value = false
            }
        }
    }

    /**
     * Internal adapter fetch (used by polling and manual refresh)
     */
    private suspend fun fetchAdaptersInternal() {
        val method = "fetchAdaptersInternal"
        try {
            logDebug(method, "Calling apiClient.listAdapters()")
            val data = apiClient.listAdapters()
            logInfo(method, "Fetched ${data.totalCount} adapters (${data.runningCount} running)")

            val adapterItems = data.adapters.map { adapterStatus ->
                val statusText = if (adapterStatus.isRunning) "running" else "stopped"
                AdapterItem(
                    id = adapterStatus.adapterId,
                    name = adapterStatus.adapterType.replaceFirstChar { it.uppercase() },
                    type = adapterStatus.adapterType.uppercase(),
                    status = statusText,
                    isHealthy = adapterStatus.isRunning
                )
            }

            _adapters.value = adapterItems
            _isConnected.value = true
            logDebug(method, "Adapters list updated: ${adapterItems.map { it.id }}")

        } catch (e: Exception) {
            logException(method, e)
            _isConnected.value = false
            throw e
        }
    }

    /**
     * Reload an adapter with its current configuration
     */
    fun reloadAdapter(adapterId: String) {
        val method = "reloadAdapter"
        logInfo(method, "Reloading adapter: $adapterId")

        if (_operationInProgress.value) {
            logWarn(method, "Operation already in progress, ignoring")
            return
        }

        viewModelScope.launch {
            try {
                _operationInProgress.value = true
                _statusMessage.value = "Reloading adapter..."

                // Find the adapter to get its type
                val adapter = _adapters.value.find { it.id == adapterId }
                if (adapter == null) {
                    logError(method, "Adapter not found: $adapterId")
                    _statusMessage.value = "Adapter not found"
                    clearStatusMessageAfterDelay()
                    return@launch
                }

                logDebug(method, "Found adapter: type=${adapter.type}")
                logDebug(method, "Calling apiClient.reloadAdapter($adapterId)")

                val result = apiClient.reloadAdapter(adapterId)
                logInfo(method, "Adapter reloaded: adapterId=${result.adapterId}, success=${result.success}")

                _statusMessage.value = if (result.success) {
                    "Adapter reloaded successfully"
                } else {
                    "Failed to reload adapter: ${result.message ?: "Unknown error"}"
                }

                // Refresh the list
                fetchAdaptersInternal()

            } catch (e: Exception) {
                logException(method, e, "adapterId=$adapterId")
                _statusMessage.value = "Error reloading adapter: ${e.message}"
            } finally {
                _operationInProgress.value = false
                clearStatusMessageAfterDelay()
            }
        }
    }

    /**
     * Remove an adapter from the runtime
     */
    fun removeAdapter(adapterId: String) {
        val method = "removeAdapter"
        logInfo(method, "Removing adapter: $adapterId")

        if (_operationInProgress.value) {
            logWarn(method, "Operation already in progress, ignoring")
            return
        }

        viewModelScope.launch {
            try {
                _operationInProgress.value = true
                _statusMessage.value = "Removing adapter..."

                logDebug(method, "Calling apiClient.removeAdapter($adapterId)")

                val result = apiClient.removeAdapter(adapterId)
                logInfo(method, "Adapter removed: adapterId=${result.adapterId}, success=${result.success}")

                _statusMessage.value = if (result.success) {
                    "Adapter removed successfully"
                } else {
                    "Failed to remove adapter: ${result.message ?: "Unknown error"}"
                }

                // Refresh the list
                fetchAdaptersInternal()

            } catch (e: Exception) {
                logException(method, e, "adapterId=$adapterId")
                _statusMessage.value = "Error removing adapter: ${e.message}"
            } finally {
                _operationInProgress.value = false
                clearStatusMessageAfterDelay()
            }
        }
    }

    /**
     * Add a new adapter (triggers add adapter flow)
     * Opens the wizard dialog and fetches loadable adapters (both configurable and direct-load).
     */
    fun addAdapter() {
        val method = "addAdapter"
        logInfo(method, "Opening adapter wizard dialog")
        viewModelScope.launch {
            _wizardLoading.value = true
            _wizardError.value = null
            try {
                val adapters = apiClient.getLoadableAdapters()
                _loadableAdapters.value = adapters
                _showWizardDialog.value = true
            } catch (e: Exception) {
                logException(method, e)
                _wizardError.value = "Failed to load adapters: ${e.message}"
            } finally {
                _wizardLoading.value = false
            }
        }
    }

    /**
     * Start the wizard for a specific adapter type.
     */
    fun startWizard(adapterType: String) {
        val method = "startWizard"
        logInfo(method, "Starting wizard for adapter type: $adapterType")
        viewModelScope.launch {
            _wizardLoading.value = true
            _wizardError.value = null
            _discoveredItems.value = emptyList()
            _discoveryExecuted.value = false
            try {
                val session = apiClient.startAdapterConfiguration(adapterType)
                _wizardSession.value = session
                // Auto-execute discovery step if first step is discovery type
                if (session.currentStep?.stepType == "discovery") {
                    logInfo(method, "First step is discovery, auto-executing...")
                    executeDiscoveryStepInternal(session)
                }
            } catch (e: Exception) {
                logException(method, e)
                _wizardError.value = "Failed to start wizard: ${e.message}"
            } finally {
                _wizardLoading.value = false
            }
        }
    }

    /**
     * Execute a discovery step (mDNS scan, etc.)
     */
    fun executeDiscoveryStep() {
        val method = "executeDiscoveryStep"
        val session = _wizardSession.value ?: return
        logInfo(method, "Executing discovery step for session: ${session.sessionId}")
        viewModelScope.launch {
            _wizardLoading.value = true
            _wizardError.value = null
            try {
                executeDiscoveryStepInternal(session)
            } catch (e: Exception) {
                logException(method, e)
                _wizardError.value = "Discovery failed: ${e.message}"
            } finally {
                _wizardLoading.value = false
            }
        }
    }

    /**
     * Internal method to execute discovery step.
     */
    private suspend fun executeDiscoveryStepInternal(session: ConfigSessionData) {
        val method = "executeDiscoveryStepInternal"
        val result = apiClient.executeConfigurationStep(session.sessionId, emptyMap())
        _discoveryExecuted.value = true

        if (result.discoveredItems.isNotEmpty()) {
            logInfo(method, "Discovery found ${result.discoveredItems.size} items")
            _discoveredItems.value = result.discoveredItems
        } else {
            logInfo(method, "No items discovered")
            _discoveredItems.value = emptyList()
        }

        // Update step index if discovery advanced us
        if (result.nextStepIndex != null) {
            _wizardSession.value = session.copy(
                currentStepIndex = result.nextStepIndex
            )
        }
    }

    /**
     * Select a discovered item and proceed to next step.
     */
    fun selectDiscoveredItem(item: DiscoveredItemData) {
        val method = "selectDiscoveredItem"
        val session = _wizardSession.value ?: return
        logInfo(method, "Selected discovered item: ${item.label}")
        // Submit selection with the item's value (typically the URL)
        viewModelScope.launch {
            _wizardLoading.value = true
            try {
                val stepData = mapOf(
                    "selected_url" to item.value,
                    "selected_id" to item.id
                )
                val result = apiClient.executeConfigurationStep(session.sessionId, stepData)
                handleStepResult(session, result)
            } catch (e: Exception) {
                logException(method, e)
                _wizardError.value = "Failed to select item: ${e.message}"
            } finally {
                _wizardLoading.value = false
            }
        }
    }

    /**
     * Submit a manual URL entry for discovery step.
     */
    fun submitManualUrl(url: String) {
        val method = "submitManualUrl"
        val session = _wizardSession.value ?: return
        logInfo(method, "Submitting manual URL: $url")
        viewModelScope.launch {
            _wizardLoading.value = true
            try {
                val stepData = mapOf("manual_url" to url)
                val result = apiClient.executeConfigurationStep(session.sessionId, stepData)
                handleStepResult(session, result)
            } catch (e: Exception) {
                logException(method, e)
                _wizardError.value = "Failed to submit URL: ${e.message}"
            } finally {
                _wizardLoading.value = false
            }
        }
    }

    /**
     * Handle step result and update session state.
     */
    private suspend fun handleStepResult(session: ConfigSessionData, result: ConfigStepResultData) {
        val method = "handleStepResult"
        // Fetch updated session status to get next step details and check completion
        try {
            val updatedSession = apiClient.getConfigurationSessionStatus(session.sessionId)
            logInfo(method, "Fetched updated session: step=${updatedSession.currentStepIndex}/${updatedSession.totalSteps}, stepType=${updatedSession.currentStep?.stepType}")

            // Check if wizard is complete (advanced past all steps)
            if (updatedSession.currentStepIndex >= updatedSession.totalSteps) {
                logInfo(method, "Wizard completed! (step ${updatedSession.currentStepIndex} >= totalSteps ${updatedSession.totalSteps})")
                closeWizard()
                fetchAdaptersInternal()
                return
            }

            _wizardSession.value = updatedSession
            _discoveredItems.value = emptyList()
            _discoveryExecuted.value = false

            // Auto-execute if next step is also discovery
            if (updatedSession.currentStep?.stepType == "discovery") {
                logInfo(method, "Next step is discovery, auto-executing...")
                executeDiscoveryStepInternal(updatedSession)
            }
        } catch (e: Exception) {
            logError(method, "Failed to fetch session status: ${e.message}")
            // Fall back to updating step index only if explicitly provided
            // Don't auto-increment - null nextStepIndex means stay on current step (e.g., awaiting callback)
            if (result.nextStepIndex != null) {
                _wizardSession.value = session.copy(
                    currentStepIndex = result.nextStepIndex
                )
            }
        }
    }

    /**
     * Load an adapter directly without configuration (for adapters that don't require config).
     */
    fun loadAdapterDirectly(adapterType: String) {
        val method = "loadAdapterDirectly"
        logInfo(method, "Loading adapter directly: $adapterType")
        viewModelScope.launch {
            _wizardLoading.value = true
            _wizardError.value = null
            try {
                val result = apiClient.loadAdapter(adapterType)
                if (result.success) {
                    logInfo(method, "Adapter loaded successfully: ${result.adapterId}")
                    closeWizard()
                    fetchAdaptersInternal() // Refresh adapters list
                    _statusMessage.value = "Adapter loaded successfully"
                    clearStatusMessageAfterDelay()
                } else {
                    logError(method, "Failed to load adapter: ${result.message}")
                    _wizardError.value = result.message ?: "Failed to load adapter"
                }
            } catch (e: Exception) {
                logException(method, e)
                _wizardError.value = "Failed to load adapter: ${e.message}"
            } finally {
                _wizardLoading.value = false
            }
        }
    }

    /**
     * Submit the current wizard step with field values.
     */
    fun submitWizardStep(stepData: Map<String, String>) {
        val method = "submitWizardStep"
        val session = _wizardSession.value ?: return
        logInfo(method, "Submitting step for session: ${session.sessionId}")
        viewModelScope.launch {
            _wizardLoading.value = true
            _wizardError.value = null
            try {
                val result = apiClient.executeConfigurationStep(session.sessionId, stepData)
                handleStepResult(session, result)
            } catch (e: Exception) {
                logException(method, e)
                _wizardError.value = "Failed to submit step: ${e.message}"
            } finally {
                _wizardLoading.value = false
            }
        }
    }

    /**
     * Go back to the previous wizard step.
     */
    fun wizardBack() {
        val method = "wizardBack"
        logInfo(method, "Going back in wizard")
        // For now, just close the session and start fresh
        _wizardSession.value = null
        _wizardError.value = null
    }

    /**
     * Close the wizard dialog.
     */
    fun closeWizard() {
        val method = "closeWizard"
        logInfo(method, "Closing wizard dialog")
        _showWizardDialog.value = false
        _wizardSession.value = null
        _loadableAdapters.value = null
        _wizardError.value = null
        _discoveredItems.value = emptyList()
        _discoveryExecuted.value = false
    }

    /**
     * Clear status message after a delay
     */
    private suspend fun clearStatusMessageAfterDelay() {
        delay(3000)
        _statusMessage.value = null
    }

    /**
     * Clear any displayed status message immediately
     */
    fun clearStatusMessage() {
        val method = "clearStatusMessage"
        logDebug(method, "Clearing status message")
        _statusMessage.value = null
    }

    override fun onCleared() {
        logInfo("onCleared", "ViewModel cleared, stopping polling")
        super.onCleared()
        stopPolling()
    }
}
