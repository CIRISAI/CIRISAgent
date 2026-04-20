package ai.ciris.mobile.shared.platform

/**
 * Web implementation of EnvFileUpdater - no-op since web doesn't have .env files.
 * Configuration is handled server-side via API.
 */
actual class EnvFileUpdater {

    actual suspend fun updateEnvWithToken(oauthIdToken: String): Result<Boolean> = Result.success(true)

    actual fun triggerConfigReload() {
        // No-op on web
    }

    actual suspend fun readLlmConfig(): EnvLlmConfig? = null

    actual suspend fun deleteEnvFile(): Result<Boolean> = Result.success(true)

    actual fun checkTokenRefreshSignal(): Boolean = false

    actual suspend fun clearSigningKey(): Result<Boolean> = Result.success(true)

    actual suspend fun clearDataOnly(): Result<Boolean> = Result.success(true)
}

actual fun createEnvFileUpdater(): EnvFileUpdater = EnvFileUpdater()
