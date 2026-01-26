package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.DeferralData
import ai.ciris.mobile.shared.api.WAStatusData
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
 * Shared ViewModel for Wise Authority screen
 *
 * Features:
 * - WA service status monitoring
 * - Pending deferrals list
 * - Deferral resolution
 * - Auto-refresh with configurable interval
 */
class WiseAuthorityViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "WiseAuthorityViewModel"
        private const val POLL_INTERVAL_MS = 10000L // Poll every 10 seconds
    }

    private fun log(level: String, method: String, message: String) {
        println("[$TAG][$level][$method] $message")
    }

    private fun logDebug(method: String, message: String) = log("DEBUG", method, message)
    private fun logInfo(method: String, message: String) = log("INFO", method, message)
    private fun logWarn(method: String, message: String) = log("WARN", method, message)
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    // WA Status
    private val _waStatus = MutableStateFlow<WAStatusData?>(null)
    val waStatus: StateFlow<WAStatusData?> = _waStatus.asStateFlow()

    // Deferrals list
    private val _deferrals = MutableStateFlow<List<DeferralData>>(emptyList())
    val deferrals: StateFlow<List<DeferralData>> = _deferrals.asStateFlow()

    // Loading state
    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    // Error state
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    // Success message (e.g., after resolving deferral)
    private val _successMessage = MutableStateFlow<String?>(null)
    val successMessage: StateFlow<String?> = _successMessage.asStateFlow()

    // Connection state
    private val _isConnected = MutableStateFlow(false)
    val isConnected: StateFlow<Boolean> = _isConnected.asStateFlow()

    // Resolving deferral state
    private val _isResolving = MutableStateFlow(false)
    val isResolving: StateFlow<Boolean> = _isResolving.asStateFlow()

    // Polling job
    private var pollingJob: Job? = null
    private var isFirstLoad = true

    init {
        logInfo("init", "WiseAuthorityViewModel initialized")
        startPolling()
    }

    /**
     * Start automatic polling
     */
    private fun startPolling() {
        val method = "startPolling"
        logInfo(method, "Starting WA polling (interval=${POLL_INTERVAL_MS}ms)")

        pollingJob = viewModelScope.launch {
            var pollCount = 0
            while (isActive) {
                pollCount++
                logDebug(method, "Poll cycle #$pollCount starting")

                try {
                    fetchDataInternal()
                    _isConnected.value = true
                    _error.value = null

                    if (pollCount % 6 == 0) {
                        logInfo(method, "Poll cycle #$pollCount completed successfully")
                    }
                } catch (e: Exception) {
                    logError(method, "Poll cycle #$pollCount failed: ${e::class.simpleName}: ${e.message}")
                    _isConnected.value = false
                    _error.value = "Connection error: ${e.message}"
                } finally {
                    if (isFirstLoad) {
                        logInfo(method, "First load complete")
                        _isLoading.value = false
                        isFirstLoad = false
                    }
                }

                delay(POLL_INTERVAL_MS)
            }
        }
    }

    /**
     * Stop automatic polling
     */
    fun stopPolling() {
        val method = "stopPolling"
        logInfo(method, "Stopping WA polling")
        pollingJob?.cancel()
        pollingJob = null
    }

    /**
     * Manual refresh triggered by user
     */
    fun refresh() {
        val method = "refresh"
        logInfo(method, "Manual refresh triggered")

        viewModelScope.launch {
            _isLoading.value = true
            logDebug(method, "Loading state set to true")

            try {
                fetchDataInternal()
                _isConnected.value = true
                _error.value = null
                logInfo(method, "Manual refresh completed successfully")
            } catch (e: Exception) {
                logError(method, "Manual refresh failed: ${e::class.simpleName}: ${e.message}")
                _isConnected.value = false
                _error.value = "Refresh failed: ${e.message}"
            } finally {
                _isLoading.value = false
                logDebug(method, "Loading state set to false")
            }
        }
    }

    /**
     * Fetch WA status and deferrals from API
     */
    private suspend fun fetchDataInternal() {
        val method = "fetchDataInternal"
        logDebug(method, "Fetching WA data from API")

        try {
            // Fetch status
            val status = apiClient.getWAStatus()
            _waStatus.value = status
            logDebug(method, "WA status: healthy=${status.serviceHealthy}, activeWAs=${status.activeWAs}, " +
                    "pendingDeferrals=${status.pendingDeferrals}")

            // Fetch deferrals
            val deferrals = apiClient.getDeferrals()
            _deferrals.value = deferrals
            logDebug(method, "Fetched ${deferrals.size} deferrals")

        } catch (e: Exception) {
            logError(method, "Failed to fetch WA data: ${e::class.simpleName}: ${e.message}")
            throw e
        }
    }

    /**
     * Resolve a pending deferral
     */
    fun resolveDeferral(deferralId: String, resolution: String, guidance: String) {
        val method = "resolveDeferral"
        logInfo(method, "Resolving deferral: id=$deferralId, resolution=$resolution")

        viewModelScope.launch {
            _isResolving.value = true
            _error.value = null

            try {
                val result = apiClient.resolveDeferral(deferralId, resolution, guidance)
                logInfo(method, "Deferral resolved: ${result.deferralId}, success=${result.success}")

                _successMessage.value = "Deferral resolved successfully"

                // Refresh to update the list
                fetchDataInternal()

            } catch (e: Exception) {
                logError(method, "Failed to resolve deferral: ${e::class.simpleName}: ${e.message}")
                _error.value = "Failed to resolve deferral: ${e.message}"
            } finally {
                _isResolving.value = false
            }
        }
    }

    /**
     * Clear any error state
     */
    fun clearError() {
        val method = "clearError"
        logDebug(method, "Clearing error state")
        _error.value = null
    }

    /**
     * Clear success message
     */
    fun clearSuccess() {
        val method = "clearSuccess"
        logDebug(method, "Clearing success message")
        _successMessage.value = null
    }

    override fun onCleared() {
        logInfo("onCleared", "ViewModel cleared, cancelling polling job")
        super.onCleared()
        pollingJob?.cancel()
    }
}
