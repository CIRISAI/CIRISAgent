package ai.ciris.mobile.shared.platform

import java.security.KeyFactory
import java.security.Security
import java.security.Signature
import java.security.spec.X509EncodedKeySpec
import java.util.Base64
import kotlinx.coroutines.test.runTest
import org.bouncycastle.jcajce.provider.asymmetric.mldsa.BCMLDSAPublicKey
import org.bouncycastle.jce.provider.BouncyCastleProvider
import org.bouncycastle.pqc.crypto.mldsa.MLDSAParameters
import org.bouncycastle.pqc.crypto.mldsa.MLDSAPublicKeyParameters
import kotlin.test.AfterTest
import kotlin.test.BeforeTest
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

/**
 * Proves the desktop [HardwareCredentialManager] is a REAL hybrid signer
 * (CIRISAgent#887): it mints a long-lived Ed25519 + ML-DSA-65 (FIPS-204 L3)
 * identity and produces signatures that an INDEPENDENT verifier — reconstructing
 * the public key from ONLY the raw, base64'd wire pubkey bytes — accepts.
 *
 * If these pass, the founder can mint a long-lived ID and sign a claim that the
 * node's Strict hybrid verifier (which has only the raw founder pubkeys from the
 * body) can verify, on desktop, end-to-end.
 */
class HybridSignerTest {

    private val b64 = Base64.getDecoder()

    @BeforeTest
    fun setUp() {
        if (Security.getProvider(BouncyCastleProvider.PROVIDER_NAME) == null) {
            Security.addProvider(BouncyCastleProvider())
        }
        // Isolate persistence per run so the long-lived identity is deterministic.
        System.setProperty("user.home", createTempHome())
    }

    @AfterTest
    fun tearDown() {
        clearPersistedIdentity()
    }

    private fun createTempHome(): String =
        java.nio.file.Files.createTempDirectory("ciris-hybrid-test").toString()

    /** Reconstruct a JCA Ed25519 verifier from ONLY the raw 32-byte pubkey. */
    private fun ed25519VerifierFromRaw(raw32: ByteArray): Signature {
        // X.509 SubjectPublicKeyInfo prefix for Ed25519 + the raw key.
        val prefix = byteArrayOf(
            0x30, 0x2a, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x03, 0x21, 0x00,
        )
        val spki = prefix + raw32
        val key = KeyFactory.getInstance("Ed25519").generatePublic(X509EncodedKeySpec(spki))
        return Signature.getInstance("Ed25519").apply { initVerify(key) }
    }

    /** Reconstruct a JCA ML-DSA-65 verifier from ONLY the raw FIPS-204 pubkey. */
    private fun mlDsa65VerifierFromRaw(raw: ByteArray): Signature {
        val params = MLDSAPublicKeyParameters(MLDSAParameters.ml_dsa_65, raw)
        val key = BCMLDSAPublicKey(params)
        return Signature.getInstance("ML-DSA-65", BouncyCastleProvider.PROVIDER_NAME)
            .apply { initVerify(key) }
    }

    @Test
    fun mintsHybridIdentityAndSignsVerifiableByRawPubkeys() = runTest {
        val mgr = HardwareCredentialManager()
        val identity = mgr.createFederationIdentity(displayName = "Founder", rpId = "https://node.example")

        val edRawB64 = assertNotNull(identity.ed25519PublicKeyB64, "Ed25519 pubkey must be present")
        val mlRawB64 = assertNotNull(identity.mlDsa65PublicKeyB64, "ML-DSA-65 pubkey must be present")

        val edRaw = b64.decode(edRawB64)
        val mlRaw = b64.decode(mlRawB64)
        assertEquals(32, edRaw.size, "raw Ed25519 pubkey must be 32 bytes")
        // FIPS-204 ML-DSA-65 public key is 1952 bytes.
        assertEquals(1952, mlRaw.size, "raw ML-DSA-65 pubkey must be 1952 bytes (FIPS-204 L3)")

        val message = """{"node_code":"CIRIS-V1-abc","founder":{"key_id":"${identity.identityKeyId}"}}"""
            .encodeToByteArray()
        val sig = mgr.sign(message)

        val edSig = b64.decode(sig.ed25519B64)
        val mlSig = b64.decode(sig.mlDsa65B64)
        assertEquals(64, edSig.size, "raw Ed25519 signature must be 64 bytes")

        // Verify Ed25519 against a verifier built from ONLY the raw wire pubkey.
        val edVerifier = ed25519VerifierFromRaw(edRaw)
        edVerifier.update(message)
        assertTrue(edVerifier.verify(edSig), "Ed25519 signature must verify against raw wire pubkey")

        // Verify ML-DSA-65 against a verifier built from ONLY the raw wire pubkey.
        val mlVerifier = mlDsa65VerifierFromRaw(mlRaw)
        mlVerifier.update(message)
        assertTrue(mlVerifier.verify(mlSig), "ML-DSA-65 signature must verify against raw wire pubkey")
    }

    @Test
    fun tamperedMessageFailsVerification() = runTest {
        val mgr = HardwareCredentialManager()
        val identity = mgr.createFederationIdentity(displayName = "Founder", rpId = "rp")
        val message = "exact-body-bytes".encodeToByteArray()
        val sig = mgr.sign(message)

        val edVerifier = ed25519VerifierFromRaw(b64.decode(identity.ed25519PublicKeyB64!!))
        edVerifier.update("tampered-body-bytes".encodeToByteArray())
        assertFalse(edVerifier.verify(b64.decode(sig.ed25519B64)), "tampered Ed25519 must NOT verify")

        val mlVerifier = mlDsa65VerifierFromRaw(b64.decode(identity.mlDsa65PublicKeyB64!!))
        mlVerifier.update("tampered-body-bytes".encodeToByteArray())
        assertFalse(mlVerifier.verify(b64.decode(sig.mlDsa65B64)), "tampered ML-DSA-65 must NOT verify")
    }

    @Test
    fun identityIsLongLivedAcrossManagerInstances() = runTest {
        val mgr1 = HardwareCredentialManager()
        val id1 = mgr1.createFederationIdentity(displayName = "Founder", rpId = "rp")

        // A fresh manager (simulating a relaunch) must reload the SAME identity.
        val mgr2 = HardwareCredentialManager()
        val id2 = mgr2.currentIdentity()
        assertNotNull(id2, "persisted identity must reload across launches")
        assertEquals(id1.identityKeyId, id2.keyId, "key_id must be stable across launches")
        assertEquals(id1.ed25519PublicKeyB64, id2.ed25519PublicKeyB64, "Ed25519 pubkey must be stable")
        assertEquals(id1.mlDsa65PublicKeyB64, id2.mlDsa65PublicKeyB64, "ML-DSA-65 pubkey must be stable")

        // And the reloaded identity must still sign verifiably.
        val message = "long-lived".encodeToByteArray()
        val sig = mgr2.sign(message)
        val v = mlDsa65VerifierFromRaw(b64.decode(id2.mlDsa65PublicKeyB64))
        v.update(message)
        assertTrue(v.verify(b64.decode(sig.mlDsa65B64)), "reloaded identity must sign verifiably")
    }

    private fun clearPersistedIdentity() {
        try {
            val prefs = java.util.prefs.Preferences.userNodeForPackage(SecureStorage::class.java)
            prefs.clear()
        } catch (_: Exception) {
        }
    }
}
