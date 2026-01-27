package ai.ciris.mobile.shared.api

import ai.ciris.mobile.shared.models.*
import ai.ciris.mobile.shared.viewmodels.SetupCompletionResult
import ai.ciris.mobile.shared.viewmodels.StateTransitionResult

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
     * Log current token state for debugging auth issues.
     * Call this when troubleshooting 401 errors.
     */
    fun logTokenState() {
        // Default no-op implementation for test fakes
    }

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
     * Transition cognitive state (WORK, DREAM, PLAY, SOLITUDE)
     * @param targetState Target state to transition to
     * @param reason Optional reason for the transition
     * @return StateTransitionResult with success status and current state
     */
    suspend fun transitionCognitiveState(targetState: String, reason: String? = null): StateTransitionResult

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

    // ===== Config API =====

    /**
     * Get LLM configuration
     */
    suspend fun getLlmConfig(): LlmConfigData

    // ===== Billing API =====

    /**
     * Get credit balance and status
     */
    suspend fun getCredits(): CreditStatusData

    // ===== Adapters API =====

    /**
     * List all adapters
     */
    suspend fun listAdapters(): AdaptersListData

    /**
     * Reload an adapter
     */
    suspend fun reloadAdapter(adapterId: String): AdapterActionData

    /**
     * Remove/unload an adapter
     */
    suspend fun removeAdapter(adapterId: String): AdapterActionData

    // ===== Services API =====

    /**
     * Get registered services information
     */
    suspend fun getServices(): ServicesResponse

    // ===== Runtime Control API =====

    /**
     * Get runtime state (processor state, queue depth, etc.)
     */
    suspend fun getRuntimeState(): RuntimeStateResponse

    /**
     * Pause runtime processing
     */
    suspend fun pauseRuntime(): RuntimeControlResponse

    /**
     * Resume runtime processing
     */
    suspend fun resumeRuntime(): RuntimeControlResponse

    /**
     * Execute a single processing step (when paused)
     */
    suspend fun singleStepProcessor(): SingleStepResponse
}

/**
 * Credit status data from billing API
 */
data class CreditStatusData(
    val hasCredit: Boolean,
    val creditsRemaining: Int,
    val freeUsesRemaining: Int,
    val dailyFreeUsesRemaining: Int?,
    val totalUses: Int,
    val planName: String?,
    val purchaseRequired: Boolean
)

/**
 * Google Play purchase verification result
 */
data class GooglePlayVerifyData(
    val success: Boolean,
    val creditsAdded: Int,
    val newBalance: Int,
    val alreadyProcessed: Boolean,
    val error: String?
)

/**
 * Adapters list data from system API
 */
data class AdaptersListData(
    val adapters: List<AdapterStatusData>,
    val totalCount: Int,
    val runningCount: Int
)

/**
 * Individual adapter status
 */
data class AdapterStatusData(
    val adapterId: String,
    val adapterType: String,
    val isRunning: Boolean
)

/**
 * Result of adapter action (reload/remove)
 */
data class AdapterActionData(
    val adapterId: String,
    val success: Boolean,
    val message: String?
)

// ===== Services API Data Models =====

/**
 * Services response from /v1/system/services
 */
data class ServicesResponse(
    val globalServices: Map<String, List<ServiceProviderData>>,
    val handlers: Map<String, Map<String, List<ServiceProviderData>>>
)

/**
 * Service provider data
 */
data class ServiceProviderData(
    val name: String,
    val priority: String,
    val priorityGroup: Int,
    val strategy: String,
    val circuitBreakerState: String,
    val capabilities: List<String>
)

// ===== Runtime API Data Models =====

/**
 * Runtime state response from /v1/system/runtime
 */
data class RuntimeStateResponse(
    val processorState: String,
    val cognitiveState: String,
    val queueDepth: Int,
    val activeTasks: List<RuntimeTaskData>
)

/**
 * Active task data in runtime state
 */
data class RuntimeTaskData(
    val taskId: String,
    val status: String,
    val thoughtCount: Int,
    val lastUpdated: String
)

/**
 * Response from pause/resume runtime operations
 */
data class RuntimeControlResponse(
    val processorState: String,
    val message: String?
)

/**
 * Response from single-step processor operation
 */
data class SingleStepResponse(
    val stepPoint: String?,
    val message: String?,
    val processingTimeMs: Long?,
    val tokensUsed: Int?
)
