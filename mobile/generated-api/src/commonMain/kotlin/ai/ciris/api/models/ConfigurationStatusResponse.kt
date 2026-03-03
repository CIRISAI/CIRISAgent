package ai.ciris.api.models

import kotlinx.serialization.*

/**
 * Response for configuration session status.
 * Matches the backend ConfigurationStatusResponse schema.
 */
@Serializable
data class ConfigurationStatusResponse(
    @SerialName("session_id") val sessionId: String? = null,
    @SerialName("adapter_type") val adapterType: String? = null,
    val status: String? = null,
    @SerialName("current_step_index") val currentStepIndex: Int? = null,
    @SerialName("total_steps") val totalSteps: Int? = null,
    @SerialName("current_step") val currentStep: ConfigurationStep? = null
)
