package ai.ciris.mobile.shared.platform

import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.MessageDigest
import java.util.Base64

/**
 * Desktop [HardwareCredentialManager].
 *
 * IDEAL: root the federation identity in a real hardware authenticator via
 * WebAuthn/FIDO2 over PC/SC (a YubiKey or platform authenticator), producing a
 * genuine WebAuthn `attestationObject`. That requires a native FIDO2/CTAP stack
 * (e.g. libfido2 via JNA, or a PC/SC bridge) which is NOT bundled in this KMP
 * module today — see BLOCKERS in the change report.
 *
 * IMPLEMENTED-AS-FAR-AS-FEASIBLE: a *software* Ed25519 fallback using the JDK's
 * built-in JCA (available on JDK 15+). It mints real Ed25519 keypairs for the
 * identity + app/agent occurrences and emits a self-describing attestation blob
 * tagged `software-fallback`. This is enough to exercise the full self-login
 * wiring end-to-end, but it is NOT hardware-backed — the node MUST reject the
 * `software-fallback` format in production. The hardware path is a clearly
 * marked TODO below.
 */
actual class HardwareCredentialManager actual constructor() {

    private fun genEd25519(): KeyPair =
        KeyPairGenerator.getInstance("Ed25519").generateKeyPair()

    private fun pub(kp: KeyPair): String =
        Base64.getEncoder().encodeToString(kp.public.encoded)

    private fun keyIdFor(pub: String): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(pub.toByteArray())
        return digest.joinToString("") { ((it.toInt() and 0xff)).toString(16).padStart(2, '0') }.take(32)
    }

    /**
     * The software fallback is always available; a true probe for an attached
     * FIDO2 authenticator is part of the hardware TODO.
     */
    actual suspend fun isAvailable(): Boolean = true

    actual suspend fun createFederationIdentity(
        displayName: String,
        rpId: String,
    ): HardwareIdentityResult {
        // TODO(hardware): replace this software fallback with a real
        // WebAuthn/FIDO2 ceremony:
        //   1. PublicKeyCredentialCreationOptions(rpId, user=displayName, …)
        //   2. drive libfido2/CTAP2 over PC/SC to get attestationObject
        //   3. parse the COSE pubkey out of authData
        //   4. set hardwareAttestation = base64(attestationObject)
        // Until that native stack lands, fall back to JCA software keys.
        PlatformLogger.w(
            "HardwareCredentialManager",
            "[desktop] Using SOFTWARE Ed25519 fallback — NOT hardware-backed. " +
                "rpId=$rpId user=$displayName",
        )

        val identity = genEd25519()
        val app = genEd25519()
        val agent = genEd25519()

        val identityPub = pub(identity)
        val attestation = Base64.getEncoder().encodeToString(
            buildString {
                append("software-fallback;")
                append("rpId=$rpId;")
                append("identity=$identityPub")
            }.toByteArray(),
        )

        return HardwareIdentityResult(
            identityKeyId = keyIdFor(identityPub),
            identityPublicKey = identityPub,
            appOccurrencePublicKey = pub(app),
            agentOccurrencePublicKey = pub(agent),
            hardwareAttestation = attestation,
        )
    }
}

actual fun createHardwareCredentialManager(): HardwareCredentialManager =
    HardwareCredentialManager()
