package ai.ciris.mobile.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * LLM Bus status and provider models.
 * Maps to Python schemas in llm_schemas.py
 */

// ============================================================================
// Enums
// ============================================================================

@Serializable
enum class DistributionStrategy {
    @SerialName("round_robin") ROUND_ROBIN,
    @SerialName("latency_based") LATENCY_BASED,
    @SerialName("random") RANDOM,
    @SerialName("least_loaded") LEAST_LOADED
}

@Serializable
enum class CircuitBreakerState {
    @SerialName("closed") CLOSED,
    @SerialName("open") OPEN,
    @SerialName("half_open") HALF_OPEN
}

@Serializable
enum class ProviderPriority {
    @SerialName("critical") CRITICAL,
    @SerialName("high") HIGH,
    @SerialName("normal") NORMAL,
    @SerialName("low") LOW,
    @SerialName("fallback") FALLBACK
}

// ============================================================================
// Circuit Breaker Schemas
// ============================================================================

@Serializable
data class CircuitBreakerConfig(
    @SerialName("failure_threshold") val failureThreshold: Int = 5,
    @SerialName("recovery_timeout_seconds") val recoveryTimeoutSeconds: Float = 10.0f,
    @SerialName("success_threshold") val successThreshold: Int = 3,
    @SerialName("timeout_duration_seconds") val timeoutDurationSeconds: Float = 30.0f
)

@Serializable
data class CircuitBreakerStatus(
    val state: CircuitBreakerState = CircuitBreakerState.CLOSED,
    @SerialName("failure_count") val failureCount: Int = 0,
    @SerialName("success_count") val successCount: Int = 0,
    @SerialName("total_calls") val totalCalls: Int = 0,
    @SerialName("total_failures") val totalFailures: Int = 0,
    @SerialName("total_successes") val totalSuccesses: Int = 0,
    @SerialName("success_rate") val successRate: Float = 1.0f,
    @SerialName("consecutive_failures") val consecutiveFailures: Int = 0,
    @SerialName("recovery_attempts") val recoveryAttempts: Int = 0,
    @SerialName("state_transitions") val stateTransitions: Int = 0,
    @SerialName("time_in_open_state_seconds") val timeInOpenStateSeconds: Float = 0.0f,
    @SerialName("last_failure_age_seconds") val lastFailureAgeSeconds: Float? = null,
    val config: CircuitBreakerConfig = CircuitBreakerConfig()
)

// ============================================================================
// Provider Status Schemas
// ============================================================================

@Serializable
data class ProviderMetrics(
    @SerialName("total_requests") val totalRequests: Int = 0,
    @SerialName("failed_requests") val failedRequests: Int = 0,
    @SerialName("failure_rate") val failureRate: Float = 0.0f,
    @SerialName("average_latency_ms") val averageLatencyMs: Float = 0.0f,
    @SerialName("consecutive_failures") val consecutiveFailures: Int = 0,
    @SerialName("last_request_time") val lastRequestTime: String? = null,
    @SerialName("last_failure_time") val lastFailureTime: String? = null,
    @SerialName("is_rate_limited") val isRateLimited: Boolean = false,
    @SerialName("rate_limit_cooldown_remaining_seconds") val rateLimitCooldownRemainingSeconds: Float? = null
)

@Serializable
data class LlmProviderStatus(
    val name: String,
    val healthy: Boolean,
    val enabled: Boolean = true,
    val priority: ProviderPriority = ProviderPriority.NORMAL,
    val metrics: ProviderMetrics = ProviderMetrics(),
    @SerialName("circuit_breaker") val circuitBreaker: CircuitBreakerStatus = CircuitBreakerStatus()
) {
    /**
     * User-friendly status message for display.
     */
    val statusMessage: String
        get() = when {
            !enabled -> "Disabled by user"
            circuitBreaker.state == CircuitBreakerState.OPEN -> "Temporarily disabled - recovering soon"
            metrics.isRateLimited -> "Rate limited - waiting for cooldown"
            healthy -> "Healthy - working normally"
            else -> "Unknown status"
        }

    /**
     * User-friendly priority label.
     */
    val priorityLabel: String
        get() = when (priority) {
            ProviderPriority.CRITICAL -> "Critical"
            ProviderPriority.HIGH -> "Primary"
            ProviderPriority.NORMAL -> "Standard"
            ProviderPriority.LOW -> "Backup"
            ProviderPriority.FALLBACK -> "Last Resort"
        }
}

// ============================================================================
// Bus Status Schemas
// ============================================================================

@Serializable
data class LlmBusStatus(
    @SerialName("distribution_strategy") val distributionStrategy: DistributionStrategy,
    @SerialName("total_requests") val totalRequests: Int = 0,
    @SerialName("failed_requests") val failedRequests: Int = 0,
    @SerialName("average_latency_ms") val averageLatencyMs: Float = 0.0f,
    @SerialName("error_rate") val errorRate: Float = 0.0f,
    @SerialName("providers_total") val providersTotal: Int = 0,
    @SerialName("providers_available") val providersAvailable: Int = 0,
    @SerialName("providers_rate_limited") val providersRateLimited: Int = 0,
    @SerialName("circuit_breakers_closed") val circuitBreakersClosed: Int = 0,
    @SerialName("circuit_breakers_open") val circuitBreakersOpen: Int = 0,
    @SerialName("circuit_breakers_half_open") val circuitBreakersHalfOpen: Int = 0,
    @SerialName("uptime_seconds") val uptimeSeconds: Float = 0.0f,
    val timestamp: String? = null
) {
    /**
     * Human-readable uptime string.
     */
    val uptimeDisplay: String
        get() {
            val seconds = uptimeSeconds.toLong()
            val hours = seconds / 3600
            val minutes = (seconds % 3600) / 60
            return if (hours > 0) "${hours}h ${minutes}m" else "${minutes}m"
        }

    /**
     * User-friendly distribution strategy label.
     */
    val distributionStrategyLabel: String
        get() = when (distributionStrategy) {
            DistributionStrategy.LATENCY_BASED -> "Automatic"
            DistributionStrategy.ROUND_ROBIN -> "Round Robin"
            DistributionStrategy.RANDOM -> "Random"
            DistributionStrategy.LEAST_LOADED -> "Least Loaded"
        }

    /**
     * Circuit breaker summary for status overview.
     */
    val circuitBreakersSummary: String
        get() = when {
            circuitBreakersOpen > 0 -> "${circuitBreakersOpen} paused"
            circuitBreakersHalfOpen > 0 -> "${circuitBreakersHalfOpen} recovering"
            else -> "All active"
        }

    /**
     * Whether all circuit breakers are healthy.
     */
    val allCircuitBreakersHealthy: Boolean
        get() = circuitBreakersOpen == 0 && circuitBreakersHalfOpen == 0
}

// ============================================================================
// API Response Wrappers
// ============================================================================

@Serializable
data class LlmBusStatusData(
    @SerialName("distribution_strategy") val distributionStrategy: String,
    @SerialName("total_requests") val totalRequests: Int = 0,
    @SerialName("failed_requests") val failedRequests: Int = 0,
    @SerialName("average_latency_ms") val averageLatencyMs: Float = 0.0f,
    @SerialName("error_rate") val errorRate: Float = 0.0f,
    @SerialName("providers_total") val providersTotal: Int = 0,
    @SerialName("providers_available") val providersAvailable: Int = 0,
    @SerialName("providers_rate_limited") val providersRateLimited: Int = 0,
    @SerialName("circuit_breakers_closed") val circuitBreakersClosed: Int = 0,
    @SerialName("circuit_breakers_open") val circuitBreakersOpen: Int = 0,
    @SerialName("circuit_breakers_half_open") val circuitBreakersHalfOpen: Int = 0,
    @SerialName("uptime_seconds") val uptimeSeconds: Float = 0.0f,
    val timestamp: String? = null
) {
    fun toLlmBusStatus(): LlmBusStatus = LlmBusStatus(
        distributionStrategy = when (distributionStrategy) {
            "round_robin" -> DistributionStrategy.ROUND_ROBIN
            "latency_based" -> DistributionStrategy.LATENCY_BASED
            "random" -> DistributionStrategy.RANDOM
            "least_loaded" -> DistributionStrategy.LEAST_LOADED
            else -> DistributionStrategy.LATENCY_BASED
        },
        totalRequests = totalRequests,
        failedRequests = failedRequests,
        averageLatencyMs = averageLatencyMs,
        errorRate = errorRate,
        providersTotal = providersTotal,
        providersAvailable = providersAvailable,
        providersRateLimited = providersRateLimited,
        circuitBreakersClosed = circuitBreakersClosed,
        circuitBreakersOpen = circuitBreakersOpen,
        circuitBreakersHalfOpen = circuitBreakersHalfOpen,
        uptimeSeconds = uptimeSeconds,
        timestamp = timestamp
    )
}

@Serializable
data class LlmBusStatusResponse(
    val data: LlmBusStatusData,
    val metadata: ApiResponseMetadata = ApiResponseMetadata()
)

@Serializable
data class LlmProvidersData(
    val providers: List<LlmProviderStatus> = emptyList(),
    @SerialName("total_count") val totalCount: Int = 0
)

@Serializable
data class LlmProvidersResponse(
    val data: LlmProvidersData,
    val metadata: ApiResponseMetadata = ApiResponseMetadata()
)

// ============================================================================
// Request/Response Schemas for Mutations
// ============================================================================

@Serializable
data class DistributionStrategyUpdateResponse(
    val success: Boolean,
    @SerialName("previous_strategy") val previousStrategy: String,
    @SerialName("new_strategy") val newStrategy: String,
    val message: String
)

@Serializable
data class CircuitBreakerResetResponse(
    val success: Boolean,
    @SerialName("provider_name") val providerName: String,
    @SerialName("previous_state") val previousState: String,
    @SerialName("new_state") val newState: String,
    val message: String
)

@Serializable
data class CircuitBreakerConfigUpdateResponse(
    val success: Boolean,
    @SerialName("provider_name") val providerName: String,
    @SerialName("previous_config") val previousConfig: CircuitBreakerConfig,
    @SerialName("new_config") val newConfig: CircuitBreakerConfig,
    val message: String
)

@Serializable
data class ProviderEnableResponse(
    val success: Boolean,
    @SerialName("provider_name") val providerName: String,
    val enabled: Boolean,
    val message: String
)

@Serializable
data class ProviderPriorityUpdateResponse(
    val success: Boolean,
    @SerialName("provider_name") val providerName: String,
    @SerialName("previous_priority") val previousPriority: String,
    @SerialName("new_priority") val newPriority: String,
    val message: String
)

@Serializable
data class ProviderDeleteResponse(
    val success: Boolean,
    @SerialName("provider_name") val providerName: String,
    val message: String
)
