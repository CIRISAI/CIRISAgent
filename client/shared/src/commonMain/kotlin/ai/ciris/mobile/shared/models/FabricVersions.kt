package ai.ciris.mobile.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * One substrate cdylib crate's version + trust status, from
 * ``GET /v1/system/fabric``. Mirrors the backend ``FabricComponent``.
 *
 * [runtimeVersion] is live today. [embeddedVersion] (the version literal in the
 * compiled cdylib) and [registryHashStatus] are pending the upstream embed +
 * registry-manifest work (CIRISPersist#189 / CIRISEdge#77 / CIRISLensCore#38 /
 * CIRISNodeCore#36 / CIRISRegistry#68); the Trust page shows them as "pending".
 */
@Serializable
data class FabricComponent(
    val name: String,
    val loaded: Boolean = false,
    @SerialName("runtime_version") val runtimeVersion: String? = null,
    @SerialName("embedded_version") val embeddedVersion: String? = null,
    @SerialName("registry_hash_status") val registryHashStatus: String = "pending",
)

@Serializable
data class FabricVersionsResponse(
    val components: List<FabricComponent> = emptyList(),
    val note: String = "",
)
