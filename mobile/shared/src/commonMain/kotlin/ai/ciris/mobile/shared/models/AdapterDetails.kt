package ai.ciris.mobile.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Detailed adapter information returned from GET /v1/system/adapters/{adapter_id}
 */
@Serializable
data class AdapterDetailsData(
    @SerialName("adapter_id")
    val adapterId: String,
    @SerialName("adapter_type")
    val adapterType: String,
    @SerialName("is_running")
    val isRunning: Boolean,
    @SerialName("loaded_at")
    val loadedAt: String? = null,
    @SerialName("services_registered")
    val servicesRegistered: List<String> = emptyList(),
    @SerialName("config_params")
    val configParams: AdapterConfigData? = null,
    val tools: List<ToolInfoData>? = null,
    val metrics: AdapterMetricsData? = null,
    @SerialName("last_activity")
    val lastActivity: String? = null
)

/**
 * Adapter configuration (sanitized - no secrets)
 */
@Serializable
data class AdapterConfigData(
    @SerialName("adapter_type")
    val adapterType: String,
    val enabled: Boolean = true,
    val persist: Boolean = false,
    val settings: Map<String, String> = emptyMap(),
    @SerialName("adapter_config")
    val adapterConfig: Map<String, String>? = null
) {
    /**
     * Get all config params as a flat map for display
     */
    fun toDisplayMap(): Map<String, String> {
        val result = mutableMapOf<String, String>()
        settings.forEach { (k, v) -> result[k] = v }
        adapterConfig?.forEach { (k, v) -> result[k] = v }
        return result
    }
}

/**
 * Adapter runtime metrics
 */
@Serializable
data class AdapterMetricsData(
    @SerialName("messages_processed")
    val messagesProcessed: Int = 0,
    @SerialName("errors_count")
    val errorsCount: Int = 0,
    @SerialName("uptime_seconds")
    val uptimeSeconds: Float = 0f,
    @SerialName("last_error")
    val lastError: String? = null,
    @SerialName("last_error_time")
    val lastErrorTime: String? = null
)

/**
 * Tool information provided by an adapter
 */
@Serializable
data class ToolInfoData(
    val name: String,
    val description: String = "",
    val category: String = "general",
    val cost: Float = 0f,
    @SerialName("when_to_use")
    val whenToUse: String? = null
)

/**
 * Response wrapper for adapter details API
 */
@Serializable
data class AdapterDetailsResponse(
    val success: Boolean,
    val data: AdapterDetailsData? = null,
    val error: String? = null,
    val timestamp: String? = null
)
