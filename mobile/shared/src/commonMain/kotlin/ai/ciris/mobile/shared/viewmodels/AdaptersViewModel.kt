package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
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
        println("[$TAG][$level][$method] $message")
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
     * For now, this is a placeholder - the actual add flow requires
     * module types and configuration wizard which is complex.
     * The UI should handle this by showing a dialog or navigation.
     */
    fun addAdapter() {
        val method = "addAdapter"
        logInfo(method, "Add adapter requested - UI should handle this")
        _statusMessage.value = "Add adapter feature requires UI dialog"
        viewModelScope.launch {
            clearStatusMessageAfterDelay()
        }
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
