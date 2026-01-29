package ai.ciris.api.models

import kotlinx.serialization.*

/**
 * A configuration step in the adapter wizard.
 * Updated to include all properties returned by the API.
 */
@Serializable
data class ConfigurationStep(
    val id: String? = null,
    @SerialName("step_id") val stepId: String? = null,
    @SerialName("step_type") val stepType: String? = null,
    val title: String? = null,
    val description: String? = null,
    val required: Boolean? = null,
    val fields: List<ConfigurationFieldDefinition>? = null
)

/**
 * A field definition within a configuration step.
 */
@Serializable
data class ConfigurationFieldDefinition(
    val name: String? = null,
    val label: String? = null,
    @SerialName("field_type") val fieldType: String? = null,
    val required: Boolean? = null,
    @SerialName("default_value") val defaultValue: String? = null,
    @SerialName("help_text") val helpText: String? = null
)
