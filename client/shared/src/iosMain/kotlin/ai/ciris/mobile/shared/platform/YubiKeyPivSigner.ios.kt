package ai.ciris.mobile.shared.platform

// TODO(later): YubiKit iOS (YKFPIVSession over NFC/Lightning/USB-C). Stub for now —
// iOS keeps the existing (non-YubiKey) federation path.
actual class YubiKeyPivSigner actual constructor() {
    actual val isSupported: Boolean = false

    actual suspend fun <T> withSession(
        onState: (YubiKeyTapState) -> Unit,
        block: suspend (YubiKeyPivSession) -> T,
    ): Result<T> {
        onState(YubiKeyTapState.ERROR)
        return Result.failure(UnsupportedOperationException("YubiKey NFC not yet supported on iOS"))
    }
}
