package ai.ciris.mobile.shared.auth

import io.ktor.client.*
import io.ktor.client.engine.cio.*
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import java.io.File

actual class FirstRunDetector {
    private val httpClient = HttpClient(CIO) {
        engine {
            requestTimeout = 5000
        }
    }

    actual suspend fun isFirstRunNeeded(cirisHomePath: String): Boolean {
        // First check local filesystem
        if (!envFileExists(cirisHomePath)) {
            return true
        }

        // .env exists, so setup was completed at some point
        return false
    }

    actual suspend fun checkSetupStatusFromApi(serverUrl: String): Boolean {
        return try {
            val response = httpClient.get("$serverUrl/v1/setup/status")
            if (response.status != HttpStatusCode.OK) {
                true // Assume setup needed if API unavailable
            } else {
                val body = response.bodyAsText()
                // Parse response to check if setup is required
                body.contains("\"setup_required\":true") ||
                    body.contains("\"is_first_run\":true")
            }
        } catch (e: Exception) {
            true // Assume setup needed if API unavailable
        }
    }

    actual suspend fun envFileExists(cirisHomePath: String): Boolean {
        val envFile = File(cirisHomePath, ".env")
        return envFile.exists() && envFile.isFile
    }

    actual fun getEnvFilePath(cirisHomePath: String): String {
        return File(cirisHomePath, ".env").absolutePath
    }
}

actual fun createFirstRunDetector(): FirstRunDetector = FirstRunDetector()
