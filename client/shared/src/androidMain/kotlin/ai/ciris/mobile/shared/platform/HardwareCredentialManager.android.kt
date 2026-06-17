package ai.ciris.mobile.shared.platform

/**
 * Android [HardwareCredentialManager] — SCAFFOLD (compiles, not implemented).
 *
 * REAL IMPLEMENTATION (TODO): use Jetpack CredentialManager
 * (androidx.credentials) to create a passkey / FIDO2 credential, OR generate a
 * hardware-backed key via the Android Keystore with `setAttestationChallenge`
 * and StrongBox where available, then surface the X.509 key-attestation chain
 * as [HardwareIdentityResult.hardwareAttestation].
 *
 * BLOCKER: requires an Activity/Context to drive CredentialManager's
 * createCredential() UI, plus the androidx.credentials + play-services-fido
 * dependencies wired into androidApp. Neither is plumbed through this expect
 * surface yet (the factory takes no Context). See the change report.
 */
actual class HardwareCredentialManager actual constructor() {

    actual suspend fun isAvailable(): Boolean = false

    actual suspend fun createFederationIdentity(
        displayName: String,
        rpId: String,
    ): HardwareIdentityResult {
        throw HardwareCredentialUnavailable(
            "Android hardware credential creation not implemented: needs " +
                "androidx.credentials CredentialManager (Activity context) or " +
                "Android Keystore key-attestation. TODO."
        )
    }

    /**
     * STUB. The real Android signer would mint the hybrid identity via BouncyCastle
     * (bcprov) or Tink + Android Keystore and ML-DSA-65; not wired yet. The founder
     * flow uses the DESKTOP actual today (CIRISAgent#887).
     */
    actual suspend fun sign(message: ByteArray): HybridSignature {
        throw HardwareCredentialUnavailable(
            "Android hybrid sign not implemented: needs BouncyCastle/Tink + ML-DSA-65. TODO."
        )
    }

    actual suspend fun currentIdentity(): FederationIdentityPublic? = null
}

actual fun createHardwareCredentialManager(): HardwareCredentialManager =
    HardwareCredentialManager()
