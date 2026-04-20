package ai.ciris.api.models
import kotlinx.serialization.*
@Serializable
data class SuccessResponseConfigurationSessionResponse(val success: Boolean = true, val data: ConfigurationSessionResponse? = null)
