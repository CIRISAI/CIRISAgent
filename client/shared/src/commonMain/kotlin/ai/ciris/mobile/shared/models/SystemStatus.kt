package ai.ciris.mobile.shared.models

import kotlinx.serialization.Serializable

/**
 * Response metadata from Python SuccessResponse wrapper
 */
@Serializable
data class ApiResponseMetadata(
    val timestamp: String? = null,
    val request_id: String? = null,
    val duration_ms: Int? = null
)

/**
 * System health data from /v1/system/health
 */
@Serializable
data class SystemStatus(
    val status: String,
    val cognitive_state: String? = null,
    val services_online: Int = 0,
    val services_total: Int = 22,
    val services: Map<String, ServiceHealth> = emptyMap()
)

/**
 * Wrapped system health response
 * Python returns: {"data": {...}, "metadata": {...}}
 */
@Serializable
data class SystemStatusResponse(
    val data: SystemStatus,
    val metadata: ApiResponseMetadata = ApiResponseMetadata()
)

@Serializable
data class ServiceHealth(
    val healthy: Boolean,
    val status: String,
    val last_check: String? = null
)

/**
 * Telemetry data from /v1/telemetry/overview
 * Matches SystemOverview from the backend API
 */
@Serializable
data class TelemetryData(
    val agent_id: String = "",
    val uptime_seconds: Double = 0.0,
    val cognitive_state: String = "unknown",
    val services_online: Int = 0,
    val services_total: Int = 22,
    val services: Map<String, ServiceHealth> = emptyMap(),
    // Resource usage
    val cpu_percent: Double = 0.0,
    val memory_mb: Double = 0.0,
    // Activity metrics (24h)
    val messages_processed_24h: Int = 0,
    val tasks_completed_24h: Int = 0,
    val errors_24h: Int = 0
)

/**
 * Wrapped telemetry response
 * Python returns: {"data": {...}, "metadata": {...}}
 */
@Serializable
data class TelemetryResponse(
    val data: TelemetryData,
    val metadata: ApiResponseMetadata = ApiResponseMetadata()
) {
    // Convenience accessors
    val agent_id: String get() = data.agent_id
    val uptime_seconds: Double get() = data.uptime_seconds
    val cognitive_state: String get() = data.cognitive_state
    val services_online: Int get() = data.services_online
    val services_total: Int get() = data.services_total
    val services: Map<String, ServiceHealth> get() = data.services
    val cpu_percent: Double get() = data.cpu_percent
    val memory_mb: Double get() = data.memory_mb
    val messages_processed_24h: Int get() = data.messages_processed_24h
    val tasks_completed_24h: Int get() = data.tasks_completed_24h
    val errors_24h: Int get() = data.errors_24h
}
