package ai.ciris.mobile.shared.models.federation

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Persist's ``LocalIdentityAggregate`` — the single-call snapshot of the
 * hybrid federation identity across the three keypair roles:
 *
 *  - Signing: Ed25519 (always present) + optional ML-DSA-65 (PQC).
 *  - Reticulum transport: X25519 + Ed25519.
 *  - Content encryption: X25519 + optional ML-KEM-768 (PQC).
 *
 * Backend source of truth: ``GET /v1/system/peers/federation-identity``
 * (``ciris_engine/logic/adapters/api/routes/system/peers.py``), which
 * sources persist 5.4.0+ ``local_identity_aggregate()`` (CIRISPersist#198,
 * CEG 1.0 §5.6.8.8.2). [keyId] is THE address production lens / registry
 * servers use to reach this node.
 *
 * Optional capability keys default to null — older persist builds and
 * non-PQC deployments simply omit them.
 */
@Serializable
data class FederationIdentityAggregate(
    @SerialName("aggregate_version")
    val aggregateVersion: Int = 0,
    @SerialName("key_id")
    val keyId: String,
    @SerialName("pqc_key_id")
    val pqcKeyId: String? = null,
    @SerialName("ed25519_pubkey_b64")
    val ed25519PubkeyB64: String,
    @SerialName("ml_dsa_65_pubkey_b64")
    val mlDsa65PubkeyB64: String? = null,
    @SerialName("reticulum_x25519_pubkey_b64")
    val reticulumX25519PubkeyB64: String? = null,
    @SerialName("reticulum_ed25519_pubkey_b64")
    val reticulumEd25519PubkeyB64: String? = null,
    @SerialName("content_x25519_pubkey_b64")
    val contentX25519PubkeyB64: String? = null,
    @SerialName("content_ml_kem_768_pubkey_b64")
    val contentMlKem768PubkeyB64: String? = null,
) {
    /** PQC signing material present (ML-DSA-65 pubkey and/or its key id). */
    val hasPqc: Boolean
        get() = mlDsa65PubkeyB64 != null || pqcKeyId != null

    /** Reticulum transport keys present (either half of the pair). */
    val hasReticulum: Boolean
        get() = reticulumX25519PubkeyB64 != null || reticulumEd25519PubkeyB64 != null

    /** Content-encryption keys present (X25519 and/or ML-KEM-768). */
    val hasContentEncryption: Boolean
        get() = contentX25519PubkeyB64 != null || contentMlKem768PubkeyB64 != null
}

/**
 * Response body (``data`` envelope contents) for
 * ``GET /v1/system/peers/federation-identity``.
 *
 * Pairs the persist [aggregate] with the companion NodeCode identity
 * (the connect-card key) so the UI can render both on one surface.
 */
@Serializable
data class FederationIdentityResponse(
    val aggregate: FederationIdentityAggregate,
    @SerialName("node_code_key_id")
    val nodeCodeKeyId: String? = null,
    @SerialName("node_code_pubkey_ed25519_base64")
    val nodeCodePubkeyEd25519Base64: String? = null,
)
