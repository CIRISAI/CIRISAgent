package ai.ciris.mobile.shared.models.federation

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

/**
 * Wire models for the **bilateral consent:replication peering** contract.
 *
 * These mirror the node-side routes being built in parallel in CIRISServer:
 *
 *   GET  /v1/federation/self-key-record  → [SignedKeyRecord] (this node's signed key)
 *   POST /v1/federation/peering          → [PeeringRequest] / [PeeringResponse]
 *
 * Peering is a CEG operation rooted in the owner's key: registering a peer's
 * [SignedKeyRecord] and emitting this node's `consent:replication` grant scoped
 * to a set of attestation prefixes. The grant is *bilateral* — ratified only
 * when both nodes hold the other's grant — so the UI drives one POST per
 * direction (A←B and B←A) and reports both.
 *
 * The generated OpenAPI SDK does not yet contain these routes (the node-side
 * src is in flight), so they are hand-written here and called via the existing
 * direct-HTTP federation client.
 */
@Serializable
data class SignedKeyRecord(
    /** Stable id of the key (e.g. Ed25519 fingerprint / key id). */
    @SerialName("key_id")
    val keyId: String,
    /** Base64/multibase-encoded public key material. */
    @SerialName("public_key")
    val publicKey: String? = null,
    /** Detached signature over the record, proving key custody. */
    val signature: String? = null,
    /** Algorithm identifier (e.g. "ed25519"). */
    val algorithm: String? = null,
    /** Optional human-facing node alias advertised alongside the key. */
    val alias: String? = null,
    /** Any additional fields the node attaches to its key record. */
    val attributes: Map<String, JsonElement>? = null,
)

/**
 * Body of POST /v1/federation/peering. Registers [peerKeyRecord] as a peer and
 * emits this node's consent:replication grant scoped to [attestationPrefixes]
 * (e.g. ["capacity:"], ["health:"]). Owner/admin-gated server-side.
 */
@Serializable
data class PeeringRequest(
    @SerialName("peer_key_id")
    val peerKeyId: String,
    @SerialName("peer_key_record")
    val peerKeyRecord: SignedKeyRecord,
    @SerialName("attestation_prefixes")
    val attestationPrefixes: List<String>,
)

/**
 * Response of POST /v1/federation/peering. [granted] reflects that THIS node
 * emitted its half of the bilateral grant; full ratification requires the peer
 * to have done the same (the card checks both directions).
 */
@Serializable
data class PeeringResponse(
    val granted: Boolean = false,
    @SerialName("peer_key_id")
    val peerKeyId: String? = null,
    @SerialName("grant_id")
    val grantId: String? = null,
    @SerialName("attestation_prefixes")
    val attestationPrefixes: List<String> = emptyList(),
    /** True if the node reports the peer's reciprocal grant is already present. */
    val reciprocal: Boolean = false,
    val message: String? = null,
)
