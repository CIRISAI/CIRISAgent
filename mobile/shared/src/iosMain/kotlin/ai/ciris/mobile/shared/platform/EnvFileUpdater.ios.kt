package ai.ciris.mobile.shared.platform

/**
 * iOS implementation of EnvFileUpdater.
 *
 * iOS uses different mechanisms for configuration management,
 * so this is a stub implementation for now.
 */
actual class EnvFileUpdater {

    actual suspend fun updateEnvWithToken(googleIdToken: String): Result<Boolean> {
        // iOS doesn't use .env files in the same way as Android
        // Configuration is typically handled through UserDefaults or Keychain
        println("[EnvFileUpdater.ios] updateEnvWithToken not implemented for iOS")
        return Result.success(false)
    }

    actual fun triggerConfigReload() {
        // iOS doesn't have the same Python runtime setup
        println("[EnvFileUpdater.ios] triggerConfigReload not implemented for iOS")
    }

    actual suspend fun readLlmConfig(): EnvLlmConfig? {
        // iOS doesn't use .env files
        println("[EnvFileUpdater.ios] readLlmConfig not implemented for iOS")
        return null
    }

    actual suspend fun deleteEnvFile(): Result<Boolean> {
        // iOS doesn't use .env files
        println("[EnvFileUpdater.ios] deleteEnvFile not implemented for iOS")
        return Result.success(false)
    }
}

/**
 * Factory function to create iOS EnvFileUpdater
 */
actual fun createEnvFileUpdater(): EnvFileUpdater = EnvFileUpdater()
