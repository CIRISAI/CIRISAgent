package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.EnrichmentCacheStatsData
import ai.ciris.mobile.shared.api.EnvironmentInfoResponse
import ai.ciris.mobile.shared.api.LocationInfoData
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * State for the Environment Info screen.
 */
data class EnvironmentInfoScreenState(
    val location: LocationInfoData? = null,
    val contextEnrichment: Map<String, Any> = emptyMap(),
    val cacheStats: EnrichmentCacheStatsData? = null,
    val timestamp: String? = null,
    val isLoading: Boolean = false,
    val isRefreshing: Boolean = false,
    val error: String? = null
)

/**
 * ViewModel for the Environment Info screen.
 *
 * Shows context data from adapters including:
 * - User location from setup (lat/long, timezone, city)
 * - Context enrichment results from adapters (weather, HA entities, etc.)
 * - Cache statistics for debugging
 */
class EnvironmentInfoViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "EnvironmentInfoViewModel"
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
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    // State
    private val _state = MutableStateFlow(EnvironmentInfoScreenState())
    val state: StateFlow<EnvironmentInfoScreenState> = _state.asStateFlow()

    private var dataLoadStarted = false

    init {
        logInfo("init", "EnvironmentInfoViewModel initialized")
    }

    /**
     * Start loading environment info.
     */
    fun startPolling() {
        val method = "startPolling"
        if (dataLoadStarted) {
            logDebug(method, "Data load already started, skipping")
            return
        }
        dataLoadStarted = true
        loadEnvironmentInfo()
    }

    /**
     * Refresh environment info.
     */
    fun refresh() {
        val method = "refresh"
        logInfo(method, "Refreshing environment info")
        _state.update { it.copy(isRefreshing = true, error = null) }
        loadEnvironmentInfo()
    }

    private fun loadEnvironmentInfo() {
        val method = "loadEnvironmentInfo"
        logInfo(method, "Loading environment info from API")

        viewModelScope.launch {
            try {
                if (!_state.value.isRefreshing) {
                    _state.update { it.copy(isLoading = true, error = null) }
                }

                val response = apiClient.getEnvironmentInfo()

                logInfo(method, "Environment info loaded: hasCoordinates=${response.location.hasCoordinates}, " +
                        "enrichmentCount=${response.contextEnrichment.size}")

                _state.update {
                    it.copy(
                        location = response.location,
                        contextEnrichment = response.contextEnrichment,
                        cacheStats = response.cacheStats,
                        timestamp = response.timestamp,
                        isLoading = false,
                        isRefreshing = false,
                        error = null
                    )
                }
            } catch (e: Exception) {
                logError(method, "Error loading environment info: ${e.message}")
                _state.update {
                    it.copy(
                        isLoading = false,
                        isRefreshing = false,
                        error = e.message ?: "Unknown error"
                    )
                }
            }
        }
    }
}
