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
}

/** Factory mirroring [createSecureStorage]. */
expect fun createHardwareCredentialManager(): HardwareCredentialManager
