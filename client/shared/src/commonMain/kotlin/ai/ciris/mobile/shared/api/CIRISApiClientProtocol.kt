package ai.ciris.mobile.shared.api

import ai.ciris.api.models.DocumentPayload
import ai.ciris.api.models.ImagePayload
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
     * Send a chat message to the agent, optionally with image/document attachments
     */
    suspend fun sendMessage(
        message: String,
        channelId: String = "mobile_app",
        images: List<ImagePayload>? = null,
        documents: List<DocumentPayload>? = null
    ): InteractResponse

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
     * Authenticate with Google ID token (Android)
     */
    suspend fun googleAuth(idToken: String, userId: String? = null): AuthResponse

    /**
     * Authenticate with Apple ID token (iOS)
     */
    suspend fun appleAuth(idToken: String, userId: String? = null): AuthResponse

    /**
     * Authenticate with native OAuth token (Google on Android, Apple on iOS)
     * @param provider OAuth provider ("google" or "apple")
     */
    suspend fun nativeAuth(idToken: String, userId: String? = null, provider: String): AuthResponse

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

    // ===== Location Search API =====

    /**
     * Search for cities by name (typeahead autocomplete)
     * @param query Search query (city name or partial)
     * @param countryCode Optional ISO 3166-1 alpha-2 country code to filter by
     * @param limit Maximum number of results (1-50, default 10)
     */
    suspend fun searchLocations(
        query: String,
        countryCode: String? = null,
        limit: Int = 10
    ): LocationSearchResponse

    /**
     * Get list of all countries
     */
    suspend fun getCountries(): CountriesResponse

    /**
     * Update user's location (city, country, coordinates)
     */
    suspend fun updateUserLocation(location: LocationResultData): UpdateLocationResult

    /**
     * Get current location from .env
     */
    suspend fun getCurrentLocation(): CurrentLocationData

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

    // ===== Environment API =====

    /**
     * Get context enrichment cache data from adapters
     */
    suspend fun getContextEnrichment(): ContextEnrichmentResponse

    /**
     * Query environment graph nodes (items in ENVIRONMENT scope)
     */
    suspend fun queryEnvironmentItems(): List<EnvironmentGraphNodeData>

    /**
     * Create an environment item
     */
    suspend fun createEnvironmentItem(
        name: String,
        category: String,
        quantity: Int,
        condition: String,
        notes: String?
    ): EnvironmentGraphNodeData

    /**
     * Delete an environment item by ID
     */
    suspend fun deleteEnvironmentItem(nodeId: String): Boolean

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
    val isRunning: Boolean,
    val servicesRegistered: List<String> = emptyList(),
    val needsReauth: Boolean = false,
    val reauthReason: String? = null,
    val hasAuthStep: Boolean = false,
    val authStepId: String? = null
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

// ===== Environment API Data Models =====

/**
 * Context enrichment response from /v1/system/adapters/context-enrichment
 */
data class ContextEnrichmentResponse(
    val entries: Map<String, Any>,
    val stats: EnrichmentCacheStatsData
)

/**
 * User location information from setup
 */
data class LocationInfoData(
    val location: String?,
    val latitude: Double?,
    val longitude: Double?,
    val timezone: String?,
    val country: String?,
    val region: String?,
    val city: String?,
    val iso6709: String?,
    val hasCoordinates: Boolean
)

/**
 * Environment graph node (persistent ENVIRONMENT scope)
 */
data class EnvironmentGraphNodeData(
    val id: String,
    val type: String,
    val attributes: Map<String, Any>,
    val createdAt: String?,
    val communityShared: Boolean
) {
    // Helper properties for item display
    val name: String get() = attributes["name"]?.toString() ?: id
    val category: String get() = attributes["category"]?.toString() ?: "have"
    val quantity: Int get() = (attributes["quantity"] as? Number)?.toInt() ?: 1
    val condition: String get() = attributes["condition"]?.toString() ?: "good"
    val notes: String? get() = attributes["notes"]?.toString()
}

/**
 * Item categories for environment items
 */
enum class ItemCategory(val displayName: String) {
    WANT("Want"),
    NEED("Need"),
    HAVE("Have"),
    CAN_BORROW("Can Borrow"),
    CAN_BARTER("Can Barter")
}

/**
 * Item conditions
 */
enum class ItemCondition(val displayName: String) {
    NEW("New"),
    GOOD("Good"),
    FAIR("Fair"),
    POOR("Poor"),
    BROKEN("Broken")
}

/**
 * Context enrichment cache statistics
 */
data class EnrichmentCacheStatsData(
    val entries: Int,
    val hits: Int,
    val misses: Int,
    val hitRatePct: Double,
    val startupPopulated: Boolean
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

// ===== Location Search API Data Models =====

/**
 * A single location search result
 */
data class LocationResultData(
    val city: String,
    val region: String?,
    val country: String,
    val countryCode: String,
    val latitude: Double,
    val longitude: Double,
    val population: Int,
    val timezone: String?,
    val displayName: String
)

/**
 * Response from location search endpoint
 */
data class LocationSearchResponse(
    val results: List<LocationResultData>,
    val query: String,
    val count: Int
)

/**
 * Country information
 */
data class CountryInfoData(
    val code: String,
    val name: String,
    val currencyCode: String?,
    val currencyName: String?
)

/**
 * Response from countries list endpoint
 */
data class CountriesResponse(
    val countries: List<CountryInfoData>,
    val count: Int
)

/**
 * Result from updating user location
 */
data class UpdateLocationResult(
    val success: Boolean,
    val message: String,
    val locationDisplay: String
)

/**
 * Current location data from backend (.env)
 */
data class CurrentLocationData(
    val configured: Boolean,
    val city: String? = null,
    val region: String? = null,
    val country: String? = null,
    val latitude: Double? = null,
    val longitude: Double? = null,
    val timezone: String? = null,
    val displayName: String? = null
)
