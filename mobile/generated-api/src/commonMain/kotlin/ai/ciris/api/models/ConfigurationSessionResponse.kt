package ai.ciris.api.models

import kotlinx.serialization.*

/**
 * Configuration session response from adapter configuration wizard.
 * Updated to include all properties returned by the API.
 */
@Serializable
data class ConfigurationSessionResponse(
    @SerialName("session_id") val sessionId: String? = null,
    @SerialName("adapter_type") val adapterType: String? = null,
    val status: String? = null,
    @SerialName("current_step_index") val currentStepIndex: Int? = null,
    @SerialName("total_steps") val totalSteps: Int? = null,
    @SerialName("current_step") val currentStep: ConfigurationStep? = null
)
