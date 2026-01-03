package ai.ciris.mobile.shared.api

import ai.ciris.mobile.shared.models.*
import ai.ciris.mobile.shared.viewmodels.SetupCompletionResult

/**
 * Protocol/interface for CIRIS API client operations.
 * Allows dependency injection and testability without subclassing final classes.
 *
 * Implementations:
 * - CIRISApiClient (actual HTTP client)
 * - Test fakes in commonTest
 */
interface CIRISApiClientProtocol {
    /**
     * Set the access token for authenticated requests
     */
    fun setAccessToken(token: String)

    /**
     * Send a chat message to the agent
     */
    suspend fun sendMessage(message: String, channelId: String = "mobile_app"): InteractResponse

    /**
     * Get recent chat messages
     */
    suspend fun getMessages(limit: Int = 20): List<ChatMessage>

    /**
     * Get system health status
     */
    suspend fun getSystemStatus(): SystemStatus

    /**
     * Get telemetry data
     */
    suspend fun getTelemetry(): TelemetryResponse

    /**
     * Login with username/password
     */
    suspend fun login(username: String, password: String): AuthResponse

    /**
     * Authenticate with Google ID token
     */
    suspend fun googleAuth(idToken: String, userId: String? = null): AuthResponse

    /**
     * Logout current session
     */
    suspend fun logout()

    /**
     * Initiate graceful shutdown
     */
    suspend fun initiateShutdown()

    /**
     * Emergency shutdown (immediate)
     */
    suspend fun emergencyShutdown()

    /**
     * Get setup wizard status
     */
    suspend fun getSetupStatus(): SetupStatusResponse

    /**
     * Complete first-run setup
     */
    suspend fun completeSetup(request: CompleteSetupRequest): SetupCompletionResult

    /**
     * Close the client and release resources
     */
    fun close()
}
