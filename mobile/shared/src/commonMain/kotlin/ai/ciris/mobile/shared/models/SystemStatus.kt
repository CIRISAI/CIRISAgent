package ai.ciris.mobile.shared.models

import kotlinx.serialization.Serializable

@Serializable
data class SystemStatus(
    val status: String,
    val cognitive_state: String,
    val services_online: Int,
    val services_total: Int,
    val services: Map<String, ServiceHealth> = emptyMap()
)

@Serializable
data class ServiceHealth(
    val healthy: Boolean,
    val status: String,
    val last_check: String? = null
)

@Serializable
data class TelemetryResponse(
    val agent_id: String,
    val uptime_seconds: Double,
    val cognitive_state: String,
    val services_online: Int,
    val services_total: Int,
    val services: Map<String, ServiceHealth>
)
