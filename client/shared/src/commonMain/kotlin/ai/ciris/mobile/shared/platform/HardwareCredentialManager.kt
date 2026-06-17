package ai.ciris.mobile.shared.platform

/**
 * Result of rooting a federation identity in a hardware key.
 *
 * Produced by [HardwareCredentialManager.createFederationIdentity]. Carries the
 * identity key id, the public keys for the asserted occurrences, and the opaque
 * platform [hardwareAttestation] blob the node validates during self-login.
 */
data class HardwareIdentityResult(
    /** Stable id of the hardware-rooted identity key (e.g. credential id). */
    val identityKeyId: String,
    /** Base64/multibase public key of the identity key. */
    val identityPublicKey: String,
    /** Public key for the `app` occurrence (this client). */
    val appOccurrencePublicKey: String,
    /** Public key for the `agent` occurrence this client speaks for. */
    val agentOccurrencePublicKey: String,
    /**
     * Opaque, platform-produced attestation proving the keys are hardware-backed.
     * Shape is platform-specific (WebAuthn attestationObject, Android key
     * attestation chain, iOS DCAppAttest assertion, …). The node validates it.
     */
    val hardwareAttestation: String,
    /**
     * Base64 **raw** Ed25519 public key (32 bytes) of the long-lived federation
     * identity — the classical half of the hybrid founder key. This is the value
     * that rides in the `/v1/setup/root` body as `founder.ed25519_pubkey_b64` and
     * that the node's verifier checks `x-ciris-signature-ed25519` against.
     */
    val ed25519PublicKeyB64: String? = null,
    /**
     * Base64 **raw** ML-DSA-65 (FIPS-204, level 3) public key of the long-lived
     * federation identity — the post-quantum half of the hybrid founder key.
     * Rides as `founder.ml_dsa_65_pubkey_b64`; the node checks
     * `x-ciris-signature-ml-dsa-65` against it. `null` on platforms whose actual
     * cannot mint ML-DSA-65 (ios/wasm stubs).
     */
    val mlDsa65PublicKeyB64: String? = null,
)

/**
 * A detached **hybrid** signature: an Ed25519 signature AND an ML-DSA-65
 * (FIPS-204) signature over the SAME message bytes. The node verifies BOTH
 * (Strict hybrid — there is no classical-only acceptance path), so a claim/login
 * is only admitted when both halves validate against the founder's two pubkeys.
 *
 * Both fields are base64 of the **raw** signature bytes (the on-the-wire FIPS-204
 * / Ed25519 signature octets — NOT a DER/ASN.1 or COSE wrapper), which is what
 * the `x-ciris-signature-*` headers carry and what `ciris-verify` expects.
 */
data class HybridSignature(
    val ed25519B64: String,
    val mlDsa65B64: String,
)

/**
 * The loaded long-lived federation identity (founder key) in its public,
 * wire-ready form. Mirrors the `founder { … }` object of the `/v1/setup/root`
 * body. `null` when no identity has been minted/persisted yet.
 */
data class FederationIdentityPublic(
    /** Stable founder display key id. */
    val keyId: String,
    /** Base64 raw Ed25519 public key. */
    val ed25519PublicKeyB64: String,
    /** Base64 raw ML-DSA-65 public key. */
    val mlDsa65PublicKeyB64: String,
)

/**
 * Thrown when a platform cannot (yet) produce a hardware-rooted identity —
 * either because the actual is a scaffold (Android/iOS) or because the device
 * lacks a usable authenticator.
 */
class HardwareCredentialUnavailable(message: String) : Exception(message)

/**
 * Platform abstraction over hardware-backed credential creation for the
 * federation identity wizard step.
 *
 * Implementations:
 *  - Desktop: WebAuthn/FIDO2 over PC/SC (security key / platform authenticator)
 *  - Android: Jetpack CredentialManager (passkeys / FIDO2)  [scaffold]
 *  - iOS:     Secure Enclave + AuthenticationServices passkeys [scaffold]
 *  - Web:     navigator.credentials WebAuthn                  [scaffold]
 *
 * Mirrors the expect-class + factory-fun convention used by [SecureStorage].
 */
expect class HardwareCredentialManager() {
    /**
     * True if this platform can actually mint a hardware-rooted identity right
     * now. UIs use this to gate the "Use hardware key" action vs. showing a
     * "not available on this platform" note.
     */
    suspend fun isAvailable(): Boolean

    /**
     * Root a federation identity in a hardware key and produce the
     * occurrence keys + attestation blob for the self-login ceremony.
     *
     * @param displayName user-facing name bound to the credential.
     * @param rpId relying-party / node identifier the credential is scoped to.
     * @throws HardwareCredentialUnavailable if the platform actual is a
     *         scaffold or no authenticator is usable.
     */
    suspend fun createFederationIdentity(
        displayName: String,
        rpId: String,
    ): HardwareIdentityResult

    /**
     * Sign [message] with BOTH halves of the long-lived federation identity
     * (Ed25519 AND ML-DSA-65) and return the detached [HybridSignature].
     *
     * The identity must already exist — call [createFederationIdentity] first
     * (it is idempotent and reloads a persisted identity across launches). The
     * caller is responsible for handing the EXACT serialized request-body bytes
     * that will be sent on the wire, so the signed bytes == the wire bytes.
     *
     * @throws HardwareCredentialUnavailable on platforms whose actual cannot
     *         produce ML-DSA-65 (ios/wasm stubs) or when no identity is loaded.
     */
    suspend fun sign(message: ByteArray): HybridSignature

    /**
     * The currently-loaded long-lived federation identity in public, wire-ready
     * form (the `founder { … }` object), or `null` if none has been minted yet.
     */
    suspend fun currentIdentity(): FederationIdentityPublic?
}

/** Factory mirroring [createSecureStorage]. */
expect fun createHardwareCredentialManager(): HardwareCredentialManager
