package ai.ciris.mobile.shared.platform

/**
 * On-device YubiKey PIV access for the **YubiKey-backed federation identity** (the
 * fed-ID that secures login / node ownership). On desktop the Rust node opens the
 * token locally via ykcs11; on a phone the node is sandboxed and cannot reach an
 * NFC/USB token, so the hardware ops must run in the app's native layer (YubiKit).
 *
 * Operations target PIV **slot 9c** (Digital Signature), an **Ed25519** key
 * (YubiKey firmware 5.7+). The private key never leaves the token; we only read the
 * public key + attestation and ask the token to sign.
 *
 * The token must stay connected for an entire [withSession] block (one tap covers
 * read-pubkey → verify-PIN → sign), because NFC is only alive while held to the
 * phone. The fed-ID mint therefore runs *inside* the block so its single Ed25519
 * signature is produced while the key is still tapped.
 *
 * Platforms: Android = yubikit-android over NFC (this milestone). iOS NFC + USB-C
 * are later; desktop/wasm are `NotSupported` (desktop mints via the Rust node).
 *
 * Mirrors the [SecureStorage] / DirectoryPicker expect/actual pattern.
 */
expect class YubiKeyPivSigner() {
    /** Whether this platform can talk to a YubiKey (Android NFC today). */
    val isSupported: Boolean

    /**
     * Wait for a YubiKey tap (NFC), open a PIV session, and run [block] with it. The
     * token stays connected for the whole block. [onState] drives the "hold your key
     * to the phone" UI. Returns [block]'s result, or a failure if no token is tapped
     * / the platform is unsupported / a PIV error occurs.
     */
    suspend fun <T> withSession(
        onState: (YubiKeyTapState) -> Unit = {},
        block: suspend (YubiKeyPivSession) -> T,
    ): Result<T>
}

/**
 * PIV operations available while a YubiKey is connected. Implemented per platform
 * (Android wraps yubikit's `PivSession`). All calls assume slot 9c / Ed25519.
 */
interface YubiKeyPivSession {
    /** The 32-byte Ed25519 public key in slot 9c. */
    suspend fun readSlot9cPublicKey(): ByteArray

    /** The slot-9c PIV attestation certificate (DER), signed by the slot-f9 key. */
    suspend fun attestSlot9c(): ByteArray

    /** Verify the PIV PIN (unlocks signing for this session). Throws on wrong PIN. */
    suspend fun verifyPin(pin: String)

    /** Sign [message] with the slot-9c Ed25519 key → a 64-byte EdDSA signature. */
    suspend fun signEd25519(message: ByteArray): ByteArray
}

/** UI state for the NFC tap flow. */
enum class YubiKeyTapState {
    /** Not started. */
    IDLE,

    /** Waiting for the user to hold their YubiKey to the phone. */
    WAITING_FOR_TAP,

    /** A YubiKey is connected and a PIV session is open. */
    CONNECTED,

    /** Performing PIV operations (read / verify-PIN / sign) — keep the key held. */
    WORKING,

    /** Done — the key may be removed. */
    DONE,

    /** An error occurred (see the returned failure). */
    ERROR,
}
