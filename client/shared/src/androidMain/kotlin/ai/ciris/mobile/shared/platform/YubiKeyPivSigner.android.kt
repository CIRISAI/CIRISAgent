package ai.ciris.mobile.shared.platform

import android.app.Activity
import android.content.Context
import java.lang.ref.WeakReference
import java.security.cert.X509Certificate
import kotlin.coroutines.resume
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext

import com.yubico.yubikit.android.YubiKitManager
import com.yubico.yubikit.android.transport.nfc.NfcConfiguration
import com.yubico.yubikit.android.transport.nfc.NfcNotAvailable
import com.yubico.yubikit.android.transport.nfc.NfcYubiKeyDevice
import com.yubico.yubikit.core.smartcard.SmartCardConnection
import com.yubico.yubikit.piv.KeyType
import com.yubico.yubikit.piv.PivSession
import com.yubico.yubikit.piv.Slot

/**
 * Android YubiKey PIV signer over **NFC** (yubikit-android 3.1.0). Targets PIV slot
 * 9c / Ed25519 (firmware 5.7+).
 *
 * Lifecycle: the whole [withSession] block runs while the YubiKey is held to the
 * phone (one tap covers read-pubkey → verify-PIN → sign). We bridge yubikit's
 * callback-style NFC discovery + connection into a single suspend scope.
 *
 * The host must register the foreground [Activity] (NFC dispatch needs it) via
 * [setActivity] from `MainActivity.onResume`, mirroring how [SecureStorage] takes a
 * context. Slot-9c pubkey is read from the attestation certificate (its subject key
 * IS the slot-9c key), avoiding a separate metadata call.
 *
 * NOTE: 3 yubikit call sites are marked `// VERIFY` — confirm exact signatures
 * against yubikit-android 3.1.0 on a real device build (the SDK's PIV Ed25519 sign +
 * attest surface is the part to pin down).
 */
actual class YubiKeyPivSigner actual constructor() {

    companion object {
        private var appContext: Context? = null
        private var activityRef: WeakReference<Activity>? = null

        /** Call from Application.onCreate(). */
        fun setContext(context: Context) {
            appContext = context.applicationContext
        }

        /** Call from MainActivity.onResume()/onPause() — NFC dispatch needs the Activity. */
        fun setActivity(activity: Activity?) {
            activityRef = activity?.let { WeakReference(it) }
        }
    }

    actual val isSupported: Boolean
        get() = appContext?.packageManager?.hasSystemFeature("android.hardware.nfc") == true

    actual suspend fun <T> withSession(
        onState: (YubiKeyTapState) -> Unit,
        block: suspend (YubiKeyPivSession) -> T,
    ): Result<T> = withContext(Dispatchers.IO) {
        val ctx = appContext
        val activity = activityRef?.get()
        if (ctx == null || activity == null) {
            onState(YubiKeyTapState.ERROR)
            return@withContext Result.failure(
                IllegalStateException("YubiKeyPivSigner needs an Activity (call setActivity in MainActivity)"),
            )
        }

        val manager = YubiKitManager(ctx)
        onState(YubiKeyTapState.WAITING_FOR_TAP)

        try {
            // 1) Wait for a single NFC tap → NfcYubiKeyDevice.
            val device: NfcYubiKeyDevice = suspendCancellableCoroutine { cont ->
                try {
                    manager.startNfcDiscovery(NfcConfiguration(), activity) { dev ->
                        if (cont.isActive) cont.resume(dev)
                    }
                } catch (e: NfcNotAvailable) {
                    if (cont.isActive) cont.cancel(e)
                }
                cont.invokeOnCancellation { runCatching { manager.stopNfcDiscovery(activity) } }
            }

            // 2) Open a SmartCardConnection → PivSession and run the block within it.
            val resultDeferred = CompletableDeferred<Result<T>>()
            device.requestConnection(SmartCardConnection::class.java) { connResult ->
                try {
                    val connection = connResult.value // throws if the connection failed
                    val piv = PivSession(connection)
                    onState(YubiKeyTapState.CONNECTED)
                    val session = AndroidPivSession(piv) { onState(YubiKeyTapState.WORKING) }
                    // block is suspend; bridge it through a blocking runner on this callback thread.
                    val r = kotlinx.coroutines.runBlocking { runCatching { block(session) } }
                    resultDeferred.complete(r)
                } catch (e: Throwable) {
                    resultDeferred.complete(Result.failure(e))
                }
            }

            val out = resultDeferred.await()
            onState(if (out.isSuccess) YubiKeyTapState.DONE else YubiKeyTapState.ERROR)
            out
        } catch (e: Throwable) {
            onState(YubiKeyTapState.ERROR)
            Result.failure(e)
        } finally {
            runCatching { manager.stopNfcDiscovery(activity) }
        }
    }
}

/** PIV ops bound to an open yubikit [PivSession] (slot 9c / Ed25519). */
private class AndroidPivSession(
    private val piv: PivSession,
    private val onWork: () -> Unit,
) : YubiKeyPivSession {

    override suspend fun readSlot9cPublicKey(): ByteArray {
        onWork()
        // The slot-9c attestation cert's subject public key IS the slot-9c key.
        val cert = piv.attestKey(Slot.SIGNATURE) // VERIFY: attestKey(Slot) -> X509Certificate
        return ed25519RawFromSpki(cert.publicKey.encoded)
    }

    override suspend fun attestSlot9c(): ByteArray {
        onWork()
        val cert: X509Certificate = piv.attestKey(Slot.SIGNATURE) // VERIFY
        return cert.encoded
    }

    override suspend fun verifyPin(pin: String) {
        onWork()
        piv.verifyPin(pin.toCharArray())
    }

    override suspend fun signEd25519(message: ByteArray): ByteArray {
        onWork()
        // yubikit-android 3.1.0 dropped the high-level PivSession.sign(); for Ed25519 the
        // card does the full PureEdDSA over the raw message via rawSignOrDecrypt, returning
        // the 64-byte signature directly.
        return piv.rawSignOrDecrypt(Slot.SIGNATURE, KeyType.ED25519, message)
    }

    /**
     * Extract the raw 32-byte Ed25519 public key from a DER SubjectPublicKeyInfo.
     * An Ed25519 SPKI is a fixed 44-byte structure whose final 32 bytes are the key.
     */
    private fun ed25519RawFromSpki(spki: ByteArray): ByteArray {
        require(spki.size >= 32) { "SPKI too short for Ed25519" }
        return spki.copyOfRange(spki.size - 32, spki.size)
    }
}
