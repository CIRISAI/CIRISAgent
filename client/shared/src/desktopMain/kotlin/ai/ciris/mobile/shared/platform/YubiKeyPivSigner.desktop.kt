package ai.ciris.mobile.shared.platform

// Desktop mints the YubiKey-backed fed-ID via the local Rust ciris-server node
// (ykcs11), not through this app-side signer. Stub so commonMain compiles.
actual class YubiKeyPivSigner actual constructor() {
    actual val isSupported: Boolean = false

    actual suspend fun <T> withSession(
        onState: (YubiKeyTapState) -> Unit,
        block: suspend (YubiKeyPivSession) -> T,
    ): Result<T> {
        onState(YubiKeyTapState.ERROR)
        return Result.failure(
            UnsupportedOperationException("Desktop mints via the node (ykcs11), not the app signer"),
        )
    }
}
