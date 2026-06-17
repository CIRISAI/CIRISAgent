package ai.ciris.mobile.shared.platform

/**
 * iOS [HardwareCredentialManager] — SCAFFOLD (compiles, not implemented).
 *
 * REAL IMPLEMENTATION (TODO): root the identity in the Secure Enclave and prove
 * it with Apple's attestation. Two complementary paths:
 *   - AuthenticationServices (ASAuthorizationPlatformPublicKeyCredentialProvider)
 *     to create a platform passkey / WebAuthn credential, returning an
 *     attestationObject; and/or
 *   - DeviceCheck `DCAppAttest` to attest a Secure-Enclave key, surfacing the
 *     assertion as [HardwareIdentityResult.hardwareAttestation].
 *
 * BLOCKER: AuthenticationServices needs a presentation anchor (UIWindow) and
 * the App Attest service requires app entitlements + a server-side challenge.
 * Neither is plumbed through this expect surface yet. See the change report.
 */
actual class HardwareCredentialManager actual constructor() {

    actual suspend fun isAvailable(): Boolean = false

    actual suspend fun createFederationIdentity(
        displayName: String,
        rpId: String,
    ): HardwareIdentityResult {
        throw HardwareCredentialUnavailable(
            "iOS hardware credential creation not implemented: needs " +
                "AuthenticationServices passkeys (presentation anchor) or " +
                "DeviceCheck DCAppAttest (Secure Enclave). TODO."
        )
    }

    /**
     * STUB. The real iOS signer would mint the hybrid identity in the Secure
     * Enclave (Ed25519) + a swift-side ML-DSA-65 implementation; not wired yet.
     */
    actual suspend fun sign(message: ByteArray): HybridSignature {
        throw HardwareCredentialUnavailable(
            "iOS hybrid sign not implemented: needs Secure Enclave + ML-DSA-65. TODO."
        )
    }

    actual suspend fun currentIdentity(): FederationIdentityPublic? = null
}

actual fun createHardwareCredentialManager(): HardwareCredentialManager =
    HardwareCredentialManager()
