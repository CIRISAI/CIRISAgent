package ai.ciris.mobile.shared.models.federation

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

/**
 * Wire models for the **CEG self-at-login ceremony** — POST /v1/self/login.
 *
 * The federation identity is rooted in a hardware key (WebAuthn/FIDO2, Secure
 * Enclave, Android Keystore, …). At login the client presents:
 *   - the [identityKeyId] (the owner-rooted identity key),
 *   - the [occurrences] it is asserting (e.g. an `app` occurrence for this
 *     client and the `agent` occurrence it speaks for), each with its own key,
 *   - a [hardwareAttestation] blob proving the keys live in real hardware.
 *
 * The node's `self_login` admits the identity and promotes the occurrences,
 * returning a session token. This route is not yet in the generated OpenAPI
 * SDK, so it is hand-written and called via direct HTTP.
 */
@Serializable
data class OccurrenceAssertion(
    /** Occurrence kind, e.g. "app" (this client) or "agent". */
    val kind: String,
    /** Public key for this occurrence (base64/multibase). */
    @SerialName("public_key")
    val publicKey: String,
    /** Optional stable id for the occurrence key. */
    @SerialName("key_id")
    val keyId: String? = null,
    /** Optional human label (device name, agent name). */
    val label: String? = null,
)

@Serializable
data class SelfLoginRequest(
    @SerialName("identity_key_id")
    val identityKeyId: String,
    val occurrences: List<OccurrenceAssertion>,
    /**
     * Opaque, platform-produced hardware attestation proving the identity +
     * occurrence keys are hardware-backed. Shape is platform-specific
     * (WebAuthn attestationObject, Android key-attestation chain, iOS
     * DCAppAttest assertion, …); the node validates it.
     */
    @SerialName("hardware_attestation")
    val hardwareAttestation: String,
    /** Optional extra signals (platform, transport hints). */
    val metadata: Map<String, JsonElement>? = null,
)

@Serializable
data class SelfLoginResponse(
    val admitted: Boolean = false,
    @SerialName("access_token")
    val accessToken: String? = null,
    @SerialName("identity_key_id")
    val identityKeyId: String? = null,
    /** Occurrences the node admitted/promoted. */
    @SerialName("promoted_occurrences")
    val promotedOccurrences: List<String> = emptyList(),
    val role: String? = null,
    val message: String? = null,
)
