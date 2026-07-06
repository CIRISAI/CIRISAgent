package ai.ciris.mobile.shared.platform

// Browsers have no PIV/NFC access path here. Stub.
actual class YubiKeyPivSigner actual constructor() {
    actual val isSupported: Boolean = false

    actual suspend fun <T> withSession(
        onState: (YubiKeyTapState) -> Unit,
        block: suspend (YubiKeyPivSession) -> T,
    ): Result<T> {
        onState(YubiKeyTapState.ERROR)
        return Result.failure(UnsupportedOperationException("YubiKey not supported on web"))
    }
}
