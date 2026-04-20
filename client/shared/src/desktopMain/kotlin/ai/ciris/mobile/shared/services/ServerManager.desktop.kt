package ai.ciris.mobile.shared.services

import ai.ciris.mobile.shared.platform.createSecureStorage
import io.ktor.client.*
import io.ktor.client.engine.cio.*
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import kotlinx.serialization.json.Json

private val httpClient = HttpClient(CIO) {
    engine {
        requestTimeout = 5000
    }
}

private val json = Json { ignoreUnknownKeys = true }

actual suspend fun platformHttpGet(url: String): Int {
    return try {
        val response = httpClient.get(url)
        response.status.value
    } catch (e: Exception) {
        -1
    }
}

actual suspend fun platformHttpPost(url: String, body: String): Pair<Int, ServerManager.ShutdownResponse> {
    return try {
        val response = httpClient.post(url) {
            contentType(ContentType.Application.Json)
            setBody(body)
        }
        val responseBody = response.bodyAsText()

        // Parse shutdown response
        val shutdownResponse = try {
            json.decodeFromString<ServerManager.ShutdownResponse>(responseBody)
        } catch (e: Exception) {
            ServerManager.ShutdownResponse(
                status = "error",
                reason = e.message,
                retryAfterMs = null,
                serverState = null,
                uptimeSeconds = null,
                resumeElapsedSeconds = null,
                resumeTimeoutSeconds = null
            )
        }

        Pair(response.status.value, shutdownResponse)
    } catch (e: Exception) {
        Pair(
            -1,
            ServerManager.ShutdownResponse(
                status = "error",
                reason = e.message,
                retryAfterMs = null,
                serverState = null,
                uptimeSeconds = null,
                resumeElapsedSeconds = null,
                resumeTimeoutSeconds = null
            )
        )
    }
}

actual suspend fun platformHttpPostWithAuth(url: String, body: String, token: String?): Int {
    return try {
        val response = httpClient.post(url) {
            contentType(ContentType.Application.Json)
            if (token != null) {
                header("Authorization", "Bearer $token")
            }
            setBody(body)
        }
        response.status.value
    } catch (e: Exception) {
        -1
    }
}

actual suspend fun platformGetAuthToken(): String? {
    return createSecureStorage().getAccessToken().getOrNull()
}
