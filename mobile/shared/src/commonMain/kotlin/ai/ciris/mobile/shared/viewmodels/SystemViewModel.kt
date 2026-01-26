package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.ui.screens.SystemChannelInfo
import ai.ciris.mobile.shared.ui.screens.SystemScreenData
import ai.ciris.mobile.shared.ui.screens.SystemServiceInfo
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
 * ViewModel for SystemScreen
 * Handles system status and control operations
 *
 * Features:
 * - Load system health and resource usage
 * - Load environmental impact metrics
 * - Manage processor state (pause/resume)
 * - Auto-refresh polling
 */
class SystemViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "SystemViewModel"
        private const val REFRESH_INTERVAL_MS = 5000L
    }

    private fun log(level: String, method: String, message: String) {
        println("[$TAG][$level][$method] $message")
    }

    private fun logDebug(method: String, message: String) = log("DEBUG", method, message)
    private fun logInfo(method: String, message: String) = log("INFO", method, message)
    private fun logWarn(method: String, message: String) = log("WARN", method, message)
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    // System data state
    private val _systemData = MutableStateFlow(SystemScreenData())
    val systemData: StateFlow<SystemScreenData> = _systemData.asStateFlow()

    // Loading state
    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    // Error state
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    // Success message
    private val _successMessage = MutableStateFlow<String?>(null)
    val successMessage: StateFlow<String?> = _successMessage.asStateFlow()

    // Auto-refresh job
    private var refreshJob: Job? = null

    init {
        logInfo("init", "SystemViewModel initialized")
        loadSystemData()
    }

    /**
     * Load all system data from API
     */
    fun loadSystemData() {
        val method = "loadSystemData"
        logInfo(method, "Loading system data")

        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null

            try {
                // Load system health
                val healthResponse = try {
                    apiClient.getSystemHealth()
                } catch (e: Exception) {
                    logWarn(method, "Failed to load health: ${e.message}")
                    null
                }

                // Load telemetry for more detailed info
                val telemetryResponse = try {
                    apiClient.getUnifiedTelemetry()
                } catch (e: Exception) {
                    logWarn(method, "Failed to load telemetry: ${e.message}")
                    null
                }

                // Load environmental metrics
                val environmentResponse = try {
                    apiClient.getEnvironmentalMetrics()
                } catch (e: Exception) {
                    logWarn(method, "Failed to load environmental metrics: ${e.message}")
                    null
                }

                // Load processor status
                val processorResponse = try {
                    apiClient.getProcessorStatus()
                } catch (e: Exception) {
                    logWarn(method, "Failed to load processor status: ${e.message}")
                    null
                }

                // Load channels
                val channelsResponse = try {
                    apiClient.getChannels()
                } catch (e: Exception) {
                    logWarn(method, "Failed to load channels: ${e.message}")
                    null
                }

                // Build service info from telemetry
                val services = telemetryResponse?.services?.map { (name, info) ->
                    SystemServiceInfo(
                        name = name,
                        healthy = info.healthy,
                        available = info.available,
                        serviceType = info.serviceType,
                        capabilities = info.capabilities
                    )
                } ?: emptyList()

                // Build channel info
                val channels = channelsResponse?.channels?.map { channel ->
                    SystemChannelInfo(
                        channelId = channel.channelId,
                        displayName = channel.displayName,
                        channelType = channel.channelType,
                        isActive = channel.isActive,
                        messageCount = channel.messageCount,
                        lastActivity = channel.lastActivity
                    )
                } ?: emptyList()

                _systemData.value = SystemScreenData(
                    health = healthResponse?.status ?: telemetryResponse?.health,
                    uptime = telemetryResponse?.uptime ?: "N/A",
                    memoryMb = telemetryResponse?.memoryMb ?: 0,
                    memoryPercent = telemetryResponse?.memoryPercent ?: 0,
                    cpuPercent = telemetryResponse?.cpuPercent ?: 0,
                    diskUsedMb = telemetryResponse?.diskUsedMb ?: 0.0,
                    carbonGrams = environmentResponse?.carbonGrams ?: 0.0,
                    energyKwh = environmentResponse?.energyKwh ?: 0.0,
                    costCents = environmentResponse?.costCents ?: 0.0,
                    tokensLastHour = environmentResponse?.tokensLastHour ?: 0,
                    tokens24h = environmentResponse?.tokens24h ?: 0,
                    isPaused = processorResponse?.isPaused ?: false,
                    cognitiveState = processorResponse?.cognitiveState ?: telemetryResponse?.cognitiveState ?: "WORK",
                    queueDepth = processorResponse?.queueDepth ?: 0,
                    services = services,
                    channels = channels
                )

                logInfo(method, "System data loaded: health=${_systemData.value.health}, " +
                        "services=${services.size}, channels=${channels.size}")

            } catch (e: Exception) {
                logError(method, "Failed to load system data: ${e::class.simpleName}: ${e.message}")
                _error.value = "Failed to load system data: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Pause the runtime
     */
    fun pauseRuntime() {
        val method = "pauseRuntime"
        logInfo(method, "Pausing runtime")

        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null

            try {
                apiClient.pauseRuntime()
                logInfo(method, "Runtime paused successfully")
                _successMessage.value = "Runtime paused"
                loadSystemData() // Reload to show updated status
            } catch (e: Exception) {
                logError(method, "Failed to pause runtime: ${e::class.simpleName}: ${e.message}")
                _error.value = "Failed to pause runtime: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Resume the runtime
     */
    fun resumeRuntime() {
        val method = "resumeRuntime"
        logInfo(method, "Resuming runtime")

        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null

            try {
                apiClient.resumeRuntime()
                logInfo(method, "Runtime resumed successfully")
                _successMessage.value = "Runtime resumed"
                loadSystemData() // Reload to show updated status
            } catch (e: Exception) {
                logError(method, "Failed to resume runtime: ${e::class.simpleName}: ${e.message}")
                _error.value = "Failed to resume runtime: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Start auto-refresh polling
     */
    fun startPolling() {
        val method = "startPolling"
        if (refreshJob?.isActive == true) {
            logDebug(method, "Polling already active")
            return
        }

        logInfo(method, "Starting auto-refresh polling")
        refreshJob = viewModelScope.launch {
            while (isActive) {
                delay(REFRESH_INTERVAL_MS)
                try {
                    loadSystemData()
                } catch (e: Exception) {
                    logError(method, "Error during auto-refresh: ${e.message}")
                }
            }
        }
    }

    /**
     * Stop auto-refresh polling
     */
    fun stopPolling() {
        val method = "stopPolling"
        logInfo(method, "Stopping auto-refresh polling")
        refreshJob?.cancel()
        refreshJob = null
    }

    /**
     * Refresh system data
     */
    fun refresh() {
        loadSystemData()
    }

    /**
     * Clear error state
     */
    fun clearError() {
        _error.value = null
    }

    /**
     * Clear success message
     */
    fun clearSuccess() {
        _successMessage.value = null
    }

    override fun onCleared() {
        super.onCleared()
        stopPolling()
    }
}
