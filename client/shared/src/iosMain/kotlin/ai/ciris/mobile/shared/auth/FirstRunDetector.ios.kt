package ai.ciris.mobile.shared.auth

import platform.Foundation.*

/**
 * iOS implementation of FirstRunDetector
 *
 * Checks for the existence of CIRIS_HOME/.env to determine if setup is needed.
 * Uses NSFileManager for filesystem operations.
 */
actual class FirstRunDetector {

    actual suspend fun isFirstRunNeeded(cirisHomePath: String): Boolean {
        // Check if .env file exists
        return !envFileExists(cirisHomePath)
    }

    actual suspend fun checkSetupStatusFromApi(serverUrl: String): Boolean {
        // TODO: Implement HTTP GET to /v1/setup/status
        // For now, return true (setup required) as fallback
        return true
    }

    actual suspend fun envFileExists(cirisHomePath: String): Boolean {
        val envPath = getEnvFilePath(cirisHomePath)
        val fileManager = NSFileManager.defaultManager
        return fileManager.fileExistsAtPath(envPath)
    }

    actual fun getEnvFilePath(cirisHomePath: String): String {
        return "$cirisHomePath/.env"
    }
}

actual fun createFirstRunDetector(): FirstRunDetector = FirstRunDetector()
