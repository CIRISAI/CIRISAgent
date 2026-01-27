package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.ui.screens.ServiceHealthItem
import ai.ciris.mobile.shared.ui.screens.TelemetryData
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
 * Shared ViewModel for telemetry screen
 * Ported from Android TelemetryFragment.kt
 *
 * Features:
 * - System telemetry polling (services, resources, activity)
 * - Cognitive state monitoring
 * - Resource usage tracking (CPU, memory, disk)
 * - Activity metrics (messages, tasks, errors in 24h)
 * - Auto-refresh with configurable interval
 */
class TelemetryViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "TelemetryViewModel"
        private const val POLL_INTERVAL_MS = 5000L
    }

    private fun log(level: String, method: String, message: String) {
        println("[$TAG][$level][$method] $message")
    }

    private fun logDebug(method: String, message: String) = log("DEBUG", method, message)
    private fun logInfo(method: String, message: String) = log("INFO", method, message)
    private fun logWarn(method: String, message: String) = log("WARN", method, message)
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    // Telemetry data state
    private val _telemetryData = MutableStateFlow(TelemetryData())
    val telemetryData: StateFlow<TelemetryData> = _telemetryData.asStateFlow()

    // Loading state
    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    // Error state
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    // Connection state
    private val _isConnected = MutableStateFlow(false)
    val isConnected: StateFlow<Boolean> = _isConnected.asStateFlow()

    // Polling job
    private var pollingJob: Job? = null
    private var isFirstLoad = true

    init {
        logInfo("init", "TelemetryViewModel initialized")
        startPolling()
    }

    /**
     * Start automatic telemetry polling
     */
    private fun startPolling() {
        val method = "startPolling"
        logInfo(method, "Starting telemetry polling (interval=${POLL_INTERVAL_MS}ms)")

        pollingJob = viewModelScope.launch {
            var pollCount = 0
            while (isActive) {
                pollCount++
                logDebug(method, "Poll cycle #$pollCount starting")

                try {
                    fetchTelemetryInternal()
                    _isConnected.value = true
                    _error.value = null

                    if (pollCount % 10 == 0) {
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
        logInfo(method, "Stopping telemetry polling")
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
                fetchTelemetryInternal()
                _isConnected.value = true
                _error.value = null
                logInfo(method, "Manual refresh completed successfully")
            } catch (e: Exception) {
                logError(method, "Manual refresh failed: ${e::class.simpleName}: ${e.message}")
                logError(method, "Stack trace: ${e.stackTraceToString().take(500)}")
                _isConnected.value = false
                _error.value = "Refresh failed: ${e.message}"
            } finally {
                _isLoading.value = false
                logDebug(method, "Loading state set to false")
            }
        }
    }

    /**
     * Fetch telemetry data from API
     */
    private suspend fun fetchTelemetryInternal() {
        val method = "fetchTelemetryInternal"
        logDebug(method, "Fetching telemetry data from API")

        try {
            val response = apiClient.getTelemetry()
            logDebug(method, "API response received")

            val data = response.data
            logDebug(method, "Raw data: uptime=${data.uptime_seconds}s, state=${data.cognitive_state}, " +
                    "servicesOnline=${data.services_online}, servicesTotal=${data.services_total}, " +
                    "cpu=${data.cpu_percent}%, memory=${data.memory_mb}MB")

            // Build service health items with activity metrics
            val serviceHealthItems = buildServiceHealthItems(
                healthyServices = data.services_online,
                totalServices = data.services_total,
                messagesProcessed24h = data.messages_processed_24h,
                tasksCompleted24h = data.tasks_completed_24h,
                errors24h = data.errors_24h
            )
            logDebug(method, "Built ${serviceHealthItems.size} service health items")

            // Map API response to TelemetryData model (UI model)
            val telemetryData = TelemetryData(
                healthyServices = data.services_online,
                totalServices = data.services_total,
                cognitiveState = data.cognitive_state.uppercase().ifEmpty { "WORK" },
                cpuPercent = data.cpu_percent.toInt(),
                memoryMb = data.memory_mb.toInt(),
                diskUsedMb = 0.0, // Not available in current API response - would need /system/resources endpoint
                messagesProcessed24h = data.messages_processed_24h,
                tasksCompleted24h = data.tasks_completed_24h,
                errors24h = data.errors_24h,
                serviceHealthItems = serviceHealthItems
            )

            logInfo(method, "Telemetry updated: services=${telemetryData.healthyServices}/${telemetryData.totalServices}, " +
                    "state=${telemetryData.cognitiveState}, cpu=${telemetryData.cpuPercent}%, memory=${telemetryData.memoryMb}MB")

            _telemetryData.value = telemetryData

        } catch (e: Exception) {
            logError(method, "Failed to fetch telemetry: ${e::class.simpleName}: ${e.message}")
            throw e
        }
    }

    /**
     * Build service health items from service counts and activity metrics
     */
    private fun buildServiceHealthItems(
        healthyServices: Int,
        totalServices: Int,
        messagesProcessed24h: Int,
        tasksCompleted24h: Int,
        errors24h: Int
    ): List<ServiceHealthItem> {
        val method = "buildServiceHealthItems"
        logDebug(method, "Building service health items: healthy=$healthyServices, total=$totalServices, " +
                "messages24h=$messagesProcessed24h, tasks24h=$tasksCompleted24h, errors24h=$errors24h")

        val items = mutableListOf<ServiceHealthItem>()

        val degradedServices = totalServices - healthyServices

        // Service status items
        if (healthyServices > 0) {
            items.add(
                ServiceHealthItem(
                    name = "Healthy Services",
                    healthy = true,
                    status = "$healthyServices services"
                )
            )
            logDebug(method, "Added healthy services item: $healthyServices services")
        }

        if (degradedServices > 0) {
            items.add(
                ServiceHealthItem(
                    name = "Degraded Services",
                    healthy = false,
                    status = "$degradedServices services"
                )
            )
            logWarn(method, "Added degraded services item: $degradedServices services")
        }

        // Activity metrics items
        items.add(
            ServiceHealthItem(
                name = "Messages (24h)",
                healthy = true,
                status = "$messagesProcessed24h"
            )
        )
        logDebug(method, "Added messages item: $messagesProcessed24h messages")

        items.add(
            ServiceHealthItem(
                name = "Tasks (24h)",
                healthy = true,
                status = "$tasksCompleted24h"
            )
        )
        logDebug(method, "Added tasks item: $tasksCompleted24h tasks")

        if (errors24h > 0) {
            items.add(
                ServiceHealthItem(
                    name = "Errors (24h)",
                    healthy = false,
                    status = "$errors24h"
                )
            )
            logWarn(method, "Added errors item: $errors24h errors")
        }

        logDebug(method, "Built ${items.size} service health items")
        return items
    }

    /**
     * Clear any error state
     */
    fun clearError() {
        val method = "clearError"
        logDebug(method, "Clearing error state")
        _error.value = null
    }

    override fun onCleared() {
        logInfo("onCleared", "ViewModel cleared, cancelling polling job")
        super.onCleared()
        pollingJob?.cancel()
    }
}
