package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.SystemLogApiData
import ai.ciris.mobile.shared.ui.screens.LogEntryData
import ai.ciris.mobile.shared.ui.screens.LogsFilter
import ai.ciris.mobile.shared.ui.screens.LogsScreenState
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * ViewModel for the Logs screen.
 *
 * Features:
 * - Fetches system logs from /v1/telemetry/logs
 * - Auto-refresh with configurable interval
 * - Filtering by log level and service
 * - Search within logs
 * - Auto-scroll to latest logs
 */
class LogsViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "LogsViewModel"
        private const val DEFAULT_REFRESH_INTERVAL_MS = 5000L
    }

    private fun log(level: String, method: String, message: String) {
        println("[$TAG][$level][$method] $message")
    }

    private fun logDebug(method: String, message: String) = log("DEBUG", method, message)
    private fun logInfo(method: String, message: String) = log("INFO", method, message)
    @Suppress("unused")
    private fun logWarn(method: String, message: String) = log("WARN", method, message)
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    // State
    private val _state = MutableStateFlow(LogsScreenState())
    val state: StateFlow<LogsScreenState> = _state.asStateFlow()

    // Polling job
    private var pollingJob: Job? = null

    init {
        logInfo("init", "LogsViewModel initialized")
        fetchLogs()
        startPolling()
    }

    /**
     * Manual refresh triggered by user
     */
    fun refresh() {
        val method = "refresh"
        logInfo(method, "Manual refresh triggered")
        fetchLogs()
    }

    /**
     * Update filter and refetch
     */
    fun updateFilter(newFilter: LogsFilter) {
        val method = "updateFilter"
        logInfo(method, "Filter changed: level=${newFilter.level}, service=${newFilter.service}, limit=${newFilter.limit}")
        _state.update { it.copy(filter = newFilter) }
        fetchLogs()
    }

    /**
     * Update search query
     */
    fun updateSearch(query: String) {
        val method = "updateSearch"
        logDebug(method, "Search query: $query")
        _state.update { it.copy(searchQuery = query) }
        // Filter logs locally based on search
        filterLogsLocally()
    }

    /**
     * Toggle auto-scroll
     */
    fun toggleAutoScroll() {
        val method = "toggleAutoScroll"
        _state.update { current ->
            val newAutoScroll = !current.autoScroll
            logInfo(method, "Auto-scroll toggled: $newAutoScroll")
            current.copy(autoScroll = newAutoScroll)
        }
    }

    /**
     * Start automatic log polling
     */
    private fun startPolling() {
        val method = "startPolling"
        logInfo(method, "Starting log polling (interval=${DEFAULT_REFRESH_INTERVAL_MS}ms)")

        pollingJob = viewModelScope.launch {
            while (isActive) {
                delay(DEFAULT_REFRESH_INTERVAL_MS)
                fetchLogs(isAutoRefresh = true)
            }
        }
    }

    /**
     * Stop automatic polling
     */
    fun stopPolling() {
        val method = "stopPolling"
        logInfo(method, "Stopping log polling")
        pollingJob?.cancel()
        pollingJob = null
    }

    /**
     * Fetch logs from API
     */
    private fun fetchLogs(isAutoRefresh: Boolean = false) {
        val method = "fetchLogs"
        val filter = _state.value.filter

        if (!isAutoRefresh) {
            logDebug(method, "Fetching logs: level=${filter.level}, service=${filter.service}, limit=${filter.limit}")
        }

        viewModelScope.launch {
            if (!isAutoRefresh) {
                _state.update { it.copy(isLoading = true, error = null) }
            }

            try {
                val result = apiClient.getSystemLogs(
                    level = filter.level,
                    service = filter.service,
                    limit = filter.limit
                )

                logInfo(method, "Fetched ${result.logs.size} logs")

                // Extract unique services for filter options
                val services = result.logs
                    .map { it.service }
                    .distinct()
                    .sorted()

                val displayLogs = result.logs.mapIndexed { index, log ->
                    LogEntryData(
                        id = "${log.timestamp}_$index",
                        timestamp = log.timestamp,
                        level = log.level,
                        service = log.service,
                        message = log.message,
                        metadata = formatLogMetadata(log),
                        traceId = log.traceId
                    )
                }

                _state.update { current ->
                    current.copy(
                        logs = filterBySearch(displayLogs, current.searchQuery),
                        availableServices = services,
                        isLoading = false,
                        error = null,
                        refreshIntervalSeconds = (DEFAULT_REFRESH_INTERVAL_MS / 1000).toInt()
                    )
                }
            } catch (e: Exception) {
                logError(method, "Failed to fetch logs: ${e::class.simpleName}: ${e.message}")
                if (!isAutoRefresh) {
                    _state.update {
                        it.copy(
                            isLoading = false,
                            error = "Failed to load logs: ${e.message}"
                        )
                    }
                }
            }
        }
    }

    private fun filterLogsLocally() {
        // Re-filter existing logs based on search query
        // This provides instant feedback while typing
        _state.update { current ->
            val allLogs = current.logs // In real impl, keep unfiltered list
            current.copy(logs = filterBySearch(allLogs, current.searchQuery))
        }
    }

    private fun filterBySearch(logs: List<LogEntryData>, query: String): List<LogEntryData> {
        if (query.isBlank()) return logs
        val lowerQuery = query.lowercase()
        return logs.filter { log ->
            log.message.lowercase().contains(lowerQuery) ||
            log.service.lowercase().contains(lowerQuery) ||
            log.level.lowercase().contains(lowerQuery)
        }
    }

    private fun formatLogMetadata(log: SystemLogApiData): String {
        return buildString {
            log.traceId?.let { appendLine("Trace ID: $it") }
            log.context?.forEach { (key, value) ->
                appendLine("$key: $value")
            }
        }
    }

    override fun onCleared() {
        logInfo("onCleared", "ViewModel cleared, stopping polling")
        stopPolling()
        super.onCleared()
    }
}
