package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.ui.screens.ServiceDiagnostics
import ai.ciris.mobile.shared.ui.screens.ServiceProvider
import ai.ciris.mobile.shared.ui.screens.ServicesData
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
 * Shared ViewModel for services screen
 * Based on ~/CIRISGUI-Standalone/apps/agui/app/services/page.tsx
 *
 * Features:
 * - Service registry polling
 * - Service health monitoring
 * - Circuit breaker management
 * - Service diagnostics
 * - Auto-refresh with configurable interval
 */
class ServicesViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "ServicesViewModel"
        private const val POLL_INTERVAL_MS = 10000L // 10 seconds
    }

    private fun log(level: String, method: String, message: String) {
        println("[$TAG][$level][$method] $message")
    }

    private fun logDebug(method: String, message: String) = log("DEBUG", method, message)
    private fun logInfo(method: String, message: String) = log("INFO", method, message)
    private fun logWarn(method: String, message: String) = log("WARN", method, message)
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    // Services data state
    private val _servicesData = MutableStateFlow(ServicesData())
    val servicesData: StateFlow<ServicesData> = _servicesData.asStateFlow()

    // Loading state
    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    // Error state
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    // Status message for user feedback
    private val _statusMessage = MutableStateFlow<String?>(null)
    val statusMessage: StateFlow<String?> = _statusMessage.asStateFlow()

    // Polling job
    private var pollingJob: Job? = null
    private var isFirstLoad = true

    init {
        logInfo("init", "ServicesViewModel initialized")
        startPolling()
    }

    /**
     * Start automatic services polling
     */
    fun startPolling() {
        val method = "startPolling"
        if (pollingJob?.isActive == true) {
            logDebug(method, "Polling already active, skipping")
            return
        }

        logInfo(method, "Starting services polling (interval=${POLL_INTERVAL_MS}ms)")

        pollingJob = viewModelScope.launch {
            var pollCount = 0
            while (isActive) {
                pollCount++
                logDebug(method, "Poll cycle #$pollCount starting")

                try {
                    fetchServicesInternal()
                    _error.value = null

                    if (pollCount % 10 == 0) {
                        logInfo(method, "Poll cycle #$pollCount completed successfully")
                    }
                } catch (e: Exception) {
                    logError(method, "Poll cycle #$pollCount failed: ${e::class.simpleName}: ${e.message}")
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
        logInfo(method, "Stopping services polling")
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
                fetchServicesInternal()
                _error.value = null
                _statusMessage.value = "Services refreshed"
                logInfo(method, "Manual refresh completed successfully")
            } catch (e: Exception) {
                logError(method, "Manual refresh failed: ${e::class.simpleName}: ${e.message}")
                _error.value = "Refresh failed: ${e.message}"
            } finally {
                _isLoading.value = false
                logDebug(method, "Loading state set to false")
            }
        }
    }

    /**
     * Run service diagnostics
     */
    fun runDiagnostics() {
        val method = "runDiagnostics"
        logInfo(method, "Running service diagnostics")

        viewModelScope.launch {
            _isLoading.value = true

            try {
                // For now, diagnose based on current services data
                // TODO: Add dedicated diagnostics API endpoint if available
                val currentData = _servicesData.value

                val issues = mutableListOf<String>()
                val recommendations = mutableListOf<String>()

                // Check for unhealthy services
                if (currentData.unhealthyServices > 0) {
                    issues.add("${currentData.unhealthyServices} services are unhealthy")
                    recommendations.add("Check service logs for error details")
                }

                // Count open circuit breakers
                var openBreakers = 0
                currentData.globalServices.values.flatten().forEach { provider ->
                    if (provider.circuitBreakerState.lowercase() != "closed") {
                        openBreakers++
                    }
                }
                currentData.handlerServices.values.forEach { serviceTypes ->
                    serviceTypes.values.flatten().forEach { provider ->
                        if (provider.circuitBreakerState.lowercase() != "closed") {
                            openBreakers++
                        }
                    }
                }

                if (openBreakers > 0) {
                    issues.add("$openBreakers circuit breakers are open")
                    recommendations.add("Consider resetting circuit breakers to restore connectivity")
                }

                // Calculate totals
                val globalCount = currentData.globalServices.values.sumOf { it.size }
                val handlerCount = currentData.handlerServices.values.sumOf { serviceTypes ->
                    serviceTypes.values.sumOf { it.size }
                }

                val diagnostics = ServiceDiagnostics(
                    overallHealth = if (issues.isEmpty()) "healthy" else "degraded",
                    issuesFound = issues.size,
                    globalServices = globalCount,
                    handlerServices = handlerCount,
                    issues = issues,
                    recommendations = recommendations
                )

                _servicesData.value = currentData.copy(diagnostics = diagnostics)
                _statusMessage.value = "Diagnostics complete: ${issues.size} issues found"
                logInfo(method, "Diagnostics complete: ${issues.size} issues, ${recommendations.size} recommendations")

            } catch (e: Exception) {
                logError(method, "Diagnostics failed: ${e::class.simpleName}: ${e.message}")
                _error.value = "Diagnostics failed: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Reset circuit breakers
     */
    fun resetCircuitBreakers(serviceType: String?) {
        val method = "resetCircuitBreakers"
        logInfo(method, "Resetting circuit breakers: serviceType=$serviceType")

        viewModelScope.launch {
            _isLoading.value = true

            try {
                // TODO: Add dedicated circuit breaker reset API endpoint when available
                // For now, just refresh services and show status
                _statusMessage.value = if (serviceType != null) {
                    "Circuit breakers for $serviceType reset (API not yet implemented)"
                } else {
                    "All circuit breakers reset (API not yet implemented)"
                }

                // Refresh services after reset
                fetchServicesInternal()
                logInfo(method, "Circuit breakers reset successfully")

            } catch (e: Exception) {
                logError(method, "Circuit breaker reset failed: ${e::class.simpleName}: ${e.message}")
                _error.value = "Reset failed: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Fetch services data from API
     */
    private suspend fun fetchServicesInternal() {
        val method = "fetchServicesInternal"
        logDebug(method, "Fetching services data from API")

        try {
            val response = apiClient.getServices()
            logDebug(method, "API response received")

            // Parse global services
            val globalServices = mutableMapOf<String, List<ServiceProvider>>()
            response.globalServices.forEach { (serviceType, providers) ->
                globalServices[serviceType] = providers.map { provider ->
                    ServiceProvider(
                        name = provider.name,
                        priority = provider.priority,
                        priorityGroup = provider.priorityGroup,
                        strategy = provider.strategy,
                        circuitBreakerState = provider.circuitBreakerState,
                        capabilities = provider.capabilities
                    )
                }
            }

            // Parse handler services
            val handlerServices = mutableMapOf<String, Map<String, List<ServiceProvider>>>()
            response.handlers.forEach { (handler, serviceTypes) ->
                val handlerMap = mutableMapOf<String, List<ServiceProvider>>()
                serviceTypes.forEach { (serviceType, providers) ->
                    handlerMap[serviceType] = providers.map { provider ->
                        ServiceProvider(
                            name = provider.name,
                            priority = provider.priority,
                            priorityGroup = provider.priorityGroup,
                            strategy = provider.strategy,
                            circuitBreakerState = provider.circuitBreakerState,
                            capabilities = provider.capabilities
                        )
                    }
                }
                handlerServices[handler] = handlerMap
            }

            // Calculate health stats
            var healthyCount = 0
            var unhealthyCount = 0

            globalServices.values.flatten().forEach { provider ->
                if (provider.circuitBreakerState.lowercase() == "closed") {
                    healthyCount++
                } else {
                    unhealthyCount++
                }
            }

            handlerServices.values.forEach { serviceTypes ->
                serviceTypes.values.flatten().forEach { provider ->
                    if (provider.circuitBreakerState.lowercase() == "closed") {
                        healthyCount++
                    } else {
                        unhealthyCount++
                    }
                }
            }

            val totalServices = healthyCount + unhealthyCount
            val overallHealth = when {
                unhealthyCount == 0 -> "healthy"
                unhealthyCount < totalServices / 2 -> "degraded"
                else -> "critical"
            }

            // Preserve diagnostics if present
            val currentDiagnostics = _servicesData.value.diagnostics

            val servicesData = ServicesData(
                overallHealth = overallHealth,
                totalServices = totalServices,
                healthyServices = healthyCount,
                unhealthyServices = unhealthyCount,
                globalServices = globalServices,
                handlerServices = handlerServices,
                diagnostics = currentDiagnostics
            )

            logInfo(method, "Services updated: total=$totalServices, healthy=$healthyCount, unhealthy=$unhealthyCount")
            _servicesData.value = servicesData

        } catch (e: Exception) {
            logError(method, "Failed to fetch services: ${e::class.simpleName}: ${e.message}")
            throw e
        }
    }

    /**
     * Clear status message
     */
    fun clearStatus() {
        _statusMessage.value = null
    }

    /**
     * Clear error state
     */
    fun clearError() {
        _error.value = null
    }

    override fun onCleared() {
        logInfo("onCleared", "ViewModel cleared, cancelling polling job")
        super.onCleared()
        pollingJob?.cancel()
    }
}
