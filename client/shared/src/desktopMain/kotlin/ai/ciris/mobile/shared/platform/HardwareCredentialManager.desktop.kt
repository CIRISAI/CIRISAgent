package ai.ciris.mobile.shared.platform

import java.security.KeyFactory
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.MessageDigest
import java.security.PrivateKey
import java.security.PublicKey
import java.security.SecureRandom
import java.security.Security
import java.security.Signature
import java.security.spec.PKCS8EncodedKeySpec
import java.security.spec.X509EncodedKeySpec
import java.util.Base64
import kotlinx.coroutines.runBlocking
import org.bouncycastle.jce.provider.BouncyCastleProvider
import org.bouncycastle.jcajce.interfaces.MLDSAPublicKey
import org.bouncycastle.jcajce.spec.MLDSAParameterSpec

/**
 * Desktop [HardwareCredentialManager] — the founder's REAL hybrid signer.
 *
 * This is what mints + signs the long-lived federation ID today (CIRISAgent#887).
 * It produces a true HYBRID (Ed25519 + ML-DSA-65) identity and can [sign] the
 * EXACT request-body bytes with BOTH keys, so the node's Strict hybrid verifier
 * (both signatures required, no classical-only path) admits the claim/self-login.
 *
 *  - **Ed25519** — JDK JCA (`Ed25519`, available JDK 15+). Raw 64-byte signature.
 *  - **ML-DSA-65** — BouncyCastle (`org.bouncycastle:bcprov-jdk18on`), the
 *    FIPS-204 level-3 parameter set (`MLDSAParameterSpec.ml_dsa_65`,
 *    algorithm "ML-DSA-65"). NOTE: ML-DSA-65 == CRYSTALS-Dilithium3 == FIPS-204
 *    security level 3; BC's `ML-DSA-65` is the *final* FIPS-204 standard (NOT the
 *    round-3 Dilithium candidate, which differs in domain-separation bytes).
 *    `sign()` / pubkeys are the RAW FIPS-204 octets (not DER/COSE).
 *
 * Keys are persisted to [SecureStorage] (AES at rest) as Base64 of the standard
 * PKCS8 (private) / X.509 (public) encodings, and reloaded on the next launch —
 * so the founder's ID is genuinely long-lived: mint once, sign forever.
 *
 * IDEAL (still a TODO): root the identity in a real hardware authenticator
 * (WebAuthn/FIDO2 over PC/SC, a YubiKey or platform authenticator) and emit a
 * genuine WebAuthn `attestationObject`. The software keys below are NOT
 * hardware-backed; the self-login attestation is still tagged `software-fallback`.
 */
actual class HardwareCredentialManager actual constructor() {

    private val storage = SecureStorage()

    /** A long-lived hybrid identity loaded into memory (keys live + raw pubkeys). */
    private class LoadedIdentity(
        val keyId: String,
        val ed25519: KeyPair,
        val mlDsa65: KeyPair,
    )

    @Volatile
    private var loaded: LoadedIdentity? = null

    companion object {
        private const val TAG = "HardwareCredentialManager"

        // SecureStorage keys for the persisted long-lived federation identity.
        private const val K_KEY_ID = "fed_identity.key_id"
        private const val K_ED_PRIV = "fed_identity.ed25519.pkcs8_b64"
        private const val K_ED_PUB = "fed_identity.ed25519.x509_b64"
        private const val K_ML_PRIV = "fed_identity.ml_dsa_65.pkcs8_b64"
        private const val K_ML_PUB = "fed_identity.ml_dsa_65.x509_b64"

        /** ML-DSA-65 == Dilithium3 == FIPS-204 level 3. BC algorithm + parameter. */
        private const val ML_DSA_ALG = "ML-DSA-65"

        private val bc: BouncyCastleProvider by lazy {
            val existing = Security.getProvider(BouncyCastleProvider.PROVIDER_NAME) as? BouncyCastleProvider
            existing ?: BouncyCastleProvider().also { Security.addProvider(it) }
        }
    }

    private fun b64(bytes: ByteArray): String = Base64.getEncoder().encodeToString(bytes)
    private fun unb64(s: String): ByteArray = Base64.getDecoder().decode(s)

    private fun genEd25519(): KeyPair =
        KeyPairGenerator.getInstance("Ed25519").generateKeyPair()

    private fun genMlDsa65(): KeyPair {
        val kpg = KeyPairGenerator.getInstance(ML_DSA_ALG, bc)
        kpg.initialize(MLDSAParameterSpec.ml_dsa_65, SecureRandom())
        return kpg.generateKeyPair()
    }

    /** X.509 SubjectPublicKeyInfo (PublicKey.encoded), base64. */
    private fun pubX509B64(kp: KeyPair): String = b64(kp.public.encoded)

    /**
     * Raw Ed25519 public key (32 bytes), base64. The JCA X.509 SPKI for Ed25519
     * is a fixed 44-byte structure whose trailing 32 bytes are the raw key.
     */
    private fun ed25519RawPubB64(kp: KeyPair): String {
        val spki = kp.public.encoded
        val raw = spki.copyOfRange(spki.size - 32, spki.size)
        return b64(raw)
    }

    /** Raw FIPS-204 ML-DSA-65 public key bytes, base64 (BC `getPublicData()`). */
    private fun mlDsa65RawPubB64(kp: KeyPair): String {
        val pub = kp.public as MLDSAPublicKey
        return b64(pub.publicData)
    }

    private fun keyIdFor(rawEd25519PubB64: String): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(rawEd25519PubB64.toByteArray())
        return digest.joinToString("") { ((it.toInt() and 0xff)).toString(16).padStart(2, '0') }.take(32)
    }

    actual suspend fun isAvailable(): Boolean = true

    /**
     * Mint (first run) or reload (subsequent launches) the long-lived hybrid
     * federation identity. Idempotent: once persisted, the SAME key_id + keys
     * come back on every call, so the founder ID is stable across launches.
     */
    actual suspend fun createFederationIdentity(
        displayName: String,
        rpId: String,
    ): HardwareIdentityResult {
        PlatformLogger.w(
            TAG,
            "[desktop] HYBRID federation identity (Ed25519 + ML-DSA-65) via JCA + BouncyCastle. " +
                "Keys are SOFTWARE (not hardware-attested yet). rpId=$rpId user=$displayName",
        )

        val identity = loadPersisted() ?: mintAndPersist()
        loaded = identity

        val edRawPub = ed25519RawPubB64(identity.ed25519)
        val mlRawPub = mlDsa65RawPubB64(identity.mlDsa65)

        // app/agent occurrence keys remain ephemeral Ed25519 (self-login surface,
        // unchanged); only the founder identity is the long-lived hybrid key.
        val app = genEd25519()
        val agent = genEd25519()

        val attestation = b64(
            buildString {
                append("software-fallback;")
                append("rpId=$rpId;")
                append("key_id=${identity.keyId};")
                append("ed25519=$edRawPub;")
                append("ml_dsa_65=${mlRawPub.take(32)}…")
            }.toByteArray(),
        )

        return HardwareIdentityResult(
            identityKeyId = identity.keyId,
            identityPublicKey = pubX509B64(identity.ed25519),
            appOccurrencePublicKey = pubX509B64(app),
            agentOccurrencePublicKey = pubX509B64(agent),
            hardwareAttestation = attestation,
            ed25519PublicKeyB64 = edRawPub,
            mlDsa65PublicKeyB64 = mlRawPub,
        )
    }

    actual suspend fun currentIdentity(): FederationIdentityPublic? {
        val id = loaded ?: loadPersisted()?.also { loaded = it } ?: return null
        return FederationIdentityPublic(
            keyId = id.keyId,
            ed25519PublicKeyB64 = ed25519RawPubB64(id.ed25519),
            mlDsa65PublicKeyB64 = mlDsa65RawPubB64(id.mlDsa65),
        )
    }

    /**
     * Sign [message] with BOTH halves. Ed25519 via JCA (raw 64-byte sig);
     * ML-DSA-65 via BouncyCastle (raw FIPS-204 sig). Both base64'd.
     */
    actual suspend fun sign(message: ByteArray): HybridSignature {
        val id = loaded ?: loadPersisted()?.also { loaded = it }
            ?: throw HardwareCredentialUnavailable(
                "No federation identity loaded — call createFederationIdentity() first.",
            )

        val edSig = Signature.getInstance("Ed25519").run {
            initSign(id.ed25519.private)
            update(message)
            sign()
        }
        val mlSig = Signature.getInstance(ML_DSA_ALG, bc).run {
            initSign(id.mlDsa65.private)
            update(message)
            sign()
        }
        return HybridSignature(ed25519B64 = b64(edSig), mlDsa65B64 = b64(mlSig))
    }

    // ─── persistence ─────────────────────────────────────────────────────────

    private fun mintAndPersist(): LoadedIdentity {
        val ed = genEd25519()
        val ml = genMlDsa65()
        val keyId = keyIdFor(ed25519RawPubB64(ed))

        runBlocking {
            storage.save(K_KEY_ID, keyId)
            storage.save(K_ED_PRIV, b64(ed.private.encoded))
            storage.save(K_ED_PUB, b64(ed.public.encoded))
            storage.save(K_ML_PRIV, b64(ml.private.encoded))
            storage.save(K_ML_PUB, b64(ml.public.encoded))
        }
        PlatformLogger.i(TAG, "[desktop] minted long-lived hybrid federation identity key_id=$keyId")
        return LoadedIdentity(keyId, ed, ml)
    }

    private fun loadPersisted(): LoadedIdentity? = runBlocking {
        val keyId = storage.get(K_KEY_ID).getOrNull() ?: return@runBlocking null
        val edPriv = storage.get(K_ED_PRIV).getOrNull() ?: return@runBlocking null
        val edPub = storage.get(K_ED_PUB).getOrNull() ?: return@runBlocking null
        val mlPriv = storage.get(K_ML_PRIV).getOrNull() ?: return@runBlocking null
        val mlPub = storage.get(K_ML_PUB).getOrNull() ?: return@runBlocking null

        try {
            val edFactory = KeyFactory.getInstance("Ed25519")
            val ed = KeyPair(
                edFactory.generatePublic(X509EncodedKeySpec(unb64(edPub))) as PublicKey,
                edFactory.generatePrivate(PKCS8EncodedKeySpec(unb64(edPriv))) as PrivateKey,
            )
            val mlFactory = KeyFactory.getInstance(ML_DSA_ALG, bc)
            val ml = KeyPair(
                mlFactory.generatePublic(X509EncodedKeySpec(unb64(mlPub))) as PublicKey,
                mlFactory.generatePrivate(PKCS8EncodedKeySpec(unb64(mlPriv))) as PrivateKey,
            )
            PlatformLogger.i(TAG, "[desktop] reloaded long-lived hybrid federation identity key_id=$keyId")
            LoadedIdentity(keyId, ed, ml)
        } catch (e: Exception) {
            PlatformLogger.e(TAG, "[desktop] failed to reload persisted identity: ${e.message}", e)
            null
        }
    }
}

actual fun createHardwareCredentialManager(): HardwareCredentialManager =
    HardwareCredentialManager()
