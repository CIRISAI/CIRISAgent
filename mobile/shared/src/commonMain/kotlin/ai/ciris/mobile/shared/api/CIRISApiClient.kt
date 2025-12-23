package ai.ciris.mobile.shared.api

import ai.ciris.mobile.shared.models.*
import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.plugins.*
import io.ktor.client.plugins.auth.*
import io.ktor.client.plugins.auth.providers.*
import io.ktor.client.plugins.contentnegotiation.*
import io.ktor.client.plugins.logging.*
import io.ktor.client.request.*
import io.ktor.http.*
import io.ktor.serialization.kotlinx.json.*
import kotlinx.serialization.json.Json

/**
 * Unified API client for CIRIS backend
 * Replaces Android's OkHttp-based API calls
 * Based on InteractActivity.kt, SettingsActivity.kt, and other Android API usage
 */
class CIRISApiClient(
    private val baseUrl: String = "http://localhost:8080",
    private var accessToken: String? = null
) {
    private val client = HttpClient {
        install(ContentNegotiation) {
            json(Json {
                ignoreUnknownKeys = true
                isLenient = true
                prettyPrint = true
            })
        }

        install(Logging) {
            logger = Logger.DEFAULT
            level = LogLevel.INFO
        }

        install(HttpTimeout) {
            requestTimeoutMillis = 30000
            connectTimeoutMillis = 10000
            socketTimeoutMillis = 30000
        }

        defaultRequest {
            contentType(ContentType.Application.Json)
            accessToken?.let {
                bearerAuth(it)
            }
        }
    }

    fun setAccessToken(token: String) {
        accessToken = token
    }

    // Chat / Interact
    suspend fun sendMessage(message: String, channelId: String = "mobile_app"): InteractResponse {
        return client.post("$baseUrl/v1/agent/interact") {
            setBody(InteractRequest(message, channelId))
        }.body()
    }

    suspend fun getMessages(limit: Int = 20): List<ChatMessage> {
        return client.get("$baseUrl/v1/agent/messages") {
            parameter("limit", limit)
        }.body()
    }

    // System Status (from InteractActivity.kt polling)
    suspend fun getSystemStatus(): SystemStatus {
        return client.get("$baseUrl/v1/system/health").body()
    }

    suspend fun getTelemetry(): TelemetryResponse {
        return client.get("$baseUrl/v1/telemetry/unified").body()
    }

    // Authentication (from LoginActivity.kt)
    suspend fun login(username: String, password: String): AuthResponse {
        return client.post("$baseUrl/v1/auth/login") {
            setBody(LoginRequest(username, password))
        }.body()
    }

    suspend fun googleAuth(idToken: String, userId: String? = null): AuthResponse {
        return client.post("$baseUrl/v1/auth/google") {
            setBody(GoogleAuthRequest(idToken, userId))
        }.body()
    }

    suspend fun logout() {
        client.post("$baseUrl/v1/auth/logout")
    }

    // Shutdown controls (from InteractActivity.kt:shutdownButton)
    suspend fun initiateShutdown() {
        client.post("$baseUrl/v1/system/shutdown")
    }

    suspend fun emergencyShutdown() {
        client.post("$baseUrl/v1/system/emergency-shutdown")
    }

    // Setup wizard (from SetupWizardActivity.kt)
    suspend fun completeSetup(llmProvider: String, apiKey: String) {
        client.post("$baseUrl/v1/setup/complete") {
            setBody(mapOf(
                "llm_provider" to llmProvider,
                "api_key" to apiKey
            ))
        }
    }

    fun close() {
        client.close()
    }
}
