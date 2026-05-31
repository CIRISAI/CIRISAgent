package ai.ciris.mobile.shared.models.federation

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Local agent's federation identity card.
 *
 * Backend source of truth: `ciris_engine/schemas/runtime/federation_api.py`
 * (``FederationIdentityResponse``). Returned by ``GET /v1/federation/identity``
 * inside the standard ``{"data": {...}}`` envelope.
 *
 * Does NOT include the global ``agent_mode`` — that ships separately on
 * ``GET /v1/system/agent-mode``.
 */
@Serializable
data class FederationIdentity(
    @SerialName("signer_key_id")
    val signerKeyId: String,
    @SerialName("crate_version")
    val crateVersion: String,
    @SerialName("peer_count_total")
    val peerCountTotal: Int,
    @SerialName("peer_count_canonical")
    val peerCountCanonical: Int,
    /**
     * Federation-surface capability strings advertised by the agent.
     * Mirrors the fixed literal list the route exposes on Edge 1.0.
     */
    val capabilities: List<String> = emptyList(),
)
