package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Scheduler stats from telemetry.
 */
data class SchedulerStatsData(
    val activeDeferrals: Int = 0,
    val tasksCompleted24h: Int = 0,
    val currentTask: String? = null,
    val cognitiveState: String = "UNKNOWN"
)

/**
 * State for the Scheduler screen.
 */
data class SchedulerScreenState(
    val stats: SchedulerStatsData = SchedulerStatsData(),
    val isLoading: Boolean = false,
    val isRefreshing: Boolean = false,
    val error: String? = null
)

/**
 * ViewModel for the Scheduler screen.
 *
 * Features:
 * - Shows task scheduler status from telemetry
 * - Displays active deferrals and completed tasks
 * - Shows current cognitive state
 */
class SchedulerViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "SchedulerViewModel"
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
    private val _state = MutableStateFlow(SchedulerScreenState())
    val state: StateFlow<SchedulerScreenState> = _state.asStateFlow()
    private var dataLoadStarted = false

    init {
        logInfo("init", "SchedulerViewModel initialized")
    }

    /**
     * Start scheduler data loading.
     */
    fun startPolling() {
        val method = "startPolling"
        if (dataLoadStarted) {
            logDebug(method, "Data load already started, skipping")
            return
        }
        dataLoadStarted = true
        logInfo(method, "Starting scheduler data loading")
        refresh()
    }

    /**
     * Stop polling.
     */
    fun stopPolling() {
        val method = "stopPolling"
        logInfo(method, "Stopping scheduler polling")
        dataLoadStarted = false
    }

    /**
     * Refresh scheduler data.
     */
    fun refresh() {
        val method = "refresh"
        logInfo(method, "Refreshing scheduler data")

        viewModelScope.launch {
            _state.update { it.copy(isRefreshing = true, error = null) }

            try {
                // Get telemetry overview which contains scheduler-related stats
                val telemetry = apiClient.getUnifiedTelemetry()

                val stats = SchedulerStatsData(
                    activeDeferrals = 0, // Will be fetched separately if needed
                    tasksCompleted24h = 0, // Not directly available
                    currentTask = null,
                    cognitiveState = telemetry.cognitiveState
                )

                // Also get environmental metrics which may have more details
                try {
                    val envMetrics = apiClient.getEnvironmentalMetrics()
                    // Environmental metrics don't have task info, but we tried
                } catch (e: Exception) {
                    logDebug(method, "Environmental metrics not available: ${e.message}")
                }

                _state.update {
                    it.copy(
                        stats = stats,
                        isRefreshing = false,
                        error = null
                    )
                }

                logInfo(method, "Scheduler stats: cognitiveState=${stats.cognitiveState}")

            } catch (e: Exception) {
                logError(method, "Failed to refresh: ${e.message}")
                _state.update {
                    it.copy(
                        isRefreshing = false,
                        error = "Failed to refresh: ${e.message}"
                    )
                }
            }
        }
    }

    override fun onCleared() {
        logInfo("onCleared", "ViewModel cleared")
        super.onCleared()
    }
}
