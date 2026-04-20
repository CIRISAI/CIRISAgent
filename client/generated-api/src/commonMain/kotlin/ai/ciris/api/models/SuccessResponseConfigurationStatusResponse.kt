package ai.ciris.api.models
import kotlinx.serialization.*
@Serializable
data class SuccessResponseConfigurationStatusResponse(val success: Boolean = true, val data: ConfigurationStatusResponse? = null)
