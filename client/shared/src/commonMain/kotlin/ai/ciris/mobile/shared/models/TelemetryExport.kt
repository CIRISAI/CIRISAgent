package ai.ciris.mobile.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Export format for telemetry destinations
 */
@Serializable
enum class ExportFormat {
    @SerialName("otlp")
    OTLP,
    @SerialName("prometheus")
    PROMETHEUS,
    @SerialName("graphite")
    GRAPHITE
}

/**
 * Telemetry signal types
 */
@Serializable
enum class SignalType {
    @SerialName("metrics")
    METRICS,
    @SerialName("traces")
    TRACES,
    @SerialName("logs")
    LOGS
}

/**
 * Authentication type for export destinations
 */
@Serializable
enum class AuthType {
    @SerialName("none")
    NONE,
    @SerialName("bearer")
    BEARER,
    @SerialName("basic")
    BASIC,
    @SerialName("header")
    HEADER
}

/**
 * Telemetry export destination
 */
@Serializable
data class ExportDestination(
    val id: String,
    val name: String,
    val endpoint: String,
    val format: ExportFormat,
    val signals: List<SignalType> = listOf(SignalType.METRICS),
    @SerialName("auth_type")
    val authType: AuthType = AuthType.NONE,
    @SerialName("auth_value")
    val authValue: String? = null,
    @SerialName("auth_header")
    val authHeader: String? = null,
    @SerialName("interval_seconds")
    val intervalSeconds: Int = 60,
    val enabled: Boolean = true,
    @SerialName("created_at")
    val createdAt: String? = null,
    @SerialName("updated_at")
    val updatedAt: String? = null
)

/**
 * Request model for creating an export destination
 */
@Serializable
data class ExportDestinationCreate(
    val name: String,
    val endpoint: String,
    val format: ExportFormat,
    val signals: List<SignalType> = listOf(SignalType.METRICS),
    @SerialName("auth_type")
    val authType: AuthType = AuthType.NONE,
    @SerialName("auth_value")
    val authValue: String? = null,
    @SerialName("auth_header")
    val authHeader: String? = null,
    @SerialName("interval_seconds")
    val intervalSeconds: Int = 60,
    val enabled: Boolean = true
)

/**
 * Request model for updating an export destination
 */
@Serializable
data class ExportDestinationUpdate(
    val name: String? = null,
    val endpoint: String? = null,
    val format: ExportFormat? = null,
    val signals: List<SignalType>? = null,
    @SerialName("auth_type")
    val authType: AuthType? = null,
    @SerialName("auth_value")
    val authValue: String? = null,
    @SerialName("auth_header")
    val authHeader: String? = null,
    @SerialName("interval_seconds")
    val intervalSeconds: Int? = null,
    val enabled: Boolean? = null
)

/**
 * Result of testing connectivity to a destination
 */
@Serializable
data class TestResult(
    val success: Boolean,
    @SerialName("status_code")
    val statusCode: Int? = null,
    val message: String,
    @SerialName("latency_ms")
    val latencyMs: Float? = null
)

/**
 * Response wrapper for destinations list
 */
@Serializable
data class DestinationsListResponse(
    val destinations: List<ExportDestination>,
    val total: Int
)

/**
 * Delete operation response
 */
@Serializable
data class DeleteResponse(
    val message: String
)

/**
 * API response wrapper for export destination operations
 */
@Serializable
data class ExportDestinationResponse(
    val success: Boolean = true,
    val data: ExportDestination? = null,
    val error: String? = null
)

/**
 * API response wrapper for destinations list
 */
@Serializable
data class DestinationsListApiResponse(
    val success: Boolean = true,
    val data: DestinationsListResponse? = null,
    val error: String? = null
)

/**
 * API response wrapper for test result
 */
@Serializable
data class TestResultApiResponse(
    val success: Boolean = true,
    val data: TestResult? = null,
    val error: String? = null
)

/**
 * API response wrapper for delete operation
 */
@Serializable
data class DeleteApiResponse(
    val success: Boolean = true,
    val data: DeleteResponse? = null,
    val error: String? = null
)
