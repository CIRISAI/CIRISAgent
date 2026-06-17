package ai.ciris.mobile.shared.platform

/**
 * Web (wasmJs) [HardwareCredentialManager] — SCAFFOLD (compiles, not implemented).
 *
 * REAL IMPLEMENTATION (TODO): call the browser WebAuthn API,
 * `navigator.credentials.create({ publicKey: … })`, with a platform or
 * cross-platform (roaming security key) authenticator, then base64-encode the
 * returned `attestationObject` into [HardwareIdentityResult.hardwareAttestation].
 *
 * BLOCKER: needs Kotlin/Wasm external interop bindings for the
 * CredentialsContainer / PublicKeyCredential WebAuthn types (not present in this
 * module) plus a secure (https) origin at runtime. See the change report.
 */
actual class HardwareCredentialManager actual constructor() {

    actual suspend fun isAvailable(): Boolean = false

    actual suspend fun createFederationIdentity(
        displayName: String,
        rpId: String,
    ): HardwareIdentityResult {
        throw HardwareCredentialUnavailable(
            "Web hardware credential creation not implemented: needs " +
                "navigator.credentials WebAuthn external bindings + secure origin. TODO."
        )
    }

    /**
     * STUB. The real web signer would use WebCrypto Ed25519 + a WASM ML-DSA-65
     * implementation; not wired yet.
     */
    actual suspend fun sign(message: ByteArray): HybridSignature {
        throw HardwareCredentialUnavailable(
            "Web hybrid sign not implemented: needs WebCrypto + ML-DSA-65. TODO."
        )
    }

    actual suspend fun currentIdentity(): FederationIdentityPublic? = null
}

actual fun createHardwareCredentialManager(): HardwareCredentialManager =
    HardwareCredentialManager()
