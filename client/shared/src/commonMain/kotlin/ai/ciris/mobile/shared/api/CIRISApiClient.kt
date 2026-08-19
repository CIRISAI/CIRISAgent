package ai.ciris.mobile.shared.api

import ai.ciris.mobile.shared.models.federation.FederationConsentScopes

import ai.ciris.mobile.shared.models.*
import ai.ciris.mobile.shared.models.safety.AgeBand
import ai.ciris.mobile.shared.models.safety.AgeStatusResponse
import ai.ciris.mobile.shared.models.safety.AssuranceLevel
import ai.ciris.mobile.shared.models.safety.ModerationDuty
import ai.ciris.mobile.shared.models.safety.ModerationPayload
import ai.ciris.mobile.shared.models.safety.ModerationRequest
import ai.ciris.mobile.shared.models.safety.ModerationResponse
import ai.ciris.mobile.shared.models.safety.NamedModeratorResponse
import ai.ciris.mobile.shared.models.safety.SafetyStatusResponse
import ai.ciris.mobile.shared.models.safety.SetAgeRequest
import ai.ciris.mobile.shared.models.safety.SetAgeResponse
import ai.ciris.mobile.shared.models.safety.WatchlistClass
import ai.ciris.mobile.shared.models.safety.WatchlistListResponse
import ai.ciris.mobile.shared.models.safety.WatchlistMode
import ai.ciris.mobile.shared.models.safety.WatchlistRequest
import ai.ciris.mobile.shared.models.safety.WatchlistResponse
import ai.ciris.mobile.shared.models.federation.EdgePeerReachability
import ai.ciris.mobile.shared.models.federation.EdgeReachabilityEntry
import ai.ciris.mobile.shared.models.federation.FederationContentRequest
import ai.ciris.mobile.shared.models.federation.FederationContentResponse
import ai.ciris.mobile.shared.models.federation.FederationPeerAppearanceUpdateRequest
import ai.ciris.mobile.shared.models.federation.FederationPeerTrustUpdateRequest
import ai.ciris.mobile.shared.models.federation.FederationIdentity
import ai.ciris.mobile.shared.models.federation.FederationIdentityResponse
import ai.ciris.mobile.shared.models.federation.FederationMetricsResponse
import ai.ciris.mobile.shared.models.federation.MintIdentityRequest
import ai.ciris.mobile.shared.models.federation.MintedIdentity
import ai.ciris.mobile.shared.models.federation.OwnedNodesDto
import ai.ciris.mobile.shared.models.federation.FederationPeerDetailResponse
import ai.ciris.mobile.shared.models.federation.FederationPeerListResponse
import ai.ciris.mobile.shared.models.federation.FederationPeerSASResponse
import ai.ciris.mobile.shared.models.federation.LocalPeerState
import ai.ciris.mobile.shared.models.federation.NodeCodeAddRequest
import ai.ciris.mobile.shared.models.federation.NodeCodeAddResponse
import ai.ciris.mobile.shared.models.federation.NodeCodeShareResponse
import ai.ciris.mobile.shared.models.federation.PeerAppearance
import ai.ciris.mobile.shared.models.federation.PeerTrustState
import ai.ciris.mobile.shared.models.federation.PeeringRequest
import ai.ciris.mobile.shared.models.federation.PeeringResponse
import ai.ciris.mobile.shared.models.federation.SelfLoginRequest
import ai.ciris.mobile.shared.models.federation.SelfLoginResponse
import ai.ciris.mobile.shared.models.federation.ClaimRemoteRequest
import ai.ciris.mobile.shared.models.federation.ClaimRemoteResponse
import ai.ciris.mobile.shared.models.federation.SignedKeyRecord
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.viewmodels.AgentTemplateInfo
import ai.ciris.mobile.shared.viewmodels.CheckDetail
import ai.ciris.mobile.shared.viewmodels.ConfigItemData
import ai.ciris.mobile.shared.viewmodels.DiscoveredLlmServer
import ai.ciris.mobile.shared.viewmodels.LlmValidationResult
import ai.ciris.mobile.shared.viewmodels.StartLocalServerResult
import ai.ciris.mobile.shared.viewmodels.ModelInfo
import ai.ciris.mobile.shared.viewmodels.SetupCompletionResult
import ai.ciris.mobile.shared.viewmodels.StateTransitionResult
import ai.ciris.mobile.shared.viewmodels.VerifyStatusResponse
import ai.ciris.api.apis.*
import ai.ciris.api.models.DocumentPayload
import ai.ciris.api.models.ImagePayload
import ai.ciris.api.models.InteractRequest as SdkInteractRequest
import ai.ciris.api.models.LoginRequest as SdkLoginRequest
import ai.ciris.api.models.SetupCompleteRequest as SdkSetupCompleteRequest
import ai.ciris.api.models.ShutdownRequest as SdkShutdownRequest
import ai.ciris.api.models.NativeTokenRequest as SdkNativeTokenRequest
import ai.ciris.api.models.StateTransitionRequest as SdkStateTransitionRequest
import ai.ciris.api.models.ConfigUpdate as SdkConfigUpdate
import ai.ciris.api.models.ConsentRequest as SdkConsentRequest
import ai.ciris.api.models.ConfigValue
import ai.ciris.api.models.SuccessResponseDictStrStr
import ai.ciris.api.models.AdapterActionRequest
import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.plugins.*
import io.ktor.client.plugins.contentnegotiation.*
import io.ktor.client.plugins.logging.*
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import io.ktor.serialization.kotlinx.json.*
import kotlinx.datetime.Instant
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.longOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.double
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.put

/**
 * Result of loading an adapter directly.
 */
data class AdapterLoadResult(
    val success: Boolean,
    val adapterId: String?,
    val message: String?
)

/**
 * Result of a CC 4.5.13 reverse-quorum moderation PROPOSAL (the
 * open-labeling / report→`scores` path — anyone MAY propose).
 *
 * Both fields are best-effort: the server route is not yet implemented
 * (see [CIRISApiClient.proposeModeration]) so [contributionId] /
 * [windowClosesAt] may be null even on a 2xx. The 48-hour window is the
 * constitutional default — the UI states it regardless of whether the
 * server echoes a concrete close time.
 */
data class ModerationProposalResult(
    val contributionId: String? = null,
    val windowClosesAt: String? = null,
)

/**
 * LLM configuration data for display in settings
 */
data class LlmConfigData(
    val provider: String,
    val baseUrl: String?,
    val model: String,
    val apiKeySet: Boolean,
    val isCirisProxy: Boolean,
    val backupBaseUrl: String?,
    val backupModel: String?,
    val backupApiKeySet: Boolean
)

/**
 * Result of a wallet USDC transfer.
 */
data class WalletTransferResult(
    val success: Boolean,
    val transactionId: String? = null,
    val txHash: String? = null,
    val amount: String,
    val currency: String,
    val recipient: String,
    val error: String? = null
)

/**
 * Result of EIP-55 address validation.
 */
data class AddressValidationResult(
    val valid: Boolean,
    val checksumValid: Boolean,
    val computedChecksum: String? = null,
    val isZeroAddress: Boolean = false,
    val error: String? = null,
    val warnings: List<String> = emptyList()
)

/**
 * Result of duplicate transaction check.
 */
data class DuplicateCheckResult(
    val isDuplicate: Boolean,
    val lastTxSecondsAgo: Int? = null,
    val windowSeconds: Int = 300,
    val warning: String? = null
)

/**
 * Extract the actual display value from a ConfigValue union type.
 * ConfigValue has multiple nullable fields (stringValue, intValue, etc.)
 * but only one will be non-null at a time.
 */
private fun ConfigValue.toDisplayString(): String {
    // Use local variables to enable smart cast (cross-module properties can't smart cast)
    val strVal = stringValue
    val intVal = intValue
    val floatVal = floatValue
    val boolVal = boolValue
    val listVal = listValue
    val dictVal = dictValue

    return when {
        strVal != null -> strVal
        intVal != null -> intVal.toString()
        floatVal != null -> floatVal.toString()
        boolVal != null -> boolVal.toString()
        listVal != null -> listVal.joinToString(", ") { it.toString() }
        dictVal != null -> dictVal.entries.joinToString(", ") { "${it.key}: ${it.value}" }
        else -> "(empty)"
    }
}

/**
 * Unified API client for CIRIS backend using the generated OpenAPI SDK.
 * This client wraps the generated API classes and provides a clean interface.
 *
 * All methods include comprehensive error logging for debugging.
 */
class CIRISApiClient(
    // Default to the local ciris-server node read API (node base :4242 → API :4243).
    baseUrl: String = "http://127.0.0.1:4243",
    private var accessToken: String? = null
) : CIRISApiClientProtocol {

    /**
     * Current effective base URL - can be updated dynamically.
     * Note: Some generated API methods may still use the original URL until
     * a new CIRISApiClient instance is created.
     */
    var baseUrl: String = baseUrl
        private set

    // ─── The node-vs-agent gate (see CIRISApiClientProtocol.setClientMode) ────
    // Held here so EVERY poller that shares this client benefits from one gate.
    // null = not probed yet (treated as agent — existing behavior unchanged).
    private var clientMode: ai.ciris.mobile.shared.models.ClientMode? = null

    override fun setClientMode(mode: ai.ciris.mobile.shared.models.ClientMode) {
        clientMode = mode
        logInfo("setClientMode", "API client gate set to $mode")
    }

    override fun isNodeMode(): Boolean = clientMode?.isNode == true

    /**
     * Short-circuit guard for AGENT-only cognitive endpoints. Returns true (and
     * logs a single quiet debug line) when the client is running against a bare
     * NODE that does not serve [method]'s endpoint — the caller then returns an
     * empty/default value instead of issuing the HTTP call that would 404/405.
     */
    private fun nodeSkip(method: String): Boolean {
        if (clientMode?.isNode == true) {
            logDebug(method, "[GATE] NODE mode — skipping agent-only endpoint")
            return true
        }
        return false
    }

    /**
     * Update the base URL for API calls.
     * This updates the URL used for direct HTTP calls and recreates all SDK API instances.
     */
    fun updateBaseUrl(newUrl: String) {
        val method = "updateBaseUrl"
        logInfo(method, "Updating baseUrl from $baseUrl to $newUrl")
        baseUrl = newUrl
        // Recreate all SDK API instances with the new URL
        recreateApiInstances()
    }

    /**
     * Recreate all SDK API instances with the current baseUrl.
     * Called after updateBaseUrl() to ensure all API objects use the new URL.
     */
    private fun recreateApiInstances() {
        val method = "recreateApiInstances"
        logInfo(method, "Recreating SDK API instances with baseUrl=$baseUrl")

        agentApi = AgentApi(
            baseUrl = baseUrl,
            httpClientEngine = null,
            httpClientConfig = httpClientConfig,
            jsonSerializer = jsonConfig
        )
        authApi = AuthenticationApi(
            baseUrl = baseUrl,
            httpClientEngine = null,
            httpClientConfig = httpClientConfig,
            jsonSerializer = jsonConfig
        )
        setupApi = SetupApi(
            baseUrl = baseUrl,
            httpClientEngine = null,
            httpClientConfig = httpClientConfig,
            jsonSerializer = jsonConfig
        )
        systemApi = SystemApi(
            baseUrl = baseUrl,
            httpClientEngine = null,
            httpClientConfig = httpClientConfig,
            jsonSerializer = jsonConfig
        )
        telemetryApi = TelemetryApi(
            baseUrl = baseUrl,
            httpClientEngine = null,
            httpClientConfig = httpClientConfig,
            jsonSerializer = jsonConfig
        )
        billingApi = BillingApi(
            baseUrl = baseUrl,
            httpClientEngine = null,
            httpClientConfig = httpClientConfig,
            jsonSerializer = jsonConfig
        )
        wiseAuthorityApi = WiseAuthorityApi(
            baseUrl = baseUrl,
            httpClientEngine = null,
            httpClientConfig = httpClientConfig,
            jsonSerializer = jsonConfig
        )
        configApi = ConfigApi(
            baseUrl = baseUrl,
            httpClientEngine = null,
            httpClientConfig = httpClientConfig,
            jsonSerializer = jsonConfig
        )
        consentApi = ConsentApi(
            baseUrl = baseUrl,
            httpClientEngine = null,
            httpClientConfig = httpClientConfig,
            jsonSerializer = jsonConfig
        )
        auditApi = AuditApi(
            baseUrl = baseUrl,
            httpClientEngine = null,
            httpClientConfig = httpClientConfig,
            jsonSerializer = jsonConfig
        )
        memoryApi = MemoryApi(
            baseUrl = baseUrl,
            httpClientEngine = null,
            httpClientConfig = httpClientConfig,
            jsonSerializer = jsonConfig
        )
        usersApi = UsersApi(
            baseUrl = baseUrl,
            httpClientEngine = null,
            httpClientConfig = httpClientConfig,
            jsonSerializer = jsonConfig
        )
        ticketsApi = TicketsApi(
            baseUrl = baseUrl,
            httpClientEngine = null,
            httpClientConfig = httpClientConfig,
            jsonSerializer = jsonConfig
        )

        logInfo(method, "All SDK API instances recreated successfully")
    }

    /**
     * Get current access token (for SSE client)
     */
    fun getAccessToken(): String? = accessToken

    companion object {
        private const val TAG = "CIRISApiClient"

        /**
         * Base URL of THIS device's **local node** — the ciris-server the app
         * runs in-process (ServerManager.serverUrl). All federation crypto
         * (JCS canonicalization + hybrid signing) happens INSIDE that node's
         * substrate; the app only drives it over plain localhost HTTP. The app
         * holds NO federation keys and signs NO federation artifacts in Kotlin.
         */
        const val LOCAL_NODE_URL = "http://127.0.0.1:4243"

        // Mask token for logging (show first 8 and last 4 chars)
        private fun maskToken(token: String?): String {
            if (token == null) return "null"
            if (token.length <= 16) return "***"
            return "${token.take(8)}...${token.takeLast(4)}"
        }
    }

    private fun logDebug(method: String, message: String) {
        PlatformLogger.d(TAG, "[$method] $message")
    }

    private fun logInfo(method: String, message: String) {
        PlatformLogger.i(TAG, "[$method] $message")
    }

    private fun logWarn(method: String, message: String) {
        PlatformLogger.w(TAG, "[$method] $message")
    }

    private fun logError(method: String, message: String) {
        PlatformLogger.e(TAG, "[$method] $message")
    }

    /**
     * Parse the checks map from the verify-status response.
     */
    private fun parseChecks(checksObj: JsonObject?): Map<String, CheckDetail>? {
        if (checksObj == null) return null
        return checksObj.mapValues { (_, value) ->
            val obj = value as? JsonObject
            CheckDetail(
                ok = (obj?.get("ok") as? JsonPrimitive)?.content?.toBoolean() ?: false,
                label = (obj?.get("label") as? JsonPrimitive)?.content ?: "",
                level = (obj?.get("level") as? JsonPrimitive)?.content?.toIntOrNull() ?: 0,
                filesChecked = (obj?.get("files_checked") as? JsonPrimitive)?.content?.toIntOrNull(),
                filesPassed = (obj?.get("files_passed") as? JsonPrimitive)?.content?.toIntOrNull(),
                filesFailed = (obj?.get("files_failed") as? JsonPrimitive)?.content?.toIntOrNull(),
                failureReason = (obj?.get("failure_reason") as? JsonPrimitive)?.content
            )
        }
    }

    private fun logException(method: String, e: Exception, context: String = "") {
        val contextStr = if (context.isNotEmpty()) " | Context: $context" else ""
        PlatformLogger.e(TAG, "[$method] Exception: ${e::class.simpleName}: ${e.message}$contextStr", e)
    }

    private val jsonConfig = Json {
        ignoreUnknownKeys = true
        isLenient = true
        prettyPrint = true
    }

    private val httpClientConfig: (HttpClientConfig<*>) -> Unit = {
        it.install(ContentNegotiation) {
            json(jsonConfig)
        }
        it.install(Logging) {
            logger = Logger.DEFAULT
            level = LogLevel.NONE // Use PlatformLogger for targeted logging instead
        }
        it.install(HttpTimeout) {
            requestTimeoutMillis = 30000
            connectTimeoutMillis = 10000
            socketTimeoutMillis = 30000
        }
    }

    // Generated API instances (var to allow recreation when baseUrl changes)
    private var agentApi = AgentApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private var authApi = AuthenticationApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private var setupApi = SetupApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private var systemApi = SystemApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private var telemetryApi = TelemetryApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private var billingApi = BillingApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private var wiseAuthorityApi = WiseAuthorityApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private var configApi = ConfigApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private var consentApi = ConsentApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private var auditApi = AuditApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private var memoryApi = MemoryApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private var usersApi = UsersApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private var ticketsApi = TicketsApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    init {
        logInfo("init", "CIRISApiClient initialized with baseUrl=$baseUrl")
    }

    override fun setAccessToken(token: String) {
        val method = "setAccessToken"
        logInfo(method, "Setting access token: ${maskToken(token)}, length=${token.length}")
        accessToken = token
        // Set bearer token on all API instances
        try {
            agentApi.setBearerToken(token)
            authApi.setBearerToken(token)
            setupApi.setBearerToken(token)
            systemApi.setBearerToken(token)
            telemetryApi.setBearerToken(token)
            billingApi.setBearerToken(token)
            wiseAuthorityApi.setBearerToken(token)
            configApi.setBearerToken(token)
            consentApi.setBearerToken(token)
            auditApi.setBearerToken(token)
            memoryApi.setBearerToken(token)
            usersApi.setBearerToken(token)
            ticketsApi.setBearerToken(token)
            logInfo(method, "Bearer token set on all API instances (13 APIs)")
        } catch (e: Exception) {
            logException(method, e, "Failed to set bearer token on API instances")
        }
    }

    /**
     * Clear the in-memory access token. Call during logout to stop
     * background polling from using the revoked token.
     */
    fun clearAccessToken() {
        val method = "clearAccessToken"
        logInfo(method, "Clearing in-memory access token")
        accessToken = null
    }

    /**
     * Log current token state for debugging auth issues.
     * Call this when troubleshooting 401 errors.
     */
    override fun logTokenState() {
        val method = "logTokenState"
        logInfo(method, "=== TOKEN STATE DEBUG ===")
        logInfo(method, "accessToken present: ${accessToken != null}")
        logInfo(method, "accessToken preview: ${maskToken(accessToken)}")
        logInfo(method, "accessToken length: ${accessToken?.length ?: 0}")
        logInfo(method, "authHeader() returns: ${if (authHeader() != null) "Bearer <token>" else "null"}")
        logInfo(method, "=========================")
    }

    private fun authHeader(): String? {
        val header = accessToken?.let { "Bearer $it" }
        logDebug("authHeader", "Auth header present: ${header != null}, token: ${maskToken(accessToken)}")
        return header
    }

    // Chat / Interact
    override suspend fun sendMessage(
        message: String,
        channelId: String,
        images: List<ImagePayload>?,
        documents: List<DocumentPayload>?
    ): InteractResponse {
        val method = "sendMessage"
        logInfo(method, "Sending message: '${message.take(50)}...' to channel=$channelId, images=${images?.size ?: 0}, docs=${documents?.size ?: 0}")
        logDebug(method, "Auth token present: ${accessToken != null}, token: ${maskToken(accessToken)}")

        return try {
            val request = SdkInteractRequest(
                message = message,
                images = images,
                documents = documents
            )
            logDebug(method, "Created SdkInteractRequest with ${images?.size ?: 0} images, ${documents?.size ?: 0} documents")

            val authHeaderValue = authHeader()
            logDebug(method, "Calling agentApi.interactV1AgentInteractPost with auth=${authHeaderValue != null}")

            val response = agentApi.interactV1AgentInteractPost(request, authHeaderValue)
            logDebug(method, "Response received: status=${response.status}, success=${response.success}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            logDebug(method, "Response body parsed successfully")

            val data = body.`data` ?: throw RuntimeException("API returned null data")
            logInfo(method, "Message sent successfully: messageId=${data.messageId}")

            InteractResponse(
                response = data.response,
                message_id = data.messageId,
                reasoning = null
            )
        } catch (e: Exception) {
            logException(method, e, "message='${message.take(30)}...', channelId=$channelId, hasToken=${accessToken != null}")
            throw e
        }
    }

    override suspend fun getMessages(limit: Int): List<ChatMessage> {
        val method = "getMessages"
        // AGENT-only: GET /v1/agent/history is 404 on a bare node (no brain).
        if (nodeSkip(method)) return emptyList()
        val authHeaderValue = authHeader()
        logDebug(method, "Fetching messages: limit=$limit, hasAuthHeader=${authHeaderValue != null}, " +
                "tokenPresent=${accessToken != null}, tokenPreview=${maskToken(accessToken)}")

        return try {
            val response = agentApi.getHistoryV1AgentHistoryGet(limit, null, authHeaderValue)
            logDebug(method, "Response: status=${response.status}")

            // Check for auth errors before parsing body (OpenAPI client may not declare 401)
            val statusCode = response.response.status.value
            if (statusCode == 401 || statusCode == 403) {
                throw RuntimeException("API error: HTTP $statusCode ${response.response.status.description}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")
            val messages = data.messages.map { msg ->
                ChatMessage(
                    id = msg.id,
                    text = msg.content,
                    type = when (msg.messageType) {
                        ai.ciris.api.models.ConversationMessage.MessageType.USER -> MessageType.USER
                        ai.ciris.api.models.ConversationMessage.MessageType.AGENT -> MessageType.AGENT
                        ai.ciris.api.models.ConversationMessage.MessageType.SYSTEM -> MessageType.SYSTEM
                        ai.ciris.api.models.ConversationMessage.MessageType.ERROR -> MessageType.ERROR
                        null -> if (msg.isAgent) MessageType.AGENT else MessageType.USER
                    },
                    timestamp = msg.timestamp,
                    reasoning = null
                )
            }
            logDebug(method, "Fetched ${messages.size} messages")
            messages
        } catch (e: Exception) {
            val errorMsg = e.message ?: ""
            val is401 = errorMsg.contains("401") || errorMsg.contains("Unauthorized", ignoreCase = true)
            logException(method, e, "limit=$limit, is401=$is401, tokenPresent=${accessToken != null}, tokenPreview=${maskToken(accessToken)}")
            throw e
        }
    }

    /**
     * Request the Python server to shut down via /v1/system/local-shutdown.
     * Used after factory reset on desktop to force a clean server restart.
     * The connection will likely fail/timeout since the server is dying — that's expected.
     */
    suspend fun postLocalShutdown() {
        val method = "postLocalShutdown"
        logInfo(method, "Sending local-shutdown request to $baseUrl/v1/system/local-shutdown")
        val client = io.ktor.client.HttpClient {
            install(io.ktor.client.plugins.contentnegotiation.ContentNegotiation) { json(jsonConfig) }
            install(io.ktor.client.plugins.HttpTimeout) {
                requestTimeoutMillis = 3000
                connectTimeoutMillis = 2000
            }
        }
        try {
            client.post("$baseUrl/v1/system/local-shutdown") {
                authHeader()?.let { header("Authorization", it) }
            }
        } catch (e: Exception) {
            // Expected — server dies before responding
            logInfo(method, "Server shutdown (expected error): ${e.message}")
        } finally {
            client.close()
        }
    }

    // ─── Agent Mode (global) ─────────────────────────────────────────────────
    // GET/PUT /v1/system/agent-mode — drives federation transport posture.
    // Hand-rolled (not via SDK) because the route is newer than the SDK regen
    // cadence and uses an envelope distinct from the SuccessResponse default.

    /**
     * Fetch the current global [AgentMode] plus the disk facts that gate
     * SERVER eligibility.
     */
    suspend fun getAgentMode(): AgentModeStatus {
        val method = "getAgentMode"
        logDebug(method, "Fetching agent-mode from $baseUrl/v1/system/agent-mode")
        val client = io.ktor.client.HttpClient {
            install(io.ktor.client.plugins.contentnegotiation.ContentNegotiation) { json(jsonConfig) }
            install(io.ktor.client.plugins.HttpTimeout) {
                requestTimeoutMillis = 10000
                connectTimeoutMillis = 5000
            }
        }
        return try {
            val response = client.get("$baseUrl/v1/system/agent-mode") {
                authHeader()?.let { header("Authorization", it) }
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("Agent-mode fetch failed: ${response.status}")
            }
            parseAgentModeStatus(response.bodyAsText())
        } catch (e: Exception) {
            logException(method, e, "url=$baseUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Attempt to switch the global [AgentMode]. Handles the 400
     * INSUFFICIENT_DISK case as a typed [AgentModeChangeResult.InsufficientDisk]
     * so the UI can render an actionable inline message.
     */
    suspend fun setAgentMode(mode: AgentMode): AgentModeChangeResult {
        val method = "setAgentMode"
        logInfo(method, "Setting agent-mode → ${mode.wire}")
        val client = io.ktor.client.HttpClient {
            install(io.ktor.client.plugins.contentnegotiation.ContentNegotiation) { json(jsonConfig) }
            install(io.ktor.client.plugins.HttpTimeout) {
                requestTimeoutMillis = 15000
                connectTimeoutMillis = 5000
            }
        }
        return try {
            val response = client.put("$baseUrl/v1/system/agent-mode") {
                authHeader()?.let { header("Authorization", it) }
                contentType(ContentType.Application.Json)
                setBody(buildJsonObject { put("mode", mode.wire) })
            }
            val body = response.bodyAsText()
            when {
                response.status.isSuccess() -> {
                    val root = Json.parseToJsonElement(body).jsonObject
                    val status = parseAgentModeStatus(body)
                    val requiresRestart = root["requires_restart"]?.jsonPrimitive?.booleanOrNull ?: true
                    AgentModeChangeResult.Success(status, requiresRestart)
                }
                response.status.value == 400 -> {
                    val root = Json.parseToJsonElement(body).jsonObject
                    val error = root["error"]?.jsonPrimitive?.contentOrNull
                    if (error == "INSUFFICIENT_DISK") {
                        val available = root["available_bytes"]?.jsonPrimitive?.longOrNull ?: 0L
                        val required = root["required_bytes"]?.jsonPrimitive?.longOrNull ?: 0L
                        AgentModeChangeResult.InsufficientDisk(available, required)
                    } else {
                        AgentModeChangeResult.Failure("Bad request: ${error ?: body.take(200)}")
                    }
                }
                else -> AgentModeChangeResult.Failure("HTTP ${response.status.value}: ${body.take(200)}")
            }
        } catch (e: Exception) {
            logException(method, e, "mode=${mode.wire}")
            AgentModeChangeResult.Failure(e.message ?: e::class.simpleName ?: "unknown error")
        } finally {
            client.close()
        }
    }

    /**
     * Decode an [AgentModeStatus] from a `{"data": {...}}`-wrapped response.
     * Used by both GET (envelope = SuccessResponse) and PUT (envelope adds
     * `requires_restart`). Tolerates an unwrapped `{...}` body for resilience.
     */
    private fun parseAgentModeStatus(rawBody: String): AgentModeStatus {
        val root = Json.parseToJsonElement(rawBody).jsonObject
        val data = root["data"]?.jsonObject ?: root
        val modeStr = data["mode"]?.jsonPrimitive?.contentOrNull
        val available = data["available_disk_bytes"]?.jsonPrimitive?.longOrNull ?: 0L
        val minimum = data["server_minimum_disk_bytes"]?.jsonPrimitive?.longOrNull ?: 0L
        val eligible = data["server_eligible"]?.jsonPrimitive?.booleanOrNull ?: false
        val dataDir = data["data_dir"]?.jsonPrimitive?.contentOrNull ?: ""
        return AgentModeStatus(
            mode = AgentMode.fromWire(modeStr),
            availableDiskBytes = available,
            serverMinimumDiskBytes = minimum,
            serverEligible = eligible,
            dataDir = dataDir,
        )
    }

    // ─── Federation surface (/v1/federation/*) ───────────────────────────────
    //
    // Served NATIVELY by the local ciris-server node (:4243) — the Python
    // duplicate routes on the agent (:8080) were deleted in the 2.9.7 DRY
    // purge. The node currently exposes: announce, node-code, peering, peers,
    // peers/{key_id}, self-key-record, conformance, adopt-scrubbed.
    //
    // SEVEN capabilities have NO node route yet (CIRISServer ask filed):
    //   identity, peers/{key_id}/sas, peers/{key_id}/trust,
    //   peers/{key_id}/appearance, metrics, content/{content_id},
    //   events/{channel} (SSE).
    // Their client methods below are DISABLED (throw immediately) until
    // CIRISServer exposes them on :4243; every call-site already handles the
    // thrown error as a degraded/"unknown" UI state.

    /**
     * Short-lived Ktor client for one direct-HTTP request. Mirrors the
     * pattern used by [getAgentMode] / [getSystemStatus] — created per-call
     * so a stuck request never poisons unrelated traffic.
     */
    // Default timeout suits quick federation GETs. Touch-gated ceremony calls
    // (provision-holder / family cosign) pass a LONG timeout: slot 9c with touch
    // policy ALWAYS needs a physical touch per Ed25519 sign, and provisioning does
    // three (USB ML-DSA wrap-challenge, holder record, custody attestation) — each
    // a session-open + PIN + human-touch-wait + sign round-trip. 30s is far too
    // short for three human touches; the request (and idle socket) must wait.
    private fun federationHttpClient(
        requestTimeoutMillis: Long = 30_000,
    ): io.ktor.client.HttpClient =
        io.ktor.client.HttpClient {
            install(io.ktor.client.plugins.contentnegotiation.ContentNegotiation) { json(jsonConfig) }
            install(io.ktor.client.plugins.HttpTimeout) {
                this.requestTimeoutMillis = requestTimeoutMillis
                connectTimeoutMillis = 10_000
                socketTimeoutMillis = requestTimeoutMillis
            }
        }

    /** Timeout for touch-gated YubiKey ceremony calls (3 touches × human latency). */
    private val ceremonyTimeoutMillis: Long = 180_000

    /**
     * Decode the ``{"data": <T>}`` envelope used by every federation
     * route. Tolerates an unwrapped ``<T>`` for resilience the same way
     * [parseAgentModeStatus] does.
     */
    private inline fun <reified T> decodeFederationEnvelope(
        rawBody: String,
        deserializer: kotlinx.serialization.KSerializer<T>,
    ): T {
        val root = Json.parseToJsonElement(rawBody).jsonObject
        val dataElement = root["data"] ?: root
        return jsonConfig.decodeFromString(deserializer, dataElement.toString())
    }

    // ─── GRADED ENFORCEMENT LADDER (/v1/admin/*) — CIRISServer #346/#361/#375 ───
    //
    // The owner's actual recourse against an admitted-but-hostile peer, in
    // src/admin_ops.rs. Every mutating call is preview → commit-with-hash: the
    // hash covers the normalized selection AND the exact row-id set it returned,
    // so what was previewed is what executes and anything else is refused with
    // `preview_hash_mismatch`. `{delegation_id, reason}` are mandatory in every
    // tombstone; the route refuses without them.
    //
    // A REFUSAL IS RETURNED, NOT THROWN. Its `{id, text}` message is the whole
    // point of these routes — "this reaches X and does not reach Y" — and a
    // client that turned a 403 into a bare exception would throw away the
    // sentence the operator needs. Only transport/parse faults throw.

    /** Parse the shared `{refused, refusal, message:{id,text}, …}` refusal body. */
    private fun parseAdminRefusal(raw: String, status: HttpStatusCode): AdminRefusal =
        try {
            jsonConfig.decodeFromString(AdminRefusal.serializer(), raw)
        } catch (e: Exception) {
            // A body this module did not author (a proxy's 502 page, an empty
            // 500). Named as its own refusal token rather than mislabelled as
            // one of the ladder's — an unparsed refusal is a distinct fact.
            //
            // The synthesized text carries NO status code: the bundle entry it
            // resolves to could not carry one, and a fallback that says more
            // than its translation would make the sentence change with the
            // reader's language. The status goes to the log instead.
            logWarn("parseAdminRefusal", "unparsable refusal body (${status.value}): ${e.message}")
            AdminRefusal(
                refusal = "unparsable_response",
                message = AdminMessage(
                    id = "moderation.ladder.unparsable_response",
                    text = "The node answered with a body this app could not read.",
                ),
            )
        }

    /**
     * **The blast-radius check** — `POST {nodeUrl}/v1/admin/preview`.
     *
     * Read-only. Returns the exact row set a commit would act on, the per-key
     * counts, whether the page was truncated, where the time window was actually
     * enforced, and the SELECTION HASH the commit must present.
     */
    suspend fun adminPreview(
        selection: AdminSelectionDto,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): AdminPreviewOutcome {
        val method = "adminPreview"
        logInfo(method, "POST $nodeUrl/v1/admin/preview")
        val client = federationHttpClient()
        return try {
            val bodyText = jsonConfig.encodeToString(AdminSelectionDto.serializer(), selection)
            val response = client.post("$nodeUrl/v1/admin/preview") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyText)
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                AdminPreviewOutcome.Refused(
                    response.status.value,
                    parseAdminRefusal(raw, response.status),
                )
            } else {
                AdminPreviewOutcome.Ok(
                    jsonConfig.decodeFromString(AdminPreviewResponse.serializer(), raw),
                )
            }
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Commit one rung of the ladder — `POST {nodeUrl}{op.route}`.
     *
     * [op] carries the route, so a caller cannot send a tier-4 body down a
     * tier-0 door. [request] must carry the selection that was PREVIEWED
     * together with the hash that preview returned; passing the form's current
     * selection instead is exactly what the hash exists to refuse.
     */
    suspend fun adminLadderCommit(
        op: AdminLadderOp,
        request: AdminLadderCommitRequest,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): AdminOpOutcome {
        val method = "adminLadderCommit"
        logInfo(
            method,
            "POST $nodeUrl${op.route} tier=${op.tier} scope=${op.requiredScope} " +
                "hash=${request.selectionHash.take(12)}…",
        )
        val client = federationHttpClient()
        return try {
            val bodyText = jsonConfig.encodeToString(
                AdminLadderCommitRequest.serializer(),
                request,
            )
            val response = client.post("$nodeUrl${op.route}") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyText)
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                AdminOpOutcome.Refused(
                    response.status.value,
                    parseAdminRefusal(raw, response.status),
                )
            } else {
                AdminOpOutcome.Ok(jsonConfig.decodeFromString(AdminOpResponse.serializer(), raw))
            }
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl, route=${op.route}")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Federation identity card — local agent's signer_key_id, crate
     * version, peer counts, and advertised capabilities.
     *
     * Hits ``GET /v1/federation/identity`` on the LOCAL NODE (:4243) — served natively since ciris-server 0.5.115 (CIRISServer#261/#920).
     */
    suspend fun getFederationIdentity(): FederationIdentity {
        val method = "getFederationIdentity"
        logDebug(method, "GET $LOCAL_NODE_URL/v1/federation/identity")
        val client = federationHttpClient()
        return try {
            val response = client.get("$LOCAL_NODE_URL/v1/federation/identity") {
                authHeader()?.let { header("Authorization", it) }
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("Federation identity fetch failed: ${response.status}")
            }
            decodeFederationEnvelope(response.bodyAsText(), FederationIdentity.serializer())
        } catch (e: Exception) {
            logException(method, e, "url=$LOCAL_NODE_URL")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * List local peers (canonical + organic). Optional filters:
     *  - [canonicalOnly]: restrict to canonical (rock-solid) peers.
     *  - [trust]: restrict to one [PeerTrustState] vocabulary value.
     *
     * Hits ``GET /v1/federation/peers`` on the LOCAL NODE (:4243) —
     * the ciris-server substrate serves the peer list natively. The
     * node ignores ``canonical_only``/``trust`` query params, so both
     * filters are applied client-side after decode.
     */
    suspend fun listFederationPeers(
        canonicalOnly: Boolean? = null,
        trust: PeerTrustState? = null,
    ): FederationPeerListResponse {
        val method = "listFederationPeers"
        logDebug(method, "GET $LOCAL_NODE_URL/v1/federation/peers canonicalOnly=$canonicalOnly trust=${trust?.wire}")
        val client = federationHttpClient()
        return try {
            val response = client.get("$LOCAL_NODE_URL/v1/federation/peers") {
                authHeader()?.let { header("Authorization", it) }
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("Federation peer list failed: ${response.status}")
            }
            val decoded = decodeFederationEnvelope(response.bodyAsText(), FederationPeerListResponse.serializer())
            // Node ignores the filter params — filter locally instead.
            var peers = decoded.peers
            if (canonicalOnly == true) peers = peers.filter { it.canonical }
            if (trust != null) peers = peers.filter { it.trust == trust }
            FederationPeerListResponse(peers = peers, total = peers.size)
        } catch (e: Exception) {
            logException(method, e, "url=$LOCAL_NODE_URL")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Fetch one peer's [LocalPeerState].
     *
     * Hits ``GET /v1/federation/peers/{keyId}`` on the LOCAL NODE
     * (:4243). Surfaces 404 (peer unknown locally) as an exception;
     * the caller decides whether to retry or render a not-found shell.
     *
     * NOTE: the node does not enrich with the Edge per-medium
     * reachability snapshot the brain route used to add, so
     * [FederationPeerDetailResponse.reachability] may be null/empty —
     * the UI already renders that as "unknown".
     */
    suspend fun getFederationPeer(keyId: String): FederationPeerDetailResponse {
        val method = "getFederationPeer"
        logDebug(method, "GET $LOCAL_NODE_URL/v1/federation/peers/$keyId")
        val client = federationHttpClient()
        return try {
            val response = client.get("$LOCAL_NODE_URL/v1/federation/peers/$keyId") {
                authHeader()?.let { header("Authorization", it) }
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("Federation peer fetch failed: ${response.status} for $keyId")
            }
            decodeFederationEnvelope(response.bodyAsText(), FederationPeerDetailResponse.serializer())
        } catch (e: Exception) {
            logException(method, e, "keyId=$keyId")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Fetch the Signal-style SAS (5 words + 6 digits) for verifying a
     * peer's pubkey out-of-band.
     *
     * Hits ``GET /v1/federation/peers/{keyId}/sas`` on the LOCAL NODE (:4243) — served natively since ciris-server 0.5.115 (CIRISServer#261/#920)
     * (GET is byte-identical to Edge PyO3 ``peer_sas``, test-proven upstream).
     */
    suspend fun getFederationPeerSAS(keyId: String): FederationPeerSASResponse {
        val method = "getFederationPeerSAS"
        logDebug(method, "GET $LOCAL_NODE_URL/v1/federation/peers/$keyId/sas")
        val client = federationHttpClient()
        return try {
            val response = client.get("$LOCAL_NODE_URL/v1/federation/peers/$keyId/sas") {
                authHeader()?.let { header("Authorization", it) }
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("Federation peer SAS fetch failed: ${response.status} for $keyId")
            }
            decodeFederationEnvelope(response.bodyAsText(), FederationPeerSASResponse.serializer())
        } catch (e: Exception) {
            logException(method, e, "keyId=$keyId")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Update the [PeerTrustState] on a known peer.
     *
     * Hits ``PUT /v1/federation/peers/{keyId}/trust`` on the LOCAL NODE (:4243) — served natively since ciris-server 0.5.115 (CIRISServer#261/#920)
     * (owner-gated like /v1/config writes; sideband persists as signed
     * config:v1 CEG rows, so it replicates like all config).
     */
    suspend fun setFederationPeerTrust(
        keyId: String,
        trust: PeerTrustState,
    ): LocalPeerState {
        val method = "setFederationPeerTrust"
        logInfo(method, "PUT $LOCAL_NODE_URL/v1/federation/peers/$keyId/trust → ${trust.wire}")
        val client = federationHttpClient()
        return try {
            val response = client.put("$LOCAL_NODE_URL/v1/federation/peers/$keyId/trust") {
                authHeader()?.let { header("Authorization", it) }
                contentType(ContentType.Application.Json)
                setBody(jsonConfig.encodeToString(
                    FederationPeerTrustUpdateRequest.serializer(),
                    FederationPeerTrustUpdateRequest(trust = trust),
                ))
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("Federation peer trust update failed: ${response.status} for $keyId")
            }
            decodeFederationEnvelope(response.bodyAsText(), LocalPeerState.serializer())
        } catch (e: Exception) {
            logException(method, e, "keyId=$keyId, trust=${trust.wire}")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Update the local-user [PeerAppearance] on a known peer.
     *
     * Hits ``PUT /v1/federation/peers/{keyId}/appearance`` on the LOCAL NODE (:4243) — served natively since ciris-server 0.5.115 (CIRISServer#261/#920).
     */
    suspend fun setFederationPeerAppearance(
        keyId: String,
        appearance: PeerAppearance,
    ): LocalPeerState {
        val method = "setFederationPeerAppearance"
        logInfo(method, "PUT $LOCAL_NODE_URL/v1/federation/peers/$keyId/appearance")
        val client = federationHttpClient()
        return try {
            val response = client.put("$LOCAL_NODE_URL/v1/federation/peers/$keyId/appearance") {
                authHeader()?.let { header("Authorization", it) }
                contentType(ContentType.Application.Json)
                setBody(jsonConfig.encodeToString(
                    FederationPeerAppearanceUpdateRequest.serializer(),
                    FederationPeerAppearanceUpdateRequest(appearance = appearance),
                ))
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("Federation peer appearance update failed: ${response.status} for $keyId")
            }
            decodeFederationEnvelope(response.bodyAsText(), LocalPeerState.serializer())
        } catch (e: Exception) {
            logException(method, e, "keyId=$keyId")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Edge metrics snapshot — counters and gauges for envelopes,
     * verify failures, queue depths, transport bytes, and peer
     * reachability ratios.
     *
     * DISABLED: agent-side ``GET /v1/federation/metrics`` was deleted
     * (2.9.7 DRY purge — Edge's ``metrics_snapshot`` owns the capability)
     * and the node (:4243) does not expose it yet. TODO(CIRISServer ask:
     * expose federation metrics on the node) — repoint to
     * [LOCAL_NODE_URL] when it lands. The Interfaces/Queue pollers treat
     * the throw as their existing degraded state.
     */
    suspend fun getFederationMetrics(): FederationMetricsResponse {
        // Node-served since ciris-server 0.5.115 (CIRISServer#261) — PyO3
        // metrics_snapshot key formats; inline_text_subscriber_count is served
        // as verified_feed_subscriber_count (model updated to match).
        val method = "getFederationMetrics"
        logDebug(method, "GET $LOCAL_NODE_URL/v1/federation/metrics")
        val client = federationHttpClient()
        return try {
            val response = client.get("$LOCAL_NODE_URL/v1/federation/metrics") {
                authHeader()?.let { header("Authorization", it) }
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("Federation metrics fetch failed: ${response.status}")
            }
            decodeFederationEnvelope(response.bodyAsText(), FederationMetricsResponse.serializer())
        } catch (e: Exception) {
            logException(method, e, "url=$LOCAL_NODE_URL")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Substrate component versions for the Trust page's fabric section.
     *
     * Hits ``GET /v1/system/fabric``. Returns each in-process cdylib crate's
     * runtime version + the (pending) embedded-version / registry-hash status.
     */
    suspend fun getFabricVersions(): ai.ciris.mobile.shared.models.FabricVersionsResponse {
        val method = "getFabricVersions"
        logDebug(method, "GET /v1/system/fabric")
        val client = io.ktor.client.HttpClient {
            install(io.ktor.client.plugins.contentnegotiation.ContentNegotiation) { json(jsonConfig) }
            install(io.ktor.client.plugins.HttpTimeout) {
                requestTimeoutMillis = 10000
                connectTimeoutMillis = 5000
            }
        }
        return try {
            val response = client.get("$baseUrl/v1/system/fabric") {
                authHeader()?.let { header("Authorization", it) }
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("Fabric versions fetch failed: ${response.status}")
            }
            val root = Json.parseToJsonElement(response.bodyAsText()).jsonObject
            val data = root["data"] ?: throw RuntimeException("Fabric response missing 'data'")
            val decoder = Json { ignoreUnknownKeys = true }
            decoder.decodeFromJsonElement(
                ai.ciris.mobile.shared.models.FabricVersionsResponse.serializer(),
                data,
            )
        } catch (e: Exception) {
            logException(method, e, "url=$baseUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Fetch federation content by SHA-256 [contentId] from [peerKeyId].
     *
     * The backend requires ``peer_key_id`` — there is no global
     * content directory today, the caller must know a candidate
     * holder. [timeoutMs] is per-fetch and clamped server-side to
     * ``[1, 300_000]`` ms; defaults to 5_000 ms here so the typical
     * user-driven case doesn't block the UI for 30s on miss.
     *
     * DISABLED: agent-side ``POST /v1/federation/content/{contentId}``
     * was deleted (2.9.7 DRY purge — Edge's ``fetch_content`` owns the
     * capability, SHA-256 integrity enforced Rust-side) and the node
     * (:4243) does not expose it yet. TODO(CIRISServer ask: expose
     * federation content fetch on the node) — repoint to
     * [LOCAL_NODE_URL] when it lands.
     */
    suspend fun fetchFederationContent(
        contentId: String,
        peerKeyId: String,
        timeoutMs: Int = 5_000,
    ): FederationContentResponse {
        // Node-served since ciris-server 0.5.115 (CIRISServer#261) — the
        // agent's 400/404/503 envelopes; multimedia ContentResult::External
        // surfaces as 503 FETCH_FAILED for now (already localized in the UI).
        val method = "fetchFederationContent"
        logInfo(method, "POST $LOCAL_NODE_URL/v1/federation/content/$contentId from peer=$peerKeyId timeout=${timeoutMs}ms")
        val client = federationHttpClient()
        return try {
            val response = client.post("$LOCAL_NODE_URL/v1/federation/content/$contentId") {
                authHeader()?.let { header("Authorization", it) }
                contentType(ContentType.Application.Json)
                setBody(jsonConfig.encodeToString(
                    FederationContentRequest.serializer(),
                    FederationContentRequest(peerKeyId = peerKeyId, timeoutMs = timeoutMs),
                ))
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("Federation content fetch failed: ${response.status} for $contentId")
            }
            decodeFederationEnvelope(response.bodyAsText(), FederationContentResponse.serializer())
        } catch (e: Exception) {
            logException(method, e, "contentId=$contentId, peer=$peerKeyId")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Propose a moderation action on a piece of content — the CC 4.5.13
     * **reverse-quorum open-labeling path**. ANYONE (any adult member)
     * MAY propose; this is deliberately NOT the authoritative duty-holder
     * action (that is the gated ``POST /v1/safety/moderation``). It files
     * a report→``scores`` Contribution against [targetId] and opens the
     * **48-hour participation window** within which a present
     * moderator/steward may act unilaterally, else the community
     * (reverse-quorum of live responders) decides.
     *
     * [action] is the wire token — one of ``report`` | ``takedown`` |
     * ``question`` (see [ai.ciris.mobile.shared.viewmodels.ModerationAction]).
     * [reason] is an optional free-form rationale.
     *
     * Hits ``POST /v1/safety/reports`` — the FSD/MODERATION_CHILD_SAFETY.md
     * §4.4 "report → surface → act" surface. **NOTE: this server route is
     * NOT YET IMPLEMENTED** (there is no ``src/safety/report.rs`` today;
     * only ``/v1/safety/moderation``, the gated duty-holder action). This
     * client targets the FSD-specified path so the UI affordance ships
     * ahead of the route; see the round report for the exact contract the
     * server must honor. The body is tolerant of either a ``{"data": …}``
     * envelope or a bare object on response.
     */
    suspend fun proposeModeration(
        targetId: String,
        action: String,
        reason: String? = null,
    ): ModerationProposalResult {
        val method = "proposeModeration"
        logInfo(method, "POST /v1/safety/reports target=$targetId action=$action reason=${reason?.take(40)}")
        val client = federationHttpClient()
        return try {
            val response = client.post("$baseUrl/v1/safety/reports") {
                authHeader()?.let { header("Authorization", it) }
                contentType(ContentType.Application.Json)
                setBody(jsonConfig.encodeToString(
                    JsonObject.serializer(),
                    buildJsonObject {
                        // The CC 4.5.5 target — content/contributor the report names.
                        put("target_key_id", targetId)
                        // report | takedown | question (the proposed action).
                        put("action", action)
                        // The open-labeling allegation token; rides `scores`.
                        put("allegation_type", "moderation:proposed:$action")
                        if (!reason.isNullOrBlank()) put("reason", reason)
                    },
                ))
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("Moderation proposal failed: ${response.status}")
            }
            // Tolerant parse — the window/contribution id may or may not be
            // echoed (the route is not yet live). Absence is not an error:
            // the 48h window is the constitutional default.
            val rawBody = response.bodyAsText()
            val root = runCatching { Json.parseToJsonElement(rawBody).jsonObject }.getOrNull()
            val data = root?.get("data")?.let {
                runCatching { it.jsonObject }.getOrNull()
            } ?: root
            ModerationProposalResult(
                contributionId = data?.get("contribution_id")?.jsonPrimitive?.contentOrNull
                    ?: data?.get("attestation_id")?.jsonPrimitive?.contentOrNull,
                windowClosesAt = data?.get("window_closes_at")?.jsonPrimitive?.contentOrNull,
            )
        } catch (e: Exception) {
            logException(method, e, "target=$targetId action=$action")
            throw e
        } finally {
            client.close()
        }
    }

    // ─── NodeCode share/add (/v1/system/peers/*) ─────────────────────────────
    //
    // NodeCode is the BOOTSTRAP UX for adding a peer; SAS verification
    // (above) is the post-add step that promotes UNKNOWN → TRUSTED.

    /**
     * Get a shareable NodeCode for the local agent's federation
     * identity. OBSERVER+ readable.
     *
     * Hits ``GET /v1/system/peers/my-node-code``.
     */
    suspend fun getMyNodeCode(
        transportHint: String? = null,
        aliasHint: String? = null,
    ): NodeCodeShareResponse {
        val method = "getMyNodeCode"
        logDebug(method, "GET /v1/system/peers/my-node-code aliasHint=$aliasHint")
        val client = federationHttpClient()
        return try {
            val response = client.get("$baseUrl/v1/system/peers/my-node-code") {
                authHeader()?.let { header("Authorization", it) }
                if (transportHint != null) parameter("transport_hint", transportHint)
                if (aliasHint != null) parameter("alias_hint", aliasHint)
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("NodeCode share failed: ${response.status}")
            }
            decodeFederationEnvelope(response.bodyAsText(), NodeCodeShareResponse.serializer())
        } catch (e: Exception) {
            logException(method, e, "url=$baseUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Full federation identity aggregate — persist's
     * ``LocalIdentityAggregate`` (signing Ed25519 + optional ML-DSA-65,
     * Reticulum transport keys, content-encryption X25519 + ML-KEM-768)
     * plus the companion NodeCode identity. This is THE address the
     * production lens / registry servers use to reach this node.
     * OBSERVER+ readable.
     *
     * Hits ``GET /v1/system/peers/federation-identity``. Returns null
     * on 503 (persist identity not yet initialized) so the caller can
     * render an "initializing" state instead of an error banner.
     */
    suspend fun getFederationIdentityAggregate(): FederationIdentityResponse? {
        val method = "getFederationIdentityAggregate"
        logDebug(method, "GET /v1/system/peers/federation-identity")
        val client = federationHttpClient()
        return try {
            val response = client.get("$baseUrl/v1/system/peers/federation-identity") {
                authHeader()?.let { header("Authorization", it) }
            }
            if (response.status == HttpStatusCode.ServiceUnavailable) {
                logDebug(method, "federation identity not yet available (503)")
                null
            } else if (!response.status.isSuccess()) {
                throw RuntimeException("Federation identity aggregate fetch failed: ${response.status}")
            } else {
                decodeFederationEnvelope(response.bodyAsText(), FederationIdentityResponse.serializer())
            }
        } catch (e: Exception) {
            logException(method, e, "url=$baseUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Add a peer from a NodeCode string. Whitespace and dashes are
     * tolerated server-side. SYSTEM_ADMIN required.
     *
     * Hits ``POST /v1/system/peers/add-from-code``.
     */
    suspend fun addPeerFromNodeCode(code: String): NodeCodeAddResponse {
        val method = "addPeerFromNodeCode"
        logInfo(method, "POST /v1/system/peers/add-from-code code='${code.take(20)}...'")
        val client = federationHttpClient()
        return try {
            val response = client.post("$baseUrl/v1/system/peers/add-from-code") {
                authHeader()?.let { header("Authorization", it) }
                contentType(ContentType.Application.Json)
                setBody(jsonConfig.encodeToString(
                    NodeCodeAddRequest.serializer(),
                    NodeCodeAddRequest(code = code),
                ))
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("NodeCode add failed: ${response.status}")
            }
            decodeFederationEnvelope(response.bodyAsText(), NodeCodeAddResponse.serializer())
        } catch (e: Exception) {
            logException(method, e, "code='${code.take(20)}...'")
            throw e
        } finally {
            client.close()
        }
    }

    // ─── Self-at-login ceremony (/v1/self/login) ─────────────────────────────
    //
    // CEG self-at-login: roots a federation identity in a hardware key and
    // presents app/agent occurrences + a hardware_attestation blob. The node's
    // self_login admits the identity and promotes the occurrences. NOT in the
    // generated SDK yet — hand-written direct HTTP.

    /**
     * Perform the CEG self-at-login ceremony.
     *
     * Hits ``POST /v1/self/login``. On success the returned
     * [SelfLoginResponse.accessToken] (if present) is applied to this client.
     */
    suspend fun selfLogin(
        request: SelfLoginRequest,
        nodeUrl: String = LOCAL_NODE_URL,
    ): SelfLoginResponse {
        val method = "selfLogin"
        logInfo(method, "POST $nodeUrl/v1/self/login identityKey=${request.identityKeyId.take(16)}… occurrences=${request.occurrences.map { it.kind }}")
        val client = federationHttpClient()
        return try {
            // Plain unsigned POST to the LOCAL node. Any federation signing the
            // ceremony needs is performed by the node's substrate, not the app.
            val bodyText = jsonConfig.encodeToString(SelfLoginRequest.serializer(), request)
            val response = client.post("$nodeUrl/v1/self/login") {
                contentType(ContentType.Application.Json)
                setBody(bodyText)
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("Self-login failed: ${response.status}")
            }
            val parsed = decodeFederationEnvelope(response.bodyAsText(), SelfLoginResponse.serializer())
            parsed.accessToken?.let { setAccessToken(it) }
            parsed
        } catch (e: Exception) {
            logException(method, e, "url=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    // ─── Bilateral consent:replication peering (/v1/federation/*) ─────────────
    //
    // GET  /v1/federation/self-key-record → this node's SignedKeyRecord
    // POST /v1/federation/peering         → register peer + emit consent grant
    //
    // The consent-objects card drives these against TWO nodes (A and B), each
    // with its own base URL + token, so these methods take an explicit
    // [nodeUrl]/[token] rather than relying solely on the client's current
    // baseUrl. NOT in the generated SDK yet — hand-written direct HTTP.

    /**
     * Fetch a node's own [SignedKeyRecord].
     *
     * Hits ``GET {nodeUrl}/v1/federation/self-key-record``.
     *
     * `/v1/federation` is a SUBSTRATE prefix — served natively by the NODE and
     * never proxied from the brain — so [nodeUrl] defaults to [LOCAL_NODE_URL],
     * not to this client's [baseUrl] (which addresses the Python brain).
     */
    suspend fun getSelfKeyRecord(
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): SignedKeyRecord {
        val method = "getSelfKeyRecord"
        logDebug(method, "GET $nodeUrl/v1/federation/self-key-record")
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/federation/self-key-record") {
                token?.let { header("Authorization", "Bearer $it") }
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("self-key-record fetch failed: ${response.status} for $nodeUrl")
            }
            // ciris-server returns the CANONICAL persist SignedKeyRecord, which nests
            // the fields under `record` ({"record":{"key_id":…,"pubkey_ed25519_base64":…}}).
            // The flat client model expects `key_id` at the top, so map the nested
            // shape here (tolerating a flat body too). We only need the identity fields.
            val text = response.bodyAsText()
            val root = kotlinx.serialization.json.Json { ignoreUnknownKeys = true }
                .parseToJsonElement(text).jsonObject
            val rec = root["record"]?.jsonObject ?: root
            val keyId = rec["key_id"]?.jsonPrimitive?.contentOrNull
                ?: throw RuntimeException("self-key-record missing key_id")
            SignedKeyRecord(
                keyId = keyId,
                publicKey = rec["pubkey_ed25519_base64"]?.jsonPrimitive?.contentOrNull,
                signature = rec["scrub_signature_classical"]?.jsonPrimitive?.contentOrNull,
                algorithm = rec["algorithm"]?.jsonPrimitive?.contentOrNull,
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Lightweight liveness probe for the local **ciris-server** node read API.
     *
     * Issues a raw `GET {nodeUrl}/v1/identity`. Any HTTP response — including a
     * non-2xx like 404/401 — means the node process is up and serving, so this
     * returns true. Only a transport/connection failure (node not running)
     * returns false. Used by startup to degrade gracefully when richer endpoints
     * (e.g. /v1/setup/status) are unavailable on a node that is otherwise up.
     */
    // ---- Desktop browser sign-in (ported from ciris-server 0.5.165) --------
    // The node serves the browser flow because desktop has no native Google
    // SDK; the app polls for the result. Ported rather than copied wholesale:
    // the server's client tree does NOT carry the 2.9.14 three-step wizard, so
    // replacing our tree with theirs would have deleted it.
    /**
     * **Desktop browser sign-in: start it, then collect the session.**
     *
     * Desktop has no native Google SDK, so the node serves the browser flow and
     * the APP has to learn the result — two processes, one sign-in. The app
     * generates a nonce, opens the browser at [oauthBrowserLoginUrl], and polls
     * here until the node hands the bearer over. One-time: the first successful
     * collection removes it, so a leaked nonce cannot be replayed afterwards.
     *
     * `null` means NOT YET (the node answers 204) — the human is still in the
     * browser. That is deliberately distinct from a failure: a caller that
     * treated "not yet" as "failed" would abandon a sign-in that is still going.
     */
    suspend fun collectOAuthHandoff(
        appNonce: String,
        localNodeUrl: String = LOCAL_NODE_URL,
        /**
         * Accept a sign-in that completed without OUR nonce — a stray browser
         * tab opened at the plain `/login` URL. Off while we still expect our
         * own flow to land; the caller turns it on only after waiting, so the
         * bound path always wins when it exists.
         */
        allowUnbound: Boolean = false,
    ): OAuthHandoff? {
        val client = federationHttpClient()
        return try {
            val response = client.get(
                "$localNodeUrl/v1/auth/oauth/handoff?app_nonce=$appNonce&allow_unbound=$allowUnbound"
            )
            if (response.status.value == 204) return null
            if (!response.status.isSuccess()) return null
            jsonConfig.decodeFromString(OAuthHandoff.serializer(), response.bodyAsText())
        } catch (_: Exception) {
            null
        } finally {
            client.close()
        }
    }

    /** The browser URL that starts a desktop sign-in for [provider]. */
    fun oauthBrowserLoginUrl(
        provider: String,
        appNonce: String,
        localNodeUrl: String = LOCAL_NODE_URL,
    ): String = "$localNodeUrl/v1/auth/oauth/$provider/login?app_nonce=$appNonce"

    /**
     * The OAuth providers this deployment actually has credentials for.
     *
     * A provider only appears here when the node was provisioned with its
     * client_id AND client_secret (the PKCE secret CI bakes from GH secrets into
     * `oauth.json`; see `oauth_provider_sync.py` — an unprovisioned provider is
     * skipped). So an empty/`google`-less list is the authoritative "sign-in with
     * Google is NOT wired on this build" signal, and the Login screen greys the
     * button out rather than offering a door that opens onto redirect_uri_mismatch.
     *
     * Served natively by the node on :4243 and proxied through the agent's front
     * door on :8080, so it answers in both node and agent mode. Returns an empty
     * list on any error — fail closed (button disabled) rather than dangle a
     * broken affordance.
     */
    suspend fun getOAuthProviders(nodeUrl: String = baseUrl): List<String> {
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/auth/oauth/providers")
            if (!response.status.isSuccess()) return emptyList()
            val root = jsonConfig.parseToJsonElement(response.bodyAsText()).jsonObject
            // Tolerate {providers:[...]} and {data:{providers:[...]}}, where each
            // entry is either a bare "google" string or an object with a name/
            // provider/id field.
            val arr = (root["providers"] ?: (root["data"] as? JsonObject)?.get("providers"))
                as? kotlinx.serialization.json.JsonArray ?: return emptyList()
            arr.mapNotNull { el ->
                when (el) {
                    is JsonPrimitive -> el.content
                    is JsonObject -> (el["name"] ?: el["provider"] ?: el["id"])
                        ?.let { (it as? JsonPrimitive)?.content }
                    else -> null
                }
            }.map { it.lowercase() }
        } catch (_: Exception) {
            emptyList()
        } finally {
            client.close()
        }
    }

    suspend fun isLocalNodeUp(nodeUrl: String = baseUrl): Boolean {
        val client = federationHttpClient()
        return try {
            client.get("$nodeUrl/v1/identity")
            true
        } catch (_: Exception) {
            false
        } finally {
            client.close()
        }
    }

    /**
     * Drive THIS device's LOCAL node to **mint the founder's hardware-rooted
     * USER federation identity** — `POST {localNodeUrl}/v1/self/identity`.
     *
     * The app performs NO crypto. The local ciris-server mints the hybrid
     * Ed25519 + ML-DSA-65 keypair in its keyring/substrate, custodied per the
     * chosen [backend] (`pkcs11`=YubiKey / `platform-sealed`=TPM·SE /
     * `software`=dev), writes the genesis CEG object to its outbox, and returns
     * the public result: the `key_id`, the shareable `CIRIS-V2-…` [fedcode], the
     * pubkeys, and the honest `hardware_type`. This is a plain owner-session
     * POST (Bearer [token]); there is no x-ciris signing in Kotlin.
     *
     * Mirrors `CIRISServer/src/identity.rs` `self_identity_handler`. All request
     * fields are optional — the node defaults the backend to `platform-sealed`
     * and the alias to `<node>-user`.
     *
     * @param label optional human display name → the `label-fingerprint` key_id.
     * @param backend optional custody hint: `pkcs11` | `platform-sealed` |
     *        `software`. Unknown values are rejected by the node (400).
     * @param provision for `pkcs11`: provision an empty PIV slot via `ykman`.
     * @param pivSlot for `pkcs11`: the PIV slot (default `9c`).
     * @param localNodeUrl base URL of THIS device's local node ([LOCAL_NODE_URL]).
     */
    suspend fun mintUserIdentity(
        label: String? = null,
        backend: String? = null,
        provision: Boolean? = null,
        pivSlot: String? = null,
        localNodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): MintedIdentity {
        val method = "mintUserIdentity"
        logInfo(method, "POST $localNodeUrl/v1/self/identity backend=${backend ?: "(default)"} label=${label ?: "(none)"}")
        val client = federationHttpClient()
        return try {
            val request = MintIdentityRequest(
                backend = backend,
                label = label,
                provision = provision,
                pivSlot = pivSlot,
            )
            val bodyText = jsonConfig.encodeToString(MintIdentityRequest.serializer(), request)
            val response = client.post("$localNodeUrl/v1/self/identity") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyText)
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                logException(method, RuntimeException("status=${response.status} body=${raw.take(300)}"), "localNodeUrl=$localNodeUrl")
                throw RuntimeException("mint identity failed: ${response.status}: ${raw.take(200)}")
            }
            // The node returns a FLAT JSON object (no `{"data": …}` envelope);
            // decodeFederationEnvelope tolerates the unwrapped shape.
            decodeFederationEnvelope(raw, MintedIdentity.serializer())
        } catch (e: Exception) {
            logException(method, e, "localNodeUrl=$localNodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Attach an OAuth identity to an existing certificate — `POST
     * {localNodeUrl}/v1/self/oauth-link`.
     *
     * CIRISServer#432, the client half. The node has routed this all along
     * (`src/auth/oauth_link.rs`), and nothing called it: the generated SDK
     * targets `/v1/users/{userId}/oauth-links`, which the node does not route,
     * so the one surface that could fix a locally-claimed node was unreachable.
     * That is the original field report — a node claimed with a username and
     * password could never have Google attached to it.
     *
     * PASS [email], not [externalId], for a human. Nobody can look up their own
     * Google `sub`; an address is the handle a person actually holds. The node
     * writes it to the cert as a provisioning slot and stamps the verified
     * provider pair on the next successful sign-in, after which the address
     * stops being load-bearing.
     *
     * Owner-gated (SYSTEM_ADMIN + FullAccess) and it refuses a delegated
     * session, because this writes a stored row that would outlive an in-memory
     * grant. Refusals carry a `reason_id`, so "not signed in" and "signed in but
     * not the owner" are answers a UI can tell apart.
     *
     * @param waId certificate to link; omit for the node's ROOT (the owner),
     *   which is the case this exists for.
     */
    suspend fun linkOAuthIdentity(
        provider: String,
        email: String? = null,
        externalId: String? = null,
        waId: String? = null,
        localNodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): OAuthLinkResult {
        val method = "linkOAuthIdentity"
        logInfo(method, "POST $localNodeUrl/v1/self/oauth-link provider=$provider by=${if (email != null) "email" else "external_id"}")
        val client = federationHttpClient()
        return try {
            val body = buildJsonObject {
                put("provider", provider)
                waId?.let { put("wa_id", it) }
                email?.let { put("email", it) }
                externalId?.let { put("external_id", it) }
            }
            val response = client.post("$localNodeUrl/v1/self/oauth-link") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(body.toString())
            }
            val raw = response.bodyAsText()
            val obj = try { Json.parseToJsonElement(raw).jsonObject } catch (_: Exception) { null }
            if (!response.status.isSuccess()) {
                // Carry the node's reason_id through — it is the difference
                // between "sign in" and "sign in as the owner".
                val reason = obj?.get("reason_id")?.jsonPrimitive?.contentOrNull
                val detail = obj?.get("error")?.jsonPrimitive?.contentOrNull
                    ?: obj?.get("detail")?.jsonPrimitive?.contentOrNull
                throw RuntimeException(detail ?: "Could not link $provider (${response.status})", null).also {
                    logError(method, "status=${response.status} reason_id=${reason ?: "<none>"} body=${raw.take(200)}")
                }
            }
            OAuthLinkResult(
                provider = obj?.get("provider")?.jsonPrimitive?.contentOrNull ?: provider,
                linked = obj?.get("linked")?.jsonPrimitive?.booleanOrNull ?: false,
                isPrimary = obj?.get("is_primary")?.jsonPrimitive?.booleanOrNull ?: false,
            )
        } catch (e: Exception) {
            logException(method, e, "localNodeUrl=$localNodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Register a peer on [nodeUrl] and emit this node's consent:replication
     * grant scoped to [PeeringRequest.attestationPrefixes]. Owner/admin-gated
     * server-side.
     *
     * Hits ``POST {nodeUrl}/v1/federation/peering``.
     */
    suspend fun postPeering(
        request: PeeringRequest,
        nodeUrl: String = baseUrl,
        token: String? = accessToken,
    ): PeeringResponse {
        val method = "postPeering"
        logInfo(method, "POST $nodeUrl/v1/federation/peering peer=${request.peerKeyId.take(16)}… prefixes=${request.attestationPrefixes}")
        val client = federationHttpClient()
        return try {
            val response = client.post("$nodeUrl/v1/federation/peering") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(jsonConfig.encodeToString(PeeringRequest.serializer(), request))
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("peering failed: ${response.status} for $nodeUrl")
            }
            decodeFederationEnvelope(response.bodyAsText(), PeeringResponse.serializer())
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl, peer=${request.peerKeyId}")
            throw e
        } finally {
            client.close()
        }
    }

    // ─── NodeCode bootstrap + node-ownership claim (CEG §0.10) ────────────────
    //
    // GET  {nodeUrl}/v1/federation/node-code → the node's own NodeCode (PUBLIC,
    //      unauthenticated). Used to identity-pin a freshly-connected node: the
    //      served code's key_id + pubkey must match the code the founder scanned.
    // POST {localNodeUrl}/v1/setup/claim-remote → drive the LOCAL node to claim a
    //      remote/target node on the owner's behalf. The LOCAL node decodes the
    //      NodeCode, builds + JCS-canonicalizes + HYBRID-SIGNS the owner-binding
    //      delegates_to(user → target, infra:*) IN ITS SUBSTRATE with the owner's
    //      identity, and POSTs it to the target node's /v1/setup/root. The app
    //      performs NO crypto — it only calls claim-remote and shows the result.
    //
    // NOT in the generated SDK — hand-written direct HTTP. claim-remote is a plain
    // UNSIGNED localhost POST: the local node authenticates the operator via the
    // normal session, so there is no x-ciris signing in Kotlin.

    /**
     * Fetch a node's own NodeCode from `GET {nodeUrl}/v1/federation/node-code`.
     *
     * UNAUTHENTICATED — the NodeCode is a PUBLIC bootstrap handle. The caller
     * uses the returned [NodeCodeShareResponse.code] (decoded locally) to
     * identity-pin the node: confirm its key_id + pubkey match the code the user
     * scanned/pasted before trusting the connection.
     */
    suspend fun getNodeCode(nodeUrl: String = baseUrl): NodeCodeShareResponse {
        val method = "getNodeCode"
        logDebug(method, "GET $nodeUrl/v1/federation/node-code")
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/federation/node-code")
            if (!response.status.isSuccess()) {
                throw RuntimeException("node-code fetch failed: ${response.status} for $nodeUrl")
            }
            decodeFederationEnvelope(response.bodyAsText(), NodeCodeShareResponse.serializer())
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * The CEG-native node list — `GET {nodeUrl}/v1/setup/owned-nodes`. Returns the
     * nodes owned by this node's bound owner (its fed ID), PROJECTED from the
     * `delegates_to(user → node)` owner-binding objects in the graph (NOT a
     * client-side store). By construction the local node appears once self-claimed.
     */
    suspend fun getOwnedNodes(nodeUrl: String = LOCAL_NODE_URL): OwnedNodesDto {
        val method = "getOwnedNodes"
        logDebug(method, "GET $nodeUrl/v1/setup/owned-nodes")
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/setup/owned-nodes")
            if (!response.status.isSuccess()) {
                throw RuntimeException("owned-nodes fetch failed: ${response.status} for $nodeUrl")
            }
            jsonConfig.decodeFromString(OwnedNodesDto.serializer(), response.bodyAsText())
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Drive the LOCAL node to claim a remote/target node on the owner's behalf —
     * `POST {localNodeUrl}/v1/setup/claim-remote`.
     *
     * The body is `{ node_code, claim_pin, cohort_scope }`. The LOCAL node decodes
     * the [nodeCode], builds + JCS-canonicalizes + HYBRID-SIGNS the owner-binding
     * `delegates_to(user → target, infra:*)` IN ITS SUBSTRATE with the owner's
     * identity, and POSTs it to the target node's `/v1/setup/root`. The app does
     * NO crypto: this is a plain UNSIGNED localhost POST and the local node
     * authenticates the operator via the normal session (Bearer [token]).
     *
     * @param localNodeUrl base URL of THIS device's local node (defaults to
     *        [LOCAL_NODE_URL]). NOT the target node — the local node reaches the
     *        target itself.
     * @return the parsed [ClaimRemoteResponse]; on a non-2xx the method throws
     *         after logging so callers can surface the node's message.
     */
    suspend fun claimRemote(
        nodeCode: String,
        claimPin: String,
        cohortScope: String,
        localNodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
        ownerPassword: String? = null,
        ownerUsername: String? = null,
    ): ClaimRemoteResponse {
        val method = "claimRemote"
        logInfo(method, "POST $localNodeUrl/v1/setup/claim-remote node_code=${nodeCode.take(20)}… cohort=$cohortScope ownerPw=${ownerPassword != null}")
        val client = federationHttpClient()
        return try {
            val request = ClaimRemoteRequest(
                nodeCode = nodeCode,
                claimPin = claimPin,
                cohortScope = cohortScope,
                ownerPassword = ownerPassword,
                ownerUsername = ownerUsername,
            )
            val bodyText = jsonConfig.encodeToString(ClaimRemoteRequest.serializer(), request)
            val response = client.post("$localNodeUrl/v1/setup/claim-remote") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyText)
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                logException(method, RuntimeException("status=${response.status} body=${raw.take(300)}"), "localNodeUrl=$localNodeUrl")
                throw RuntimeException("claim-remote failed: ${response.status}: ${raw.take(200)}")
            }
            decodeFederationEnvelope(raw, ClaimRemoteResponse.serializer())
        } catch (e: Exception) {
            logException(method, e, "localNodeUrl=$localNodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * **Upgrade an existing (already-owned) node to a fed-ID owner-binding** —
     * `POST {localNodeUrl}/v1/self/upgrade-owner`. The WAs-need-fed-IDs migration:
     * a node owned the legacy way (a password/OAuth ROOT WA with NO fed-ID) is
     * re-rooted on a fed-ID by persisting `delegates_to(fed-ID → node)` — the
     * existing login is PRESERVED (non-destructive owner-binding model).
     *
     * PREREQ: a fed-ID must already be minted on the node ([mintUserIdentity]) and
     * [token] must be the EXISTING owner's session (password/OAuth login). Returns
     * `{ owner, node_key_id, owner_binding_attestation_id }`.
     */
    suspend fun upgradeOwnerToFedId(
        localNodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): String {
        val method = "upgradeOwnerToFedId"
        logInfo(method, "POST $localNodeUrl/v1/self/upgrade-owner")
        val client = federationHttpClient()
        return try {
            val response = client.post("$localNodeUrl/v1/self/upgrade-owner") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody("{}")
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                logException(method, RuntimeException("status=${response.status} body=${raw.take(300)}"), "localNodeUrl=$localNodeUrl")
                throw RuntimeException("upgrade-owner failed: ${response.status}: ${raw.take(200)}")
            }
            raw
        } catch (e: Exception) {
            logException(method, e, "localNodeUrl=$localNodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * **Record the bound owner's self-declared age band** — `POST {localNodeUrl}/v1/self/age`.
     * The wizard-time, loopback + owner-session path (the app does NO crypto): the
     * LOCAL node records the self-declared age for its bound owner fed-ID in its
     * substrate. Run AFTER the claim (the owner must exist) with the owner session.
     * [band] is `"minor"` | `"adult"`. Returns the raw JSON.
     */
    suspend fun setAgeSelf(
        band: String,
        localNodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): String {
        val method = "setAgeSelf"
        logInfo(method, "POST $localNodeUrl/v1/self/age band=$band")
        val client = federationHttpClient()
        return try {
            val response = client.post("$localNodeUrl/v1/self/age") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody("{\"band\":\"$band\"}")
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                logException(method, RuntimeException("status=${response.status} body=${raw.take(300)}"), "localNodeUrl=$localNodeUrl")
                throw RuntimeException("set-age failed: ${response.status}: ${raw.take(200)}")
            }
            raw
        } catch (e: Exception) {
            logException(method, e, "localNodeUrl=$localNodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * **Opt IN to the federation** — `POST {localNodeUrl}/v1/federation/announce`.
     * Ownership is self-scoped (private) by default; this promotes the owner-binding
     * self→FEDERATION and enables the node's identity announce so the community can
     * find and federate with it. Owner-session-gated + loopback-only; idempotent and
     * takes effect on the node's NEXT boot. Run AFTER the claim (the owner must
     * exist) with the owner session. Returns the parsed [AnnounceOwnershipResponse].
     */
    suspend fun announceOwnership(
        localNodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.AnnounceOwnershipResponse {
        val method = "announceOwnership"
        logInfo(method, "POST $localNodeUrl/v1/federation/announce")
        val client = federationHttpClient()
        return try {
            val response = client.post("$localNodeUrl/v1/federation/announce") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody("{}")
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                logException(method, RuntimeException("status=${response.status} body=${raw.take(300)}"), "localNodeUrl=$localNodeUrl")
                throw RuntimeException("announce failed: ${response.status}: ${raw.take(200)}")
            }
            decodeFederationEnvelope(raw, ai.ciris.mobile.shared.models.federation.AnnounceOwnershipResponse.serializer())
        } catch (e: Exception) {
            logException(method, e, "localNodeUrl=$localNodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    // ─── Delegations (device-authorization grants) — owner authorizes an agent ──
    //
    // The owner approves a device code an agent generated out-of-band, minting a
    // delegated `dgrant:` token (owner authority + actor attribution). These drive
    // the local node only (owner session); the in-memory grant registry is the
    // interim home until the substrate-native delegation surface lands.

    /** List the owner's LIVE delegations — `GET {nodeUrl}/v1/auth/device/grants`. */
    suspend fun listDelegations(
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): List<ai.ciris.mobile.shared.models.federation.DelegationDto> {
        val method = "listDelegations"
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/auth/device/grants") {
                token?.let { header("Authorization", "Bearer $it") }
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("list delegations failed: ${response.status}: ${raw.take(160)}")
            }
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.DelegationsResponse.serializer(),
                raw,
            ).grants
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Create a delegation the owner hands to an agent —
     * `POST {nodeUrl}/v1/auth/device/delegate`. The owner names a `label` and
     * chooses `mode`: `"create"` mints a fresh agent fed-ID, `"existing"` binds
     * an `existingKeyId`. Owner-session-gated. Returns a claim URL + PIN to hand
     * over (the agent then claims via `POST /v1/auth/device/claim`).
     */
    suspend fun createDelegation(
        label: String,
        mode: String, // "create" | "existing"
        existingKeyId: String? = null,
        scope: List<String> = listOf("owner:act-on-behalf"),
        constraints: ai.ciris.mobile.shared.models.federation.DelegationConstraints? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.CreateDelegationResponse {
        val method = "createDelegation"
        logInfo(method, "POST $nodeUrl/v1/auth/device/delegate mode=$mode label=$label")
        val client = federationHttpClient()
        return try {
            val scopeJson = scope.joinToString(",", "[", "]") { "\"$it\"" }
            val keyField = existingKeyId?.takeIf { it.isNotBlank() }
                ?.let { ",\"existing_key_id\":\"${it.trim()}\"" } ?: ""
            val constraintsField = constraints?.takeIf { !it.isUnconstrained() }
                ?.let { ",\"constraints\":${encodeDelegationConstraints(it)}" } ?: ""
            val body = "{\"mode\":\"${mode.trim()}\",\"label\":\"${label.trim()}\"" +
                "$keyField,\"scope\":$scopeJson$constraintsField}"
            val response = client.post("$nodeUrl/v1/auth/device/delegate") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(body)
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                // Full body — never truncate a server error (the createDelegation-500
                // lesson: the load-bearing verify_hybrid_required / attesting_key_id
                // detail lived past char 160). The node also logs it server-side.
                throw RuntimeException("create delegation failed: ${response.status}: $raw")
            }
            val parsed = jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.CreateDelegationResponse.serializer(),
                raw,
            )
            // Best-effort transparency: if the offer body didn't embed the grant's
            // characteristics but the node sent the compact `x-ciris-delegation`
            // response header, parse it so the owner can review what they granted.
            if (parsed.delegation == null) {
                response.headers["x-ciris-delegation"]?.let { hdr ->
                    runCatching {
                        jsonConfig.decodeFromString(
                            ai.ciris.mobile.shared.models.federation.GrantCharacteristics.serializer(),
                            hdr,
                        )
                    }.getOrNull()?.let { return parsed.copy(delegation = it) }
                }
            }
            parsed
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Hand-encode [DelegationConstraints] to compact JSON, matching this file's
     * hand-built-body convention. The tri-state [actionsAllow] is preserved
     * exactly: absent when `null`, `[]` when read-only, else the subset — so the
     * node sees the owner's intent verbatim. [actionsDeny] is emitted only when
     * non-empty; [goal] is JSON-string-escaped.
     */
    private fun encodeDelegationConstraints(
        c: ai.ciris.mobile.shared.models.federation.DelegationConstraints,
    ): String {
        val parts = mutableListOf<String>()
        c.actionsAllow?.let { list ->
            parts += "\"actions_allow\":" + list.joinToString(",", "[", "]") { "\"$it\"" }
        }
        if (c.actionsDeny.isNotEmpty()) {
            parts += "\"actions_deny\":" + c.actionsDeny.joinToString(",", "[", "]") { "\"$it\"" }
        }
        c.goal?.takeIf { it.isNotBlank() }?.let { goal ->
            val escaped = goal.replace("\\", "\\\\").replace("\"", "\\\"")
            parts += "\"goal\":\"$escaped\""
        }
        return "{" + parts.joinToString(",") + "}"
    }

    /**
     * Approve a pending device code — `POST {nodeUrl}/v1/auth/device/approve`.
     * The owner enters the `user_code` the agent showed them; approving mints the
     * delegated token. Owner-session-gated; this is the human-consent gate.
     *
     * Optional [constraints] TIGHTEN the grant on approval (the server can only
     * narrow, never widen) — same shape as the issue path.
     */
    suspend fun approveDeviceCode(
        userCode: String,
        constraints: ai.ciris.mobile.shared.models.federation.DelegationConstraints? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): String {
        val method = "approveDeviceCode"
        logInfo(method, "POST $nodeUrl/v1/auth/device/approve user_code=$userCode")
        val client = federationHttpClient()
        return try {
            val constraintsField = constraints?.takeIf { !it.isUnconstrained() }
                ?.let { ",\"constraints\":${encodeDelegationConstraints(it)}" } ?: ""
            val response = client.post("$nodeUrl/v1/auth/device/approve") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody("{\"user_code\":\"${userCode.trim()}\"$constraintsField}")
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("approve failed: ${response.status}: ${raw.take(160)}")
            }
            raw
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /** Revoke all delegations to a client — `POST {nodeUrl}/v1/auth/device/revoke`. */
    suspend fun revokeDelegation(
        clientId: String,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): String {
        val method = "revokeDelegation"
        logInfo(method, "POST $nodeUrl/v1/auth/device/revoke client_id=$clientId")
        val client = federationHttpClient()
        return try {
            val response = client.post("$nodeUrl/v1/auth/device/revoke") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody("{\"client_id\":\"${clientId.trim()}\"}")
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("revoke failed: ${response.status}: ${raw.take(160)}")
            }
            raw
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    // ─── Self-occurrence enrollment (/v1/self/occurrence*) — CIRISServer #76 ─────
    //
    // "Manage my self + log in as myself on another device" (src/auth/occurrence.rs,
    // CEG §5.6.8.8 / §11.7). A "self" is a roster of occurrence rows over ONE root
    // fed-ID; any ACTIVE occurrence stands in for the self, so a second device makes
    // the founder's identity survive the loss of the first.
    //
    //   GET  /v1/self/occurrences?identity_key_id=… → roster (PUBLIC, unauthenticated)
    //   POST /v1/self/occurrence                     → ADD a device (federation-signed)
    //   POST /v1/self/occurrence/revoke              → REVOKE a device (federation-signed)
    //
    // The ADD / REVOKE are federation-signed requests. The app holds NO keys and
    // performs NO crypto: it drives the LOCAL node with a plain owner-session POST and
    // the node signs with the user's resolved fed-ID signer — the SAME posture as the
    // consent / peering / claim-remote / delegation cards (see [createDelegation],
    // [claimRemote], [selfLogin]). There is no x-ciris signing in Kotlin.

    /**
     * The device roster — `GET {nodeUrl}/v1/self/occurrences?identity_key_id=…`.
     *
     * UNAUTHENTICATED by design: an occurrence roster is public §5.6.8.8 binding
     * metadata (pubkeys + device_class), same posture as the self-key-record. Returns
     * the currently-ACTIVE occurrences (admitted, not revoked) of [identityKeyId].
     */
    suspend fun getSelfOccurrences(
        identityKeyId: String,
        nodeUrl: String = LOCAL_NODE_URL,
    ): ai.ciris.mobile.shared.models.federation.SelfOccurrencesResponse {
        val method = "getSelfOccurrences"
        logDebug(method, "GET $nodeUrl/v1/self/occurrences identity=${identityKeyId.take(16)}…")
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/self/occurrences") {
                url { parameters.append("identity_key_id", identityKeyId) }
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("self-occurrences fetch failed: ${response.status}: ${raw.take(160)}")
            }
            decodeFederationEnvelope(
                raw,
                ai.ciris.mobile.shared.models.federation.SelfOccurrencesResponse.serializer(),
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl, identity=$identityKeyId")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Add a device as an occurrence — `POST {nodeUrl}/v1/self/occurrence`.
     *
     * Federation-signed by the live primary (the user's fed-ID). The app sends a
     * plain owner-session POST to the LOCAL node; the node signs the body with the
     * resolved user signer (same as [createDelegation] / [claimRemote]). When the new
     * device's signing key is not yet in the directory, supply [request.occurrenceKeyRecord]
     * to admit it via the fail-secure proof-of-possession gate.
     */
    suspend fun addOccurrence(
        request: ai.ciris.mobile.shared.models.federation.AddOccurrenceRequest,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.AddOccurrenceResponse {
        val method = "addOccurrence"
        logInfo(
            method,
            "POST $nodeUrl/v1/self/occurrence identity=${request.identityKeyId.take(16)}… " +
                "occurrence=${request.occurrence.occurrenceKeyId.take(16)}… class=${request.occurrence.deviceClass}",
        )
        val client = federationHttpClient()
        return try {
            val bodyText = jsonConfig.encodeToString(
                ai.ciris.mobile.shared.models.federation.AddOccurrenceRequest.serializer(),
                request,
            )
            val response = client.post("$nodeUrl/v1/self/occurrence") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyText)
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("add occurrence failed: ${response.status}: ${raw.take(200)}")
            }
            decodeFederationEnvelope(
                raw,
                ai.ciris.mobile.shared.models.federation.AddOccurrenceResponse.serializer(),
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl, identity=${request.identityKeyId}")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Revoke a (lost / stolen) device — `POST {nodeUrl}/v1/self/occurrence/revoke`.
     *
     * Federation-signed by a SURVIVING occurrence (or the root). For a STOLEN device
     * you must sign with a different surviving key — never the compromised one
     * (CEG §11.7.4). The app sends a plain owner-session POST to the LOCAL node; the
     * node signs with the resolved user signer.
     */
    suspend fun revokeOccurrence(
        identityKeyId: String,
        occurrenceKeyId: String,
        reason: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.RevokeOccurrenceResponse {
        val method = "revokeOccurrence"
        logInfo(
            method,
            "POST $nodeUrl/v1/self/occurrence/revoke identity=${identityKeyId.take(16)}… " +
                "occurrence=${occurrenceKeyId.take(16)}…",
        )
        val client = federationHttpClient()
        return try {
            val bodyText = jsonConfig.encodeToString(
                ai.ciris.mobile.shared.models.federation.RevokeOccurrenceRequest.serializer(),
                ai.ciris.mobile.shared.models.federation.RevokeOccurrenceRequest(
                    identityKeyId = identityKeyId,
                    occurrenceKeyId = occurrenceKeyId,
                    reason = reason?.takeIf { it.isNotBlank() },
                ),
            )
            val response = client.post("$nodeUrl/v1/self/occurrence/revoke") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyText)
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("revoke occurrence failed: ${response.status}: ${raw.take(200)}")
            }
            decodeFederationEnvelope(
                raw,
                ai.ciris.mobile.shared.models.federation.RevokeOccurrenceResponse.serializer(),
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl, identity=$identityKeyId")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Create a **portable software identity occurrence** — `POST {nodeUrl}/v1/self/
     * occurrence/portable`.
     *
     * The LOCAL node mints a fresh *software* hybrid keyset INTO [targetDir] (a USB
     * folder the user picked) and binds it as a primary-authorized occurrence of the
     * owner's self. The app passes only the PATH; the node writes the seeds + does
     * the crypto. NO private bytes are returned. Owner-session POST (Bearer [token])
     * + loopback-only.
     *
     * A software keyset is inherently insecure — the explicitly-accepted bootstrap
     * trade-off (surfaced in the UI danger sublabel + the on-disk manifest).
     *
     * Mirrors `CIRISServer/src/auth/portable_occurrence.rs`.
     */
    suspend fun createPortableOccurrence(
        targetDir: String,
        label: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.PortableOccurrenceResponse {
        val method = "createPortableOccurrence"
        logInfo(method, "POST $nodeUrl/v1/self/occurrence/portable target=$targetDir label=${label ?: "(none)"}")
        val client = federationHttpClient()
        return try {
            val bodyText = jsonConfig.encodeToString(
                ai.ciris.mobile.shared.models.federation.PortableOccurrenceRequest.serializer(),
                ai.ciris.mobile.shared.models.federation.PortableOccurrenceRequest(
                    targetDir = targetDir,
                    label = label?.takeIf { it.isNotBlank() },
                ),
            )
            val response = client.post("$nodeUrl/v1/self/occurrence/portable") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyText)
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("create portable occurrence failed: ${response.status}: ${raw.take(200)}")
            }
            decodeFederationEnvelope(
                raw,
                ai.ciris.mobile.shared.models.federation.PortableOccurrenceResponse.serializer(),
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl, targetDir=$targetDir")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * **Associate an existing fed-ID** as THIS device's active user identity —
     * `POST {nodeUrl}/v1/self/associate`.
     *
     * Directory path: [sourceDir] points at a folder holding a portable software
     * keyset; the node installs it as this device's user fed-ID (so this device
     * signs as that occurrence). YubiKey path ([yubikey] = true) is server-GATED in
     * this pass (returns 501 until the on-device token read is wired). Owner-session
     * POST + loopback-only.
     */
    suspend fun associateFedId(
        sourceDir: String? = null,
        yubikey: Boolean = false,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.AssociateResponse {
        val method = "associateFedId"
        logInfo(method, "POST $nodeUrl/v1/self/associate source=${sourceDir ?: "(none)"} yubikey=$yubikey")
        val client = federationHttpClient()
        return try {
            val bodyText = jsonConfig.encodeToString(
                ai.ciris.mobile.shared.models.federation.AssociateRequest.serializer(),
                ai.ciris.mobile.shared.models.federation.AssociateRequest(
                    sourceDir = sourceDir?.takeIf { it.isNotBlank() },
                    yubikey = yubikey,
                ),
            )
            val response = client.post("$nodeUrl/v1/self/associate") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyText)
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("associate fed-ID failed: ${response.status}: ${raw.take(200)}")
            }
            decodeFederationEnvelope(
                raw,
                ai.ciris.mobile.shared.models.federation.AssociateResponse.serializer(),
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl, sourceDir=$sourceDir")
            throw e
        } finally {
            client.close()
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    //  THE MESH-CONFIG + COMMONS SURFACES (CIRISServer #346/#365 + #367)
    //  src/mesh_config_surface.rs · src/commons_surface.rs
    //
    //  Both surfaces answer with a BODY on non-2XX statuses, and the body is
    //  the answer rather than an error page:
    //
    //    GET /v1/mesh-config      503 + {standing:"unreadable", settings:null}
    //    GET /v1/commons/standing 404 + {standing:"action_unknown", fold:null}
    //                             503 + {standing:"unreadable",    fold:null}
    //    POST (any write door)    409 + {refused:true, refusal:"<token>"}
    //
    //  So these calls decode the body FIRST and only throw when it will not
    //  parse. Treating a 404 here as a transport failure would erase the very
    //  distinction the two surfaces were built to preserve — "we could not
    //  ask" is a different fact from "nobody objected", and both are 200-shaped
    //  answers arriving on non-200 statuses.
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * Decode a surface body that may arrive on any status. Throws only when the
     * body is absent or unparseable — a refusal/absence body is a real answer.
     */
    private fun <T> decodeSurfaceBody(
        method: String,
        raw: String,
        status: HttpStatusCode,
        serializer: kotlinx.serialization.KSerializer<T>,
    ): T {
        if (raw.isBlank()) {
            throw RuntimeException("$method: empty body (status=$status)")
        }
        return try {
            jsonConfig.decodeFromString(serializer, raw)
        } catch (e: Exception) {
            logException(method, e, "status=$status, body=${raw.take(200)}")
            throw RuntimeException("$method failed: $status: ${raw.take(200)}")
        }
    }

    /**
     * The effective mesh-config values, their provenance, their counting-down
     * TTLs, the closed key registry and — the point of #365 — each key's
     * `consumption` label. `GET {nodeUrl}/v1/mesh-config`.
     *
     * [now] pins the instant every TTL counts down from (RFC 3339), so a replay
     * of an incident reads the same numbers twice.
     */
    suspend fun getMeshConfig(
        now: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.surfaces.MeshConfigRead {
        val method = "getMeshConfig"
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/mesh-config") {
                token?.let { header("Authorization", "Bearer $it") }
                now?.let { parameter("now", it) }
            }
            decodeSurfaceBody(
                method,
                response.bodyAsText(),
                response.status,
                ai.ciris.mobile.shared.models.surfaces.MeshConfigRead.serializer(),
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /** Every mesh-config row this node holds, newest first — `GET {nodeUrl}/v1/mesh-config/history`. */
    suspend fun getMeshConfigHistory(
        limit: Int? = null,
        now: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.surfaces.MeshConfigHistory {
        val method = "getMeshConfigHistory"
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/mesh-config/history") {
                token?.let { header("Authorization", "Bearer $it") }
                limit?.let { parameter("limit", it) }
                now?.let { parameter("now", it) }
            }
            decodeSurfaceBody(
                method,
                response.bodyAsText(),
                response.status,
                ai.ciris.mobile.shared.models.surfaces.MeshConfigHistory.serializer(),
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * The durable path — `POST {nodeUrl}/v1/mesh-config/durable`. Owner-gated
     * on the never-delegatable `wipe` verb.
     *
     * With `dry_run` the node signs and submits NOTHING and hands back the
     * canonical envelope + `payload_sha256` a co-signer must sign. Which acts
     * earn a durable setting is the substrate's ruling, re-read per call.
     */
    suspend fun postMeshConfigDurable(
        request: ai.ciris.mobile.shared.models.surfaces.MeshConfigDurableRequest,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.surfaces.MeshConfigWriteResult {
        val method = "postMeshConfigDurable"
        logInfo(method, "POST $nodeUrl/v1/mesh-config/durable key=${request.key} dry_run=${request.dryRun}")
        val client = federationHttpClient()
        return try {
            val body = jsonConfig.encodeToString(
                ai.ciris.mobile.shared.models.surfaces.MeshConfigDurableRequest.serializer(),
                request,
            )
            val response = client.post("$nodeUrl/v1/mesh-config/durable") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(body)
            }
            decodeSurfaceBody(
                method,
                response.bodyAsText(),
                response.status,
                ai.ciris.mobile.shared.models.surfaces.MeshConfigWriteResult.serializer(),
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl, key=${request.key}")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * The emergency relief path — `POST {nodeUrl}/v1/mesh-config/relief`.
     * `ttl_hours` is mandatory: relief that does not expire is not relief. The
     * BOUND is the substrate's (`ttl_too_long`); this client never clamps.
     */
    suspend fun postMeshConfigRelief(
        request: ai.ciris.mobile.shared.models.surfaces.MeshConfigReliefRequest,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.surfaces.MeshConfigWriteResult {
        val method = "postMeshConfigRelief"
        logInfo(method, "POST $nodeUrl/v1/mesh-config/relief key=${request.key} ttl_hours=${request.ttlHours}")
        val client = federationHttpClient()
        return try {
            val body = jsonConfig.encodeToString(
                ai.ciris.mobile.shared.models.surfaces.MeshConfigReliefRequest.serializer(),
                request,
            )
            val response = client.post("$nodeUrl/v1/mesh-config/relief") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(body)
            }
            decodeSurfaceBody(
                method,
                response.bodyAsText(),
                response.status,
                ai.ciris.mobile.shared.models.surfaces.MeshConfigWriteResult.serializer(),
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl, key=${request.key}")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * The commons' live answer about ONE action —
     * `GET {nodeUrl}/v1/commons/standing`.
     *
     * [cohort] is `family` | `community` | `affiliations`; `self` is refused
     * with its own token because one identity's own devices are not a commons.
     */
    suspend fun getCommonsStanding(
        cohort: String,
        cohortKeyId: String,
        actionId: String,
        now: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.surfaces.CommonsStanding {
        val method = "getCommonsStanding"
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/commons/standing") {
                token?.let { header("Authorization", "Bearer $it") }
                parameter("cohort", cohort)
                parameter("cohort_key_id", cohortKeyId)
                parameter("action_id", actionId)
                now?.let { parameter("now", it) }
            }
            decodeSurfaceBody(
                method,
                response.bodyAsText(),
                response.status,
                ai.ciris.mobile.shared.models.surfaces.CommonsStanding.serializer(),
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl, cohort=$cohort, action=$actionId")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * **Raise the brake** — `POST {nodeUrl}/v1/commons/objections`. One member
     * is enough; there is no threshold to reach. `grounds` is mandatory and is
     * recorded, never interpreted.
     */
    suspend fun postCommonsObjection(
        request: ai.ciris.mobile.shared.models.surfaces.CommonsObjectionRequest,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.surfaces.CommonsWriteResult {
        val method = "postCommonsObjection"
        logInfo(method, "POST $nodeUrl/v1/commons/objections action=${request.actionId}")
        val client = federationHttpClient()
        return try {
            val body = jsonConfig.encodeToString(
                ai.ciris.mobile.shared.models.surfaces.CommonsObjectionRequest.serializer(),
                request,
            )
            val response = client.post("$nodeUrl/v1/commons/objections") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(body)
            }
            decodeSurfaceBody(
                method,
                response.bodyAsText(),
                response.status,
                ai.ciris.mobile.shared.models.surfaces.CommonsWriteResult.serializer(),
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl, action=${request.actionId}")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Cast an upholding / overruling ballot — `POST {nodeUrl}/v1/commons/ballots`.
     *
     * A ballot has NO force on its own: its price is paid at read time against
     * a denominator that does not exist yet when it is cast. A member may change
     * their mind; the latest ballot governs.
     */
    suspend fun postCommonsBallot(
        request: ai.ciris.mobile.shared.models.surfaces.CommonsBallotRequest,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.surfaces.CommonsWriteResult {
        val method = "postCommonsBallot"
        logInfo(method, "POST $nodeUrl/v1/commons/ballots objection=${request.objectionId} upholds=${request.upholds}")
        val client = federationHttpClient()
        return try {
            val body = jsonConfig.encodeToString(
                ai.ciris.mobile.shared.models.surfaces.CommonsBallotRequest.serializer(),
                request,
            )
            val response = client.post("$nodeUrl/v1/commons/ballots") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(body)
            }
            decodeSurfaceBody(
                method,
                response.bodyAsText(),
                response.status,
                ai.ciris.mobile.shared.models.surfaces.CommonsWriteResult.serializer(),
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl, objection=${request.objectionId}")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * **Lift a brake** — `POST {nodeUrl}/v1/commons/dismissals`. This one costs
     * the cohort's m-of-n, and the returned `quorum` names what was counted
     * against what was required on BOTH arms.
     *
     * With `dry_run` nothing is signed or submitted: the response carries the
     * canonical envelope and the `payload_sha256` every co-signer must sign.
     * The m-of-n is unreachable without that step.
     */
    suspend fun postCommonsDismissal(
        request: ai.ciris.mobile.shared.models.surfaces.CommonsDismissalRequest,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.surfaces.CommonsWriteResult {
        val method = "postCommonsDismissal"
        logInfo(
            method,
            "POST $nodeUrl/v1/commons/dismissals objection=${request.objectionId} " +
                "dry_run=${request.dryRun} co_signers=${request.additionalScrubs.size}",
        )
        val client = federationHttpClient()
        return try {
            val body = jsonConfig.encodeToString(
                ai.ciris.mobile.shared.models.surfaces.CommonsDismissalRequest.serializer(),
                request,
            )
            val response = client.post("$nodeUrl/v1/commons/dismissals") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(body)
            }
            decodeSurfaceBody(
                method,
                response.bodyAsText(),
                response.status,
                ai.ciris.mobile.shared.models.surfaces.CommonsWriteResult.serializer(),
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl, objection=${request.objectionId}")
            throw e
        } finally {
            client.close()
        }
    }

    // ─── HUMANITY_ACCORD surface (/v1/accord*) — CIRISServer #41 (src/accord.rs) ─
    //
    // The constitutional safe-mesh floor: a hardware-attested holder roster that
    // jointly holds a `quorum:2/3` kill-switch over invocations (CC 4.2.1). The app
    // drives the LOCAL node only (owner session); it holds NO keys and performs NO
    // crypto. `concur` just POSTs — the node's resolved local holder signer signs.

    /** The accord family + consensus protocol — `GET {nodeUrl}/v1/accord/family`. */
    suspend fun getAccordFamily(
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.AccordFamilyDto? {
        val method = "getAccordFamily"
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/accord/family") {
                token?.let { header("Authorization", "Bearer $it") }
            }
            val raw = response.bodyAsText()
            // 404 / empty body = no accord family established yet.
            if (response.status == HttpStatusCode.NotFound || raw.isBlank()) {
                return null
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("get accord family failed: ${response.status}: ${raw.take(160)}")
            }
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.AccordFamilyDto.serializer(),
                raw,
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /** The accord holder registry — `GET {nodeUrl}/v1/accord-holders`. */
    suspend fun getAccordHolders(
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.AccordHoldersResponse {
        val method = "getAccordHolders"
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/accord-holders") {
                token?.let { header("Authorization", "Bearer $it") }
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("get accord holders failed: ${response.status}: ${raw.take(160)}")
            }
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.AccordHoldersResponse.serializer(),
                raw,
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /** Pending accord invocations + quorum status — `GET {nodeUrl}/v1/accord/invocations`. */
    suspend fun getAccordInvocations(
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): List<ai.ciris.mobile.shared.models.federation.AccordInvocationDto> {
        val method = "getAccordInvocations"
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/accord/invocations") {
                token?.let { header("Authorization", "Bearer $it") }
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("get accord invocations failed: ${response.status}: ${raw.take(160)}")
            }
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.AccordInvocationsResponse.serializer(),
                raw,
            ).invocations
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Concur on a pending invocation as an accord holder —
     * `POST {nodeUrl}/v1/accord/invocation/concur`. Owner-session-gated. The app
     * holds NO keys: it posts the holder's fed [holderKeyId] + [mldsaUsbPath] + PIN
     * and the node RE-OPENS the holder's YubiKey + USB-wrapped ML-DSA and produces
     * the cosignature over the pending invocation's canonical bytes (mirrors
     * admit-node). Touch-gated — a touch-required slot 9c BLOCKS the call until tapped.
     */
    suspend fun concurInvocation(
        invocationKind: String,
        invocationId: String,
        holderKeyId: String,
        mldsaUsbPath: String,
        userPin: String? = null,
        pivSlot: String? = null,
        modulePath: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.AccordConcurResponse {
        val method = "concurInvocation"
        logInfo(method, "POST $nodeUrl/v1/accord/invocation/concur kind=$invocationKind id=$invocationId holder=$holderKeyId usb=$mldsaUsbPath")
        // Touch-gated (slot 9c is touch-ALWAYS) — long timeout + the caller prompts.
        val client = federationHttpClient(ceremonyTimeoutMillis)
        return try {
            val pkcs11 = buildJsonObject {
                userPin?.takeIf { it.isNotBlank() }?.let { put("user_pin", JsonPrimitive(it)) }
                pivSlot?.takeIf { it.isNotBlank() }?.let { put("piv_slot", JsonPrimitive(it)) }
                modulePath?.takeIf { it.isNotBlank() }?.let { put("module_path", JsonPrimitive(it)) }
            }
            val bodyJson = buildJsonObject {
                put("invocation_kind", JsonPrimitive(invocationKind.trim()))
                put("invocation_id", JsonPrimitive(invocationId.trim()))
                put("key_id", JsonPrimitive(holderKeyId.trim()))
                put("mldsa_usb_path", JsonPrimitive(mldsaUsbPath.trim()))
                put("pkcs11", pkcs11)
            }
            val response = client.post("$nodeUrl/v1/accord/invocation/concur") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyJson.toString())
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("concur failed: ${response.status}: ${raw.take(160)}")
            }
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.AccordConcurResponse.serializer(),
                raw,
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * The surfaced NON-BINDING accord events (completed drills + announcements) —
     * `GET {nodeUrl}/v1/accord/events` (CIRISServer#41). Public read.
     */
    suspend fun listAccordEvents(
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.AccordEventsResponse {
        val method = "listAccordEvents"
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/accord/events") {
                token?.let { header("Authorization", "Bearer $it") }
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("list accord events failed: ${response.status}: ${raw.take(160)}")
            }
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.AccordEventsResponse.serializer(),
                raw,
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * The read-only halt-latch state (the enforceable kill-switch) —
     * `GET {nodeUrl}/v1/accord/halt-status` (CIRISServer#41). Public read; drives
     * the unmissable ACTIVE-HALT banner. Never writes or clears the latch.
     */
    suspend fun getAccordHaltStatus(
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.AccordHaltStatusResponse {
        val method = "getAccordHaltStatus"
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/accord/halt-status") {
                token?.let { header("Authorization", "Bearer $it") }
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("get halt-status failed: ${response.status}: ${raw.take(160)}")
            }
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.AccordHaltStatusResponse.serializer(),
                raw,
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * **Initiate a drill** — `POST {nodeUrl}/v1/accord/drill` (owner-session-gated,
     * holder action). A drill is a NON-BINDING rehearsal of the 2-of-3 kill-switch
     * delivery path; it accumulates cosignatures toward quorum via
     * `/v1/accord/invocation/concur` and, on reaching it, is surfaced in
     * `/v1/accord/events` — it NEVER halts. Mirrors [concurInvocation]'s no-crypto
     * posture: the node builds + signs the drill invocation with its resolved local
     * holder signer; the app sends no crypto.
     */
    suspend fun initiateDrill(
        invocationId: String,
        holderKeyId: String,
        mldsaUsbPath: String,
        userPin: String? = null,
        pivSlot: String? = null,
        modulePath: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.AccordConcurResponse {
        val method = "initiateDrill"
        logInfo(method, "POST $nodeUrl/v1/accord/drill id=$invocationId holder=$holderKeyId usb=$mldsaUsbPath")
        // Touch-gated (slot 9c is touch-ALWAYS) — long timeout + the caller prompts.
        val client = federationHttpClient(ceremonyTimeoutMillis)
        return try {
            val pkcs11 = buildJsonObject {
                userPin?.takeIf { it.isNotBlank() }?.let { put("user_pin", JsonPrimitive(it)) }
                pivSlot?.takeIf { it.isNotBlank() }?.let { put("piv_slot", JsonPrimitive(it)) }
                modulePath?.takeIf { it.isNotBlank() }?.let { put("module_path", JsonPrimitive(it)) }
            }
            // The node synthesizes the (non-binding) drill invocation from the id and
            // produces the initiating cosignature from the holder's YubiKey + USB — the
            // app holds no keys and fabricates no signed envelope.
            val bodyJson = buildJsonObject {
                put("invocation_id", JsonPrimitive(invocationId.trim()))
                put("key_id", JsonPrimitive(holderKeyId.trim()))
                put("mldsa_usb_path", JsonPrimitive(mldsaUsbPath.trim()))
                put("pkcs11", pkcs11)
            }
            val response = client.post("$nodeUrl/v1/accord/drill") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyJson.toString())
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("initiate drill failed: ${response.status}: ${raw.take(200)}")
            }
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.AccordConcurResponse.serializer(),
                raw,
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * **Raise a halt** — `POST {nodeUrl}/v1/accord/halt` (owner-session-gated, holder
     * action). RAISES a 2-of-3 CONSTITUTIONAL kill-switch invocation: the node synthesizes
     * the constitutional invocation from [invocationId] and produces THIS holder's initiating
     * cosignature from their YubiKey + USB. That single signature is **sub-quorum** — it does
     * NOT latch anything; it gossips and the other holders cosign via
     * `/v1/accord/invocation/concur`, and the 2-of-3-completing signature is what latches the
     * halt. The binding twin of [initiateDrill]; the app holds no keys.
     */
    suspend fun initiateHalt(
        invocationId: String,
        holderKeyId: String,
        mldsaUsbPath: String,
        userPin: String? = null,
        pivSlot: String? = null,
        modulePath: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.AccordConcurResponse {
        val method = "initiateHalt"
        logInfo(method, "POST $nodeUrl/v1/accord/halt id=$invocationId holder=$holderKeyId usb=$mldsaUsbPath")
        // Touch-gated (slot 9c is touch-ALWAYS) — long timeout + the caller prompts.
        val client = federationHttpClient(ceremonyTimeoutMillis)
        return try {
            val pkcs11 = buildJsonObject {
                userPin?.takeIf { it.isNotBlank() }?.let { put("user_pin", JsonPrimitive(it)) }
                pivSlot?.takeIf { it.isNotBlank() }?.let { put("piv_slot", JsonPrimitive(it)) }
                modulePath?.takeIf { it.isNotBlank() }?.let { put("module_path", JsonPrimitive(it)) }
            }
            val bodyJson = buildJsonObject {
                put("invocation_id", JsonPrimitive(invocationId.trim()))
                put("key_id", JsonPrimitive(holderKeyId.trim()))
                put("mldsa_usb_path", JsonPrimitive(mldsaUsbPath.trim()))
                put("pkcs11", pkcs11)
            }
            val response = client.post("$nodeUrl/v1/accord/halt") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyJson.toString())
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("raise halt failed: ${response.status}: ${raw.take(200)}")
            }
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.AccordConcurResponse.serializer(),
                raw,
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * **Post an announce** — `POST {nodeUrl}/v1/accord/announce` (owner-session-gated,
     * holder action). An announce is a single-holder `notify` message (threshold 1 —
     * complete on a valid signature); it is gossiped + surfaced in `/v1/accord/events`
     * and NEVER halts. Mirrors [concurInvocation]'s no-crypto posture: the node builds
     * + signs the notify (binding the [message] to the payload hash) with its resolved
     * local holder signer; the app sends only the plaintext.
     */
    suspend fun initiateAnnounce(
        message: String,
        holderKeyId: String,
        mldsaUsbPath: String,
        userPin: String? = null,
        pivSlot: String? = null,
        modulePath: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.AccordAnnounceResponse {
        val method = "initiateAnnounce"
        logInfo(method, "POST $nodeUrl/v1/accord/announce len=${message.length} holder=$holderKeyId usb=$mldsaUsbPath")
        // Touch-gated (slot 9c is touch-ALWAYS) — long timeout + the caller prompts.
        val client = federationHttpClient(ceremonyTimeoutMillis)
        return try {
            val pkcs11 = buildJsonObject {
                userPin?.takeIf { it.isNotBlank() }?.let { put("user_pin", JsonPrimitive(it)) }
                pivSlot?.takeIf { it.isNotBlank() }?.let { put("piv_slot", JsonPrimitive(it)) }
                modulePath?.takeIf { it.isNotBlank() }?.let { put("module_path", JsonPrimitive(it)) }
            }
            // The node synthesizes the `notify` invocation binding this message and
            // produces the cosignature from the holder's YubiKey + USB (app holds no keys).
            val bodyJson = buildJsonObject {
                put("message", JsonPrimitive(message))
                put("key_id", JsonPrimitive(holderKeyId.trim()))
                put("mldsa_usb_path", JsonPrimitive(mldsaUsbPath.trim()))
                put("pkcs11", pkcs11)
            }
            val response = client.post("$nodeUrl/v1/accord/announce") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyJson.toString())
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("initiate announce failed: ${response.status}: ${raw.take(200)}")
            }
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.AccordAnnounceResponse.serializer(),
                raw,
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * **Provision a portable accord holder** —
     * `POST {nodeUrl}/v1/accord/provision-holder`. The loopback-only setup route
     * behind the guided "Provision Accord Holder" flow (CIRISServer#41).
     *
     * The node opens the holder's ALREADY-FIPS-approved YubiKey (slot-9c Ed25519),
     * AEAD-wraps a fresh ML-DSA-65 seed to [mldsaUsbPath] (unwrappable only by the
     * YubiKey via touch + PIN), and mints the holder record + the portable_2fa
     * custody attestation. The app does NO crypto — it only POSTs to the loopback
     * endpoint; the substrate does everything.
     *
     * The ONE user choice is [mldsaUsbPath] (the USB directory). [userPin] is
     * optional (the token may prompt out of band); [pivSlot] defaults to `9c`.
     *
     * Touching the physical YubiKey (PIN + touch) is the real authority; a
     * touch-required token BLOCKS the call until tapped. On success the holder
     * asks the node owner to register them (`POST /v1/accord/holder`).
     */
    suspend fun provisionAccordHolder(
        keyId: String,
        mldsaUsbPath: String,
        userPin: String? = null,
        pivSlot: String? = null,
        modulePath: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.AccordProvisionResponse {
        val method = "provisionAccordHolder"
        logInfo(method, "POST $nodeUrl/v1/accord/provision-holder key_id=$keyId usb=$mldsaUsbPath")
        // Touch-gated: slot 9c (touch policy ALWAYS) needs a physical touch per
        // Ed25519 sign — provisioning does THREE (USB ML-DSA wrap-challenge, holder
        // record, custody attestation). Long timeout + the caller surfaces the
        // "touch each blink (~3×)" prompt.
        logInfo(method, "this needs ~3 YubiKey touches (slot 9c is touch-ALWAYS); waiting up to ${ceremonyTimeoutMillis / 1000}s")
        val client = federationHttpClient(ceremonyTimeoutMillis)
        return try {
            val pkcs11 = buildJsonObject {
                userPin?.takeIf { it.isNotBlank() }?.let { put("user_pin", JsonPrimitive(it)) }
                pivSlot?.takeIf { it.isNotBlank() }?.let { put("piv_slot", JsonPrimitive(it)) }
                modulePath?.takeIf { it.isNotBlank() }?.let { put("module_path", JsonPrimitive(it)) }
            }
            val bodyJson = buildJsonObject {
                put("key_id", JsonPrimitive(keyId.trim()))
                put("mldsa_usb_path", JsonPrimitive(mldsaUsbPath.trim()))
                put("pkcs11", pkcs11)
            }
            val response = client.post("$nodeUrl/v1/accord/provision-holder") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyJson.toString())
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("provision holder failed: ${response.status}: ${raw.take(220)}")
            }
            val parsed = jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.AccordProvisionResponse.serializer(),
                raw,
            )
            logInfo(method, "provisioned key_id=${parsed.keyId} (custody=${parsed.custodyAttestation != null})")
            parsed
        } catch (e: Exception) {
            val hint = if (e is io.ktor.client.plugins.HttpRequestTimeoutException) {
                " — timed out waiting for YubiKey touches; touch the key EACH time it blinks (≈3×) and retry"
            } else {
                ""
            }
            logException(method, e, "nodeUrl=$nodeUrl$hint")
            throw RuntimeException("${e.message ?: "provision failed"}$hint", e)
        } finally {
            client.close()
        }
    }

    /**
     * **Admit a node to the trust root** — `POST {nodeUrl}/v1/accord/admit-node`
     * (loopback, CIRISServer#140 / CIRISVerify#162). The accord holder (A1) RE-OPENS
     * their YubiKey + USB-wrapped ML-DSA and **scrub-signs** the target node's
     * registration (+ emits their own `steward,accord_holder` anchor). The node
     * writes the resulting **admission records** to a predictable outbox path and
     * returns them — not the seed, which is the `GenesisBundle` the genesis ceremony
     * saves to `<home>/mesh-genesis.json`.
     * The app holds NO keys — the touch on the YubiKey IS consent.
     * 1-of-N bootstrap: a single holder suffices (a trust EXTENSION, not the 2/3
     * kill-switch). The target's pubkeys come from the node's self-key-record.
     */
    suspend fun admitNode(
        holderKeyId: String,
        mldsaUsbPath: String,
        targetKeyId: String,
        targetEd25519Base64: String,
        targetMlDsa65Base64: String,
        targetIdentityType: String = "node",
        userPin: String? = null,
        pivSlot: String? = null,
        modulePath: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.AdmitNodeResponse {
        val method = "admitNode"
        logInfo(method, "POST $nodeUrl/v1/accord/admit-node holder=$holderKeyId target=$targetKeyId usb=$mldsaUsbPath")
        logInfo(method, "needs a YubiKey touch (slot 9c is touch-ALWAYS) for the scrub + anchor signatures; waiting up to ${ceremonyTimeoutMillis / 1000}s")
        val client = federationHttpClient(ceremonyTimeoutMillis)
        return try {
            val pkcs11 = buildJsonObject {
                userPin?.takeIf { it.isNotBlank() }?.let { put("user_pin", JsonPrimitive(it)) }
                pivSlot?.takeIf { it.isNotBlank() }?.let { put("piv_slot", JsonPrimitive(it)) }
                modulePath?.takeIf { it.isNotBlank() }?.let { put("module_path", JsonPrimitive(it)) }
            }
            val target = buildJsonObject {
                put("key_id", JsonPrimitive(targetKeyId.trim()))
                put("pubkey_ed25519_base64", JsonPrimitive(targetEd25519Base64.trim()))
                put("pubkey_ml_dsa_65_base64", JsonPrimitive(targetMlDsa65Base64.trim()))
                put("identity_type", JsonPrimitive(targetIdentityType.trim().ifBlank { "node" }))
            }
            val bodyJson = buildJsonObject {
                put("key_id", JsonPrimitive(holderKeyId.trim()))
                put("mldsa_usb_path", JsonPrimitive(mldsaUsbPath.trim()))
                put("pkcs11", pkcs11)
                put("target", target)
            }
            val response = client.post("$nodeUrl/v1/accord/admit-node") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyJson.toString())
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("admit node failed: ${response.status}: ${raw.take(220)}")
            }
            val parsed = jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.AdmitNodeResponse.serializer(),
                raw,
            )
            logInfo(method, "admitted target=$targetKeyId → saved seed to ${parsed.savedTo}")
            parsed
        } catch (e: Exception) {
            val hint = if (e is io.ktor.client.plugins.HttpRequestTimeoutException) {
                " — timed out waiting for the YubiKey touch; touch the key when it blinks and retry"
            } else {
                ""
            }
            logException(method, e, "nodeUrl=$nodeUrl$hint")
            throw RuntimeException("${e.message ?: "admit node failed"}$hint", e)
        } finally {
            client.close()
        }
    }

    /**
     * **List canonical servers** — `GET {nodeUrl}/v1/accord/canonical/servers`
     * (CIRISServer#164). The rock-solid mesh-seed anchors: nodes whose registration
     * an accord holder scrub-signed AND flagged `canonical`. Visible to everyone.
     */
    suspend fun listCanonicalServers(
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.CanonicalServersResponse {
        val method = "listCanonicalServers"
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/accord/canonical/servers") {
                token?.let { header("Authorization", "Bearer $it") }
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("list canonical servers failed: ${response.status}: ${raw.take(220)}")
            }
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.CanonicalServersResponse.serializer(),
                raw,
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            ai.ciris.mobile.shared.models.federation.CanonicalServersResponse()
        } finally {
            client.close()
        }
    }

    /**
     * **Add a canonical server** — `POST {nodeUrl}/v1/accord/canonical/add`
     * (loopback, CIRISServer#164). The accord holder RE-OPENS their YubiKey +
     * USB-wrapped ML-DSA and **scrub-signs** the target node's registration, ALSO
     * flagging it `canonical` so it becomes a mesh-seed anchor. Same hardware inputs
     * as [admitNode], plus the target's pubkeys and an OPTIONAL bootstrap transport
     * ([transportKind] + [destination]) recorded as the canonical server's address.
     * 1-of-N: a single holder suffices. The app holds NO keys — the touch IS consent.
     */
    suspend fun addCanonicalServer(
        holderKeyId: String,
        mldsaUsbPath: String,
        targetKeyId: String,
        targetEd25519Base64: String,
        targetMlDsa65Base64: String,
        targetIdentityType: String = "node",
        userPin: String? = null,
        pivSlot: String? = null,
        modulePath: String? = null,
        transportKind: String? = null,
        destination: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.AddCanonicalServerResponse {
        val method = "addCanonicalServer"
        logInfo(method, "POST $nodeUrl/v1/accord/canonical/add holder=$holderKeyId target=$targetKeyId usb=$mldsaUsbPath")
        logInfo(method, "needs a YubiKey touch (slot 9c is touch-ALWAYS) for the scrub signature; waiting up to ${ceremonyTimeoutMillis / 1000}s")
        val client = federationHttpClient(ceremonyTimeoutMillis)
        return try {
            val pkcs11 = buildJsonObject {
                userPin?.takeIf { it.isNotBlank() }?.let { put("user_pin", JsonPrimitive(it)) }
                pivSlot?.takeIf { it.isNotBlank() }?.let { put("piv_slot", JsonPrimitive(it)) }
                modulePath?.takeIf { it.isNotBlank() }?.let { put("module_path", JsonPrimitive(it)) }
            }
            val target = buildJsonObject {
                put("key_id", JsonPrimitive(targetKeyId.trim()))
                put("pubkey_ed25519_base64", JsonPrimitive(targetEd25519Base64.trim()))
                put("pubkey_ml_dsa_65_base64", JsonPrimitive(targetMlDsa65Base64.trim()))
                put("identity_type", JsonPrimitive(targetIdentityType.trim().ifBlank { "node" }))
            }
            val bodyJson = buildJsonObject {
                put("key_id", JsonPrimitive(holderKeyId.trim()))
                put("mldsa_usb_path", JsonPrimitive(mldsaUsbPath.trim()))
                put("pkcs11", pkcs11)
                put("target", target)
                transportKind?.takeIf { it.isNotBlank() }?.let { put("transport_kind", JsonPrimitive(it.trim())) }
                destination?.takeIf { it.isNotBlank() }?.let { put("destination", JsonPrimitive(it.trim())) }
            }
            val response = client.post("$nodeUrl/v1/accord/canonical/add") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyJson.toString())
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("add canonical server failed: ${response.status}: ${raw.take(220)}")
            }
            val parsed = jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.AddCanonicalServerResponse.serializer(),
                raw,
            )
            logInfo(
                method,
                "added canonical=${parsed.canonicalKeyId} → admission records at ${parsed.admissionRecordsPath}",
            )
            parsed
        } catch (e: Exception) {
            val hint = if (e is io.ktor.client.plugins.HttpRequestTimeoutException) {
                " — timed out waiting for the YubiKey touch; touch the key when it blinks and retry"
            } else {
                ""
            }
            logException(method, e, "nodeUrl=$nodeUrl$hint")
            throw RuntimeException("${e.message ?: "add canonical server failed"}$hint", e)
        } finally {
            client.close()
        }
    }

    /**
     * **Withdraw a canonical server** — `POST {nodeUrl}/v1/accord/canonical/withdraw`
     * (CIRISServer#164). DESTRUCTIVE: needs a 2-of-3 accord proposal (a second/third
     * holder must co-sign) — a lone holder cannot complete it. [proposalDigest] names
     * the accord proposal this withdrawal is authorized under.
     */
    suspend fun withdrawCanonical(
        keyId: String,
        proposalDigest: String,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.CanonicalWithdrawResponse {
        val method = "withdrawCanonical"
        logInfo(method, "POST $nodeUrl/v1/accord/canonical/withdraw key_id=$keyId")
        val client = federationHttpClient()
        return try {
            val bodyJson = buildJsonObject {
                put("key_id", JsonPrimitive(keyId.trim()))
                put("proposal_digest", JsonPrimitive(proposalDigest.trim()))
            }
            val response = client.post("$nodeUrl/v1/accord/canonical/withdraw") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyJson.toString())
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("withdraw canonical failed: ${response.status}: ${raw.take(220)}")
            }
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.CanonicalWithdrawResponse.serializer(),
                raw,
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw RuntimeException(e.message ?: "withdraw canonical failed", e)
        } finally {
            client.close()
        }
    }

    /**
     * **List withdrawn / superseded canonical servers** —
     * `GET {nodeUrl}/v1/accord/canonical/withdrawals` (CIRISServer#164). The audit
     * log of canonical records that were withdrawn or superseded. Visible to everyone.
     */
    suspend fun listCanonicalWithdrawals(
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.CanonicalWithdrawalsResponse {
        val method = "listCanonicalWithdrawals"
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/accord/canonical/withdrawals") {
                token?.let { header("Authorization", "Bearer $it") }
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("list canonical withdrawals failed: ${response.status}: ${raw.take(220)}")
            }
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.CanonicalWithdrawalsResponse.serializer(),
                raw,
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            ai.ciris.mobile.shared.models.federation.CanonicalWithdrawalsResponse()
        } finally {
            client.close()
        }
    }

    /**
     * **Propose a canonical server (co-scrub scrub #1)** —
     * `POST {nodeUrl}/v1/accord/canonical/propose` (CIRISServer#174). The local accord
     * holder (A1) RE-OPENS their YubiKey + USB-wrapped ML-DSA and scrub-signs the
     * target as `canonical`, producing a 1-scrub **partial** that does NOT yet confer
     * canonical (m-of-n). The node saves + gossips it to accord peers; hand / gossip it
     * to the next holder to [cosignCanonicalServer]. Same hardware + body shape as
     * [addCanonicalServer]. The app holds NO keys — the YubiKey touch is consent.
     */
    suspend fun proposeCanonicalServer(
        holderKeyId: String,
        mldsaUsbPath: String,
        targetKeyId: String,
        targetEd25519Base64: String,
        targetMlDsa65Base64: String,
        targetIdentityType: String = "node",
        userPin: String? = null,
        pivSlot: String? = null,
        modulePath: String? = null,
        transportKind: String? = null,
        destination: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.ProposeCanonicalResponse {
        val method = "proposeCanonicalServer"
        logInfo(method, "POST $nodeUrl/v1/accord/canonical/propose holder=$holderKeyId target=$targetKeyId usb=$mldsaUsbPath")
        logInfo(method, "needs a YubiKey touch (slot 9c is touch-ALWAYS) for the scrub signature; waiting up to ${ceremonyTimeoutMillis / 1000}s")
        val client = federationHttpClient(ceremonyTimeoutMillis)
        return try {
            val pkcs11 = buildJsonObject {
                userPin?.takeIf { it.isNotBlank() }?.let { put("user_pin", JsonPrimitive(it)) }
                pivSlot?.takeIf { it.isNotBlank() }?.let { put("piv_slot", JsonPrimitive(it)) }
                modulePath?.takeIf { it.isNotBlank() }?.let { put("module_path", JsonPrimitive(it)) }
            }
            val target = buildJsonObject {
                put("key_id", JsonPrimitive(targetKeyId.trim()))
                put("pubkey_ed25519_base64", JsonPrimitive(targetEd25519Base64.trim()))
                put("pubkey_ml_dsa_65_base64", JsonPrimitive(targetMlDsa65Base64.trim()))
                put("identity_type", JsonPrimitive(targetIdentityType.trim().ifBlank { "node" }))
            }
            val bodyJson = buildJsonObject {
                put("key_id", JsonPrimitive(holderKeyId.trim()))
                put("mldsa_usb_path", JsonPrimitive(mldsaUsbPath.trim()))
                put("pkcs11", pkcs11)
                put("target", target)
                transportKind?.takeIf { it.isNotBlank() }?.let { put("transport_kind", JsonPrimitive(it.trim())) }
                destination?.takeIf { it.isNotBlank() }?.let { put("destination", JsonPrimitive(it.trim())) }
            }
            val response = client.post("$nodeUrl/v1/accord/canonical/propose") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyJson.toString())
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("propose canonical failed: ${response.status}: ${raw.take(220)}")
            }
            val parsed = jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.ProposeCanonicalResponse.serializer(),
                raw,
            )
            logInfo(method, "proposed ${parsed.targetKeyId} scrubs=${parsed.distinctScrubCount} gossiped_to=${parsed.gossipedTo}")
            parsed
        } catch (e: Exception) {
            val hint = if (e is io.ktor.client.plugins.HttpRequestTimeoutException) {
                " — timed out waiting for the YubiKey touch; touch the key when it blinks and retry"
            } else {
                ""
            }
            logException(method, e, "nodeUrl=$nodeUrl$hint")
            throw RuntimeException("${e.message ?: "propose canonical failed"}$hint", e)
        } finally {
            client.close()
        }
    }

    /**
     * **Cosign a canonical co-scrub** — `POST {nodeUrl}/v1/accord/canonical/cosign`
     * (CIRISServer#174). THIS holder (e.g. B1) RE-OPENS their YubiKey + USB ML-DSA and
     * appends their scrub to the [partial] over the BYTE-IDENTICAL envelope (verify's
     * `append_scrub`). [partial] MUST be the verbatim `SignedKeyRecord` JSON from a
     * [proposeCanonicalServer] / prior cosign (a pending entry's `partial`, or a pasted
     * one) — it is submitted UNCHANGED so the canonical bytes match. At the family
     * m-of-n the record is adopted (`conferred`); else the advanced partial is returned.
     */
    suspend fun cosignCanonicalServer(
        holderKeyId: String,
        mldsaUsbPath: String,
        partial: JsonElement,
        userPin: String? = null,
        pivSlot: String? = null,
        modulePath: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.CosignCanonicalResponse {
        val method = "cosignCanonicalServer"
        logInfo(method, "POST $nodeUrl/v1/accord/canonical/cosign holder=$holderKeyId usb=$mldsaUsbPath")
        logInfo(method, "needs a YubiKey touch (slot 9c is touch-ALWAYS) for the scrub signature; waiting up to ${ceremonyTimeoutMillis / 1000}s")
        val client = federationHttpClient(ceremonyTimeoutMillis)
        return try {
            val pkcs11 = buildJsonObject {
                userPin?.takeIf { it.isNotBlank() }?.let { put("user_pin", JsonPrimitive(it)) }
                pivSlot?.takeIf { it.isNotBlank() }?.let { put("piv_slot", JsonPrimitive(it)) }
                modulePath?.takeIf { it.isNotBlank() }?.let { put("module_path", JsonPrimitive(it)) }
            }
            val bodyJson = buildJsonObject {
                put("key_id", JsonPrimitive(holderKeyId.trim()))
                put("mldsa_usb_path", JsonPrimitive(mldsaUsbPath.trim()))
                put("pkcs11", pkcs11)
                // Submit the partial VERBATIM — never re-encode the signed envelope.
                put("partial", partial)
            }
            val response = client.post("$nodeUrl/v1/accord/canonical/cosign") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyJson.toString())
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("cosign canonical failed: ${response.status}: ${raw.take(220)}")
            }
            val parsed = jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.CosignCanonicalResponse.serializer(),
                raw,
            )
            logInfo(method, "cosigned ${parsed.targetKeyId} scrubs=${parsed.distinctScrubCount} conferred=${parsed.conferred} gossiped_to=${parsed.gossipedTo}")
            parsed
        } catch (e: Exception) {
            val hint = if (e is io.ktor.client.plugins.HttpRequestTimeoutException) {
                " — timed out waiting for the YubiKey touch; touch the key when it blinks and retry"
            } else {
                ""
            }
            logException(method, e, "nodeUrl=$nodeUrl$hint")
            throw RuntimeException("${e.message ?: "cosign canonical failed"}$hint", e)
        } finally {
            client.close()
        }
    }

    /**
     * **Propose a batch of CI-worker keys (co-scrub scrub #1)** —
     * `POST {nodeUrl}/v1/accord/ci-key/propose`. The BATCH twin of
     * [proposeCanonicalServer]: the local accord holder RE-OPENS their YubiKey +
     * USB-wrapped ML-DSA and scrub-signs EVERY [targets] node key in ONE ceremony
     * (roles set `infra:attest` server-side — the app sends no roles). Same hardware
     * inputs; the target list rides as a `targets` ARRAY. Each result is a single
     * co-scrub propose. The app holds NO keys — the YubiKey touch is consent.
     */
    suspend fun proposeCiKeys(
        holderKeyId: String,
        mldsaUsbPath: String,
        userPin: String? = null,
        targets: List<ai.ciris.mobile.shared.models.federation.CiKeyTargetInput>,
        pivSlot: String? = null,
        modulePath: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.CiKeyProposeResponse {
        val method = "proposeCiKeys"
        logInfo(method, "POST $nodeUrl/v1/accord/ci-key/propose holder=$holderKeyId targets=${targets.size} usb=$mldsaUsbPath")
        logInfo(method, "needs a YubiKey touch (slot 9c is touch-ALWAYS) for the scrub signatures; waiting up to ${ceremonyTimeoutMillis / 1000}s")
        val client = federationHttpClient(ceremonyTimeoutMillis)
        return try {
            val pkcs11 = buildJsonObject {
                userPin?.takeIf { it.isNotBlank() }?.let { put("user_pin", JsonPrimitive(it)) }
                pivSlot?.takeIf { it.isNotBlank() }?.let { put("piv_slot", JsonPrimitive(it)) }
                modulePath?.takeIf { it.isNotBlank() }?.let { put("module_path", JsonPrimitive(it)) }
            }
            val targetsJson = JsonArray(
                targets.map { t ->
                    buildJsonObject {
                        put("key_id", JsonPrimitive(t.keyId.trim()))
                        put("pubkey_ed25519_base64", JsonPrimitive(t.pubkeyEd25519Base64.trim()))
                        put("pubkey_ml_dsa_65_base64", JsonPrimitive(t.pubkeyMlDsa65Base64.trim()))
                        put("identity_type", JsonPrimitive(t.identityType.trim().ifBlank { "node" }))
                    }
                },
            )
            val bodyJson = buildJsonObject {
                put("key_id", JsonPrimitive(holderKeyId.trim()))
                put("mldsa_usb_path", JsonPrimitive(mldsaUsbPath.trim()))
                put("pkcs11", pkcs11)
                put("targets", targetsJson)
            }
            val response = client.post("$nodeUrl/v1/accord/ci-key/propose") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyJson.toString())
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("propose ci-keys failed: ${response.status}: ${raw.take(220)}")
            }
            val parsed = jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.CiKeyProposeResponse.serializer(),
                raw,
            )
            logInfo(method, "proposed ci-keys results=${parsed.results.size}")
            parsed
        } catch (e: Exception) {
            val hint = if (e is io.ktor.client.plugins.HttpRequestTimeoutException) {
                " — timed out waiting for the YubiKey touch; touch the key when it blinks and retry"
            } else {
                ""
            }
            logException(method, e, "nodeUrl=$nodeUrl$hint")
            throw RuntimeException("${e.message ?: "propose ci-keys failed"}$hint", e)
        } finally {
            client.close()
        }
    }

    /**
     * **Cosign a batch of CI-worker co-scrubs** —
     * `POST {nodeUrl}/v1/accord/ci-key/cosign`. The BATCH twin of
     * [cosignCanonicalServer]: THIS holder RE-OPENS their YubiKey + USB ML-DSA and
     * appends their scrub to EVERY [partials] `SignedKeyRecord` over the BYTE-IDENTICAL
     * envelope. Each partial rides as a raw [JsonElement] and is submitted UNCHANGED so
     * the canonical bytes match. Each result is a single co-scrub cosign.
     */
    suspend fun cosignCiKeys(
        holderKeyId: String,
        mldsaUsbPath: String,
        userPin: String? = null,
        partials: List<JsonElement>,
        pivSlot: String? = null,
        modulePath: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.CiKeyCosignResponse {
        val method = "cosignCiKeys"
        logInfo(method, "POST $nodeUrl/v1/accord/ci-key/cosign holder=$holderKeyId partials=${partials.size} usb=$mldsaUsbPath")
        logInfo(method, "needs a YubiKey touch (slot 9c is touch-ALWAYS) for the scrub signatures; waiting up to ${ceremonyTimeoutMillis / 1000}s")
        val client = federationHttpClient(ceremonyTimeoutMillis)
        return try {
            val pkcs11 = buildJsonObject {
                userPin?.takeIf { it.isNotBlank() }?.let { put("user_pin", JsonPrimitive(it)) }
                pivSlot?.takeIf { it.isNotBlank() }?.let { put("piv_slot", JsonPrimitive(it)) }
                modulePath?.takeIf { it.isNotBlank() }?.let { put("module_path", JsonPrimitive(it)) }
            }
            val bodyJson = buildJsonObject {
                put("key_id", JsonPrimitive(holderKeyId.trim()))
                put("mldsa_usb_path", JsonPrimitive(mldsaUsbPath.trim()))
                put("pkcs11", pkcs11)
                // Submit the partials VERBATIM — never re-encode the signed envelopes.
                put("partials", JsonArray(partials))
            }
            val response = client.post("$nodeUrl/v1/accord/ci-key/cosign") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyJson.toString())
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("cosign ci-keys failed: ${response.status}: ${raw.take(220)}")
            }
            val parsed = jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.CiKeyCosignResponse.serializer(),
                raw,
            )
            logInfo(method, "cosigned ci-keys results=${parsed.results.size} conferred=${parsed.results.count { it.conferred }}")
            parsed
        } catch (e: Exception) {
            val hint = if (e is io.ktor.client.plugins.HttpRequestTimeoutException) {
                " — timed out waiting for the YubiKey touch; touch the key when it blinks and retry"
            } else {
                ""
            }
            logException(method, e, "nodeUrl=$nodeUrl$hint")
            throw RuntimeException("${e.message ?: "cosign ci-keys failed"}$hint", e)
        } finally {
            client.close()
        }
    }

    /**
     * **List pending canonical co-scrubs** —
     * `GET {nodeUrl}/v1/accord/canonical/pending` (CIRISServer#174). The co-scrub
     * partials this node holds that are still short of the family m-of-n (arrived via
     * accord gossip or a local propose). Backs the Trust Root's "Pending co-signs"
     * section. Read-only; never throws (returns empty on any error).
     */
    suspend fun listPendingCoscrubs(
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): List<ai.ciris.mobile.shared.models.federation.PendingCoscrubDto> {
        val method = "listPendingCoscrubs"
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/accord/canonical/pending") {
                token?.let { header("Authorization", "Bearer $it") }
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("list pending co-scrubs failed: ${response.status}: ${raw.take(220)}")
            }
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.PendingCoscrubsResponse.serializer(),
                raw,
            ).pending
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            emptyList()
        } finally {
            client.close()
        }
    }

    /**
     * **Supersede a canonical server** — `POST {nodeUrl}/v1/accord/canonical/supersede`
     * (CIRISServer#174). DESTRUCTIVE / 2-of-3: admits the successor [newRecord] (a full
     * A1-scrubbed `SignedKeyRecord`, assembled by the add-canonical / co-scrub ceremony)
     * BEFORE tombstoning [oldKeyId] with `superseded_by`, so the canonical set is never
     * momentarily empty. [proposalDigest] names the authorizing accord proposal; persist
     * re-tallies it. [newRecord] rides verbatim (never re-encoded). Mirrors
     * [withdrawCanonical].
     */
    suspend fun supersedeCanonical(
        oldKeyId: String,
        newRecord: JsonElement,
        proposalDigest: String,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.CanonicalSupersedeResponse {
        val method = "supersedeCanonical"
        logInfo(method, "POST $nodeUrl/v1/accord/canonical/supersede old_key_id=$oldKeyId")
        val client = federationHttpClient()
        return try {
            val bodyJson = buildJsonObject {
                put("old_key_id", JsonPrimitive(oldKeyId.trim()))
                // The successor record VERBATIM — never re-encode the signed envelope.
                put("new_record", newRecord)
                put("proposal_digest", JsonPrimitive(proposalDigest.trim()))
            }
            val response = client.post("$nodeUrl/v1/accord/canonical/supersede") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyJson.toString())
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("supersede canonical failed: ${response.status}: ${raw.take(220)}")
            }
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.CanonicalSupersedeResponse.serializer(),
                raw,
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw RuntimeException(e.message ?: "supersede canonical failed", e)
        } finally {
            client.close()
        }
    }

    /**
     * **Re-mint source** — `GET {nodeUrl}/v1/accord/genesis/remint-source`
     * (FSD/MESH_GENESIS.md). Everything needed to PRE-FILL a "re-mint existing trust
     * root" ceremony: the full accord holder roster (A1/B1/C1) + the existing
     * canonical server(s) with their pubkeys, transport hints, and whether each
     * record already confers `infra:serve`. C1 need not be present — the family is
     * quorum:2/3, so its record rides here and the roster stays complete. Throws on
     * failure (an empty roster would be misleading, unlike the fail-soft lists).
     */
    suspend fun getGenesisRemintSource(
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.RemintSourceDto {
        val method = "getGenesisRemintSource"
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/accord/genesis/remint-source") {
                token?.let { header("Authorization", "Bearer $it") }
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("remint source failed: ${response.status}: ${raw.take(220)}")
            }
            val parsed = jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.RemintSourceDto.serializer(),
                raw,
            )
            logInfo(method, "remint source holders=${parsed.holders.size} canonicals=${parsed.canonicals.size} quorum=${parsed.quorum}")
            parsed
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw RuntimeException(e.message ?: "remint source failed", e)
        } finally {
            client.close()
        }
    }

    /**
     * The seed ceremony's refusal text — a non-200 body is `{"error": …}`. Falls back
     * to the raw prefix when the body isn't that shape, so nothing is swallowed.
     */
    private fun genesisSeedError(raw: String): String =
        runCatching {
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.GenesisSeedErrorDto.serializer(),
                raw,
            ).error
        }.getOrNull()?.takeIf { it.isNotBlank() } ?: raw.take(220)

    /**
     * **Propose the portable mesh-genesis seed (authorization #1)** —
     * `POST {nodeUrl}/v1/accord/genesis/propose`. The FIRST accord holder RE-OPENS
     * their YubiKey + USB-wrapped ML-DSA and signs the seed's charter + grant over
     * the existing roster and the [serveKeyId] canonical node. Same hardware inputs
     * as [proposeCanonicalServer] / [proposeCiKeys]; [ip] optionally overrides the
     * serve node's address hint.
     *
     * Returns the (still-partial) bundle VERBATIM plus the running authorization
     * tally — hold the bundle unchanged and hand it to [cosignGenesis]. The app
     * holds NO keys; the YubiKey touch is the human consent.
     */
    suspend fun proposeGenesis(
        holderKeyId: String,
        mldsaUsbPath: String,
        userPin: String? = null,
        serveKeyId: String,
        ip: String? = null,
        pivSlot: String? = null,
        modulePath: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.GenesisSeedResponse {
        val method = "proposeGenesis"
        logInfo(method, "POST $nodeUrl/v1/accord/genesis/propose holder=$holderKeyId serve=$serveKeyId usb=$mldsaUsbPath")
        logInfo(method, "needs a YubiKey touch (slot 9c is touch-ALWAYS) for the seed signature; waiting up to ${ceremonyTimeoutMillis / 1000}s")
        val client = federationHttpClient(ceremonyTimeoutMillis)
        return try {
            val pkcs11 = buildJsonObject {
                userPin?.takeIf { it.isNotBlank() }?.let { put("user_pin", JsonPrimitive(it)) }
                pivSlot?.takeIf { it.isNotBlank() }?.let { put("piv_slot", JsonPrimitive(it)) }
                modulePath?.takeIf { it.isNotBlank() }?.let { put("module_path", JsonPrimitive(it)) }
            }
            val bodyJson = buildJsonObject {
                put("holder_key_id", JsonPrimitive(holderKeyId.trim()))
                put("mldsa_usb_path", JsonPrimitive(mldsaUsbPath.trim()))
                put("pkcs11", pkcs11)
                put("serve_key_id", JsonPrimitive(serveKeyId.trim()))
                ip?.takeIf { it.isNotBlank() }?.let { put("ip", JsonPrimitive(it.trim())) }
            }
            val response = client.post("$nodeUrl/v1/accord/genesis/propose") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyJson.toString())
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("propose genesis seed failed: ${response.status}: ${genesisSeedError(raw)}")
            }
            val parsed = jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.GenesisSeedResponse.serializer(),
                raw,
            )
            logInfo(method, "proposed seed authorizations=${parsed.authorizationsHave}/${parsed.authorizationsNeeded} complete=${parsed.complete}")
            parsed
        } catch (e: Exception) {
            val hint = if (e is io.ktor.client.plugins.HttpRequestTimeoutException) {
                " — timed out waiting for the YubiKey touch; touch the key when it blinks and retry"
            } else {
                ""
            }
            logException(method, e, "nodeUrl=$nodeUrl$hint")
            throw RuntimeException("${e.message ?: "propose genesis seed failed"}$hint", e)
        } finally {
            client.close()
        }
    }

    /**
     * **Cosign the portable mesh-genesis seed (authorization #2…)** —
     * `POST {nodeUrl}/v1/accord/genesis/cosign`. The SECOND accord holder authorizes
     * the SAME [bundle] on their own YubiKey. [bundle] rides VERBATIM (the raw
     * [JsonElement] returned by [proposeGenesis] / a prior cosign) — never re-encoded
     * through a typed model, so the authorized bytes match and no server field is
     * dropped. `complete` flips true once the tally meets what the server needs; the
     * node REJECTS a holder who has already authorized this bundle.
     */
    suspend fun cosignGenesis(
        holderKeyId: String,
        mldsaUsbPath: String,
        userPin: String? = null,
        bundle: JsonElement,
        pivSlot: String? = null,
        modulePath: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.GenesisSeedResponse {
        val method = "cosignGenesis"
        logInfo(method, "POST $nodeUrl/v1/accord/genesis/cosign holder=$holderKeyId usb=$mldsaUsbPath")
        logInfo(method, "needs a YubiKey touch (slot 9c is touch-ALWAYS) for the seed signature; waiting up to ${ceremonyTimeoutMillis / 1000}s")
        val client = federationHttpClient(ceremonyTimeoutMillis)
        return try {
            val pkcs11 = buildJsonObject {
                userPin?.takeIf { it.isNotBlank() }?.let { put("user_pin", JsonPrimitive(it)) }
                pivSlot?.takeIf { it.isNotBlank() }?.let { put("piv_slot", JsonPrimitive(it)) }
                modulePath?.takeIf { it.isNotBlank() }?.let { put("module_path", JsonPrimitive(it)) }
            }
            val bodyJson = buildJsonObject {
                put("holder_key_id", JsonPrimitive(holderKeyId.trim()))
                put("mldsa_usb_path", JsonPrimitive(mldsaUsbPath.trim()))
                put("pkcs11", pkcs11)
                // The bundle VERBATIM — never re-encode the authorized envelope.
                put("bundle", bundle)
            }
            val response = client.post("$nodeUrl/v1/accord/genesis/cosign") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyJson.toString())
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("cosign genesis seed failed: ${response.status}: ${genesisSeedError(raw)}")
            }
            val parsed = jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.GenesisSeedResponse.serializer(),
                raw,
            )
            logInfo(method, "cosigned seed authorizations=${parsed.authorizationsHave}/${parsed.authorizationsNeeded} complete=${parsed.complete}")
            parsed
        } catch (e: Exception) {
            val hint = if (e is io.ktor.client.plugins.HttpRequestTimeoutException) {
                " — timed out waiting for the YubiKey touch; touch the key when it blinks and retry"
            } else {
                ""
            }
            logException(method, e, "nodeUrl=$nodeUrl$hint")
            throw RuntimeException("${e.message ?: "cosign genesis seed failed"}$hint", e)
        } finally {
            client.close()
        }
    }

    /**
     * **YubiKey readiness** — `GET {nodeUrl}/v1/accord/yubikey-status` (loopback).
     * Reports whether an inserted YubiKey is ready for accord provisioning (detected,
     * FIPS-approved, slot 9C key + certificate) + the PIN/PUK tries remaining, so the
     * ceremony UI can show "YUBI DETECTED — FIPS COMPLIANT — 9C PROVISIONED — READY".
     * Never throws on a missing token — returns `detected=false` with a hint.
     */

    /**
     * **Propose a moderation-duty conferral (scrub #1)** —
     * `POST {nodeUrl}/v1/accord/duty/propose`. The local accord holder confers
     * [duty] (`slash` | `moderate` | `review`) on [subjectKeyId], stating whether the
     * subject may pass the duty on ([subDelegation]) and how far
     * ([subDelegationDepth]; null = bounded only by the global rail of 5).
     *
     * The returned `partial` does NOT yet confer the duty — hand it to the next
     * holder's [cosignDutyConferral] unchanged. The app holds NO keys: the node
     * opens the holder's YubiKey + USB ML-DSA and signs (a touch is the consent).
     */
    suspend fun proposeDutyConferral(
        holderKeyId: String,
        mldsaUsbPath: String,
        subjectKeyId: String,
        /** The duties to confer — a SET; the wire field is `duties`. */
        duties: List<String>,
        subDelegation: Boolean,
        subDelegationDepth: Int? = null,
        /** PIV user PIN — the holder's YubiKey cannot be opened without it. */
        userPin: String? = null,
        pivSlot: String? = null,
        modulePath: String? = null,
        pkcs11: JsonElement? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.DutyConferralResponse {
        val method = "proposeDutyConferral"
        logInfo(
            method,
            "POST $nodeUrl/v1/accord/duty/propose holder=$holderKeyId subject=$subjectKeyId " +
                "duties=${duties.joinToString("+")} sub_delegation=$subDelegation " +
                    "depth=${subDelegationDepth ?: "(rail)"}",
        )
        logInfo(method, "needs a YubiKey touch for the scrub signature; waiting up to ${ceremonyTimeoutMillis / 1000}s")
        val client = federationHttpClient(ceremonyTimeoutMillis)
        return try {
            val bodyText = jsonConfig.encodeToString(
                ai.ciris.mobile.shared.models.federation.DutyProposeRequest.serializer(),
                ai.ciris.mobile.shared.models.federation.DutyProposeRequest(
                    holder = ai.ciris.mobile.shared.models.federation.DutyHolder(
                        keyId = holderKeyId.trim(),
                        mldsaUsbPath = mldsaUsbPath.trim(),
                        pkcs11 = pkcs11 ?: buildJsonObject {
                            userPin?.takeIf { it.isNotBlank() }
                                ?.let { put("user_pin", JsonPrimitive(it)) }
                            pivSlot?.takeIf { it.isNotBlank() }
                                ?.let { put("piv_slot", JsonPrimitive(it)) }
                            modulePath?.takeIf { it.isNotBlank() }
                                ?.let { put("module_path", JsonPrimitive(it)) }
                        },
                    ),
                    subjectKeyId = subjectKeyId.trim(),
                    duties = duties.map { it.trim() }.filter { it.isNotEmpty() }.sorted(),
                    subDelegation = subDelegation,
                    subDelegationDepth = subDelegationDepth,
                ),
            )
            val response = client.post("$nodeUrl/v1/accord/duty/propose") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyText)
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("propose duty conferral failed: ${response.status}: ${raw.take(200)}")
            }
            decodeFederationEnvelope(
                raw,
                ai.ciris.mobile.shared.models.federation.DutyConferralResponse.serializer(),
            )
        } catch (e: Exception) {
            logException(
                method,
                e,
                "nodeUrl=$nodeUrl, subject=$subjectKeyId, duties=${duties.joinToString("+")}",
            )
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * **Cosign a moderation-duty conferral** —
     * `POST {nodeUrl}/v1/accord/duty/cosign`. THIS holder appends their scrub to
     * [partial] over the BYTE-IDENTICAL envelope. [partial] MUST be the verbatim
     * blob a prior propose / cosign returned — it is submitted UNCHANGED. At the
     * family m-of-n the conferral is adopted; otherwise the advanced partial comes
     * back for the next holder.
     */
    suspend fun cosignDutyConferral(
        holderKeyId: String,
        mldsaUsbPath: String,
        partial: JsonElement,
        userPin: String? = null,
        pivSlot: String? = null,
        modulePath: String? = null,
        pkcs11: JsonElement? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.DutyConferralResponse {
        val method = "cosignDutyConferral"
        logInfo(method, "POST $nodeUrl/v1/accord/duty/cosign holder=$holderKeyId usb=$mldsaUsbPath")
        logInfo(method, "needs a YubiKey touch for the scrub signature; waiting up to ${ceremonyTimeoutMillis / 1000}s")
        val client = federationHttpClient(ceremonyTimeoutMillis)
        return try {
            val bodyText = jsonConfig.encodeToString(
                ai.ciris.mobile.shared.models.federation.DutyCosignRequest.serializer(),
                ai.ciris.mobile.shared.models.federation.DutyCosignRequest(
                    holder = ai.ciris.mobile.shared.models.federation.DutyHolder(
                        keyId = holderKeyId.trim(),
                        mldsaUsbPath = mldsaUsbPath.trim(),
                        pkcs11 = pkcs11 ?: buildJsonObject {
                            userPin?.takeIf { it.isNotBlank() }
                                ?.let { put("user_pin", JsonPrimitive(it)) }
                            pivSlot?.takeIf { it.isNotBlank() }
                                ?.let { put("piv_slot", JsonPrimitive(it)) }
                            modulePath?.takeIf { it.isNotBlank() }
                                ?.let { put("module_path", JsonPrimitive(it)) }
                        },
                    ),
                    // Submit the partial VERBATIM — never re-encode the signed envelope.
                    partial = partial,
                ),
            )
            val response = client.post("$nodeUrl/v1/accord/duty/cosign") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyText)
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("cosign duty conferral failed: ${response.status}: ${raw.take(200)}")
            }
            decodeFederationEnvelope(
                raw,
                ai.ciris.mobile.shared.models.federation.DutyConferralResponse.serializer(),
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl, holder=$holderKeyId")
            throw e
        } finally {
            client.close()
        }
    }

    suspend fun getYubiKeyStatus(
        nodeUrl: String = LOCAL_NODE_URL,
    ): ai.ciris.mobile.shared.models.federation.YubiKeyStatus {
        val method = "getYubiKeyStatus"
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/accord/yubikey-status")
            val raw = response.bodyAsText()
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.YubiKeyStatus.serializer(),
                raw,
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            ai.ciris.mobile.shared.models.federation.YubiKeyStatus(
                detected = false,
                hint = "couldn't reach the node's YubiKey probe: ${e.message}",
            )
        } finally {
            client.close()
        }
    }

    /**
     * Is [token] a LIVE user-account session on the node? Probes `GET /v1/auth/me`
     * (HTTP 200 ⇒ the opaque `sess:` token resolves to an active `wa_cert` row;
     * 401 ⇒ unknown/expired/revoked). This is the gate behind "sign in as <fedID>":
     * the founder's federation identity is accessible ONLY via the associated
     * user-account session, never as a credential-less door. The node separately
     * refuses to SIGN with the fedID without a live owner session (server-side
     * `resolve_user_signer` choke point), so this client check mirrors that.
     */
    suspend fun hasLiveSession(
        token: String,
        nodeUrl: String = baseUrl,
    ): Boolean {
        val method = "hasLiveSession"
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/auth/me") {
                header("Authorization", "Bearer $token")
            }
            val ok = response.status.value == 200
            logInfo(method, "session probe → HTTP ${response.status.value} (live=$ok)")
            ok
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            false
        } finally {
            client.close()
        }
    }

    /**
     * **Register an accord holder** — `POST {nodeUrl}/v1/accord/holder`
     * (owner-session-gated). Admits a holder's self-signed `accord_holder`
     * [holderRecord] (+ the optional `portable_2fa` [custodyAttestation] from
     * provisioning, verified against the pinned Yubico root). The two artifacts
     * are the verbatim ones [provisionAccordHolder] returned; the app never
     * inspects them. Used by the genesis ceremony to register each of the 6 keys.
     */
    suspend fun registerAccordHolder(
        holderRecord: kotlinx.serialization.json.JsonElement,
        custodyAttestation: kotlinx.serialization.json.JsonElement? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ) {
        val method = "registerAccordHolder"
        logInfo(method, "POST $nodeUrl/v1/accord/holder")
        val client = federationHttpClient()
        try {
            val bodyJson = buildJsonObject {
                put("key_record", holderRecord)
                custodyAttestation?.let { put("custody_attestation", it) }
            }
            val response = client.post("$nodeUrl/v1/accord/holder") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyJson.toString())
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("register holder failed: ${response.status}: ${raw.take(220)}")
            }
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * **Build the genesis family envelope** —
     * `POST {nodeUrl}/v1/accord/genesis/envelope` (owner-gated). Returns the
     * canonical, JCS-significant envelope over the PRIMARY [memberKeyIds] (fixed
     * order). The holders co-sign it byte-for-byte; the app NEVER rebuilds it.
     */
    suspend fun genesisEnvelope(
        memberKeyIds: List<String>,
        familyName: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.GenesisEnvelopeResponse {
        val method = "genesisEnvelope"
        logInfo(method, "POST $nodeUrl/v1/accord/genesis/envelope members=${memberKeyIds.size}")
        val client = federationHttpClient()
        return try {
            val bodyJson = buildJsonObject {
                familyName?.takeIf { it.isNotBlank() }?.let { put("family_name", JsonPrimitive(it)) }
                put("member_key_ids", JsonArray(memberKeyIds.map { JsonPrimitive(it.trim()) }))
            }
            val response = client.post("$nodeUrl/v1/accord/genesis/envelope") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyJson.toString())
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("genesis envelope failed: ${response.status}: ${raw.take(220)}")
            }
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.GenesisEnvelopeResponse.serializer(),
                raw,
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * **Cosign the genesis family envelope** —
     * `POST {nodeUrl}/v1/accord/family/cosign` (loopback-only, `pkcs11`-gated).
     * One PRIMARY holder RE-INSERTS their YubiKey; the node re-opens it + the
     * USB-wrapped ML-DSA half and cosigns the verbatim [envelope]. The physical
     * touch IS the holder's consent. Returns `{ signature, member }` — the app
     * collects them and relays them to [genesisAssemble]. The app does NO crypto.
     */
    suspend fun cosignAccordFamily(
        keyId: String,
        mldsaUsbPath: String,
        envelope: kotlinx.serialization.json.JsonElement,
        userPin: String? = null,
        pivSlot: String? = null,
        modulePath: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.CosignFamilyResponse {
        val method = "cosignAccordFamily"
        logInfo(method, "POST $nodeUrl/v1/accord/family/cosign key_id=$keyId usb=$mldsaUsbPath")
        // Touch-gated like provisioning: re-opens the YubiKey + signs the envelope
        // (slot 9c touch-ALWAYS). Long timeout + touch-each-blink prompt.
        logInfo(method, "this needs YubiKey touch(es) (slot 9c is touch-ALWAYS); waiting up to ${ceremonyTimeoutMillis / 1000}s")
        val client = federationHttpClient(ceremonyTimeoutMillis)
        return try {
            val pkcs11 = buildJsonObject {
                userPin?.takeIf { it.isNotBlank() }?.let { put("user_pin", JsonPrimitive(it)) }
                pivSlot?.takeIf { it.isNotBlank() }?.let { put("piv_slot", JsonPrimitive(it)) }
                modulePath?.takeIf { it.isNotBlank() }?.let { put("module_path", JsonPrimitive(it)) }
            }
            val bodyJson = buildJsonObject {
                put("key_id", JsonPrimitive(keyId.trim()))
                put("mldsa_usb_path", JsonPrimitive(mldsaUsbPath.trim()))
                put("envelope", envelope)
                put("pkcs11", pkcs11)
            }
            val response = client.post("$nodeUrl/v1/accord/family/cosign") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyJson.toString())
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("cosign family failed: ${response.status}: ${raw.take(220)}")
            }
            logInfo(method, "cosigned key_id=$keyId")
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.CosignFamilyResponse.serializer(),
                raw,
            )
        } catch (e: Exception) {
            val hint = if (e is io.ktor.client.plugins.HttpRequestTimeoutException) {
                " — timed out waiting for YubiKey touch; touch the key EACH time it blinks and retry"
            } else {
                ""
            }
            logException(method, e, "nodeUrl=$nodeUrl$hint")
            throw RuntimeException("${e.message ?: "cosign failed"}$hint", e)
        } finally {
            client.close()
        }
    }

    /**
     * **Assemble the genesis** — `POST {nodeUrl}/v1/accord/genesis/assemble`
     * (owner-gated). Verifies the 2-of-3 founder quorum over the verbatim
     * [envelope] using the collected [founders] (`ThresholdMember`s) + [signatures]
     * (`ThresholdSignature`s) from [cosignAccordFamily], then returns the assembled
     * genesis — the cold-start bake artifact (CIRISVerify#107) the operator SAVES.
     */
    suspend fun genesisAssemble(
        envelope: kotlinx.serialization.json.JsonElement,
        founders: List<kotlinx.serialization.json.JsonElement>,
        signatures: List<kotlinx.serialization.json.JsonElement>,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.federation.GenesisAssembleResponse {
        val method = "genesisAssemble"
        logInfo(method, "POST $nodeUrl/v1/accord/genesis/assemble founders=${founders.size} sigs=${signatures.size}")
        val client = federationHttpClient()
        return try {
            val bodyJson = buildJsonObject {
                put("envelope", envelope)
                put("founders", JsonArray(founders))
                put("signatures", JsonArray(signatures))
            }
            val response = client.post("$nodeUrl/v1/accord/genesis/assemble") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyJson.toString())
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("genesis assemble failed: ${response.status}: ${raw.take(220)}")
            }
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.federation.GenesisAssembleResponse.serializer(),
                raw,
            )
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    // ─── Tier S (self-directed) + tier R (per-reader) — CIRISServer#345 ───────
    //
    // `src/admin_ops.rs`, the two rungs that act on NOBODY else: tier S is this
    // node's own three standings (shed load / stop accepting / legal
    // compulsion), tier R is what THIS reader makes of judgements other parties
    // issued. Owner session only (Bearer), and every act carries the owner's own
    // `delegation_id` + a free-text `reason`.
    //
    // Three properties this block is written to preserve:
    //
    //  1. **A failed read is never a clean one.** `GET /v1/admin/self` answers
    //     503 *with the standings still in the body* when an axis is unreadable,
    //     and `POST /v1/admin/reader/fold` does the same, precisely so a client
    //     reading only one half cannot conclude "nothing in force". Both halves
    //     are decoded here; neither is thrown away.
    //  2. **Unreachable is an answer.** Tier S is the only rung available under
    //     partition, so a transport failure returns `Unreachable` rather than
    //     throwing — the operator wants these controls exactly when the network
    //     is gone, and "could not reach the node" is not "nothing in force".
    //  3. **`compelled_by` rides on the compulsion alone.** Only
    //     [selfDeclareCompelled] takes it; the other five acts have no parameter
    //     that could carry it, so a voluntary stop cannot wear a compelled one's
    //     marks.

    /** The one refusal shape `refusal()` / `err()` emit, or null if this body is
     *  not one (e.g. the 503 that still carries standings). */
    private fun adminRefusalOrNull(
        raw: String,
    ): ai.ciris.mobile.shared.models.selfreader.AdminRefusalDto? = try {
        val obj = jsonConfig.parseToJsonElement(raw).jsonObject
        if (obj["refused"]?.jsonPrimitive?.booleanOrNull == true) {
            jsonConfig.decodeFromString(
                ai.ciris.mobile.shared.models.selfreader.AdminRefusalDto.serializer(),
                raw,
            )
        } else {
            null
        }
    } catch (_: Exception) {
        null
    }

    /** A body we could not read at all. Carries no `id`, so the UI falls back to
     *  the raw text — and, being a refusal, is never rendered as a clean state. */
    private fun adminOpaqueRefusal(
        raw: String,
    ): ai.ciris.mobile.shared.models.selfreader.AdminRefusalDto =
        ai.ciris.mobile.shared.models.selfreader.AdminRefusalDto(
            refused = true,
            refusal = "unreadable_response",
            message = ai.ciris.mobile.shared.models.selfreader.AdminMessage(
                id = "",
                text = raw.take(240).ifBlank { "The node returned no body." },
            ),
        )

    /** Does this body carry the named object? Used to tell the tier S / tier R
     *  503-with-content halves from a plain refusal at the same status. */
    private fun bodyHasKey(raw: String, key: String): Boolean = try {
        jsonConfig.parseToJsonElement(raw).jsonObject[key] != null
    } catch (_: Exception) {
        false
    }

    /**
     * The three self-directed standings, side by side —
     * `GET {nodeUrl}/v1/admin/self`.
     *
     * A 503 whose body still carries `standings` is a READ, flagged
     * [ai.ciris.mobile.shared.models.selfreader.SelfStandingOutcome.Read.partiallyUnreadable]:
     * the unreadable axes are present and marked `unreadable`, and must not be
     * shown as "nothing in force".
     */
    suspend fun getSelfStanding(
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.selfreader.SelfStandingOutcome {
        val method = "getSelfStanding"
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/admin/self") {
                token?.let { header("Authorization", "Bearer $it") }
            }
            val raw = response.bodyAsText()
            val carriesStandings = bodyHasKey(raw, "standings")
            if (response.status.isSuccess() || carriesStandings) {
                val decoded = jsonConfig.decodeFromString(
                    ai.ciris.mobile.shared.models.selfreader.SelfStandingResponse.serializer(),
                    raw,
                )
                ai.ciris.mobile.shared.models.selfreader.SelfStandingOutcome.Read(
                    response = decoded,
                    partiallyUnreadable = !response.status.isSuccess() ||
                        !decoded.unreadableAxes.isNullOrEmpty(),
                )
            } else {
                ai.ciris.mobile.shared.models.selfreader.SelfStandingOutcome.Refused(
                    refusal = adminRefusalOrNull(raw) ?: adminOpaqueRefusal(raw),
                    httpStatus = response.status.value,
                )
            }
        } catch (e: Exception) {
            // Deliberately NOT rethrown: see property 2 above.
            logException(method, e, "nodeUrl=$nodeUrl")
            ai.ciris.mobile.shared.models.selfreader.SelfStandingOutcome.Unreachable(
                e.message ?: e::class.simpleName ?: "unreachable",
            )
        } finally {
            client.close()
        }
    }

    /**
     * Owner login against the LOCAL NODE — `POST {localNodeUrl}/v1/auth/login`.
     *
     * The post-claim owner session MUST come from the node: the self-claim writes
     * the owner ROOT cert into the node's substrate and ROTATES the setup session
     * (FSD/FIRST_RUN_STATECHART.md, axis S), while the brain (:8080) is still in
     * setup mode with no auth routes mounted — `login()` (SDK, brain-bound) can
     * never succeed at that point (its 404 body fails LoginResponse parsing,
     * which is exactly the E6x failure the first conformance runs captured).
     * Accepts the friendly username OR the wa_id. Response shape verified live
     * on ciris-server 0.5.122:
     * {"access_token","token_type","expires_in","role","user_id"}.
     *
     * Returns the bearer token; does NOT mutate [accessToken] — callers decide.
     */
    suspend fun loginToNode(
        username: String,
        password: String,
        localNodeUrl: String = LOCAL_NODE_URL,
    ): String {
        val method = "loginToNode"
        logInfo(method, "POST $localNodeUrl/v1/auth/login user=$username")
        val client = federationHttpClient()
        return try {
            val response = client.post("$localNodeUrl/v1/auth/login") {
                contentType(ContentType.Application.Json)
                setBody(
                    buildJsonObject {
                        put("username", username)
                        put("password", password)
                    }.toString()
                )
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                logException(method, RuntimeException("status=${response.status} body=${raw.take(300)}"), "localNodeUrl=$localNodeUrl")
                throw RuntimeException("node login failed: ${response.status}: ${raw.take(200)}")
            }
            val obj = Json.parseToJsonElement(raw).jsonObject
            val tokenValue = obj["access_token"]?.jsonPrimitive?.content
            if (tokenValue.isNullOrBlank()) {
                throw RuntimeException("node login: no access_token in response: ${raw.take(200)}")
            }
            logInfo(
                method,
                "node owner session established (role=${obj["role"]?.jsonPrimitive?.content} " +
                    "user_id=${obj["user_id"]?.jsonPrimitive?.content})",
            )
            tokenValue
        } catch (e: Exception) {
            logException(method, e, "localNodeUrl=$localNodeUrl user=$username")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * **Author the explicit trace-sharing consent** —
     * `POST {localNodeUrl}/v1/federation/consent` (owner-gated; ciris-server
     * >= the explicit-consent cut). Consent is NO LONGER auto-authored at node
     * boot: when the user opts into "Send traces to CIRIS L3C", the wizard (or
     * the Manage Consent card) must author `consent:replication` explicitly,
     * once, AFTER the owner claim (pre-claim the route 403s). Idempotent —
     * re-POST is a no-op.
     *
     * When [peerKeyId] is null, the method resolves the canonical the node is
     * rooted to via `GET {localNodeUrl}/v1/accord/canonical/servers` (first
     * entry). [attestationPrefixes] is the explicit scope the user consented
     * to (empty ⇒ the node 400s — pass what was actually consented).
     *
     * [analyze] is CC#46's be-scored dimension and is the OWNER'S ANSWER —
     * pass what they chose. The substrate marks it `required: false` with named
     * costs, so a caller that always sends true grants a dimension the user was
     * never asked about. The default exists only for callers acting on a
     * standing opt-in with no fresh answer to hand.
     *
     * @return the raw response body (carries `grant_attestation_id`).
     */
    suspend fun authorFederationConsent(
        peerKeyId: String? = null,
        attestationPrefixes: List<String> = FederationConsentScopes.TO_CANONICAL,
        analyze: Boolean = true,
        localNodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): String {
        val method = "authorFederationConsent"
        val client = federationHttpClient()
        return try {
            val peer = peerKeyId ?: run {
                // `canonical/servers`, NOT `canonical-servers`. The route is
                // `/v1/accord/canonical/servers` (accord_provision.rs:3458); the
                // hyphenated spelling 404s and there is no redirect. Verified live:
                //   :4243 /v1/accord/canonical-servers  -> 404
                //   :4243 /v1/accord/canonical/servers  -> 200 {"servers":[...]}
                //
                // The cost of the typo was the whole trace plane. Consent WAS
                // requested and the owner session WAS valid; this lookup threw, the
                // catch is non-fatal by design, and setup completed reporting
                // success while `consent:replication` was never authored — so
                // sealed traces strand at (self, local) forever. A first-run wizard
                // that says it consented and did not is exactly the failure the
                // [ORDER] saga logging exists to make visible.
                val resp = client.get("$localNodeUrl/v1/accord/canonical/servers") {
                    token?.let { header("Authorization", "Bearer $it") }
                }
                val raw = resp.bodyAsText()
                if (!resp.status.isSuccess()) {
                    throw RuntimeException("canonical/servers failed: ${resp.status}: ${raw.take(200)}")
                }
                // Envelope-tolerant first-key extraction: [{"key_id": ...}] or {"data":[...]}
                Regex("\"key_id\"\\s*:\\s*\"([^\"]+)\"").find(raw)?.groupValues?.get(1)
                    ?: throw RuntimeException("no canonical server in: ${raw.take(200)}")
            }
            val prefixesJson = attestationPrefixes.joinToString(",") { "\"$it\"" }
            logInfo(method, "POST $localNodeUrl/v1/federation/consent peer=$peer scope=$attestationPrefixes")
            val response = client.post("$localNodeUrl/v1/federation/consent") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                // `analyze`: CC#46 (persist v22) — the subject's consent to BE SCORED
                // (consent:state:granted:v1, scope analyze, naming the recipient's
                // DERIVED key). Forward-compat: servers without the field ignore it;
                // the CIRISServer ask extends the route to author it atomically.
                setBody("""{"peer_key_id":"$peer","attestation_prefixes":[$prefixesJson],"analyze":$analyze}""")
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                logException(method, RuntimeException("status=${response.status} body=${raw.take(300)}"), "localNodeUrl=$localNodeUrl")
                throw RuntimeException("federation consent failed: ${response.status}: ${raw.take(200)}")
            }
            raw
        } catch (e: Exception) {
            logException(method, e, "localNodeUrl=$localNodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /** Shared body for all six tier S acts. */
    private suspend fun postSelfAct(
        method: String,
        path: String,
        request: ai.ciris.mobile.shared.models.selfreader.SelfCommitRequest,
        nodeUrl: String,
        token: String?,
    ): ai.ciris.mobile.shared.models.selfreader.SelfActOutcome {
        val client = federationHttpClient()
        return try {
            val bodyText = jsonConfig.encodeToString(
                ai.ciris.mobile.shared.models.selfreader.SelfCommitRequest.serializer(),
                request,
            )
            val response = client.post("$nodeUrl$path") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyText)
            }
            val raw = response.bodyAsText()
            if (response.status.isSuccess()) {
                ai.ciris.mobile.shared.models.selfreader.SelfActOutcome.Recorded(
                    jsonConfig.decodeFromString(
                        ai.ciris.mobile.shared.models.selfreader.SelfActResponse.serializer(),
                        raw,
                    ),
                )
            } else {
                ai.ciris.mobile.shared.models.selfreader.SelfActOutcome.Refused(
                    refusal = adminRefusalOrNull(raw) ?: adminOpaqueRefusal(raw),
                    httpStatus = response.status.value,
                )
            }
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl, path=$path")
            ai.ciris.mobile.shared.models.selfreader.SelfActOutcome.Unreachable(
                e.message ?: e::class.simpleName ?: "unreachable",
            )
        } finally {
            client.close()
        }
    }

    /** Shed my own load — `POST {nodeUrl}/v1/admin/self/shed`. Axis `load_shed`. */
    suspend fun selfShedLoad(
        delegationId: String,
        reason: String,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.selfreader.SelfActOutcome = postSelfAct(
        method = "selfShedLoad",
        path = "/v1/admin/self/shed",
        request = ai.ciris.mobile.shared.models.selfreader.SelfCommitRequest(
            delegationId = delegationId,
            reason = reason,
        ),
        nodeUrl = nodeUrl,
        token = token,
    )

    /** Carry a full load again — `POST {nodeUrl}/v1/admin/self/resume-load`. */
    suspend fun selfResumeLoad(
        delegationId: String,
        reason: String,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.selfreader.SelfActOutcome = postSelfAct(
        method = "selfResumeLoad",
        path = "/v1/admin/self/resume-load",
        request = ai.ciris.mobile.shared.models.selfreader.SelfCommitRequest(
            delegationId = delegationId,
            reason = reason,
        ),
        nodeUrl = nodeUrl,
        token = token,
    )

    /**
     * Take on nothing new — `POST {nodeUrl}/v1/admin/self/stop-accepting`.
     * Axis `accepting`. **A CHOICE this node made**, and never a flavour of
     * compulsion: it takes no `compelled_by`.
     */
    suspend fun selfStopAccepting(
        delegationId: String,
        reason: String,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.selfreader.SelfActOutcome = postSelfAct(
        method = "selfStopAccepting",
        path = "/v1/admin/self/stop-accepting",
        request = ai.ciris.mobile.shared.models.selfreader.SelfCommitRequest(
            delegationId = delegationId,
            reason = reason,
        ),
        nodeUrl = nodeUrl,
        token = token,
    )

    /** Accept again — `POST {nodeUrl}/v1/admin/self/resume-accepting`. */
    suspend fun selfResumeAccepting(
        delegationId: String,
        reason: String,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.selfreader.SelfActOutcome = postSelfAct(
        method = "selfResumeAccepting",
        path = "/v1/admin/self/resume-accepting",
        request = ai.ciris.mobile.shared.models.selfreader.SelfCommitRequest(
            delegationId = delegationId,
            reason = reason,
        ),
        nodeUrl = nodeUrl,
        token = token,
    )

    /**
     * Declare legal compulsion — `POST {nodeUrl}/v1/admin/self/compelled`.
     * Axis `legal_compulsion`, and its own act: force applied from OUTSIDE the
     * mesh, never recorded as a choice.
     *
     * @param compelledBy optional, and the ONLY act that carries it. Blank is a
     *   real answer — an operator under a gag order may be unable to name the
     *   authority, and a compulsion nobody can attribute still deserves a trace.
     */
    suspend fun selfDeclareCompelled(
        delegationId: String,
        reason: String,
        compelledBy: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.selfreader.SelfActOutcome = postSelfAct(
        method = "selfDeclareCompelled",
        path = "/v1/admin/self/compelled",
        request = ai.ciris.mobile.shared.models.selfreader.SelfCommitRequest(
            delegationId = delegationId,
            reason = reason,
            compelledBy = compelledBy?.trim()?.takeIf { it.isNotEmpty() },
        ),
        nodeUrl = nodeUrl,
        token = token,
    )

    /**
     * The compulsion ended — `POST {nodeUrl}/v1/admin/self/compulsion-lifted`.
     * A distinct act: a compulsion that ENDED is not a compulsion that never
     * happened, and both rows survive.
     */
    suspend fun selfCompulsionLifted(
        delegationId: String,
        reason: String,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.selfreader.SelfActOutcome = postSelfAct(
        method = "selfCompulsionLifted",
        path = "/v1/admin/self/compulsion-lifted",
        request = ai.ciris.mobile.shared.models.selfreader.SelfCommitRequest(
            delegationId = delegationId,
            reason = reason,
        ),
        nodeUrl = nodeUrl,
        token = token,
    )

    /**
     * What THIS reader makes of the judgements it holds about one subject —
     * `POST {nodeUrl}/v1/admin/reader/fold`. Read-only.
     *
     * The 503 half is decoded too, as
     * [ai.ciris.mobile.shared.models.selfreader.ReaderFoldOutcome.Unreadable]:
     * an unreadable policy rendered as an empty one silently drops every
     * restriction it carried.
     */
    suspend fun readerFold(
        subjectKeyId: String,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.selfreader.ReaderFoldOutcome {
        val method = "readerFold"
        val client = federationHttpClient()
        return try {
            val bodyText = jsonConfig.encodeToString(
                ai.ciris.mobile.shared.models.selfreader.ReaderFoldRequest.serializer(),
                ai.ciris.mobile.shared.models.selfreader.ReaderFoldRequest(
                    subjectKeyId = subjectKeyId,
                ),
            )
            val response = client.post("$nodeUrl/v1/admin/reader/fold") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyText)
            }
            val raw = response.bodyAsText()
            val decodeFold = {
                jsonConfig.decodeFromString(
                    ai.ciris.mobile.shared.models.selfreader.ReaderFoldResponse.serializer(),
                    raw,
                )
            }
            when {
                response.status.isSuccess() ->
                    ai.ciris.mobile.shared.models.selfreader.ReaderFoldOutcome.Read(decodeFold())
                // The unreadable standing rendered on BOTH halves.
                bodyHasKey(raw, "standing") && adminRefusalOrNull(raw) == null ->
                    ai.ciris.mobile.shared.models.selfreader.ReaderFoldOutcome.Unreadable(decodeFold())
                else -> ai.ciris.mobile.shared.models.selfreader.ReaderFoldOutcome.Refused(
                    refusal = adminRefusalOrNull(raw) ?: adminOpaqueRefusal(raw),
                    httpStatus = response.status.value,
                )
            }
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl, subject=$subjectKeyId")
            ai.ciris.mobile.shared.models.selfreader.ReaderFoldOutcome.Unreachable(
                e.message ?: e::class.simpleName ?: "unreachable",
            )
        } finally {
            client.close()
        }
    }

    /** Shared body for honour + decline: same gates, opposite decision, SAME
     *  success shape — a decline is not an error path. */
    private suspend fun postReaderDecision(
        method: String,
        path: String,
        request: ai.ciris.mobile.shared.models.selfreader.ReaderCommitRequest,
        nodeUrl: String,
        token: String?,
    ): ai.ciris.mobile.shared.models.selfreader.ReaderDecisionOutcome {
        val client = federationHttpClient()
        return try {
            val bodyText = jsonConfig.encodeToString(
                ai.ciris.mobile.shared.models.selfreader.ReaderCommitRequest.serializer(),
                request,
            )
            val response = client.post("$nodeUrl$path") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(bodyText)
            }
            val raw = response.bodyAsText()
            if (response.status.isSuccess()) {
                ai.ciris.mobile.shared.models.selfreader.ReaderDecisionOutcome.Recorded(
                    jsonConfig.decodeFromString(
                        ai.ciris.mobile.shared.models.selfreader.ReaderDecisionResponse.serializer(),
                        raw,
                    ),
                )
            } else {
                ai.ciris.mobile.shared.models.selfreader.ReaderDecisionOutcome.Refused(
                    refusal = adminRefusalOrNull(raw) ?: adminOpaqueRefusal(raw),
                    httpStatus = response.status.value,
                )
            }
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl, path=$path")
            ai.ciris.mobile.shared.models.selfreader.ReaderDecisionOutcome.Unreachable(
                e.message ?: e::class.simpleName ?: "unreachable",
            )
        } finally {
            client.close()
        }
    }

    /** Adopt one judgement — `POST {nodeUrl}/v1/admin/reader/honour`. */
    suspend fun readerHonour(
        judgementId: String,
        delegationId: String,
        reason: String,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.selfreader.ReaderDecisionOutcome = postReaderDecision(
        method = "readerHonour",
        path = "/v1/admin/reader/honour",
        request = ai.ciris.mobile.shared.models.selfreader.ReaderCommitRequest(
            judgementId = judgementId,
            delegationId = delegationId,
            reason = reason,
        ),
        nodeUrl = nodeUrl,
        token = token,
    )

    /**
     * Refuse one judgement — `POST {nodeUrl}/v1/admin/reader/decline`.
     *
     * **A normal outcome, not an error.** An issued judgement is advisory to
     * each reader; two readers with different policies reaching different,
     * both-valid states from the same judgement is the design working. This
     * returns the same
     * [Recorded][ai.ciris.mobile.shared.models.selfreader.ReaderDecisionOutcome.Recorded]
     * a honour does.
     */
    suspend fun readerDecline(
        judgementId: String,
        delegationId: String,
        reason: String,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.selfreader.ReaderDecisionOutcome = postReaderDecision(
        method = "readerDecline",
        path = "/v1/admin/reader/decline",
        request = ai.ciris.mobile.shared.models.selfreader.ReaderCommitRequest(
            judgementId = judgementId,
            delegationId = delegationId,
            reason = reason,
        ),
        nodeUrl = nodeUrl,
        token = token,
    )

    // ─── Holistic SAFETY surface (/v1/safety/*) — CIRISServer v0.4.6 ──────────
    //
    // The safety cards drive THIS device's local node only. The app holds NO
    // keys and performs NO crypto: every signing / admission decision is made by
    // the node's substrate. These are plain localhost requests (Bearer [token]
    // for the owner session); there is no x-ciris signing in Kotlin.
    //
    // Mirrors CIRISServer/src/safety/{age,moderation,named,watchlist}.rs exactly.
    // Hand-written direct HTTP (not in the generated SDK).

    /**
     * **Set the caller's self-declared age band** — the onboarding "state your
     * age range" step. `POST {localNodeUrl}/v1/safety/age-assurance`.
     *
     * Mirrors `age.rs::set_age` (`SetAgeRequest { subject_key_id, band, level? }`).
     * Only the `self` level is settable here — the node rejects provider/
     * government with 400 (a subject cannot self-mint verified adulthood). The
     * node signs + promotes the assurance; the subject controls their own level
     * and misdeclaration NEVER slashes (it routes to adjudication).
     */
    suspend fun setAgeAssurance(
        subjectKeyId: String,
        band: AgeBand,
        level: AssuranceLevel? = null,
        localNodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): SetAgeResponse {
        val method = "setAgeAssurance"
        logInfo(method, "POST $localNodeUrl/v1/safety/age-assurance subject=${subjectKeyId.take(16)}… band=$band")
        val client = federationHttpClient()
        return try {
            val request = SetAgeRequest(subjectKeyId = subjectKeyId, band = band, level = level)
            val response = client.post("$localNodeUrl/v1/safety/age-assurance") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(jsonConfig.encodeToString(SetAgeRequest.serializer(), request))
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("set age-assurance failed: ${response.status}: ${raw.take(200)}")
            }
            decodeFederationEnvelope(raw, SetAgeResponse.serializer())
        } catch (e: Exception) {
            logException(method, e, "localNodeUrl=$localNodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * **Read an identity's current age assurance** —
     * `GET {nodeUrl}/v1/safety/age-assurance/{key_id}`. Mirrors `age.rs::get_age`
     * (`AgeStatusResponse { key_id, assurance? }`). `assurance` is null when none
     * is on record — callers MUST treat null PROTECTIVELY (default to minor).
     */
    suspend fun getAgeAssurance(
        keyId: String,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): AgeStatusResponse {
        val method = "getAgeAssurance"
        logDebug(method, "GET $nodeUrl/v1/safety/age-assurance/$keyId")
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/safety/age-assurance/$keyId") {
                token?.let { header("Authorization", "Bearer $it") }
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("get age-assurance failed: ${response.status} for $keyId")
            }
            decodeFederationEnvelope(response.bodyAsText(), AgeStatusResponse.serializer())
        } catch (e: Exception) {
            logException(method, e, "keyId=$keyId")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * **The aggregate protective posture/status** for an identity —
     * `GET {nodeUrl}/v1/safety/status/{key_id}`. Mirrors `age.rs::safety_status`
     * (`{ key_id, age_assurance?, honesty{…} }`). The honesty block is kept TRUE
     * by the server and surfaced verbatim by the child-safety card.
     */
    suspend fun getSafetyStatus(
        keyId: String,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): SafetyStatusResponse {
        val method = "getSafetyStatus"
        logDebug(method, "GET $nodeUrl/v1/safety/status/$keyId")
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/safety/status/$keyId") {
                token?.let { header("Authorization", "Bearer $it") }
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("get safety status failed: ${response.status} for $keyId")
            }
            decodeFederationEnvelope(response.bodyAsText(), SafetyStatusResponse.serializer())
        } catch (e: Exception) {
            logException(method, e, "keyId=$keyId")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * **File a ModerationEvent** — `POST {nodeUrl}/v1/safety/moderation`. Mirrors
     * `moderation.rs::moderation` (`ModerationRequest { signer_key_id,
     * community_key_id, duty, allegation_type, target_key_ids[], payload }`).
     *
     * Admitted IFF the signer holds the duty (`moderate`/`takedown`/`review`) or
     * sits on a live delegated chain (the §11.10 gate, enforced by the node).
     * Non-holders get 403 — "the duty is held or delegated, never assumed". The
     * app does no crypto; the node decides authority.
     */
    suspend fun fileModeration(
        signerKeyId: String,
        communityKeyId: String,
        duty: ModerationDuty,
        allegationType: String,
        targetKeyIds: List<String> = emptyList(),
        note: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): ModerationResponse {
        val method = "fileModeration"
        logInfo(method, "POST $nodeUrl/v1/safety/moderation community=${communityKeyId.take(16)}… duty=$duty allegation=$allegationType")
        val client = federationHttpClient()
        return try {
            val request = ModerationRequest(
                signerKeyId = signerKeyId,
                communityKeyId = communityKeyId,
                duty = duty,
                allegationType = allegationType,
                targetKeyIds = targetKeyIds,
                payload = note?.let { ModerationPayload(note = it) },
            )
            val response = client.post("$nodeUrl/v1/safety/moderation") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(jsonConfig.encodeToString(ModerationRequest.serializer(), request))
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("file moderation failed: ${response.status}: ${raw.take(200)}")
            }
            decodeFederationEnvelope(raw, ModerationResponse.serializer())
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * **The named-moderator existence status** for a community —
     * `GET {nodeUrl}/v1/safety/named-moderator/{community_key_id}`. Mirrors
     * `named.rs::named_status` (`{ community_key_id, existence{verdict…},
     * fails_secure }`). The verdict is one of `operate` / `auto_promote` /
     * `quiesce` (FAIL SECURE — better no group than an unmoderated one).
     */
    suspend fun getNamedModerator(
        communityKeyId: String,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): NamedModeratorResponse {
        val method = "getNamedModerator"
        logDebug(method, "GET $nodeUrl/v1/safety/named-moderator/$communityKeyId")
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/safety/named-moderator/$communityKeyId") {
                token?.let { header("Authorization", "Bearer $it") }
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("named-moderator fetch failed: ${response.status} for $communityKeyId")
            }
            decodeFederationEnvelope(response.bodyAsText(), NamedModeratorResponse.serializer())
        } catch (e: Exception) {
            logException(method, e, "communityKeyId=$communityKeyId")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * **The current watchlist enables for a group** —
     * `GET {nodeUrl}/v1/safety/watchlist/{group_key_id}`. Mirrors
     * `watchlist.rs::list_enables` (`{ group_key_id, enables[], honesty{…} }`).
     * The honesty block (per-group/never-global, cannot reach private content,
     * hashes operator-provisioned) is surfaced verbatim by the child-safety card.
     */
    suspend fun getWatchlist(
        groupKeyId: String,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): WatchlistListResponse {
        val method = "getWatchlist"
        logDebug(method, "GET $nodeUrl/v1/safety/watchlist/$groupKeyId")
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/safety/watchlist/$groupKeyId") {
                token?.let { header("Authorization", "Bearer $it") }
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("watchlist fetch failed: ${response.status} for $groupKeyId")
            }
            decodeFederationEnvelope(response.bodyAsText(), WatchlistListResponse.serializer())
        } catch (e: Exception) {
            logException(method, e, "groupKeyId=$groupKeyId")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * **Enable or disable a per-group content watchlist** —
     * `POST {nodeUrl}/v1/safety/watchlist`. Mirrors `watchlist.rs::watchlist`'s
     * flattened body (`signer_key_id` + the flattened `WatchlistEnable`).
     *
     * Opt-in, default OFF, per-group, NEVER global. `moderate`-gated; CSAM
     * additionally `takedown`-gated (a CSAM match auto-files a takedown). Pass
     * `enabled=false` to turn a watchlist OFF (the node emits a `withdraws` —
     * consent requires revocability). Non-authorized signers get 403.
     */
    suspend fun setWatchlist(
        signerKeyId: String,
        groupKeyId: String,
        watchlistId: String,
        watchlistClass: WatchlistClass,
        enabled: Boolean,
        mode: WatchlistMode,
        routeToModerator: String? = null,
        nodeUrl: String = LOCAL_NODE_URL,
        token: String? = accessToken,
    ): WatchlistResponse {
        val method = "setWatchlist"
        logInfo(method, "POST $nodeUrl/v1/safety/watchlist group=${groupKeyId.take(16)}… id=$watchlistId enabled=$enabled class=$watchlistClass")
        val client = federationHttpClient()
        return try {
            val request = WatchlistRequest(
                signerKeyId = signerKeyId,
                groupKeyId = groupKeyId,
                watchlistId = watchlistId,
                watchlistClass = watchlistClass,
                enabled = enabled,
                mode = mode,
                routeToModerator = routeToModerator,
            )
            val response = client.post("$nodeUrl/v1/safety/watchlist") {
                token?.let { header("Authorization", "Bearer $it") }
                contentType(ContentType.Application.Json)
                setBody(jsonConfig.encodeToString(WatchlistRequest.serializer(), request))
            }
            val raw = response.bodyAsText()
            if (!response.status.isSuccess()) {
                throw RuntimeException("set watchlist failed: ${response.status}: ${raw.take(200)}")
            }
            decodeFederationEnvelope(raw, WatchlistResponse.serializer())
        } catch (e: Exception) {
            logException(method, e, "nodeUrl=$nodeUrl")
            throw e
        } finally {
            client.close()
        }
    }

    // System Status (from /v1/system/health)
    // Uses direct HTTP to support dynamic baseUrl changes
    override suspend fun getSystemStatus(): SystemStatus {
        val method = "getSystemStatus"
        logDebug(method, "Fetching system health from $baseUrl")

        val client = io.ktor.client.HttpClient {
            install(io.ktor.client.plugins.contentnegotiation.ContentNegotiation) { json(jsonConfig) }
            install(io.ktor.client.plugins.HttpTimeout) {
                requestTimeoutMillis = 10000
                connectTimeoutMillis = 5000
            }
        }

        return try {
            val response = client.get("$baseUrl/v1/system/health") {
                authHeader()?.let { header("Authorization", it) }
            }

            if (!response.status.isSuccess()) {
                throw RuntimeException("Health check failed: ${response.status}")
            }

            val body = response.bodyAsText()
            logDebug(method, "Response body: ${body.take(200)}...")

            // Parse JSON response
            val json = kotlinx.serialization.json.Json { ignoreUnknownKeys = true }
            val parsed = json.parseToJsonElement(body).jsonObject
            val data = parsed["data"]?.jsonObject

            val status = data?.get("status")?.jsonPrimitive?.contentOrNull ?: "unknown"
            val cognitiveState = data?.get("cognitive_state")?.jsonPrimitive?.contentOrNull

            // Parse services for counts
            var healthyCount = 0
            var totalCount = 0
            data?.get("services")?.jsonObject?.forEach { (_, info) ->
                val svcInfo = info.jsonObject
                val svcHealthy = svcInfo["healthy"]?.jsonPrimitive?.intOrNull ?: 0
                val svcAvailable = svcInfo["available"]?.jsonPrimitive?.intOrNull ?: 0
                healthyCount += svcHealthy
                totalCount += svcAvailable
            }

            logDebug(method, "System status: $status, cognitive_state: $cognitiveState, services: $healthyCount/$totalCount")

            SystemStatus(
                status = status,
                cognitive_state = cognitiveState,
                services_online = healthyCount,
                services_total = totalCount,
                services = emptyMap()
            )
        } catch (e: Exception) {
            logException(method, e, "url=$baseUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Probe the node's structured server health at `/v1/health` (unauthenticated —
     * liveness is public). Returns the [NodeHealth] facts that drive the universal
     * client's node-vs-agent gate ([ai.ciris.mobile.shared.models.ClientMode]) and
     * the version-mismatch banner: the node `version`, its `role`
     * (`"fabric-node"` for a bare node), and the optional `cognitive_state` (present
     * only when an agent enriches the endpoint).
     *
     * `/v1/health` is a SUBSTRATE prefix — served natively by the NODE on :4243 and
     * never proxied from the brain, and the Python brain on :8080 does not serve it
     * at all. Callers must therefore pass the NODE base URL; the [baseUrl] default
     * is kept only for clients already constructed against the node.
     */
    suspend fun getNodeHealth(nodeUrl: String = baseUrl): NodeHealth {
        val method = "getNodeHealth"
        logDebug(method, "Probing node health at $nodeUrl/v1/health")

        val client = io.ktor.client.HttpClient {
            install(io.ktor.client.plugins.contentnegotiation.ContentNegotiation) { json(jsonConfig) }
            install(io.ktor.client.plugins.HttpTimeout) {
                requestTimeoutMillis = 10000
                connectTimeoutMillis = 5000
            }
        }

        return try {
            val response = client.get("$nodeUrl/v1/health") {
                authHeader()?.let { header("Authorization", it) }
            }

            if (!response.status.isSuccess()) {
                throw RuntimeException("Node health failed: ${response.status}")
            }

            val body = response.bodyAsText()
            val json = kotlinx.serialization.json.Json { ignoreUnknownKeys = true }
            val data = json.parseToJsonElement(body).jsonObject["data"]?.jsonObject

            val cognitiveState = data?.get("cognitive_state")?.jsonPrimitive?.contentOrNull
            var serviceCount = 0
            data?.get("services")?.jsonObject?.forEach { (_, _) -> serviceCount++ }

            NodeHealth(
                status = data?.get("status")?.jsonPrimitive?.contentOrNull ?: "unknown",
                role = data?.get("role")?.jsonPrimitive?.contentOrNull,
                version = data?.get("version")?.jsonPrimitive?.contentOrNull,
                cognitiveState = cognitiveState,
                serviceCount = serviceCount
            )
        } finally {
            client.close()
        }
    }

    override suspend fun getTelemetry(): TelemetryResponse {
        val method = "getTelemetry"
        logDebug(method, "Fetching telemetry overview")

        return try {
            val response = telemetryApi.getTelemetryOverviewV1TelemetryOverviewGet(authHeader())
            logDebug(method, "Response: status=${response.status}")

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")

            val healthyServices = data.healthyServices ?: 0
            val degradedServices = data.degradedServices ?: 0
            val cpuPercent = data.cpuPercent ?: 0.0
            val memoryMb = data.memoryMb ?: 0.0
            val messagesProcessed24h = data.messagesProcessed24h ?: 0
            val tasksCompleted24h = data.tasksCompleted24h ?: 0
            val errors24h = data.errors24h ?: 0

            logInfo(method, "Telemetry: uptime=${data.uptimeSeconds}s, state=${data.cognitiveState}, " +
                    "services=${healthyServices}/${healthyServices + degradedServices}, " +
                    "cpu=${cpuPercent}%, memory=${memoryMb}MB")

            TelemetryResponse(
                data = TelemetryData(
                    agent_id = "",
                    uptime_seconds = data.uptimeSeconds,
                    cognitive_state = data.cognitiveState,
                    services_online = healthyServices,
                    services_total = healthyServices + degradedServices,
                    services = emptyMap(),
                    cpu_percent = cpuPercent,
                    memory_mb = memoryMb,
                    messages_processed_24h = messagesProcessed24h,
                    tasks_completed_24h = tasksCompleted24h,
                    errors_24h = errors24h
                )
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    // Authentication
    override suspend fun login(username: String, password: String): AuthResponse {
        val method = "login"
        logInfo(method, "Attempting login for user: $username")

        return try {
            val request = SdkLoginRequest(username = username, password = password)
            val response = authApi.loginV1AuthLoginPost(request)
            logDebug(method, "Response: status=${response.status}")

            val body = response.body()
            logInfo(method, "Login successful: userId=${body.userId}, role=${body.role}")

            AuthResponse(
                access_token = body.accessToken,
                token_type = "bearer",
                user = UserInfo(
                    user_id = body.userId,
                    email = "",
                    name = null,
                    photo_url = null,
                    role = body.role.value
                )
            )
        } catch (e: Exception) {
            logException(method, e, "username=$username")
            throw e
        }
    }

    override suspend fun getOwnerHint(nodeUrl: String?): OwnerHint? {
        val method = "getOwnerHint"
        val hintUrl = nodeUrl ?: baseUrl
        // Personal-install-only endpoint shipped in 2.9.2. On a server
        // install the backend returns 404 and we render an empty hint —
        // never throw, never block the Login UI on a slow / offline
        // backend, never log at ERROR for the expected 404 case.
        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
            }
            try {
                val response: HttpResponse = client.get("$hintUrl/v1/auth/owner-hint")
                if (response.status.value == 404) {
                    logDebug(method, "owner-hint endpoint returned 404 (multi-tenant server or pre-2.9.2 backend)")
                    return null
                }
                if (response.status.value !in 200..299) {
                    logWarn(method, "owner-hint returned ${response.status} — rendering empty hint")
                    return null
                }
                val body: OwnerHintResponse = response.body()
                val hint = body.owner_hint
                if (hint == null) {
                    logInfo(method, "owner-hint endpoint returned null hint (setup not complete yet)")
                } else {
                    logInfo(method, "owner-hint: provider=${hint.oauth_provider} authType=${hint.auth_type}")
                }
                hint
            } finally {
                client.close()
            }
        } catch (e: Exception) {
            // Network/parse failure — log at DEBUG and degrade silently.
            // The Login screen renders fine without a hint.
            logDebug(method, "owner-hint fetch failed (${e::class.simpleName}: ${e.message?.take(60)}); rendering empty hint")
            null
        }
    }

    override suspend fun googleAuth(idToken: String, userId: String?): AuthResponse {
        val method = "googleAuth"
        logInfo(method, "Attempting Google auth: userId=$userId, idToken=${maskToken(idToken)}")

        return try {
            val request = SdkNativeTokenRequest(
                idToken = idToken,
                provider = "google"
            )
            logDebug(method, "Calling nativeGoogleTokenExchangeV1AuthNativeGooglePost")

            val response = authApi.nativeGoogleTokenExchangeV1AuthNativeGooglePost(request)
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                val errorBody = try {
                    response.response.bodyAsText()
                } catch (_: Exception) { "Unknown error" }
                logError(method, "Server returned ${response.status}: $errorBody")
                throw Exception("Token exchange failed (${response.status}): $errorBody")
            }

            // DECODE FAILURES MUST SAY WHAT CAME BACK (CIRISAgent#1056).
            //
            // A 2xx whose body does not match NativeTokenResponse used to escape
            // as ktor's own message:
            //
            //   NoTransformationFoundException: Expected response body of the type
            //   ai.ciris.api.models.NativeTokenResponse but was SourceByteReadChannel
            //
            // On Android that left the user staring at the Login screen after a
            // SUCCESSFUL Google sign-in, with nothing in the log naming the
            // endpoint, the status, the content type, or a single byte of what the
            // server actually sent. The `!response.success` branch above builds a
            // good diagnostic and is simply never reached in this case.
            val body = try {
                response.body()
            } catch (e: Exception) {
                val contentType = try {
                    response.response.headers["Content-Type"] ?: "(none)"
                } catch (_: Exception) { "(unreadable)" }
                val raw = try {
                    response.response.bodyAsText().take(400)
                } catch (_: Exception) { "(body unreadable)" }
                logError(
                    method,
                    "Token exchange returned ${response.status} but the body could not be decoded as " +
                        "NativeTokenResponse. content-type=$contentType body=$raw",
                )
                throw Exception(
                    "Token exchange returned ${response.status} with a body this client cannot read " +
                        "(content-type=$contentType). First bytes: $raw",
                )
            }
            logInfo(method, "Google auth successful: userId=${body.userId}, role=${body.role}")

            AuthResponse(
                access_token = body.accessToken,
                token_type = "bearer",
                user = UserInfo(
                    user_id = body.userId,
                    email = "",
                    name = null,
                    photo_url = null,
                    role = body.role
                )
            )
        } catch (e: Exception) {
            logException(method, e, "userId=$userId")
            throw e
        }
    }

    override suspend fun appleAuth(idToken: String, userId: String?): AuthResponse {
        val method = "appleAuth"
        logInfo(method, "Attempting Apple auth: userId=$userId, idToken=${maskToken(idToken)}")

        return try {
            // Use manual HTTP request since generated SDK doesn't include Apple auth endpoint
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
                install(Logging) {
                    level = LogLevel.INFO
                }
            }

            val requestBody = mapOf(
                "id_token" to idToken,
                "provider" to "apple"
            )

            logDebug(method, "POST $baseUrl/v1/auth/native/apple")
            val response: HttpResponse = client.post("$baseUrl/v1/auth/native/apple") {
                contentType(ContentType.Application.Json)
                setBody(requestBody)
            }

            logDebug(method, "Response status: ${response.status}")

            if (response.status.value !in 200..299) {
                val errorBody = response.body<String>()
                logError(method, "Apple auth failed: ${response.status} - $errorBody")
                throw Exception("Apple auth failed: ${response.status}")
            }

            val body: NativeTokenResponseBody = response.body()
            logInfo(method, "Apple auth successful: userId=${body.userId}, role=${body.role}")

            client.close()

            AuthResponse(
                access_token = body.accessToken,
                token_type = "bearer",
                user = UserInfo(
                    user_id = body.userId,
                    email = body.email ?: "",
                    name = body.name,
                    photo_url = null,
                    role = body.role
                )
            )
        } catch (e: Exception) {
            logException(method, e, "userId=$userId")
            throw e
        }
    }

    @Serializable
    private data class NativeTokenResponseBody(
        @SerialName("access_token") val accessToken: String,
        @SerialName("token_type") val tokenType: String,
        @SerialName("expires_in") val expiresIn: Int,
        @SerialName("user_id") val userId: String,
        val role: String,
        val email: String? = null,
        val name: String? = null
    )

    override suspend fun nativeAuth(idToken: String, userId: String?, provider: String): AuthResponse {
        val method = "nativeAuth"
        logInfo(method, "Attempting native auth: provider=$provider, userId=$userId")

        return when (provider.lowercase()) {
            "google" -> googleAuth(idToken, userId)
            "apple" -> appleAuth(idToken, userId)
            else -> throw IllegalArgumentException("Unknown OAuth provider: $provider")
        }
    }

    override suspend fun logout() {
        val method = "logout"
        logInfo(method, "Logging out")

        try {
            authApi.logoutV1AuthLogoutPost(authHeader())
            logInfo(method, "Logout successful")
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    // Shutdown controls
    override suspend fun initiateShutdown() {
        val method = "initiateShutdown"
        logInfo(method, "Initiating graceful shutdown")

        try {
            val request = SdkShutdownRequest(
                reason = "User requested shutdown",
                confirm = true
            )
            systemApi.shutdownSystemV1SystemShutdownPost(request, authHeader())
            logInfo(method, "Shutdown initiated successfully")
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    override suspend fun emergencyShutdown() {
        val method = "emergencyShutdown"
        logWarn(method, "Initiating EMERGENCY shutdown")

        try {
            val request = SdkShutdownRequest(
                reason = "Emergency shutdown",
                confirm = true,
                force = true
            )
            systemApi.shutdownSystemV1SystemShutdownPost(request, authHeader())
            logInfo(method, "Emergency shutdown initiated successfully")
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    // Cognitive state transitions
    override suspend fun transitionCognitiveState(targetState: String, reason: String?): StateTransitionResult {
        val method = "transitionCognitiveState"
        logInfo(method, "Transitioning cognitive state to: $targetState, reason: $reason")

        return try {
            val request = SdkStateTransitionRequest(
                targetState = targetState,
                reason = reason
            )
            logDebug(method, "Created SdkStateTransitionRequest: targetState=$targetState, reason=$reason")

            val response = systemApi.transitionCognitiveStateV1SystemStateTransitionPost(request, authHeader())
            logDebug(method, "Response: status=${response.status}")

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")

            logInfo(method, "Transition result: success=${data.success}, currentState=${data.currentState}, previousState=${data.previousState}, message=${data.message}")

            StateTransitionResult(
                success = data.success,
                message = data.message,
                currentState = data.currentState,
                previousState = data.previousState
            )
        } catch (e: Exception) {
            logException(method, e, "targetState=$targetState, reason=$reason")
            throw e
        }
    }

    // Setup wizard
    override suspend fun getSetupStatus(): SetupStatusResponse {
        val method = "getSetupStatus"
        logDebug(method, "Fetching setup status")

        return try {
            val response = setupApi.getSetupStatusV1SetupStatusGet()
            logDebug(method, "Response: status=${response.status}")

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")

            logInfo(method, "Setup status: required=${data.setupRequired}, firstRun=${data.isFirstRun}, configExists=${data.configExists}")

            SetupStatusResponse(
                data = SetupStatusData(
                    setup_required = data.setupRequired,
                    has_env_file = data.configExists,
                    has_admin_user = !data.isFirstRun
                )
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * Get available adapters for setup wizard.
     * Returns ALL adapters with their platform requirements.
     * Call filterAdaptersForPlatform() to filter based on current platform.
     */
    suspend fun getSetupAdapters(): List<CommunicationAdapter> {
        val method = "getSetupAdapters"
        logDebug(method, "Fetching setup adapters")

        return try {
            val response = setupApi.listAdaptersV1SetupAdaptersGet()
            logDebug(method, "Response: status=${response.status}")

            val body = response.body()
            val adapters = body.`data` ?: emptyList()

            logInfo(method, "Fetched ${adapters.size} adapters")

            adapters.map { adapter ->
                CommunicationAdapter(
                    id = adapter.id,
                    name = adapter.name,
                    description = adapter.description,
                    // Use backend's requires_config field (wizard-based adapters)
                    requires_config = adapter.requiresConfig ?: false,
                    config_fields = adapter.configFields ?: emptyList(),
                    requires_binaries = adapter.requiresBinaries ?: false,
                    required_binaries = adapter.requiredBinaries ?: emptyList(),
                    supported_platforms = adapter.supportedPlatforms ?: emptyList(),
                    requires_ciris_services = adapter.requiresCirisServices ?: false,
                    enabled_by_default = adapter.enabledByDefault ?: false
                )
            }
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * Get available agent templates from setup API.
     * V1.9.7: Added for Advanced Settings template selection.
     */
    suspend fun getSetupTemplates(): List<AgentTemplateInfo> {
        val method = "getSetupTemplates"
        logDebug(method, "Fetching setup templates")

        return try {
            val response = setupApi.listTemplatesV1SetupTemplatesGet()
            logDebug(method, "Response: status=${response.status}")

            val body = response.body()
            val templates = body.`data` ?: emptyList()

            logInfo(method, "Fetched ${templates.size} templates")

            templates.map { template ->
                AgentTemplateInfo(
                    id = template.id,
                    name = template.name,
                    description = template.description
                )
            }
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * Get the exhaustive tool disclosure for the first-run wizard.
     * Calls GET /v1/setup/tool-disclosure (no auth required during setup).
     *
     * The server generates this from each tool service's own get_all_tool_info(),
     * so it always reflects what is actually registered. Used by the
     * OPTIONAL_FEATURES step to tell the operator what each adapter choice grants
     * and which tools no choice controls.
     *
     * Not part of the generated SDK surface, so this uses a direct request in the
     * same idiom as getAgentMode().
     */
    /**
     * The substrate's OWN consent copy for the wizard's federation screen —
     * `GET {apiBaseUrl}/v1/setup/consent-disclosure`, which serves
     * `ciris_server.consent_disclosure()` unedited.
     *
     * THROWS rather than returning a default. There is no honest fallback: the
     * screen exists to render the substrate's words, and inventing a substitute
     * is exactly the drift the export was written to prevent.
     */
    suspend fun getConsentDisclosure(): ai.ciris.mobile.shared.models.ConsentDisclosure {
        val method = "getConsentDisclosure"
        logDebug(method, "Fetching consent disclosure from $baseUrl/v1/setup/consent-disclosure")
        val client = io.ktor.client.HttpClient {
            install(io.ktor.client.plugins.HttpTimeout) {
                requestTimeoutMillis = 15000
                connectTimeoutMillis = 5000
            }
        }
        return try {
            val response = client.get("$baseUrl/v1/setup/consent-disclosure") {
                authHeader()?.let { header("Authorization", it) }
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("Consent disclosure fetch failed: ${response.status}")
            }
            val root = Json.parseToJsonElement(response.bodyAsText()).jsonObject
            val data = root["data"] ?: throw RuntimeException("Consent disclosure response has no data")
            val disclosure = Json { ignoreUnknownKeys = true }.decodeFromJsonElement(
                ai.ciris.mobile.shared.models.ConsentDisclosure.serializer(),
                data,
            )
            logInfo(
                method,
                "Fetched consent disclosure: ${disclosure.grants.size} grants, " +
                    "location max_resolution=${disclosure.location.maxResolution}, " +
                    "locale=${disclosure.sourceLocale}",
            )
            disclosure
        } catch (e: Exception) {
            logException(method, e, "url=$baseUrl")
            throw e
        } finally {
            client.close()
        }
    }

    suspend fun getSetupToolDisclosure(): ToolDisclosureReport {
        val method = "getSetupToolDisclosure"
        logDebug(method, "Fetching tool disclosure from $baseUrl/v1/setup/tool-disclosure")
        val client = io.ktor.client.HttpClient {
            install(io.ktor.client.plugins.HttpTimeout) {
                requestTimeoutMillis = 30000
                connectTimeoutMillis = 5000
            }
        }
        return try {
            val response = client.get("$baseUrl/v1/setup/tool-disclosure") {
                authHeader()?.let { header("Authorization", it) }
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("Tool disclosure fetch failed: ${response.status}")
            }
            val root = Json.parseToJsonElement(response.bodyAsText()).jsonObject
            val data = root["data"] ?: throw RuntimeException("Tool disclosure response has no data")
            val decoder = Json { ignoreUnknownKeys = true }
            val report = decoder.decodeFromJsonElement(
                ToolDisclosureReport.serializer(),
                data
            )
            logInfo(method, "Fetched disclosure: ${report.total_tools} tools across " +
                "${report.adapters.size} adapters + ${report.always_on.size} always-on groups")
            report
        } catch (e: Exception) {
            logException(method, e, "url=$baseUrl")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Validate LLM configuration by testing the connection.
     * Calls POST /v1/setup/validate-llm
     *
     * @param provider Provider ID (openai, anthropic, local, other)
     * @param apiKey API key for the provider
     * @param baseUrl Optional base URL for custom endpoints
     * @param model Optional model name to test
     * @return LlmValidationResult with success/failure status and message
     */
    suspend fun validateLlmConfiguration(
        provider: String,
        apiKey: String,
        baseUrl: String? = null,
        model: String? = null
    ): LlmValidationResult {
        val method = "validateLlmConfiguration"
        logInfo(method, "Validating LLM config: provider=$provider, baseUrl=${baseUrl ?: "default"}, model=${model ?: "default"}")

        return try {
            val request = ai.ciris.api.models.LLMValidationRequest(
                provider = provider,
                apiKey = apiKey,
                baseUrl = baseUrl,
                model = model
            )

            val response = setupApi.validateLlmV1SetupValidateLlmPost(request)
            logDebug(method, "Response: status=${response.status}")

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")

            logInfo(method, "Validation result: valid=${data.valid}, message=${data.message}")

            LlmValidationResult(
                valid = data.valid,
                message = data.message,
                error = data.error
            )
        } catch (e: Exception) {
            logException(method, e)
            LlmValidationResult(
                valid = false,
                message = "Connection failed",
                error = e.message ?: "Unknown error"
            )
        }
    }

    /**
     * List available models from a provider's live API.
     * Calls POST /v1/setup/list-models
     *
     * @param provider Provider ID (openai, anthropic, local, other)
     * @param apiKey API key for the provider
     * @param baseUrl Optional base URL for custom endpoints
     * @return [ModelListResult] — the models AND whether they came from the
     *         provider ("live") or from cached static data ("static"). Callers
     *         must not present a static list as the provider's catalogue.
     */
    suspend fun listModels(
        provider: String,
        apiKey: String,
        baseUrl: String? = null
    ): ModelListResult {
        val method = "listModels"
        logInfo(method, "Listing models: provider=$provider, baseUrl=${baseUrl ?: "default"}")

        return try {
            // Use manual HTTP request to ensure auth header is sent
            // (generated SDK has requiresAuthentication=false for this endpoint)
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
            }

            val requestBody = mapOf(
                "provider" to provider,
                "api_key" to apiKey,
                "base_url" to baseUrl
            )

            val response = client.post("${this.baseUrl}/v1/setup/list-models") {
                authHeader()?.let { header("Authorization", it) }
                contentType(io.ktor.http.ContentType.Application.Json)
                setBody(requestBody)
            }

            logDebug(method, "Response: status=${response.status}")
            client.close()

            if (response.status.value !in 200..299) {
                logError(method, "API returned error status: ${response.status}")
                return ModelListResult(emptyList(), "error", "HTTP ${response.status}")
            }

            val body = response.body<ListModelsApiResponse>()
            val data = body.data
                ?: return ModelListResult(emptyList(), "error", "empty response body")

            val models = data.models?.map { model ->
                ModelInfo(
                    id = model.id ?: "",
                    displayName = model.displayName ?: model.id ?: "Unknown",
                    cirisCompatible = model.cirisCompatible ?: false,
                    cirisRecommended = model.cirisRecommended ?: false,
                    contextWindow = model.contextWindow
                )
            } ?: emptyList()

            val source = data.source ?: "unknown"
            if (source != "live") {
                // Say WHY, at WARN. This was an INFO line that reported the
                // source and swallowed the reason, so the one signal that the
                // list was not the provider's went unnoticed in both the log
                // and the UI.
                logWarn(method, "Models are NOT live (source=$source): ${data.error ?: "no reason given"}")
            } else {
                logInfo(method, "Listed ${models.size} models from live")
            }
            ModelListResult(models, source, data.error)
        } catch (e: Exception) {
            logException(method, e)
            ModelListResult(emptyList(), "error", e.message ?: e::class.simpleName)
        }
    }

    /**
     * What `listModels` returned AND where it came from.
     *
     * CIRISAgent#1062. This used to be a bare `List<ModelInfo>`, so a live list
     * and a cached static fallback were the same value. All three call sites —
     * the setup wizard, LLM settings, and the settings view-model — then
     * auto-selected "the best model" out of whichever they got. A user who set
     * up Groq while the live query was failing picked from OpenAI-flavoured
     * cached data, and nothing on screen said the list was not his provider's.
     *
     * `source` is "live" or "static"; `error` is the reason the live query
     * failed, which the server has always sent and we always discarded.
     */
    data class ModelListResult(
        val models: List<ModelInfo>,
        val source: String,
        val error: String? = null
    ) {
        /** True only when this list actually came from the provider. */
        val isLive: Boolean get() = source == "live"
    }

    /**
     * Response wrapper for /v1/setup/list-models endpoint
     */
    @Serializable
    private data class ListModelsApiResponse(
        val status: String? = null,
        val data: ListModelsData? = null
    )

    @Serializable
    private data class ListModelsData(
        val source: String? = null,
        val models: List<LiveModelInfo>? = null,
        // The server ALREADY sends this on a static fallback ("Live query failed:
        // <cause>. Showing cached model data.") and we were dropping it on the
        // floor, which is why a stale list was indistinguishable from a live one.
        val error: String? = null
    )

    @Serializable
    private data class LiveModelInfo(
        val id: String? = null,
        @SerialName("display_name") val displayName: String? = null,
        @SerialName("ciris_compatible") val cirisCompatible: Boolean? = null,
        @SerialName("ciris_recommended") val cirisRecommended: Boolean? = null,
        @SerialName("context_window") val contextWindow: Int? = null
    )

    /**
     * Discover local LLM inference servers on the network.
     * Uses hostname probing and port scanning to find servers like:
     * - Ollama (port 11434)
     * - llama.cpp (port 8080)
     * - vLLM (port 8000)
     * - LM Studio (port 1234)
     *
     * @param timeoutSeconds Total timeout for discovery (default 5.0)
     * @param includeLocalhost Whether to probe localhost ports (default true)
     * @return List of discovered servers with their available models
     */
    suspend fun discoverLocalLlmServers(
        timeoutSeconds: Float = 12.0f,
        includeLocalhost: Boolean = true
    ): List<DiscoveredLlmServer> {
        val method = "discoverLocalLlmServers"
        logInfo(method, "Discovering local LLM servers (timeout=${timeoutSeconds}s, localhost=$includeLocalhost)")

        return try {
            // Use longer HTTP timeout since discovery involves mDNS + HTTP probes
            val httpTimeoutMs = ((timeoutSeconds + 8) * 1000).toLong()
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = httpTimeoutMs
                    socketTimeoutMillis = httpTimeoutMs
                    connectTimeoutMillis = 5000
                }
            }

            val response = client.post("${this.baseUrl}/v1/setup/discover-local-llm") {
                authHeader()?.let { header("Authorization", it) }
                contentType(io.ktor.http.ContentType.Application.Json)
                setBody(DiscoverLlmRequest(timeoutSeconds, includeLocalhost))
            }

            logDebug(method, "Response: status=${response.status}")
            client.close()

            if (response.status.value !in 200..299) {
                logError(method, "API returned error status: ${response.status}")
                return emptyList()
            }

            val body = response.body<DiscoverLlmApiResponse>()
            val data = body.data ?: return emptyList()

            val servers = data.servers?.map { server ->
                DiscoveredLlmServer(
                    id = server.id ?: "",
                    label = server.label ?: server.url ?: "Unknown",
                    url = server.url ?: "",
                    serverType = server.serverType ?: "unknown",
                    modelCount = server.modelCount ?: 0,
                    models = server.models ?: emptyList()
                )
            } ?: emptyList()

            logInfo(method, "Discovered ${servers.size} servers via ${data.discoveryMethods?.joinToString() ?: "unknown"}")
            servers
        } catch (e: Exception) {
            logException(method, e)
            emptyList()
        }
    }

    /**
     * Response wrapper for /v1/setup/discover-local-llm endpoint
     */
    @Serializable
    private data class DiscoverLlmRequest(
        @SerialName("timeout_seconds") val timeoutSeconds: Float,
        @SerialName("include_localhost") val includeLocalhost: Boolean
    )

    @Serializable
    private data class DiscoverLlmApiResponse(
        val status: String? = null,
        val data: DiscoverLlmData? = null,
        val metadata: JsonObject? = null  // SuccessResponse wrapper metadata
    )

    @Serializable
    private data class DiscoverLlmData(
        val servers: List<DiscoveredLlmServerApi>? = null,
        @SerialName("total_count") val totalCount: Int? = null,
        @SerialName("discovery_methods") val discoveryMethods: List<String>? = null,
        val error: String? = null
    )

    @Serializable
    private data class DiscoveredLlmServerApi(
        val id: String? = null,
        val label: String? = null,
        val url: String? = null,
        @SerialName("server_type") val serverType: String? = null,
        @SerialName("model_count") val modelCount: Int? = null,
        val models: List<String>? = null,
        val metadata: JsonObject? = null  // Server metadata (hostname, ip, port, source)
    )

    /**
     * Start a local LLM inference server (llama.cpp or Ollama).
     *
     * Used when the device is capable of local inference but no server is
     * currently running. This starts the server in the background with a
     * keepalive. After starting, call discoverLocalLlmServers() to find it.
     *
     * @param serverType Server to start: "llama_cpp" or "ollama"
     * @param model Model to load: "gemma-4-e2b" or "gemma-4-e4b"
     * @param port Port for the server (default 8080)
     * @param confirmDownload If true, confirms model download if needed
     * @return StartLocalServerResult with success status and server info
     */
    suspend fun startLocalLlmServer(
        serverType: String = "llama_cpp",
        model: String = "gemma-4-e2b",
        port: Int = 8080,
        confirmDownload: Boolean = false
    ): StartLocalServerResult {
        val method = "startLocalLlmServer"
        logInfo(method, "Starting local LLM server (type=$serverType, model=$model, port=$port, confirmDownload=$confirmDownload)")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = 120_000  // Starting server can take time
                    connectTimeoutMillis = 10_000
                }
            }

            val response = client.post("${this.baseUrl}/v1/setup/start-local-server") {
                authHeader()?.let { header("Authorization", it) }
                contentType(io.ktor.http.ContentType.Application.Json)
                setBody(StartLocalServerRequest(serverType, model, port, confirmDownload))
            }

            logDebug(method, "Response: status=${response.status}")
            client.close()

            if (response.status.value !in 200..299) {
                logError(method, "API returned error status: ${response.status}")
                return StartLocalServerResult(
                    success = false,
                    message = "Server returned error: ${response.status}"
                )
            }

            val body = response.body<StartLocalServerApiResponse>()
            val data = body.data ?: return StartLocalServerResult(
                success = false,
                message = "Invalid response from server"
            )

            val result = StartLocalServerResult(
                success = data.success ?: false,
                serverUrl = data.serverUrl,
                serverType = data.serverType ?: serverType,
                model = data.model ?: model,
                pid = data.pid,
                message = data.message ?: "Unknown status",
                estimatedReadySeconds = data.estimatedReadySeconds ?: 60,
                requiresDownload = data.requiresDownload ?: false,
                downloadSize = data.downloadSize
            )

            logInfo(method, "Start server result: success=${result.success}, message=${result.message}")
            result
        } catch (e: Exception) {
            logException(method, e)
            StartLocalServerResult(
                success = false,
                message = "Failed to start server: ${e.message ?: "Unknown error"}"
            )
        }
    }

    /**
     * Request for starting a local LLM server
     */
    @Serializable
    private data class StartLocalServerRequest(
        @SerialName("server_type") val serverType: String,
        val model: String,
        val port: Int,
        @SerialName("confirm_download") val confirmDownload: Boolean = false
    )

    @Serializable
    private data class StartLocalServerApiResponse(
        val status: String? = null,
        val data: StartLocalServerData? = null,
        val metadata: JsonObject? = null
    )

    @Serializable
    private data class StartLocalServerData(
        val success: Boolean? = null,
        @SerialName("server_url") val serverUrl: String? = null,
        @SerialName("server_type") val serverType: String? = null,
        val model: String? = null,
        val pid: Int? = null,
        val message: String? = null,
        @SerialName("estimated_ready_seconds") val estimatedReadySeconds: Int? = null,
        @SerialName("requires_download") val requiresDownload: Boolean? = null,
        @SerialName("download_size") val downloadSize: String? = null
    )

    /**
     * Get CIRISVerify status for Trust and Security display.
     * V2.0: CIRISVerify is REQUIRED for CIRIS 2.0+ agents.
     *
     * Returns the status of CIRISVerify including:
     * - Whether the library is loaded (REQUIRED for CIRIS 2.0+)
     * - Hardware security type (TPM, Secure Enclave, Software)
     * - Key status (none, ephemeral, portal_pending, portal_active)
     * - Attestation status
     */
    suspend fun getVerifyStatus(
        playIntegrityToken: String? = null,
        playIntegrityNonce: String? = null,
        refresh: Boolean = false
    ): VerifyStatusResponse {
        val method = "getVerifyStatus"
        // NODE mode: the ciris-server fabric node serves a read-only
        // `GET /v1/system/verify-status` (src/health.rs verify_status_router) —
        // CIRISVerify is part of the node substrate, so it reports loaded +
        // the node's derived federation key_id + custody class + attestation
        // checks. (The agent path below uses /v1/auth/attestation, which on a
        // bare node is a POST-only EMIT route and 405s on a GET.)
        logDebug(method, "Fetching CIRISVerify status (node=${isNodeMode()}, hasPlayIntegrity=${playIntegrityToken != null})")

        // Uses cached attestation from auth service - should be fast
        // Full attestation with Play Integrity may take longer
        val timeoutMs = 30000L
        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = timeoutMs
                connectTimeoutMillis = 10000
                socketTimeoutMillis = timeoutMs
            }
        }

        return try {
            // Use auth/attestation endpoint for cached attestation (fast, no network calls)
            // Falls back to setup/verify-status only during first-run setup with Play Integrity
            val url = if (playIntegrityToken != null && playIntegrityNonce != null) {
                // Full attestation with Play Integrity - use setup endpoint (first-run only)
                "$baseUrl/v1/setup/verify-status?mode=full&play_integrity_token=$playIntegrityToken&play_integrity_nonce=$playIntegrityNonce"
            } else {
                // Verify is substrate-owned. The read-only status route lives on the
                // node (:4243 serves it natively); in AGENT mode (iOS/desktop bundle,
                // isNodeMode()==false) the agent's front door proxies the SAME path to
                // the node (auth_proxy.py `proxy_verify_status_to_node`). Both answer a
                // GET 200. The old agent-mode fallback hit `/v1/auth/attestation`, which
                // 2.9.14 made a POST-only node route → GET 405 every 30s (132×/session on
                // a live iPhone). One path for both modes closes that for good; `refresh`
                // rides through as a query param the node honors (or safely ignores).
                val base = "$baseUrl/v1/system/verify-status"
                if (refresh) "$base?refresh=true" else base
            }
            val response = client.get(url)

            if (response.status != HttpStatusCode.OK) {
                val errorDetail = try {
                    val errBody = response.body<JsonObject>()
                    (errBody["detail"] as? JsonPrimitive)?.content
                } catch (_: Exception) { null }
                throw Exception(errorDetail ?: "Verify status failed: HTTP ${response.status}")
            }

            val body = response.body<JsonObject>()
            val data = body["data"] as? JsonObject
                ?: throw Exception("Invalid response format")

            // DEBUG: Log raw API response fields (debug level to reduce spam)
            logDebug(method, "=== RAW API RESPONSE DEBUG ===")
            logDebug(method, "files_checked=${data["files_checked"]}")
            logDebug(method, "files_passed=${data["files_passed"]}")
            logDebug(method, "per_file_results keys=${(data["per_file_results"] as? JsonObject)?.keys?.size ?: 0}")
            logDebug(method, "python_modules_checked=${data["python_modules_checked"]}")
            logDebug(method, "python_modules_passed=${data["python_modules_passed"]}")
            logDebug(method, "module_integrity_ok=${data["module_integrity_ok"]}")
            logDebug(method, "module_integrity_summary=${data["module_integrity_summary"]}")
            logDebug(method, "cross_validated_files count=${(data["cross_validated_files"] as? kotlinx.serialization.json.JsonArray)?.size ?: 0}")
            logDebug(method, "filesystem_verified_files count=${(data["filesystem_verified_files"] as? kotlinx.serialization.json.JsonArray)?.size ?: 0}")
            logDebug(method, "agent_verified_files count=${(data["agent_verified_files"] as? kotlinx.serialization.json.JsonArray)?.size ?: 0}")
            logDebug(method, "=== END RAW API RESPONSE DEBUG ===")

            val loaded = (data["loaded"] as? JsonPrimitive)?.content?.toBoolean() ?: false
            val verifyStatus = VerifyStatusResponse(
                loaded = loaded,
                version = (data["version"] as? JsonPrimitive)?.content,
                agentVersion = (data["agent_version"] as? JsonPrimitive)?.content,
                hardwareType = (data["hardware_type"] as? JsonPrimitive)?.content,
                keyStatus = (data["key_status"] as? JsonPrimitive)?.content ?: "none",
                keyId = (data["key_id"] as? JsonPrimitive)?.content,
                attestationStatus = (data["attestation_status"] as? JsonPrimitive)?.content ?: "not_attempted",
                error = (data["error"] as? JsonPrimitive)?.content,
                diagnosticInfo = (data["diagnostic_info"] as? JsonPrimitive)?.content,
                disclaimer = (data["disclaimer"] as? JsonPrimitive)?.content
                    ?: "CIRISVerify provides cryptographic attestation of agent identity.",
                // Attestation level checks
                dnsUsOk = (data["dns_us_ok"] as? JsonPrimitive)?.content?.toBoolean() ?: false,
                dnsEuOk = (data["dns_eu_ok"] as? JsonPrimitive)?.content?.toBoolean() ?: false,
                httpsUsOk = (data["https_us_ok"] as? JsonPrimitive)?.content?.toBoolean() ?: false,
                httpsEuOk = (data["https_eu_ok"] as? JsonPrimitive)?.content?.toBoolean() ?: false,
                binaryOk = (data["binary_ok"] as? JsonPrimitive)?.content?.toBoolean() ?: false,
                fileIntegrityOk = (data["file_integrity_ok"] as? JsonPrimitive)?.content?.toBoolean() ?: false,
                registryOk = (data["registry_ok"] as? JsonPrimitive)?.content?.toBoolean() ?: false,
                auditOk = (data["audit_ok"] as? JsonPrimitive)?.content?.toBoolean() ?: false,
                envOk = (data["env_ok"] as? JsonPrimitive)?.content?.toBoolean() ?: false,
                playIntegrityOk = (data["play_integrity_ok"] as? JsonPrimitive)?.content?.toBoolean() ?: false,
                playIntegrityVerdict = (data["play_integrity_verdict"] as? JsonPrimitive)?.content,
                maxLevel = (data["max_level"] as? JsonPrimitive)?.content?.toIntOrNull() ?: 0,
                levelPending = (data["level_pending"] as? JsonPrimitive)?.content?.toBoolean() ?: false,
                // New detailed fields
                attestationMode = (data["attestation_mode"] as? JsonPrimitive)?.content ?: "partial",
                platformOs = (data["platform_os"] as? JsonPrimitive)?.content,
                platformArch = (data["platform_arch"] as? JsonPrimitive)?.content,
                totalFiles = (data["total_files"] as? JsonPrimitive)?.content?.toIntOrNull(),
                filesChecked = (data["files_checked"] as? JsonPrimitive)?.content?.toIntOrNull(),
                filesPassed = (data["files_passed"] as? JsonPrimitive)?.content?.toIntOrNull(),
                filesFailed = (data["files_failed"] as? JsonPrimitive)?.content?.toIntOrNull(),
                integrityFailureReason = (data["integrity_failure_reason"] as? JsonPrimitive)?.content,
                // Parse checks map (for detailed view)
                checks = parseChecks(data["checks"] as? JsonObject),
                // Keep details as raw JsonElement map for flexibility
                details = (data["details"] as? JsonObject)?.mapValues { it.value },
                // === v0.7.0 Fields - Enhanced verification details ===
                ed25519Fingerprint = (data["ed25519_fingerprint"] as? JsonPrimitive)?.content,
                keyStorageMode = (data["key_storage_mode"] as? JsonPrimitive)?.content,
                hardwareBacked = (data["hardware_backed"] as? JsonPrimitive)?.content?.toBoolean() ?: false,
                targetTriple = (data["target_triple"] as? JsonPrimitive)?.content,
                binarySelfCheck = (data["binary_self_check"] as? JsonPrimitive)?.content,
                binaryHash = (data["binary_hash"] as? JsonPrimitive)?.content,
                expectedBinaryHash = (data["expected_binary_hash"] as? JsonPrimitive)?.content,
                functionSelfCheck = (data["function_self_check"] as? JsonPrimitive)?.content,
                functionsChecked = (data["functions_checked"] as? JsonPrimitive)?.content?.toIntOrNull(),
                functionsPassed = (data["functions_passed"] as? JsonPrimitive)?.content?.toIntOrNull(),
                registryKeyStatus = (data["registry_key_status"] as? JsonPrimitive)?.content,
                // v0.8.1: Python integrity fields
                pythonIntegrityOk = (data["python_integrity_ok"] as? JsonPrimitive)?.content?.toBoolean() ?: false,
                pythonModulesChecked = (data["python_modules_checked"] as? JsonPrimitive)?.content?.toIntOrNull(),
                pythonModulesPassed = (data["python_modules_passed"] as? JsonPrimitive)?.content?.toIntOrNull(),
                pythonTotalHash = (data["python_total_hash"] as? JsonPrimitive)?.content,
                pythonHashValid = (data["python_hash_valid"] as? JsonPrimitive)?.content?.toBoolean() ?: false,
                // v0.8.4: Detail lists for UI
                filesMissingCount = (data["files_missing_count"] as? JsonPrimitive)?.content?.toIntOrNull(),
                filesMissingList = (data["files_missing_list"] as? kotlinx.serialization.json.JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.content },
                filesFailedList = (data["files_failed_list"] as? kotlinx.serialization.json.JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.content },
                filesUnexpectedList = (data["files_unexpected_list"] as? kotlinx.serialization.json.JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.content },
                functionsFailedList = (data["functions_failed_list"] as? kotlinx.serialization.json.JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.content },
                // v0.8.6: Mobile exclusion tracking (discord, reddit, cli, etc.)
                mobileExcludedCount = (data["mobile_excluded_count"] as? JsonPrimitive)?.content?.toIntOrNull(),
                mobileExcludedList = (data["mobile_excluded_list"] as? kotlinx.serialization.json.JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.content },
                // v0.8.6+: Per-file results for deconflicted integrity display
                perFileResults = (data["per_file_results"] as? JsonObject)?.let { obj ->
                    obj.entries.associate { (k, v) -> k to ((v as? JsonPrimitive)?.content ?: "unknown") }
                },
                // v0.8.5: Registry sources agreement
                sourcesAgreeing = (data["sources_agreeing"] as? JsonPrimitive)?.content?.toIntOrNull(),
                // Attestation proof hardware type (nested in attestation_proof object)
                attestationProofHardwareType = (data["attestation_proof"] as? JsonObject)?.let {
                    (it["hardware_type"] as? JsonPrimitive)?.content
                },
                // v0.9.7: Cache timestamp
                cachedAt = (data["cached_at"] as? JsonPrimitive)?.content,
                // v0.9.7: Unified module integrity (cross-validation)
                moduleIntegrityOk = (data["module_integrity_ok"] as? JsonPrimitive)?.content?.toBooleanStrictOrNull() ?: false,
                moduleIntegritySummary = (data["module_integrity_summary"] as? JsonObject)?.let { obj ->
                    obj.entries.associate { (k, v) -> k to ((v as? JsonPrimitive)?.content?.toIntOrNull() ?: 0) }
                },
                crossValidatedFiles = (data["cross_validated_files"] as? kotlinx.serialization.json.JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.content },
                filesystemVerifiedFiles = (data["filesystem_verified_files"] as? kotlinx.serialization.json.JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.content },
                agentVerifiedFiles = (data["agent_verified_files"] as? kotlinx.serialization.json.JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.content },
                diskAgentMismatch = (data["disk_agent_mismatch"] as? JsonObject)?.let { obj ->
                    obj.entries.associate { (k, v) -> k to v }
                },
                registryMismatchFiles = (data["registry_mismatch_files"] as? JsonObject)?.let { obj ->
                    obj.entries.associate { (k, v) -> k to v }
                }
            )

            logDebug(method, "Verify status: loaded=$loaded, keyStatus=${verifyStatus.keyStatus}, maxLevel=${verifyStatus.maxLevel}, levelPending=${verifyStatus.levelPending}, hwType=${verifyStatus.attestationProofHardwareType ?: verifyStatus.hardwareType}, sourcesAgreeing=${verifyStatus.sourcesAgreeing}/3, playOk=${verifyStatus.playIntegrityOk}")

            // DEBUG: Log parsed values (debug level to reduce spam)
            logDebug(method, "=== PARSED VALUES DEBUG ===")
            logDebug(method, "filesChecked=${verifyStatus.filesChecked}, filesPassed=${verifyStatus.filesPassed}")
            logDebug(method, "perFileResults count=${verifyStatus.perFileResults?.size ?: 0}")
            logDebug(method, "pythonModulesChecked=${verifyStatus.pythonModulesChecked}, pythonModulesPassed=${verifyStatus.pythonModulesPassed}")
            logDebug(method, "moduleIntegrityOk=${verifyStatus.moduleIntegrityOk}")
            logDebug(method, "moduleIntegritySummary=${verifyStatus.moduleIntegritySummary}")
            logDebug(method, "crossValidatedFiles count=${verifyStatus.crossValidatedFiles?.size ?: 0}")
            logDebug(method, "filesystemVerifiedFiles count=${verifyStatus.filesystemVerifiedFiles?.size ?: 0}")
            logDebug(method, "agentVerifiedFiles count=${verifyStatus.agentVerifiedFiles?.size ?: 0}")
            logDebug(method, "=== END PARSED VALUES DEBUG ===")

            verifyStatus
        } catch (e: Exception) {
            logException(method, e)
            // Return a default "not loaded" response on error
            VerifyStatusResponse(
                loaded = false,
                error = e.message ?: "Failed to fetch verify status"
            )
        } finally {
            client.close()
        }
    }

    // ========== Connect to Node (Device Auth Flow) ==========
    //
    // The three device-auth endpoints (connect-node, connect-node/status,
    // reset-device-auth) are served natively by the LOCAL NODE substrate
    // (ciris-server, :4243) — same paths, same .device_auth_session.json
    // semantics. Only download-package stays on the brain (:8080).

    /**
     * Initiate device auth with a CIRISNode.
     * Calls POST /v1/setup/connect-node on the local node (:4243).
     */
    suspend fun connectToNode(nodeUrl: String): ConnectNodeResult {
        val method = "connectToNode"
        logInfo(method, "Initiating device auth for node: $nodeUrl")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = 30000
                connectTimeoutMillis = 15000
            }
        }

        return try {
            val response = client.post("$LOCAL_NODE_URL/v1/setup/connect-node") {
                contentType(ContentType.Application.Json)
                setBody(mapOf("node_url" to nodeUrl))
            }

            if (response.status != HttpStatusCode.OK) {
                // Try to extract detail from error response
                val errorDetail = try {
                    val errBody = response.body<JsonObject>()
                    (errBody["detail"] as? JsonPrimitive)?.content
                } catch (_: Exception) { null }
                throw Exception(errorDetail ?: "Connect-node failed: HTTP ${response.status}")
            }

            val body = response.body<JsonObject>()
            val data = body["data"] as? JsonObject
                ?: throw Exception("Invalid response format")

            // Portal URL: prefer from response (normalized by backend), fall back to input
            val responsePortalUrl = (data["portal_url"] as? JsonPrimitive)?.content
            val normalizedPortalUrl = responsePortalUrl
                ?: if (nodeUrl.startsWith("http://") || nodeUrl.startsWith("https://"))
                    nodeUrl.trimEnd('/') else "https://${nodeUrl.trimEnd('/')}"

            ConnectNodeResult(
                verificationUriComplete = (data["verification_uri_complete"] as? JsonPrimitive)?.content ?: "",
                deviceCode = (data["device_code"] as? JsonPrimitive)?.content ?: "",
                userCode = (data["user_code"] as? JsonPrimitive)?.content ?: "",
                portalUrl = normalizedPortalUrl,
                expiresIn = (data["expires_in"] as? JsonPrimitive)?.content?.toIntOrNull() ?: 900,
                interval = (data["interval"] as? JsonPrimitive)?.content?.toIntOrNull() ?: 5
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Poll device auth status.
     * Calls GET /v1/setup/connect-node/status on the local node (:4243).
     */
    suspend fun pollNodeAuthStatus(deviceCode: String, portalUrl: String): NodeAuthPollResult {
        val method = "pollNodeAuthStatus"
        logInfo(method, "========== POLL START ==========")
        logInfo(method, "deviceCode: ${deviceCode.take(16)}...")
        logInfo(method, "portalUrl: $portalUrl")
        val fullUrl = "$LOCAL_NODE_URL/v1/setup/connect-node/status"
        logInfo(method, "Full URL: $fullUrl")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = 15000
                connectTimeoutMillis = 10000
            }
        }

        return try {
            logInfo(method, "Making HTTP GET request...")
            val response = client.get(fullUrl) {
                parameter("device_code", deviceCode)
                parameter("portal_url", portalUrl)
            }
            logInfo(method, "HTTP response received: status=${response.status}")

            if (response.status != HttpStatusCode.OK) {
                logException(method, Exception("Poll failed: HTTP ${response.status}"))
                throw Exception("Poll failed: HTTP ${response.status}")
            }

            val bodyText = response.bodyAsText()
            logInfo(method, "Response body (first 500 chars): ${bodyText.take(500)}")

            val body = Json.parseToJsonElement(bodyText).jsonObject
            val data = body["data"] as? JsonObject
                ?: throw Exception("Invalid response format - no 'data' field")

            val status = (data["status"] as? JsonPrimitive)?.content ?: "error"
            val keyId = (data["key_id"] as? JsonPrimitive)?.content
            val error = (data["error"] as? JsonPrimitive)?.content
            logInfo(method, "Parsed response: status=$status, keyId=$keyId, error=$error")

            val result = NodeAuthPollResult(
                status = status,
                template = (data["template"] as? JsonPrimitive)?.content,
                adapters = null, // TODO: Parse adapters list from JSON array. MVP: null.
                orgId = (data["org_id"] as? JsonPrimitive)?.content,
                signingKeyB64 = (data["signing_key_b64"] as? JsonPrimitive)?.content,
                keyId = keyId,
                stewardshipTier = (data["stewardship_tier"] as? JsonPrimitive)?.content?.toIntOrNull(),
                error = error
            )
            logInfo(method, "========== POLL END (returning result) ==========")
            result
        } catch (e: Exception) {
            logException(method, e)
            logInfo(method, "========== POLL END (exception: ${e.message}) ==========")
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Reset device auth session on server.
     * Calls POST /v1/setup/reset-device-auth on the local node (:4243).
     * Used when user backs out of NODE_AUTH flow to clear stale node state.
     */
    suspend fun resetDeviceAuthOnServer(): Boolean {
        val method = "resetDeviceAuthOnServer"
        logDebug(method, "Resetting device auth session on server")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = 5000
                connectTimeoutMillis = 3000
            }
        }

        return try {
            val response = client.post("$LOCAL_NODE_URL/v1/setup/reset-device-auth") {
                contentType(ContentType.Application.Json)
                setBody("{}")
            }

            val success = response.status == HttpStatusCode.OK
            if (success) {
                logInfo(method, "Device auth session reset successfully")
            } else {
                logWarn(method, "Device auth reset returned HTTP ${response.status}")
            }
            success
        } catch (e: Exception) {
            // Non-fatal - log but don't throw since this is cleanup
            logWarn(method, "Failed to reset device auth on server: ${e.message}")
            false
        } finally {
            client.close()
        }
    }

    override suspend fun completeSetup(request: CompleteSetupRequest): SetupCompletionResult {
        val method = "completeSetup"
        logInfo(method, "Completing setup: provider=${request.llm_provider}, template=${request.template_id}, username=${request.admin_username}")

        return try {
            val sdkRequest = SdkSetupCompleteRequest(
                llmProvider = request.llm_provider,
                llmApiKey = request.llm_api_key,
                llmBaseUrl = request.llm_base_url,
                llmModel = request.llm_model,
                backupLlmApiKey = request.backup_llm_api_key,
                backupLlmBaseUrl = request.backup_llm_base_url,
                backupLlmModel = request.backup_llm_model,
                templateId = request.template_id,
                enabledAdapters = request.enabled_adapters,
                adapterConfig = request.adapter_config.mapValues { JsonPrimitive(it.value) },
                agentPort = request.agent_port,
                systemAdminPassword = request.system_admin_password,
                adminUsername = request.admin_username,
                adminPassword = request.admin_password,
                oauthProvider = request.oauth_provider,
                oauthExternalId = request.oauth_external_id,
                oauthEmail = request.oauth_email,
                nodeUrl = request.node_url,
                signingKeyId = request.signing_key_id,
                signingKeyProvisioned = request.signing_key_provisioned,
                provisionedSigningKeyB64 = request.provisioned_signing_key_b64
            )
            logDebug(method, "Created SdkSetupCompleteRequest with signingKeyId=${request.signing_key_id}")

            // Use manual HTTP request to handle error responses properly
            // The generated SDK tries to parse error responses as success, which fails
            val httpClient = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                        // DEFAULT-COLLISION FIX: the generated SdkSetupCompleteRequest
                        // declares adminUsername default "admin". With kotlinx's
                        // default encodeDefaults=false, a user who picks EXACTLY
                        // "admin" serializes as an ABSENT field → the server's
                        // pydantic default ("owner") wins → the account is created
                        // as "owner" and the user's admin/password login bounces
                        // forever. Encode set values always; keep omitting nulls so
                        // server-side defaults still apply to genuinely-unset fields.
                        encodeDefaults = true
                        explicitNulls = false
                    })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = 60000  // 60s for setup completion
                    connectTimeoutMillis = 10000
                    socketTimeoutMillis = 60000
                }
                // Don't throw on non-2xx responses - we handle them manually
                expectSuccess = false
            }

            try {
                val httpResponse = httpClient.post("$baseUrl/v1/setup/complete") {
                    contentType(io.ktor.http.ContentType.Application.Json)
                    setBody(sdkRequest)
                }

                val statusCode = httpResponse.status.value
                val responseBody = httpResponse.bodyAsText()
                logDebug(method, "Response: status=$statusCode, body=${responseBody.take(500)}")

                when {
                    statusCode == 422 -> {
                        // FastAPI validation error
                        logError(method, "FastAPI validation failure (422): $responseBody")
                        val detail = try {
                            val detailMatch = Regex(""""detail"\s*:\s*"([^"]+)"""").find(responseBody)
                            detailMatch?.groupValues?.get(1) ?: responseBody
                        } catch (_: Exception) {
                            responseBody
                        }
                        SetupCompletionResult(
                            success = false,
                            message = "Setup failed",
                            error = "Validation error: $detail"
                        )
                    }
                    statusCode in 400..499 -> {
                        logError(method, "Client error (HTTP $statusCode): $responseBody")
                        SetupCompletionResult(
                            success = false,
                            message = "Setup failed",
                            error = "HTTP $statusCode: $responseBody"
                        )
                    }
                    statusCode in 500..599 -> {
                        logError(method, "Server error (HTTP $statusCode): $responseBody")
                        // Try to extract detailed error from response body
                        val errorDetail = try {
                            val errorJson = Json.decodeFromString<Map<String, kotlinx.serialization.json.JsonElement>>(responseBody)
                            val detail = errorJson["detail"]
                            when {
                                detail is kotlinx.serialization.json.JsonObject -> {
                                    val code = detail["code"]?.toString()?.trim('"') ?: ""
                                    val message = detail["message"]?.toString()?.trim('"') ?: ""
                                    if (code.isNotEmpty()) "[$code] $message" else message.ifEmpty { responseBody }
                                }
                                detail != null -> detail.toString().trim('"')
                                else -> responseBody
                            }
                        } catch (_: Exception) {
                            responseBody.ifEmpty { "Server error ($statusCode)" }
                        }
                        SetupCompletionResult(
                            success = false,
                            message = "Setup failed",
                            error = errorDetail
                        )
                    }
                    statusCode in 200..299 -> {
                        // Success - parse the response
                        val successResponse = Json.decodeFromString<SuccessResponseDictStrStr>(responseBody)
                        val data = successResponse.`data`
                        val success = data["status"] == "completed"
                        val message = data["message"] ?: "Setup completed"
                        logInfo(method, "Setup complete: success=$success, message=$message")
                        SetupCompletionResult(
                            success = success,
                            message = message,
                            agentId = null,
                            adminUserId = data["username"],
                            error = null
                        )
                    }
                    else -> {
                        logError(method, "Unexpected status code $statusCode: $responseBody")
                        SetupCompletionResult(
                            success = false,
                            message = "Setup failed",
                            error = "Unexpected response: HTTP $statusCode"
                        )
                    }
                }
            } finally {
                httpClient.close()
            }
        } catch (e: Exception) {
            logException(method, e, "provider=${request.llm_provider}, template=${request.template_id}")
            SetupCompletionResult(
                success = false,
                message = "Setup failed",
                error = e.message ?: "Unknown error"
            )
        }
    }

    /**
     * Get current LLM configuration from the backend.
     * Used by Settings screen to show actual configuration.
     */
    override suspend fun getLlmConfig(): LlmConfigData {
        val method = "getLlmConfig"
        // AGENT-only: LLM config is 404 on a bare node (no brain to configure).
        if (nodeSkip(method)) return LlmConfigData(
            provider = "",
            baseUrl = null,
            model = "",
            apiKeySet = false,
            isCirisProxy = false,
            backupBaseUrl = null,
            backupModel = null,
            backupApiKeySet = false,
        )
        logDebug(method, "Fetching current LLM configuration")
        logDebug(method, "Auth header: ${authHeader()}")

        return try {
            // Use manual HTTP request since generated SDK doesn't include auth for this endpoint
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
            }

            val response = client.get("$baseUrl/v1/setup/config") {
                authHeader()?.let { header("Authorization", it) }
            }

            logDebug(method, "Response: status=${response.status}")

            if (response.status.value !in 200..299) {
                logError(method, "API returned error status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status.value}")
            }

            val body = response.body<SetupConfigApiResponse>()
            val data = body.data ?: throw RuntimeException("API returned null data")

            // Check if CIRIS services are disabled (BYOK mode)
            val cirisServicesEnabled = try {
                getCirisServicesStatus()
            } catch (e: Exception) {
                logWarn(method, "Failed to get CIRIS services status: ${e.message}, assuming enabled")
                true
            }

            // Detect if using CIRIS proxy - BOTH conditions must be true:
            // 1. CIRIS services must be enabled (not disabled)
            // 2. URL must be a CIRIS proxy URL
            val llmBaseUrl = data.llmBaseUrl ?: ""
            val urlIsCirisProxy = data.llmProvider == "ciris_proxy" ||
                    llmBaseUrl.contains("ciris", ignoreCase = true) ||
                    llmBaseUrl.contains("llm.ciris", ignoreCase = true) ||
                    llmBaseUrl.contains("proxy", ignoreCase = true)
            val isCirisProxy = cirisServicesEnabled && urlIsCirisProxy

            logDebug(method, "LLM Config: provider=${data.llmProvider}, model=${data.llmModel}, " +
                    "baseUrl=$llmBaseUrl, isCirisProxy=$isCirisProxy, cirisServicesEnabled=$cirisServicesEnabled, " +
                    "apiKeySet=${data.llmApiKeySet}")

            client.close()

            LlmConfigData(
                provider = data.llmProvider ?: "unknown",
                baseUrl = data.llmBaseUrl,
                model = data.llmModel ?: "default",
                apiKeySet = data.llmApiKeySet ?: false,
                isCirisProxy = isCirisProxy,
                backupBaseUrl = data.backupLlmBaseUrl,
                backupModel = data.backupLlmModel,
                backupApiKeySet = data.backupLlmApiKeySet ?: false
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * Response wrapper for /v1/setup/config endpoint
     */
    @Serializable
    private data class SetupConfigApiResponse(
        val status: String? = null,
        val data: SetupConfigData? = null
    )

    @Serializable
    private data class SetupConfigData(
        @SerialName("llm_provider") val llmProvider: String? = null,
        @SerialName("llm_base_url") val llmBaseUrl: String? = null,
        @SerialName("llm_model") val llmModel: String? = null,
        @SerialName("llm_api_key_set") val llmApiKeySet: Boolean? = null,
        @SerialName("backup_llm_base_url") val backupLlmBaseUrl: String? = null,
        @SerialName("backup_llm_model") val backupLlmModel: String? = null,
        @SerialName("backup_llm_api_key_set") val backupLlmApiKeySet: Boolean? = null
    )

    /**
     * Update LLM configuration in .env file.
     * This persists the LLM settings so they survive app restarts.
     *
     * @param provider LLM provider ID (openai, openrouter, anthropic, etc.)
     * @param apiKey API key (null to keep existing)
     * @param baseUrl Custom base URL (null for provider default)
     * @param model Model name (null to keep existing)
     * @return Result with success status and message
     */
    suspend fun updateLlmConfig(
        provider: String,
        apiKey: String?,
        baseUrl: String?,
        model: String?
    ): Result<String> {
        val method = "updateLlmConfig"
        logInfo(method, "Updating LLM config: provider=$provider, baseUrl=${baseUrl ?: "default"}, model=${model ?: "unchanged"}")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
            }

            @Serializable
            data class UpdateLlmRequest(
                @SerialName("llm_provider") val llmProvider: String,
                @SerialName("llm_api_key") val llmApiKey: String? = null,
                @SerialName("llm_base_url") val llmBaseUrl: String? = null,
                @SerialName("llm_model") val llmModel: String? = null
            )

            val request = UpdateLlmRequest(
                llmProvider = provider,
                llmApiKey = apiKey,
                llmBaseUrl = baseUrl,
                llmModel = model
            )

            val response = client.put("${this.baseUrl}/v1/setup/llm") {
                authHeader()?.let { header("Authorization", it) }
                contentType(ContentType.Application.Json)
                setBody(request)
            }

            client.close()

            logDebug(method, "Response: status=${response.status}")

            if (response.status.value !in 200..299) {
                logError(method, "API returned error status: ${response.status}")
                return Result.failure(RuntimeException("API error: HTTP ${response.status.value}"))
            }

            logInfo(method, "LLM config updated successfully")
            Result.success("LLM configuration updated successfully")
        } catch (e: Exception) {
            logException(method, e)
            Result.failure(e)
        }
    }

    // ===== Billing API =====

    override suspend fun getCredits(): CreditStatusData {
        val method = "getCredits"
        // AGENT-only: billing/credits is 404 on a bare node. Report "free / no
        // billing" so the node UI shows no purchase prompts.
        if (nodeSkip(method)) return CreditStatusData(
            hasCredit = true,
            creditsRemaining = 0,
            freeUsesRemaining = 0,
            dailyFreeUsesRemaining = null,
            totalUses = 0,
            planName = null,
            purchaseRequired = false,
        )
        logDebug(method, "Fetching credit status")

        return try {
            val response = billingApi.getCreditsV1ApiBillingCreditsGet(authHeader())
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            logDebug(method, "Credits: hasCredit=${body.hasCredit}, remaining=${body.creditsRemaining}, " +
                    "freeUses=${body.freeUsesRemaining}, plan=${body.planName}")

            CreditStatusData(
                hasCredit = body.hasCredit,
                creditsRemaining = body.creditsRemaining,
                freeUsesRemaining = body.freeUsesRemaining,
                dailyFreeUsesRemaining = body.dailyFreeUsesRemaining,
                totalUses = body.totalUses,
                planName = body.planName,
                purchaseRequired = body.purchaseRequired
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * Verify a Google Play purchase and add credits.
     */
    suspend fun verifyGooglePlayPurchase(
        purchaseToken: String,
        productId: String,
        packageName: String
    ): GooglePlayVerifyData {
        val method = "verifyGooglePlayPurchase"
        logInfo(method, "Verifying Google Play purchase: productId=$productId")

        return try {
            val request = ai.ciris.api.models.GooglePlayVerifyRequest(
                purchaseToken = purchaseToken,
                productId = productId,
                packageName = packageName
            )
            val response = billingApi.verifyGooglePlayPurchaseV1ApiBillingGooglePlayVerifyPost(
                googlePlayVerifyRequest = request,
                authorization = authHeader()
            )
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            logInfo(method, "Purchase verified: success=${body.success}, creditsAdded=${body.creditsAdded}, newBalance=${body.newBalance}")

            GooglePlayVerifyData(
                success = body.success,
                creditsAdded = body.creditsAdded ?: 0,
                newBalance = body.newBalance ?: 0,
                alreadyProcessed = body.alreadyProcessed ?: false,
                error = body.error
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    // ===== Adapters API =====

    override suspend fun listAdapters(): AdaptersListData {
        val method = "listAdapters"
        // AGENT-only: GET /v1/system/adapters is 404 on a bare node.
        if (nodeSkip(method)) return AdaptersListData(
            adapters = emptyList(),
            totalCount = 0,
            runningCount = 0,
        )
        logInfo(method, "Listing adapters")

        return try {
            val response = systemApi.listAdaptersV1SystemAdaptersGet(authHeader())
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")
            logInfo(method, "API response: total=${data.totalCount}, running=${data.runningCount}, adapters.size=${data.adapters.size}")
            data.adapters.forEachIndexed { index, adapter ->
                logInfo(method, "  API adapter[$index]: id=${adapter.adapterId}, type=${adapter.adapterType}, running=${adapter.isRunning}, needsReauth=${adapter.needsReauth}, hasAuthStep=${adapter.hasAuthStep}")
            }

            AdaptersListData(
                adapters = data.adapters.map { adapter ->
                    AdapterStatusData(
                        adapterId = adapter.adapterId,
                        adapterType = adapter.adapterType,
                        isRunning = adapter.isRunning,
                        needsReauth = adapter.needsReauth,
                        reauthReason = adapter.reauthReason,
                        hasAuthStep = adapter.hasAuthStep,
                        authStepId = adapter.authStepId
                    )
                },
                totalCount = data.totalCount,
                runningCount = data.runningCount
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    override suspend fun reloadAdapter(adapterId: String): AdapterActionData {
        val method = "reloadAdapter"
        logInfo(method, "Reloading adapter: $adapterId")

        return try {
            val request = ai.ciris.api.models.AdapterActionRequest(
                config = null,
                force = false,
                persist = false
            )
            val response = systemApi.reloadAdapterV1SystemAdaptersAdapterIdReloadPut(
                adapterId = adapterId,
                adapterActionRequest = request,
                authorization = authHeader()
            )
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")
            logInfo(method, "Adapter reloaded: adapterId=${data.adapterId}, success=${data.success}")

            AdapterActionData(
                adapterId = data.adapterId,
                success = data.success,
                message = data.message
            )
        } catch (e: Exception) {
            logException(method, e, "adapterId=$adapterId")
            throw e
        }
    }

    override suspend fun removeAdapter(adapterId: String): AdapterActionData {
        val method = "removeAdapter"
        logInfo(method, "Removing adapter: $adapterId")

        return try {
            val response = systemApi.unloadAdapterV1SystemAdaptersAdapterIdDelete(
                adapterId = adapterId,
                authorization = authHeader()
            )
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")
            logInfo(method, "Adapter removed: adapterId=${data.adapterId}, success=${data.success}")

            AdapterActionData(
                adapterId = data.adapterId,
                success = data.success,
                message = data.message
            )
        } catch (e: Exception) {
            logException(method, e, "adapterId=$adapterId")
            throw e
        }
    }

    /**
     * Get detailed status of a specific adapter including config, services, tools, and metrics.
     */
    suspend fun getAdapterDetails(adapterId: String): ai.ciris.mobile.shared.models.AdapterDetailsData {
        val method = "getAdapterDetails"
        logInfo(method, "Fetching adapter details: $adapterId")

        return try {
            val response = systemApi.getAdapterStatusV1SystemAdaptersAdapterIdGet(
                adapterId = adapterId,
                authorization = authHeader()
            )
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")
            logInfo(method, "Adapter details received: adapterId=${data.adapterId}, services=${data.servicesRegistered?.size ?: 0}, tools=${data.tools?.size ?: 0}")

            // Convert API model to our internal model
            ai.ciris.mobile.shared.models.AdapterDetailsData(
                adapterId = data.adapterId,
                adapterType = data.adapterType,
                isRunning = data.isRunning,
                loadedAt = data.loadedAt?.toString(),
                servicesRegistered = data.servicesRegistered ?: emptyList(),
                configParams = data.configParams?.let { config ->
                    ai.ciris.mobile.shared.models.AdapterConfigData(
                        adapterType = config.adapterType,
                        enabled = config.enabled ?: true,
                        persist = config.persist ?: false,
                        settings = config.settings?.mapValues { it.value?.toString() ?: "" } ?: emptyMap()
                    )
                },
                tools = data.tools?.map { tool ->
                    ai.ciris.mobile.shared.models.ToolInfoData(
                        name = tool.name,
                        description = tool.description,
                        category = tool.category ?: "general",
                        cost = tool.cost?.toFloat() ?: 0f,
                        whenToUse = tool.whenToUse
                    )
                },
                metrics = data.metrics?.let { m ->
                    ai.ciris.mobile.shared.models.AdapterMetricsData(
                        messagesProcessed = m.messagesProcessed ?: 0,
                        errorsCount = m.errorsCount ?: 0,
                        uptimeSeconds = (m.uptimeSeconds ?: 0.0).toFloat(),
                        lastError = m.lastError,
                        lastErrorTime = m.lastErrorTime?.toString()
                    )
                },
                lastActivity = data.lastActivity?.toString()
            )
        } catch (e: Exception) {
            logException(method, e, "adapterId=$adapterId")
            throw e
        }
    }

    /**
     * Get available module/adapter types for adding new adapters.
     */
    suspend fun getModuleTypes(): ModuleTypesData {
        val method = "getModuleTypes"
        logInfo(method, "Fetching available module types")

        return try {
            val response = systemApi.listModuleTypesV1SystemAdaptersTypesGet(authHeader())
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")
            logInfo(method, "Module types: ${data.totalCore} core, ${data.totalAdapters} adapters")

            ModuleTypesData(
                coreModules = data.coreModules.map { module ->
                    ModuleTypeData(
                        moduleId = module.moduleId,
                        name = module.name,
                        version = module.version,
                        description = module.description,
                        moduleSource = module.moduleSource,
                        serviceTypes = (module.serviceTypes ?: emptyList()).filter { it.isNotBlank() },
                        capabilities = (module.capabilities ?: emptyList()).filter { it.isNotBlank() },
                        platformAvailable = module.platformAvailable ?: true
                    )
                },
                adapters = data.adapters.map { module ->
                    ModuleTypeData(
                        moduleId = module.moduleId,
                        name = module.name,
                        version = module.version,
                        description = module.description,
                        moduleSource = module.moduleSource,
                        serviceTypes = (module.serviceTypes ?: emptyList()).filter { it.isNotBlank() },
                        capabilities = (module.capabilities ?: emptyList()).filter { it.isNotBlank() },
                        platformAvailable = module.platformAvailable ?: true
                    )
                },
                totalCore = data.totalCore,
                totalAdapters = data.totalAdapters
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * Get adapters that support interactive configuration (have wizard workflows).
     * Only returns adapters that are available on the current platform.
     */
    suspend fun getConfigurableAdapters(): ConfigurableAdaptersData {
        val method = "getConfigurableAdapters"
        logInfo(method, "Fetching configurable adapters")

        return try {
            val response = systemApi.listConfigurableAdaptersV1SystemAdaptersConfigurableGet(authHeader())
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")
            logInfo(method, "Configurable adapters: ${data.totalCount} found")

            ConfigurableAdaptersData(
                adapters = data.adapters.map { adapter ->
                    ConfigurableAdapterData(
                        adapterType = adapter.adapterType,
                        name = adapter.name,
                        description = adapter.description,
                        workflowType = adapter.workflowType,
                        stepCount = adapter.stepCount,
                        requiresOauth = adapter.requiresOauth ?: false
                    )
                },
                totalCount = data.totalCount
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * Get all loadable adapters (both configurable and direct-load).
     * Returns adapters that can be loaded via wizard OR directly without configuration.
     */
    suspend fun getLoadableAdapters(): LoadableAdaptersData {
        val method = "getLoadableAdapters"
        val url = "$baseUrl/v1/system/adapters/loadable"
        val auth = authHeader()
        logInfo(method, "GET $url | auth=${auth != null} token=${maskToken(accessToken)}")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
                install(Logging) {
                    level = LogLevel.INFO
                }
            }

            val response: HttpResponse = client.get(url) {
                auth?.let { headers { append("Authorization", it) } }
            }

            logInfo(method, "Response: ${response.status.value} ${response.status.description}")

            if (response.status.value !in 200..299) {
                val errorBody = response.body<String>()
                logError(method, "FAILED ${response.status} | url=$url | auth=${auth != null} | body=$errorBody")
                client.close()
                throw Exception("Failed to fetch loadable adapters: ${response.status}")
            }

            // Parse the response
            val responseText = response.body<String>()
            logDebug(method, "Response body: $responseText")
            client.close()

            val json = Json { ignoreUnknownKeys = true }
            val parsed = json.parseToJsonElement(responseText).jsonObject
            val dataObj = parsed["data"]?.jsonObject ?: throw RuntimeException("No data in response")

            val adapters = dataObj["adapters"]?.jsonArray?.map { adapterJson ->
                val obj = adapterJson.jsonObject
                LoadableAdapterData(
                    adapterType = obj["adapter_type"]?.jsonPrimitive?.content ?: "",
                    name = obj["name"]?.jsonPrimitive?.content ?: "",
                    description = obj["description"]?.jsonPrimitive?.content ?: "",
                    requiresConfiguration = obj["requires_configuration"]?.jsonPrimitive?.boolean ?: false,
                    workflowType = obj["workflow_type"]?.jsonPrimitive?.contentOrNull,
                    stepCount = obj["step_count"]?.jsonPrimitive?.int ?: 0,
                    requiresOauth = obj["requires_oauth"]?.jsonPrimitive?.boolean ?: false,
                    serviceTypes = obj["service_types"]?.jsonArray?.map { it.jsonPrimitive.content } ?: emptyList(),
                    platformAvailable = obj["platform_available"]?.jsonPrimitive?.boolean ?: true,
                    externalDependencies = obj["external_dependencies"]?.jsonArray?.map { it.jsonPrimitive.content } ?: emptyList(),
                    dependenciesAvailable = obj["dependencies_available"]?.jsonPrimitive?.boolean ?: true,
                    missingDependencies = obj["missing_dependencies"]?.jsonArray?.map { it.jsonPrimitive.content } ?: emptyList(),
                    loadedInstances = obj["loaded_instances"]?.jsonPrimitive?.int ?: 0
                )
            } ?: emptyList()

            val result = LoadableAdaptersData(
                adapters = adapters,
                totalCount = dataObj["total_count"]?.jsonPrimitive?.int ?: adapters.size,
                configurableCount = dataObj["configurable_count"]?.jsonPrimitive?.int ?: 0,
                directLoadCount = dataObj["direct_load_count"]?.jsonPrimitive?.int ?: 0
            )

            logInfo(method, "Loadable adapters: ${result.totalCount} total (${result.configurableCount} configurable, ${result.directLoadCount} direct)")
            result
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * Load an adapter directly (for adapters that don't require configuration).
     */
    suspend fun loadAdapter(adapterType: String): AdapterLoadResult {
        return loadAdapterWithConfig(adapterType, config = null, persist = false)
    }

    /**
     * Load an adapter with configuration options.
     *
     * @param adapterType The adapter type to load (e.g., "ciris_accord_metrics")
     * @param config Optional configuration map for the adapter (will be serialized to JSON)
     * @param persist Whether to save config to graph for auto-restore on restart
     */
    suspend fun loadAdapterWithConfig(
        adapterType: String,
        config: Map<String, Any>? = null,
        persist: Boolean = true
    ): AdapterLoadResult {
        val method = "loadAdapterWithConfig"
        logInfo(method, "Loading adapter: $adapterType with config=$config, persist=$persist")

        return try {
            // Serialize config map to JSON string (SDK expects String, not Map)
            val configJson = config?.let { map ->
                buildString {
                    append("{")
                    map.entries.forEachIndexed { index, (key, value) ->
                        if (index > 0) append(",")
                        append("\"$key\":")
                        when (value) {
                            is String -> append("\"$value\"")
                            is Boolean -> append(value)
                            is Number -> append(value)
                            else -> append("\"$value\"")
                        }
                    }
                    append("}")
                }
            }

            val request = AdapterActionRequest(
                config = configJson,
                force = false,
                persist = persist
            )
            val response = systemApi.loadAdapterV1SystemAdaptersAdapterTypePost(
                adapterType = adapterType,
                adapterActionRequest = request,
                authorization = authHeader()
            )
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                return AdapterLoadResult(
                    success = false,
                    adapterId = null,
                    message = "API error: HTTP ${response.status}"
                )
            }

            val body = response.body()
            val data = body.`data` ?: return AdapterLoadResult(
                success = false,
                adapterId = null,
                message = "API returned null data"
            )

            logInfo(method, "Adapter load result: success=${data.success}, adapterId=${data.adapterId}")

            AdapterLoadResult(
                success = data.success ?: false,
                adapterId = data.adapterId,
                message = data.message
            )
        } catch (e: Exception) {
            logException(method, e)
            AdapterLoadResult(
                success = false,
                adapterId = null,
                message = "Error: ${e.message}"
            )
        }
    }

    /**
     * Start an adapter configuration wizard session.
     *
     * @param adapterType Type of adapter to configure
     * @param startStepId Optional step ID to start at (useful for re-auth flows)
     */
    suspend fun startAdapterConfiguration(adapterType: String, startStepId: String? = null): ConfigSessionData {
        val method = "startAdapterConfiguration"
        logInfo(method, "Starting configuration for adapter type: $adapterType, startStepId: $startStepId")

        return try {
            val response = systemApi.startAdapterConfigurationV1SystemAdaptersAdapterTypeConfigureStartPost(
                adapterType = adapterType,
                authorization = authHeader(),
                startStepId = startStepId
            )
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")
            logInfo(method, "Config session started: sessionId=${data.sessionId}, " +
                    "step=${data.currentStepIndex}/${data.totalSteps}")

            ConfigSessionData(
                sessionId = data.sessionId ?: "",
                adapterType = data.adapterType ?: "",
                status = data.status ?: "",
                currentStepIndex = data.currentStepIndex ?: 0,
                totalSteps = data.totalSteps ?: 0,
                currentStep = data.currentStep?.let { step ->
                    mapConfigStep(step)
                }
            )
        } catch (e: Exception) {
            logException(method, e, "adapterType=$adapterType")
            throw e
        }
    }

    /**
     * Map SDK ConfigurationStep to mobile ConfigStepData.
     */
    private fun mapConfigStep(step: ai.ciris.api.models.ConfigurationStep): ConfigStepData {
        return ConfigStepData(
            stepId = step.stepId ?: "",
            stepType = step.stepType ?: "",
            title = step.title ?: "",
            description = step.description,
            required = step.required ?: false,
            fields = step.fields?.map { field ->
                ConfigFieldData(
                    name = field.name ?: "",
                    label = field.label ?: "",
                    // Backend uses "type", SDK may have "field_type" as fallback
                    fieldType = field.type ?: field.fieldType ?: "",
                    required = field.required ?: false,
                    defaultValue = field.default ?: field.defaultValue,
                    helpText = field.description ?: field.helpText,
                    // Map options for select-type fields
                    options = field.options?.map { option ->
                        ConfigFieldOption(
                            value = option.value ?: "",
                            label = option.label ?: option.value ?: "",
                            description = option.description
                        )
                    } ?: emptyList()
                )
            } ?: emptyList()
        )
    }

    /**
     * Execute a step in the adapter configuration wizard.
     */
    suspend fun executeConfigurationStep(
        sessionId: String,
        stepData: Map<String, String>
    ): ConfigStepResultData {
        val method = "executeConfigurationStep"
        logInfo(method, "=== EXECUTE CONFIG STEP ===")
        logInfo(method, "Session: $sessionId")
        logInfo(method, "Step data keys: ${stepData.keys}")
        logInfo(method, "Step data values: $stepData")

        return try {
            val request = ai.ciris.api.models.StepExecutionRequest(
                stepData = stepData.mapValues { (_, v) ->
                    kotlinx.serialization.json.JsonPrimitive(v)
                }
            )
            val response = systemApi.executeConfigurationStepV1SystemAdaptersConfigureSessionIdStepPost(
                sessionId = sessionId,
                stepExecutionRequest = request,
                authorization = authHeader()
            )
            logInfo(method, "Response HTTP status: ${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")
            logInfo(method, "Response data: success=${data.success}, error=${data.error}, nextStepIndex=${data.nextStepIndex}")
            logInfo(method, "Response data keys: ${data.`data`?.keys}")
            logInfo(method, "Response data.data: ${data.`data`?.entries?.joinToString { "${it.key}=${it.value.toString().take(100)}" }}")

            // Check if this is a discovery step (has discovered_items in data, even if empty)
            val isDiscoveryStep = data.`data`?.containsKey("discovered_items") == true

            // Determine if workflow is complete:
            // - We cannot determine completion here as we don't know totalSteps
            // - The ViewModel must check if nextStepIndex >= totalSteps after fetching session status
            // - Set isComplete=false here; ViewModel will determine actual completion
            val isComplete = false
            logInfo(method, "Step result: success=${data.success}, nextStep=${data.nextStepIndex}, isDiscovery=$isDiscoveryStep, isComplete=$isComplete")

            // Parse discovered_items from data field if present (for discovery steps)
            val discoveredItems = data.`data`?.get("discovered_items")?.let { itemsJson ->
                try {
                    val itemsList = mutableListOf<DiscoveredItemData>()
                    if (itemsJson is kotlinx.serialization.json.JsonArray) {
                        for (item in itemsJson) {
                            if (item is kotlinx.serialization.json.JsonObject) {
                                val id = item["id"]?.let { (it as? kotlinx.serialization.json.JsonPrimitive)?.content } ?: ""
                                val label = item["label"]?.let { (it as? kotlinx.serialization.json.JsonPrimitive)?.content } ?: ""
                                val metadataObj = item["metadata"] as? kotlinx.serialization.json.JsonObject
                                val metadata = metadataObj?.entries?.associate { (k, v) ->
                                    k to ((v as? kotlinx.serialization.json.JsonPrimitive)?.content ?: "")
                                } ?: emptyMap()
                                // Get value from item["value"], or fall back to metadata URL keys
                                val value = item["value"]?.let { (it as? kotlinx.serialization.json.JsonPrimitive)?.content }
                                    ?.takeIf { it.isNotEmpty() }
                                    ?: metadata["url"]  // Home Assistant uses metadata.url
                                    ?: metadata["portal_url"]  // CIRISNode uses metadata.portal_url
                                    ?: metadata["base_url"]  // Generic fallback
                                    ?: ""
                                itemsList.add(DiscoveredItemData(id, label, value, metadata))
                            }
                        }
                    }
                    logInfo(method, "Parsed ${itemsList.size} discovered items")
                    itemsList
                } catch (e: Exception) {
                    logError(method, "Failed to parse discovered_items: ${e.message}")
                    emptyList()
                }
            } ?: emptyList()

            // Extract OAuth URL from data field if present (for OAuth steps)
            val oauthUrl = data.`data`?.get("oauth_url")?.let {
                (it as? kotlinx.serialization.json.JsonPrimitive)?.content
            }
            val awaitingCallback = data.`data`?.get("awaiting_callback")?.let {
                (it as? kotlinx.serialization.json.JsonPrimitive)?.content?.toBooleanStrictOrNull()
            } ?: false

            logInfo(method, "=== OAUTH URL EXTRACTION ===")
            logInfo(method, "oauth_url present in data: ${data.`data`?.containsKey("oauth_url")}")
            logInfo(method, "awaiting_callback present in data: ${data.`data`?.containsKey("awaiting_callback")}")
            if (oauthUrl != null) {
                logInfo(method, "Extracted OAuth URL (full): $oauthUrl")
            } else {
                logInfo(method, "No oauth_url extracted from response")
            }
            logInfo(method, "awaitingCallback: $awaitingCallback")

            // Parse select options from data field if present (for select steps)
            val selectOptions = data.`data`?.get("options")?.let { optionsJson ->
                try {
                    val optionsList = mutableListOf<SelectOptionData>()
                    if (optionsJson is kotlinx.serialization.json.JsonArray) {
                        for (opt in optionsJson) {
                            if (opt is kotlinx.serialization.json.JsonObject) {
                                val id = opt["id"]?.let { (it as? kotlinx.serialization.json.JsonPrimitive)?.content } ?: ""
                                val label = opt["label"]?.let { (it as? kotlinx.serialization.json.JsonPrimitive)?.content } ?: id
                                val description = opt["description"]?.let { (it as? kotlinx.serialization.json.JsonPrimitive)?.content }
                                val metadataObj = opt["metadata"] as? kotlinx.serialization.json.JsonObject
                                val defaultEnabled = metadataObj?.get("default")?.let {
                                    (it as? kotlinx.serialization.json.JsonPrimitive)?.content?.toBooleanStrictOrNull()
                                } ?: false
                                optionsList.add(SelectOptionData(id, label, description, defaultEnabled))
                            }
                        }
                    }
                    logInfo(method, "Parsed ${optionsList.size} select options")
                    optionsList
                } catch (e: Exception) {
                    logError(method, "Failed to parse options: ${e.message}")
                    emptyList()
                }
            } ?: emptyList()

            ConfigStepResultData(
                success = data.success,
                message = data.error, // error message is the only message from this endpoint
                nextStepIndex = data.nextStepIndex,
                isComplete = isComplete,
                nextStep = null, // Next step needs to be fetched from session status
                discoveredItems = discoveredItems,
                oauthUrl = oauthUrl,
                awaitingCallback = awaitingCallback,
                selectOptions = selectOptions
            )
        } catch (e: Exception) {
            logException(method, e, "sessionId=$sessionId")
            throw e
        }
    }

    /**
     * Get the current status of a configuration session.
     * Used to fetch next step details after step execution.
     */
    suspend fun getConfigurationSessionStatus(sessionId: String): ConfigSessionData {
        val method = "getConfigurationSessionStatus"
        logInfo(method, "Getting session status for: $sessionId")

        return try {
            val response = systemApi.getConfigurationStatusV1SystemAdaptersConfigureSessionIdGet(
                sessionId = sessionId,
                authorization = authHeader()
            )
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")
            logInfo(method, "Session status: step=${data.currentStepIndex}/${data.totalSteps}, status=${data.status}, stepType=${data.currentStep?.stepType}")
            logInfo(method, "Collected config keys: ${data.collectedConfig?.keys}")

            // Flatten collected config to displayable strings
            val collectedConfig = data.collectedConfig?.mapValues { (_, v) ->
                when (v) {
                    is kotlinx.serialization.json.JsonPrimitive -> v.content
                    else -> v.toString()
                }
            } ?: emptyMap()

            ConfigSessionData(
                sessionId = data.sessionId ?: sessionId,
                adapterType = data.adapterType ?: "",
                status = data.status ?: "",
                currentStepIndex = data.currentStepIndex ?: 0,
                totalSteps = data.totalSteps ?: 0,
                currentStep = data.currentStep?.let { step -> mapConfigStep(step) },
                collectedConfig = collectedConfig
            )
        } catch (e: Exception) {
            logException(method, e, "sessionId=$sessionId")
            throw e
        }
    }

    /**
     * Complete an adapter configuration wizard and load the adapter.
     */
    suspend fun completeAdapterConfiguration(
        sessionId: String,
        persist: Boolean = true
    ): ConfigCompleteData {
        val method = "completeAdapterConfiguration"
        logInfo(method, "Completing configuration for session: $sessionId, persist=$persist")

        return try {
            val request = ai.ciris.api.models.ConfigurationCompleteRequest(persist = persist)
            val response = systemApi.completeConfigurationV1SystemAdaptersConfigureSessionIdCompletePost(
                sessionId = sessionId,
                configurationCompleteRequest = request,
                authorization = authHeader()
            )
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")
            logInfo(method, "Config complete: success=${data.success}, adapterType=${data.adapterType}")

            ConfigCompleteData(
                success = data.success,
                adapterId = data.adapterType, // API returns adapterType, we use it as adapterId
                message = data.message,
                persisted = data.persisted ?: false
            )
        } catch (e: Exception) {
            logException(method, e, "sessionId=$sessionId")
            throw e
        }
    }

    // ===== Wise Authority API =====

    suspend fun getWAStatus(): WAStatusData {
        val method = "getWAStatus"
        // AGENT-only: the WA (Wise Authority) status endpoint is 404 on a bare
        // node. Report an inactive WA service.
        if (nodeSkip(method)) return WAStatusData(
            serviceHealthy = false,
            activeWAs = 0,
            pendingDeferrals = 0,
            deferrals24h = 0,
            averageResolutionTimeMinutes = 0.0,
            timestamp = null,
        )
        logInfo(method, "Fetching WA status")

        return try {
            // Use direct HTTP call to parse subscribers field (not in SDK yet)
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
            }

            val response = client.get("$baseUrl/v1/wa/status") {
                header("Authorization", "Bearer $accessToken")
            }

            if (response.status != HttpStatusCode.OK) {
                logError(method, "API returned non-success status: ${response.status}")
                client.close()
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val jsonString = response.bodyAsText()
            client.close()

            val json = Json.parseToJsonElement(jsonString).jsonObject
            val data = json["data"]?.jsonObject
                ?: throw RuntimeException("API returned null data")

            val serviceHealthy = data["service_healthy"]?.jsonPrimitive?.boolean ?: false
            val activeWAs = data["active_was"]?.jsonPrimitive?.int ?: 0
            val pendingDeferrals = data["pending_deferrals"]?.jsonPrimitive?.int ?: 0
            val deferrals24h = data["deferrals_24h"]?.jsonPrimitive?.int ?: 0
            val avgResolutionTime = data["average_resolution_time_minutes"]?.jsonPrimitive?.contentOrNull?.toDoubleOrNull() ?: 0.0
            val timestamp = data["timestamp"]?.jsonPrimitive?.contentOrNull
            val subscribers = data["subscribers"]?.jsonArray?.mapNotNull {
                it.jsonPrimitive.contentOrNull
            } ?: emptyList()

            logInfo(method, "WA Status: healthy=$serviceHealthy, activeWAs=$activeWAs, " +
                    "pendingDeferrals=$pendingDeferrals, deferrals24h=$deferrals24h, " +
                    "subscribers=${subscribers.size}")

            WAStatusData(
                serviceHealthy = serviceHealthy,
                activeWAs = activeWAs,
                pendingDeferrals = pendingDeferrals,
                deferrals24h = deferrals24h,
                averageResolutionTimeMinutes = avgResolutionTime,
                timestamp = timestamp,
                subscribers = subscribers
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    // ===== Wallet API =====

    suspend fun getWalletStatus(): ai.ciris.mobile.shared.ui.screens.WalletStatusResponse {
        val method = "getWalletStatus"
        // AGENT-only: the wallet/billing balance endpoint is 404 on a bare node.
        // Defaults = "no wallet" (all fields default to the no-wallet state).
        if (nodeSkip(method)) return ai.ciris.mobile.shared.ui.screens.WalletStatusResponse()
        logInfo(method, "Fetching wallet status")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = 15000
                    connectTimeoutMillis = 10000
                    socketTimeoutMillis = 15000
                }
            }

            val response = client.get("$baseUrl/v1/wallet/status") {
                header("Authorization", "Bearer $accessToken")
            }

            if (response.status != HttpStatusCode.OK) {
                logError(method, "API returned non-success status: ${response.status}")
                client.close()
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val jsonString = response.bodyAsText()
            client.close()

            val json = Json.parseToJsonElement(jsonString).jsonObject

            // Parse spending progress (handle null vs missing vs object)
            val spendingElement = json["spending"]
            val spendingJson = if (spendingElement != null && spendingElement !is JsonNull) {
                spendingElement.jsonObject
            } else null
            val spending = if (spendingJson != null) {
                ai.ciris.mobile.shared.ui.screens.SpendingProgress(
                    sessionSpent = spendingJson["session_spent"]?.jsonPrimitive?.contentOrNull ?: "0.00",
                    sessionRemaining = spendingJson["session_remaining"]?.jsonPrimitive?.contentOrNull ?: "500.00",
                    sessionLimit = spendingJson["session_limit"]?.jsonPrimitive?.contentOrNull ?: "500.00",
                    sessionResetMinutes = spendingJson["session_reset_minutes"]?.jsonPrimitive?.int ?: 60,
                    dailySpent = spendingJson["daily_spent"]?.jsonPrimitive?.contentOrNull ?: "0.00",
                    dailyRemaining = spendingJson["daily_remaining"]?.jsonPrimitive?.contentOrNull ?: "1000.00",
                    dailyResetHours = spendingJson["daily_reset_hours"]?.jsonPrimitive?.int ?: 24
                )
            } else null

            // Parse gas estimate (handle null vs missing vs object)
            val gasElement = json["gas_estimate"]
            val gasJson = if (gasElement != null && gasElement !is JsonNull) {
                gasElement.jsonObject
            } else null
            val gasEstimate = if (gasJson != null) {
                ai.ciris.mobile.shared.ui.screens.GasEstimate(
                    gasPriceGwei = gasJson["gas_price_gwei"]?.jsonPrimitive?.contentOrNull ?: "0.00",
                    usdcTransferGas = gasJson["usdc_transfer_gas"]?.jsonPrimitive?.int ?: 65000,
                    ethTransferGas = gasJson["eth_transfer_gas"]?.jsonPrimitive?.int ?: 21000,
                    usdcTransferCostEth = gasJson["usdc_transfer_cost_eth"]?.jsonPrimitive?.contentOrNull ?: "0.000000",
                    usdcTransferCostUsd = gasJson["usdc_transfer_cost_usd"]?.jsonPrimitive?.contentOrNull ?: "0.00",
                    ethPriceUsd = gasJson["eth_price_usd"]?.jsonPrimitive?.contentOrNull ?: "2000"
                )
            } else null

            // Parse security advisories (handle null vs missing vs array)
            val advisoriesElement = json["security_advisories"]
            val advisoriesJson = if (advisoriesElement != null && advisoriesElement !is JsonNull) {
                advisoriesElement.jsonArray
            } else null
            val securityAdvisories = advisoriesJson?.mapNotNull { advElement ->
                val adv = advElement.jsonObject
                ai.ciris.mobile.shared.ui.screens.SecurityAdvisoryData(
                    cve = adv["cve"]?.jsonPrimitive?.contentOrNull,
                    title = adv["title"]?.jsonPrimitive?.contentOrNull ?: "Unknown",
                    impact = adv["impact"]?.jsonPrimitive?.contentOrNull ?: "Unknown",
                    remediation = adv["remediation"]?.jsonPrimitive?.contentOrNull
                )
            } ?: emptyList()

            // Parse recent transactions (handle null vs missing vs array)
            val txElement = json["recent_transactions"]
            val txJson = if (txElement != null && txElement !is JsonNull) {
                txElement.jsonArray
            } else null
            val recentTransactions = txJson?.mapNotNull { txItem ->
                val txObj = txItem.jsonObject
                ai.ciris.mobile.shared.ui.screens.TransactionSummary(
                    transactionId = txObj["transaction_id"]?.jsonPrimitive?.contentOrNull ?: "",
                    type = txObj["type"]?.jsonPrimitive?.contentOrNull ?: "send",
                    amount = txObj["amount"]?.jsonPrimitive?.contentOrNull ?: "0.00",
                    currency = txObj["currency"]?.jsonPrimitive?.contentOrNull ?: "USDC",
                    recipient = txObj["recipient"]?.jsonPrimitive?.contentOrNull,
                    sender = txObj["sender"]?.jsonPrimitive?.contentOrNull,
                    status = txObj["status"]?.jsonPrimitive?.contentOrNull ?: "pending",
                    timestamp = txObj["timestamp"]?.jsonPrimitive?.contentOrNull ?: "",
                    explorerUrl = txObj["explorer_url"]?.jsonPrimitive?.contentOrNull
                )
            } ?: emptyList()

            val walletStatus = ai.ciris.mobile.shared.ui.screens.WalletStatusResponse(
                hasWallet = json["has_wallet"]?.jsonPrimitive?.boolean ?: false,
                isInitializing = json["is_initializing"]?.jsonPrimitive?.boolean ?: false,
                provider = json["provider"]?.jsonPrimitive?.contentOrNull ?: "x402",
                network = json["network"]?.jsonPrimitive?.contentOrNull ?: "base-sepolia",
                currency = json["currency"]?.jsonPrimitive?.contentOrNull ?: "USDC",
                balance = json["balance"]?.jsonPrimitive?.contentOrNull ?: "0.00",
                ethBalance = json["eth_balance"]?.jsonPrimitive?.contentOrNull ?: "0.00",
                needsGas = json["needs_gas"]?.jsonPrimitive?.boolean ?: true,
                address = json["address"]?.jsonPrimitive?.contentOrNull,
                paymasterEnabled = json["paymaster_enabled"]?.jsonPrimitive?.boolean ?: false,
                paymasterKeyConfigured = json["paymaster_key_configured"]?.jsonPrimitive?.boolean ?: false,
                isReceiveOnly = json["is_receive_only"]?.jsonPrimitive?.boolean ?: true,
                attestationLevel = json["attestation_level"]?.jsonPrimitive?.int ?: 0,
                maxTransactionLimit = json["max_transaction_limit"]?.jsonPrimitive?.contentOrNull ?: "0.00",
                dailyLimit = json["daily_limit"]?.jsonPrimitive?.contentOrNull ?: "0.00",
                hardwareTrustDegraded = json["hardware_trust_degraded"]?.jsonPrimitive?.boolean ?: false,
                trustDegradationReason = json["trust_degradation_reason"]?.jsonPrimitive?.contentOrNull,
                securityAdvisories = securityAdvisories,
                spending = spending,
                gasEstimate = gasEstimate,
                recentTransactions = recentTransactions
            )

            logInfo(method, "Wallet status: address=${walletStatus.address}, balance=${walletStatus.balance}, level=${walletStatus.attestationLevel}")
            walletStatus
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    suspend fun transferUsdc(recipient: String, amount: String, memo: String? = null): WalletTransferResult {
        val method = "transferUsdc"
        logInfo(method, "Transferring $amount USDC to $recipient")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
            }

            val response = client.post("$baseUrl/v1/wallet/transfer") {
                header("Authorization", "Bearer $accessToken")
                contentType(ContentType.Application.Json)
                setBody(buildJsonObject {
                    put("recipient", recipient)
                    put("amount", amount)
                    if (memo != null) put("memo", memo)
                })
            }

            val jsonString = response.bodyAsText()
            client.close()

            val json = Json.parseToJsonElement(jsonString).jsonObject

            val result = WalletTransferResult(
                success = json["success"]?.jsonPrimitive?.boolean ?: false,
                transactionId = json["transaction_id"]?.jsonPrimitive?.contentOrNull,
                txHash = json["tx_hash"]?.jsonPrimitive?.contentOrNull,
                amount = json["amount"]?.jsonPrimitive?.contentOrNull ?: amount,
                currency = json["currency"]?.jsonPrimitive?.contentOrNull ?: "USDC",
                recipient = json["recipient"]?.jsonPrimitive?.contentOrNull ?: recipient,
                error = json["error"]?.jsonPrimitive?.contentOrNull
            )

            if (result.success) {
                logInfo(method, "Transfer successful: txHash=${result.txHash}")
            } else {
                logError(method, "Transfer failed: ${result.error}")
            }
            result
        } catch (e: Exception) {
            logException(method, e)
            WalletTransferResult(
                success = false,
                amount = amount,
                currency = "USDC",
                recipient = recipient,
                error = e.message ?: "Unknown error"
            )
        }
    }

    /**
     * Validate an EVM address with EIP-55 checksum verification.
     */
    suspend fun validateAddress(address: String): AddressValidationResult {
        val method = "validateAddress"
        logInfo(method, "Validating address")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
            }

            val response = client.post("$baseUrl/v1/wallet/validate-address") {
                header("Authorization", "Bearer $accessToken")
                contentType(ContentType.Application.Json)
                setBody(buildJsonObject {
                    put("address", address)
                })
            }

            val jsonString = response.bodyAsText()
            client.close()

            val json = Json.parseToJsonElement(jsonString).jsonObject

            AddressValidationResult(
                valid = json["valid"]?.jsonPrimitive?.boolean ?: false,
                checksumValid = json["checksum_valid"]?.jsonPrimitive?.boolean ?: false,
                computedChecksum = json["computed_checksum"]?.jsonPrimitive?.contentOrNull,
                isZeroAddress = json["is_zero_address"]?.jsonPrimitive?.boolean ?: false,
                error = json["error"]?.jsonPrimitive?.contentOrNull,
                warnings = json["warnings"]?.jsonArray?.mapNotNull {
                    it.jsonPrimitive.contentOrNull
                } ?: emptyList()
            )
        } catch (e: Exception) {
            logException(method, e)
            AddressValidationResult(
                valid = false,
                checksumValid = false,
                error = e.message ?: "Validation failed"
            )
        }
    }

    /**
     * Check if a transaction would be a duplicate.
     */
    suspend fun checkDuplicateTransaction(
        recipient: String,
        amount: String,
        currency: String = "USDC"
    ): DuplicateCheckResult {
        val method = "checkDuplicateTransaction"
        logInfo(method, "Checking for duplicate transaction")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
            }

            val response = client.post("$baseUrl/v1/wallet/check-duplicate") {
                header("Authorization", "Bearer $accessToken")
                contentType(ContentType.Application.Json)
                setBody(buildJsonObject {
                    put("recipient", recipient)
                    put("amount", amount)
                    put("currency", currency)
                })
            }

            val jsonString = response.bodyAsText()
            client.close()

            val json = Json.parseToJsonElement(jsonString).jsonObject

            DuplicateCheckResult(
                isDuplicate = json["is_duplicate"]?.jsonPrimitive?.boolean ?: false,
                lastTxSecondsAgo = json["last_tx_seconds_ago"]?.jsonPrimitive?.int,
                windowSeconds = json["window_seconds"]?.jsonPrimitive?.int ?: 300,
                warning = json["warning"]?.jsonPrimitive?.contentOrNull
            )
        } catch (e: Exception) {
            logException(method, e)
            DuplicateCheckResult(
                isDuplicate = false,
                warning = "Could not check for duplicates: ${e.message}"
            )
        }
    }

    suspend fun getDeferrals(waId: String? = null): List<DeferralData> {
        val method = "getDeferrals"
        logInfo(method, "Fetching deferrals, waId=$waId")

        return try {
            val response = wiseAuthorityApi.getDeferralsV1WaDeferralsGet(waId, authHeader())
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")
            val deferrals = data.deferrals.map { deferral ->
                DeferralData(
                    deferralId = deferral.deferralId,
                    createdAt = deferral.createdAt.toString(),
                    deferredBy = deferral.deferredBy,
                    taskId = deferral.taskId,
                    thoughtId = deferral.thoughtId,
                    reason = deferral.reason,
                    channelId = deferral.channelId,
                    userId = deferral.userId,
                    priority = deferral.priority ?: "normal",
                    assignedWaId = deferral.assignedWaId,
                    requiresRole = deferral.requiresRole,
                    status = deferral.status ?: "pending",
                    resolution = deferral.resolution,
                    resolvedAt = deferral.resolvedAt?.toString(),
                    question = deferral.question,
                    context = deferral.context,
                    timeoutAt = deferral.timeoutAt
                )
            }
            logInfo(method, "Fetched ${deferrals.size} deferrals")
            deferrals
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    suspend fun resolveDeferral(deferralId: String, resolution: String, guidance: String): ResolveDeferralData {
        val method = "resolveDeferral"
        logInfo(method, "Resolving deferral: id=$deferralId, resolution=$resolution")

        return try {
            val request = ai.ciris.api.models.ResolveDeferralRequest(
                resolution = resolution,
                guidance = guidance
            )
            val response = wiseAuthorityApi.resolveDeferralV1WaDeferralsDeferralIdResolvePost(
                deferralId = deferralId,
                resolveDeferralRequest = request,
                authorization = authHeader()
            )
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")
            logInfo(method, "Deferral resolved: deferralId=${data.deferralId}, success=${data.success}")

            ResolveDeferralData(
                deferralId = data.deferralId,
                success = data.success,
                resolvedAt = data.resolvedAt.toString()
            )
        } catch (e: Exception) {
            logException(method, e, "deferralId=$deferralId")
            throw e
        }
    }

    // ===== Config API =====

    suspend fun listConfigs(prefix: String? = null): ConfigListData {
        val method = "listConfigs"
        logInfo(method, "Listing configs, prefix=$prefix")

        return try {
            val response = configApi.listConfigsV1ConfigGet(prefix, authHeader())
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")
            logInfo(method, "Configs: total=${data.total}")

            ConfigListData(
                configs = data.configs.map { config ->
                    ConfigItemData(
                        key = config.key,
                        displayValue = config.`value`.toDisplayString(),
                        updatedAt = config.updatedAt,
                        updatedBy = config.updatedBy,
                        isSensitive = config.isSensitive ?: false
                    )
                },
                total = data.total
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    suspend fun getConfig(key: String): ConfigItemData {
        val method = "getConfig"
        logInfo(method, "Getting config: $key")

        return try {
            val response = configApi.getConfigV1ConfigKeyGet(key, authHeader())
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")
            logInfo(method, "Config retrieved: key=${data.key}")

            ConfigItemData(
                key = data.key,
                displayValue = data.`value`.toDisplayString(),
                updatedAt = data.updatedAt,
                updatedBy = data.updatedBy,
                isSensitive = data.isSensitive ?: false
            )
        } catch (e: Exception) {
            logException(method, e, "key=$key")
            throw e
        }
    }

    suspend fun updateConfig(key: String, value: String, reason: String? = null): ConfigItemData {
        val method = "updateConfig"
        logInfo(method, "Updating config: $key")

        return try {
            val request = SdkConfigUpdate(
                `value` = JsonPrimitive(value),
                reason = reason
            )
            val response = configApi.updateConfigV1ConfigKeyPut(key, request, authHeader())
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")
            logInfo(method, "Config updated: key=${data.key}")

            ConfigItemData(
                key = data.key,
                displayValue = data.`value`.toDisplayString(),
                updatedAt = data.updatedAt,
                updatedBy = data.updatedBy,
                isSensitive = data.isSensitive ?: false
            )
        } catch (e: Exception) {
            logException(method, e, "key=$key")
            throw e
        }
    }

    suspend fun deleteConfig(key: String) {
        val method = "deleteConfig"
        logInfo(method, "Deleting config: $key")

        try {
            val response = configApi.deleteConfigV1ConfigKeyDelete(key, authHeader())
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            logInfo(method, "Config deleted: key=$key")
        } catch (e: Exception) {
            logException(method, e, "key=$key")
            throw e
        }
    }

    // ===== Consent API =====

    suspend fun getConsentStatus(): ConsentStatusData? {
        val method = "getConsentStatus"
        logInfo(method, "Fetching consent status")

        return try {
            val response = consentApi.getConsentStatusV1ConsentStatusGet(authHeader())
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            if (!body.hasConsent) {
                logInfo(method, "No consent record exists")
                return null
            }

            logInfo(method, "Consent status: stream=${body.stream}, expiresAt=${body.expiresAt}")

            ConsentStatusData(
                hasConsent = body.hasConsent,
                userId = body.userId,
                stream = body.stream,
                grantedAt = body.grantedAt,
                expiresAt = body.expiresAt
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    suspend fun getConsentStreams(): ConsentStreamsData {
        val method = "getConsentStreams"
        logInfo(method, "Fetching consent streams")

        return try {
            val response = consentApi.getConsentStreamsV1ConsentStreamsGet()
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            logInfo(method, "Consent streams: ${body.streams.size} available, default=${body.default}")

            ConsentStreamsData(
                streams = body.streams.mapValues { (_, metadata) ->
                    StreamMetadataData(
                        name = metadata.name,
                        description = metadata.description,
                        durationDays = metadata.durationDays,
                        autoForget = metadata.autoForget ?: false,
                        learningEnabled = metadata.learningEnabled ?: false,
                        identityRemoved = metadata.identityRemoved ?: false,
                        requiresCategories = metadata.requiresCategories ?: false
                    )
                },
                default = body.default
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    suspend fun grantConsent(stream: String, categories: List<String> = emptyList(), reason: String? = null): ConsentGrantData {
        val method = "grantConsent"
        logInfo(method, "Granting consent: stream=$stream, categories=$categories")

        return try {
            val streamEnum = try {
                ai.ciris.api.models.ConsentStream.valueOf(stream.uppercase())
            } catch (e: IllegalArgumentException) {
                ai.ciris.api.models.ConsentStream.TEMPORARY
            }
            val categoryEnums = categories.mapNotNull { cat ->
                try {
                    ai.ciris.api.models.ConsentCategory.valueOf(cat.uppercase())
                } catch (e: IllegalArgumentException) {
                    null
                }
            }
            val request = SdkConsentRequest(
                stream = streamEnum,
                categories = categoryEnums,
                reason = reason,
                userId = "current_user" // userId is required
            )
            val response = consentApi.grantConsentV1ConsentGrantPost(request, authHeader())
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            logInfo(method, "Consent granted: userId=${body.userId}, stream=${body.stream}")

            ConsentGrantData(
                userId = body.userId,
                stream = body.stream.value,
                grantedAt = body.grantedAt.toString(),
                expiresAt = body.expiresAt?.toString()
            )
        } catch (e: Exception) {
            logException(method, e, "stream=$stream")
            throw e
        }
    }

    suspend fun getConsentImpact(): ConsentImpactReportData {
        val method = "getConsentImpact"
        logInfo(method, "Fetching consent impact")

        return try {
            val response = consentApi.getImpactReportV1ConsentImpactGet(authHeader())
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            logInfo(method, "Impact: interactions=${body.totalInteractions}, patterns=${body.patternsContributed}, helped=${body.usersHelped}")

            ConsentImpactReportData(
                userId = body.userId,
                totalInteractions = body.totalInteractions,
                patternsContributed = body.patternsContributed,
                usersHelped = body.usersHelped,
                impactScore = body.impactScore
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    suspend fun getConsentAudit(limit: Int = 100): List<ConsentAuditEntryApiData> {
        val method = "getConsentAudit"
        logInfo(method, "Fetching consent audit, limit=$limit")

        return try {
            val response = consentApi.getAuditTrailV1ConsentAuditGet(limit, authHeader())
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            logInfo(method, "Audit entries: ${body.size}")

            body.map { entry ->
                ConsentAuditEntryApiData(
                    entryId = entry.entryId,
                    userId = entry.userId,
                    timestamp = entry.timestamp.toString(),
                    previousStream = entry.previousStream.value,
                    newStream = entry.newStream.value,
                    initiatedBy = entry.initiatedBy,
                    reason = entry.reason
                )
            }
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    suspend fun getPartnershipStatus(): PartnershipStatusData {
        val method = "getPartnershipStatus"
        logInfo(method, "Fetching partnership status")

        return try {
            val response = consentApi.checkPartnershipStatusV1ConsentPartnershipStatusGet(authHeader())
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            logInfo(method, "Partnership status: ${body.partnershipStatus}")

            PartnershipStatusData(
                status = body.partnershipStatus,
                requestedAt = null,
                decidedAt = null,
                reason = body.message
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    suspend fun requestPartnership(reason: String? = null) {
        val method = "requestPartnership"
        logInfo(method, "Requesting partnership, reason=$reason")

        try {
            // Use grantConsent with PARTNERED stream to request partnership
            val request = SdkConsentRequest(
                stream = ai.ciris.api.models.ConsentStream.PARTNERED,
                categories = emptyList(),
                reason = reason ?: "Partnership requested via mobile app",
                userId = "current_user"
            )
            val response = consentApi.grantConsentV1ConsentGrantPost(request, authHeader())
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            logInfo(method, "Partnership request submitted")
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    // ===== Extended System API =====

    suspend fun getSystemHealth(): SystemHealthData {
        val method = "getSystemHealth"
        // Per-poll fetch (every 30s) — debug; the INFO line below fires only when
        // something is actually wrong, so a steady status=ok node doesn't spam.
        logDebug(method, "Fetching system health")

        return try {
            // Use direct HTTP call to properly parse warnings
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
            }

            val response = client.get("$baseUrl/v1/system/health") {
                header("Authorization", "Bearer $accessToken")
            }

            if (response.status != HttpStatusCode.OK) {
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val jsonText = response.bodyAsText()
            val json = Json.parseToJsonElement(jsonText).jsonObject
            val data = json["data"]?.jsonObject ?: throw RuntimeException("API returned null data")

            val status = data["status"]?.jsonPrimitive?.content ?: "unknown"
            val cognitiveState = data["cognitive_state"]?.jsonPrimitive?.content ?: "UNKNOWN"

            // Parse warnings array
            val warnings = data["warnings"]?.jsonArray?.mapNotNull { warningElement ->
                try {
                    val warningObj = warningElement.jsonObject
                    SystemWarning(
                        code = warningObj["code"]?.jsonPrimitive?.content ?: "",
                        message = warningObj["message"]?.jsonPrimitive?.content ?: "",
                        severity = warningObj["severity"]?.jsonPrimitive?.content ?: "warning",
                        actionUrl = warningObj["action_url"]?.jsonPrimitive?.contentOrNull
                    )
                } catch (e: Exception) {
                    logWarn(method, "Failed to parse warning: ${e.message}")
                    null
                }
            } ?: emptyList()

            // Parse degraded_mode flag
            val degradedMode = data["degraded_mode"]?.jsonPrimitive?.boolean ?: false

            // Only surface at INFO when something is actually wrong (status not
            // ok, degraded mode, or warnings present). A steady "status=ok" every
            // 30s is noise → debug.
            val healthMsg = "System health: status=$status, cognitiveState=$cognitiveState, warnings=${warnings.size}, degradedMode=$degradedMode"
            if (status != "ok" || degradedMode || warnings.isNotEmpty()) {
                logInfo(method, healthMsg)
            } else {
                logDebug(method, healthMsg)
            }

            SystemHealthData(
                status = status,
                cognitiveState = cognitiveState,
                warnings = warnings,
                degradedMode = degradedMode
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    suspend fun getTools(): ToolsResult {
        val method = "getTools"
        logInfo(method, "Fetching available tools")

        return try {
            // Use direct HTTP call to parse the tools response properly
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
            }

            val response = client.get("$baseUrl/v1/system/tools") {
                header("Authorization", "Bearer $accessToken")
            }

            if (response.status != HttpStatusCode.OK) {
                logError(method, "API returned non-success status: ${response.status}")
                client.close()
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val jsonString = response.bodyAsText()
            client.close()

            val json = Json.parseToJsonElement(jsonString).jsonObject
            val dataArray = json["data"]?.jsonArray ?: emptyList()
            val metadataObj = json["metadata"]?.jsonObject

            val tools = dataArray.mapNotNull { toolElement ->
                val tool = toolElement.jsonObject
                ToolInfoData(
                    name = tool["name"]?.jsonPrimitive?.contentOrNull ?: return@mapNotNull null,
                    description = tool["description"]?.jsonPrimitive?.contentOrNull ?: "",
                    provider = tool["provider"]?.jsonPrimitive?.contentOrNull ?: "unknown",
                    category = tool["category"]?.jsonPrimitive?.contentOrNull ?: "general",
                    cost = tool["cost"]?.jsonPrimitive?.contentOrNull?.toDoubleOrNull() ?: 0.0,
                    whenToUse = tool["when_to_use"]?.jsonPrimitive?.contentOrNull,
                    parameters = tool["parameters"]?.jsonObject?.let { params ->
                        params.entries.associate { (k, v) -> k to v.toString() }
                    }
                )
            }

            val metadata = metadataObj?.let {
                ToolsMetadataData(
                    providers = it["providers"]?.jsonArray?.mapNotNull { p ->
                        p.jsonPrimitive.contentOrNull
                    } ?: emptyList(),
                    providerCount = it["provider_count"]?.jsonPrimitive?.int ?: 0,
                    totalTools = it["total_tools"]?.jsonPrimitive?.int ?: tools.size
                )
            }

            logInfo(method, "Loaded ${tools.size} tools from ${metadata?.providerCount ?: 0} providers")

            ToolsResult(
                tools = tools,
                metadata = metadata
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    suspend fun getUnifiedTelemetry(): UnifiedTelemetryData {
        val method = "getUnifiedTelemetry"
        logInfo(method, "Fetching unified telemetry")

        return try {
            // Use telemetry overview instead since unified returns kotlin.Any
            val response = telemetryApi.getTelemetryOverviewV1TelemetryOverviewGet(authHeader())
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")

            val healthyServices = data.healthyServices ?: 0
            val degradedServices = data.degradedServices ?: 0
            val cpuPercent = data.cpuPercent ?: 0.0
            val memoryMb = data.memoryMb ?: 0.0
            val diskUsedMb = data.diskUsedMb ?: 0.0

            logInfo(method, "Telemetry: uptime=${data.uptimeSeconds}s, state=${data.cognitiveState}, " +
                    "services=$healthyServices/$healthyServices, " +
                    "cpu=$cpuPercent%, memory=${memoryMb}MB, disk=${diskUsedMb}MB")

            UnifiedTelemetryData(
                health = if (degradedServices == 0) "healthy" else "degraded",
                uptime = "${(data.uptimeSeconds / 3600).toInt()}h ${((data.uptimeSeconds % 3600) / 60).toInt()}m",
                cognitiveState = data.cognitiveState,
                memoryMb = memoryMb.toInt(),
                memoryPercent = 0, // Not available from overview
                cpuPercent = cpuPercent.toInt(),
                diskUsedMb = diskUsedMb,
                servicesOnline = healthyServices,
                servicesTotal = healthyServices + degradedServices,
                services = emptyMap() // Not available from overview
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    suspend fun getEnvironmentalMetrics(): EnvironmentalMetricsData? {
        val method = "getEnvironmentalMetrics"
        logInfo(method, "Fetching environmental metrics from telemetry overview")

        return try {
            // Use telemetry overview which contains environmental metrics
            val response = telemetryApi.getTelemetryOverviewV1TelemetryOverviewGet(authHeader())

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                return null
            }

            val body = response.body()
            val data = body.`data` ?: return null

            val carbonGrams = data.carbonLastHourGrams ?: 0.0
            val energyKwh = data.energyLastHourKwh ?: 0.0
            val costCents = data.costLastHourCents ?: 0.0
            val tokensLastHour = (data.tokensLastHour ?: 0.0).toInt()
            val tokens24h = (data.tokens24h ?: 0.0).toInt()

            logInfo(method, "Environmental: carbon=${carbonGrams}g, energy=${energyKwh}kWh, " +
                    "cost=${costCents}c, tokens=$tokensLastHour/hr, tokens24h=$tokens24h")

            EnvironmentalMetricsData(
                carbonGrams = carbonGrams,
                energyKwh = energyKwh,
                costCents = costCents,
                tokensLastHour = tokensLastHour,
                tokens24h = tokens24h
            )
        } catch (e: Exception) {
            logException(method, e)
            null
        }
    }

    suspend fun getProcessorStatus(): ProcessorStatusData? {
        val method = "getProcessorStatus"
        logInfo(method, "Fetching processor status")

        return try {
            // Use the system health endpoint which includes processor info
            val response = systemApi.getSystemHealthV1SystemHealthGet()
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")

            // Extract queue depth from services if available
            val queueDepth = data.services["processing"]?.get("queue_depth") ?: 0

            ProcessorStatusData(
                isPaused = data.status == "paused",
                cognitiveState = data.cognitiveState ?: "UNKNOWN",
                queueDepth = queueDepth
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    suspend fun getChannels(): ChannelsData? {
        val method = "getChannels"
        logInfo(method, "Fetching channels")

        return try {
            val authHeaderValue = accessToken?.let { "Bearer $it" }
            val response = agentApi.getChannelsV1AgentChannelsGet(authHeaderValue)
            val body = response.body()

            val channels = body.data?.channels?.map { channel ->
                ChannelInfoData(
                    channelId = channel.channelId,
                    displayName = channel.displayName ?: channel.channelId,
                    channelType = channel.channelType,
                    isActive = channel.isActive ?: true,
                    messageCount = channel.messageCount ?: 0,
                    lastActivity = channel.lastActivity?.toString()
                )
            } ?: emptyList()

            logInfo(method, "Fetched ${channels.size} channels")
            ChannelsData(channels = channels)
        } catch (e: Exception) {
            logWarn(method, "Failed to fetch channels: ${e.message}")
            // Return empty data if endpoint fails (might not be available)
            ChannelsData(channels = emptyList())
        }
    }


    // ===== LLM Bus API =====

    /**
     * Get LLM Bus status including distribution strategy and aggregate metrics.
     * Returns bus health, provider counts, circuit breaker summary.
     */
    /**
     * Per-bus telemetry snapshot for the 6 CIRIS buses, from
     * ``/v1/telemetry/unified?category=buses``. Returns a map keyed by
     * the bus name used in the backend (``llm_bus``, ``memory_bus``,
     * ``communication_bus``, ``wise_bus``, ``tool_bus``,
     * ``runtime_control_bus``). Each value holds the few fields the FG
     * detail panel renders — bounded shape, no speculative properties.
     *
     * Used by the cell viz's BusArc panel to light up non-LLM buses;
     * LLM has its own richer endpoint (``getLlmProviders``).
     */
    suspend fun getBusTelemetry(): Map<String, ai.ciris.mobile.shared.models.BusTelemetrySnapshot> {
        val method = "getBusTelemetry"
        val url = "$baseUrl/v1/telemetry/unified?category=buses&view=operational"
        logDebug(method, "GET $url")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = 10000
                connectTimeoutMillis = 5000
            }
        }
        return try {
            val response = client.get(url) {
                authHeader()?.let { header("Authorization", it) }
            }
            if (!response.status.isSuccess()) {
                throw RuntimeException("Bus telemetry failed: ${response.status}")
            }
            val body = response.bodyAsText()
            val json = kotlinx.serialization.json.Json { ignoreUnknownKeys = true }
            val parsed = json.parseToJsonElement(body).jsonObject
            // Unified can be wrapped in ``data`` envelope or flat; accept both.
            val svcMap = (parsed["data"]?.jsonObject ?: parsed)["services"]?.jsonObject
                ?: return emptyMap()
            svcMap.entries.mapNotNull { (key, value) ->
                if (!key.endsWith("_bus")) return@mapNotNull null
                val obj = value.jsonObject
                val custom = obj["custom_metrics"]?.jsonObject
                key to ai.ciris.mobile.shared.models.BusTelemetrySnapshot(
                    healthy = obj["healthy"]?.jsonPrimitive?.booleanOrNull ?: true,
                    messagesSent = custom?.get("messages_sent")?.jsonPrimitive?.longOrNull
                        ?: obj["requests_handled"]?.jsonPrimitive?.longOrNull ?: 0L,
                    averageLatencyMs = custom?.get("average_latency_ms")?.jsonPrimitive?.doubleOrNull ?: 0.0,
                    queueDepth = custom?.get("queue_depth")?.jsonPrimitive?.intOrNull ?: 0,
                    errorsLastHour = custom?.get("errors_last_hour")?.jsonPrimitive?.intOrNull
                        ?: obj["error_count"]?.jsonPrimitive?.intOrNull ?: 0,
                )
            }.toMap()
        } catch (e: Exception) {
            logException(method, e, "url=$url")
            emptyMap()
        } finally {
            client.close()
        }
    }

    suspend fun getLlmBusStatus(): ai.ciris.mobile.shared.models.LlmBusStatus {
        val method = "getLlmBusStatus"
        val url = "$baseUrl/v1/system/llm/status"
        logInfo(method, "GET $url")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = 10000
                    connectTimeoutMillis = 5000
                }
            }

            val response = client.get(url) {
                authHeader()?.let { header("Authorization", it) }
            }

            if (!response.status.isSuccess()) {
                client.close()
                throw RuntimeException("LLM Bus status failed: ${response.status}")
            }

            val body = response.bodyAsText()
            client.close()
            logDebug(method, "Response body: ${body.take(200)}...")

            val json = Json { ignoreUnknownKeys = true }
            val parsed = json.parseToJsonElement(body).jsonObject
            val data = parsed["data"]?.jsonObject ?: throw RuntimeException("No data in response")

            ai.ciris.mobile.shared.models.LlmBusStatus(
                distributionStrategy = when (data["distribution_strategy"]?.jsonPrimitive?.content) {
                    "round_robin" -> ai.ciris.mobile.shared.models.DistributionStrategy.ROUND_ROBIN
                    "latency_based" -> ai.ciris.mobile.shared.models.DistributionStrategy.LATENCY_BASED
                    "random" -> ai.ciris.mobile.shared.models.DistributionStrategy.RANDOM
                    "least_loaded" -> ai.ciris.mobile.shared.models.DistributionStrategy.LEAST_LOADED
                    else -> ai.ciris.mobile.shared.models.DistributionStrategy.LATENCY_BASED
                },
                totalRequests = data["total_requests"]?.jsonPrimitive?.intOrNull ?: 0,
                failedRequests = data["failed_requests"]?.jsonPrimitive?.intOrNull ?: 0,
                averageLatencyMs = data["average_latency_ms"]?.jsonPrimitive?.doubleOrNull?.toFloat() ?: 0.0f,
                errorRate = data["error_rate"]?.jsonPrimitive?.doubleOrNull?.toFloat() ?: 0.0f,
                providersTotal = data["providers_total"]?.jsonPrimitive?.intOrNull ?: 0,
                providersAvailable = data["providers_available"]?.jsonPrimitive?.intOrNull ?: 0,
                providersRateLimited = data["providers_rate_limited"]?.jsonPrimitive?.intOrNull ?: 0,
                circuitBreakersClosed = data["circuit_breakers_closed"]?.jsonPrimitive?.intOrNull ?: 0,
                circuitBreakersOpen = data["circuit_breakers_open"]?.jsonPrimitive?.intOrNull ?: 0,
                circuitBreakersHalfOpen = data["circuit_breakers_half_open"]?.jsonPrimitive?.intOrNull ?: 0,
                uptimeSeconds = data["uptime_seconds"]?.jsonPrimitive?.doubleOrNull?.toFloat() ?: 0.0f,
                timestamp = data["timestamp"]?.jsonPrimitive?.contentOrNull
            )
        } catch (e: Exception) {
            logException(method, e, "url=$url")
            throw e
        }
    }

    /**
     * Get all LLM providers with their status, metrics, and circuit breaker state.
     */
    suspend fun getLlmProviders(): List<ai.ciris.mobile.shared.models.LlmProviderStatus> {
        val method = "getLlmProviders"
        val url = "$baseUrl/v1/system/llm/providers"
        logInfo(method, "GET $url")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = 10000
                    connectTimeoutMillis = 5000
                }
            }

            val response = client.get(url) {
                authHeader()?.let { header("Authorization", it) }
            }

            if (!response.status.isSuccess()) {
                client.close()
                throw RuntimeException("LLM providers failed: ${response.status}")
            }

            val body = response.bodyAsText()
            client.close()
            logDebug(method, "Response body: ${body.take(500)}...")

            val json = Json { ignoreUnknownKeys = true }
            val parsed = json.parseToJsonElement(body).jsonObject
            val data = parsed["data"]?.jsonObject ?: throw RuntimeException("No data in response")
            val providers = data["providers"]?.jsonArray ?: emptyList()

            providers.map { providerJson ->
                val p = providerJson.jsonObject
                val metrics = p["metrics"]?.jsonObject
                val cb = p["circuit_breaker"]?.jsonObject
                val cbConfig = cb?.get("config")?.jsonObject

                ai.ciris.mobile.shared.models.LlmProviderStatus(
                    name = p["name"]?.jsonPrimitive?.content ?: "Unknown",
                    healthy = p["healthy"]?.jsonPrimitive?.boolean ?: false,
                    enabled = p["enabled"]?.jsonPrimitive?.boolean ?: true,
                    priority = when (p["priority"]?.jsonPrimitive?.content) {
                        "critical" -> ai.ciris.mobile.shared.models.ProviderPriority.CRITICAL
                        "high" -> ai.ciris.mobile.shared.models.ProviderPriority.HIGH
                        "normal" -> ai.ciris.mobile.shared.models.ProviderPriority.NORMAL
                        "low" -> ai.ciris.mobile.shared.models.ProviderPriority.LOW
                        "fallback" -> ai.ciris.mobile.shared.models.ProviderPriority.FALLBACK
                        else -> ai.ciris.mobile.shared.models.ProviderPriority.NORMAL
                    },
                    metrics = ai.ciris.mobile.shared.models.ProviderMetrics(
                        totalRequests = metrics?.get("total_requests")?.jsonPrimitive?.intOrNull ?: 0,
                        failedRequests = metrics?.get("failed_requests")?.jsonPrimitive?.intOrNull ?: 0,
                        failureRate = metrics?.get("failure_rate")?.jsonPrimitive?.doubleOrNull?.toFloat() ?: 0.0f,
                        averageLatencyMs = metrics?.get("average_latency_ms")?.jsonPrimitive?.doubleOrNull?.toFloat() ?: 0.0f,
                        consecutiveFailures = metrics?.get("consecutive_failures")?.jsonPrimitive?.intOrNull ?: 0,
                        lastRequestTime = metrics?.get("last_request_time")?.jsonPrimitive?.contentOrNull,
                        lastFailureTime = metrics?.get("last_failure_time")?.jsonPrimitive?.contentOrNull,
                        isRateLimited = metrics?.get("is_rate_limited")?.jsonPrimitive?.boolean ?: false,
                        rateLimitCooldownRemainingSeconds = metrics?.get("rate_limit_cooldown_remaining_seconds")?.jsonPrimitive?.doubleOrNull?.toFloat()
                    ),
                    circuitBreaker = ai.ciris.mobile.shared.models.CircuitBreakerStatus(
                        state = when (cb?.get("state")?.jsonPrimitive?.content) {
                            "closed" -> ai.ciris.mobile.shared.models.CircuitBreakerState.CLOSED
                            "open" -> ai.ciris.mobile.shared.models.CircuitBreakerState.OPEN
                            "half_open" -> ai.ciris.mobile.shared.models.CircuitBreakerState.HALF_OPEN
                            else -> ai.ciris.mobile.shared.models.CircuitBreakerState.CLOSED
                        },
                        failureCount = cb?.get("failure_count")?.jsonPrimitive?.intOrNull ?: 0,
                        successCount = cb?.get("success_count")?.jsonPrimitive?.intOrNull ?: 0,
                        totalCalls = cb?.get("total_calls")?.jsonPrimitive?.intOrNull ?: 0,
                        totalFailures = cb?.get("total_failures")?.jsonPrimitive?.intOrNull ?: 0,
                        totalSuccesses = cb?.get("total_successes")?.jsonPrimitive?.intOrNull ?: 0,
                        successRate = cb?.get("success_rate")?.jsonPrimitive?.doubleOrNull?.toFloat() ?: 1.0f,
                        consecutiveFailures = cb?.get("consecutive_failures")?.jsonPrimitive?.intOrNull ?: 0,
                        recoveryAttempts = cb?.get("recovery_attempts")?.jsonPrimitive?.intOrNull ?: 0,
                        stateTransitions = cb?.get("state_transitions")?.jsonPrimitive?.intOrNull ?: 0,
                        timeInOpenStateSeconds = cb?.get("time_in_open_state_seconds")?.jsonPrimitive?.doubleOrNull?.toFloat() ?: 0.0f,
                        lastFailureAgeSeconds = cb?.get("last_failure_age_seconds")?.jsonPrimitive?.doubleOrNull?.toFloat(),
                        config = ai.ciris.mobile.shared.models.CircuitBreakerConfig(
                            failureThreshold = cbConfig?.get("failure_threshold")?.jsonPrimitive?.intOrNull ?: 5,
                            recoveryTimeoutSeconds = cbConfig?.get("recovery_timeout_seconds")?.jsonPrimitive?.doubleOrNull?.toFloat() ?: 10.0f,
                            successThreshold = cbConfig?.get("success_threshold")?.jsonPrimitive?.intOrNull ?: 3,
                            timeoutDurationSeconds = cbConfig?.get("timeout_duration_seconds")?.jsonPrimitive?.doubleOrNull?.toFloat() ?: 30.0f
                        )
                    )
                )
            }
        } catch (e: Exception) {
            logException(method, e, "url=$url")
            throw e
        }
    }

    /**
     * Update the LLM Bus distribution strategy.
     */
    suspend fun updateLlmDistributionStrategy(strategy: ai.ciris.mobile.shared.models.DistributionStrategy): ai.ciris.mobile.shared.models.DistributionStrategyUpdateResponse {
        val method = "updateLlmDistributionStrategy"
        val url = "$baseUrl/v1/system/llm/distribution"
        logInfo(method, "PUT $url strategy=${strategy.name.lowercase()}")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = 10000
                    connectTimeoutMillis = 5000
                }
            }

            val response = client.put(url) {
                authHeader()?.let { header("Authorization", it) }
                contentType(ContentType.Application.Json)
                setBody(buildJsonObject {
                    put("strategy", strategy.name.lowercase())
                })
            }

            if (!response.status.isSuccess()) {
                client.close()
                throw RuntimeException("Update distribution strategy failed: ${response.status}")
            }

            val body = response.bodyAsText()
            client.close()
            logDebug(method, "Response body: $body")

            val json = Json { ignoreUnknownKeys = true }
            val parsed = json.parseToJsonElement(body).jsonObject
            val data = parsed["data"]?.jsonObject ?: throw RuntimeException("No data in response")

            ai.ciris.mobile.shared.models.DistributionStrategyUpdateResponse(
                success = data["success"]?.jsonPrimitive?.boolean ?: false,
                previousStrategy = data["previous_strategy"]?.jsonPrimitive?.content ?: "",
                newStrategy = data["new_strategy"]?.jsonPrimitive?.content ?: "",
                message = data["message"]?.jsonPrimitive?.content ?: ""
            )
        } catch (e: Exception) {
            logException(method, e, "url=$url")
            throw e
        }
    }

    /**
     * Reset a circuit breaker for a specific provider.
     */
    suspend fun resetLlmCircuitBreaker(providerName: String, force: Boolean = false): ai.ciris.mobile.shared.models.CircuitBreakerResetResponse {
        val method = "resetLlmCircuitBreaker"
        val url = "$baseUrl/v1/system/llm/providers/$providerName/circuit-breaker/reset"
        logInfo(method, "POST $url force=$force")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = 10000
                    connectTimeoutMillis = 5000
                }
            }

            val response = client.post(url) {
                authHeader()?.let { header("Authorization", it) }
                contentType(ContentType.Application.Json)
                setBody(buildJsonObject {
                    put("force", force)
                })
            }

            if (!response.status.isSuccess()) {
                client.close()
                throw RuntimeException("Reset circuit breaker failed: ${response.status}")
            }

            val body = response.bodyAsText()
            client.close()
            logDebug(method, "Response body: $body")

            val json = Json { ignoreUnknownKeys = true }
            val parsed = json.parseToJsonElement(body).jsonObject
            val data = parsed["data"]?.jsonObject ?: throw RuntimeException("No data in response")

            ai.ciris.mobile.shared.models.CircuitBreakerResetResponse(
                success = data["success"]?.jsonPrimitive?.boolean ?: false,
                providerName = data["provider_name"]?.jsonPrimitive?.content ?: providerName,
                previousState = data["previous_state"]?.jsonPrimitive?.content ?: "",
                newState = data["new_state"]?.jsonPrimitive?.content ?: "",
                message = data["message"]?.jsonPrimitive?.content ?: ""
            )
        } catch (e: Exception) {
            logException(method, e, "url=$url")
            throw e
        }
    }

    /**
     * Update circuit breaker configuration for a specific provider.
     */
    suspend fun updateLlmCircuitBreakerConfig(
        providerName: String,
        failureThreshold: Int? = null,
        recoveryTimeoutSeconds: Float? = null,
        successThreshold: Int? = null,
        timeoutDurationSeconds: Float? = null
    ): ai.ciris.mobile.shared.models.CircuitBreakerConfigUpdateResponse {
        val method = "updateLlmCircuitBreakerConfig"
        val url = "$baseUrl/v1/system/llm/providers/$providerName/circuit-breaker/config"
        logInfo(method, "PUT $url")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = 10000
                    connectTimeoutMillis = 5000
                }
            }

            val response = client.put(url) {
                authHeader()?.let { header("Authorization", it) }
                contentType(ContentType.Application.Json)
                setBody(buildJsonObject {
                    failureThreshold?.let { put("failure_threshold", it) }
                    recoveryTimeoutSeconds?.let { put("recovery_timeout_seconds", it) }
                    successThreshold?.let { put("success_threshold", it) }
                    timeoutDurationSeconds?.let { put("timeout_duration_seconds", it) }
                })
            }

            if (!response.status.isSuccess()) {
                client.close()
                throw RuntimeException("Update circuit breaker config failed: ${response.status}")
            }

            val body = response.bodyAsText()
            client.close()
            logDebug(method, "Response body: $body")

            val json = Json { ignoreUnknownKeys = true }
            val parsed = json.parseToJsonElement(body).jsonObject
            val data = parsed["data"]?.jsonObject ?: throw RuntimeException("No data in response")

            val prevConfig = data["previous_config"]?.jsonObject
            val newConfig = data["new_config"]?.jsonObject

            ai.ciris.mobile.shared.models.CircuitBreakerConfigUpdateResponse(
                success = data["success"]?.jsonPrimitive?.boolean ?: false,
                providerName = data["provider_name"]?.jsonPrimitive?.content ?: providerName,
                previousConfig = ai.ciris.mobile.shared.models.CircuitBreakerConfig(
                    failureThreshold = prevConfig?.get("failure_threshold")?.jsonPrimitive?.intOrNull ?: 5,
                    recoveryTimeoutSeconds = prevConfig?.get("recovery_timeout_seconds")?.jsonPrimitive?.doubleOrNull?.toFloat() ?: 10.0f,
                    successThreshold = prevConfig?.get("success_threshold")?.jsonPrimitive?.intOrNull ?: 3,
                    timeoutDurationSeconds = prevConfig?.get("timeout_duration_seconds")?.jsonPrimitive?.doubleOrNull?.toFloat() ?: 30.0f
                ),
                newConfig = ai.ciris.mobile.shared.models.CircuitBreakerConfig(
                    failureThreshold = newConfig?.get("failure_threshold")?.jsonPrimitive?.intOrNull ?: 5,
                    recoveryTimeoutSeconds = newConfig?.get("recovery_timeout_seconds")?.jsonPrimitive?.doubleOrNull?.toFloat() ?: 10.0f,
                    successThreshold = newConfig?.get("success_threshold")?.jsonPrimitive?.intOrNull ?: 3,
                    timeoutDurationSeconds = newConfig?.get("timeout_duration_seconds")?.jsonPrimitive?.doubleOrNull?.toFloat() ?: 30.0f
                ),
                message = data["message"]?.jsonPrimitive?.content ?: ""
            )
        } catch (e: Exception) {
            logException(method, e, "url=$url")
            throw e
        }
    }

    /**
     * Update a provider's priority level.
     *
     * @param providerName Name of the provider to update
     * @param priority New priority level: "critical", "high", "normal", "low", "fallback"
     */
    suspend fun updateLlmProviderPriority(
        providerName: String,
        priority: ai.ciris.mobile.shared.models.ProviderPriority
    ): ai.ciris.mobile.shared.models.ProviderPriorityUpdateResponse {
        val method = "updateLlmProviderPriority"
        val url = "$baseUrl/v1/system/llm/providers/$providerName/priority"
        logInfo(method, "PUT $url priority=${priority.name.lowercase()}")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = 10000
                    connectTimeoutMillis = 5000
                }
            }

            val response = client.put(url) {
                authHeader()?.let { header("Authorization", it) }
                contentType(ContentType.Application.Json)
                setBody(buildJsonObject {
                    put("priority", priority.name.lowercase())
                })
            }

            if (!response.status.isSuccess()) {
                client.close()
                throw RuntimeException("Update provider priority failed: ${response.status}")
            }

            val body = response.bodyAsText()
            client.close()
            logDebug(method, "Response body: $body")

            val json = Json { ignoreUnknownKeys = true }
            val parsed = json.parseToJsonElement(body).jsonObject
            val data = parsed["data"]?.jsonObject ?: throw RuntimeException("No data in response")

            ai.ciris.mobile.shared.models.ProviderPriorityUpdateResponse(
                success = data["success"]?.jsonPrimitive?.boolean ?: false,
                providerName = data["provider_name"]?.jsonPrimitive?.content ?: providerName,
                previousPriority = data["previous_priority"]?.jsonPrimitive?.content ?: "",
                newPriority = data["new_priority"]?.jsonPrimitive?.content ?: "",
                message = data["message"]?.jsonPrimitive?.content ?: ""
            )
        } catch (e: Exception) {
            logException(method, e, "url=$url")
            throw e
        }
    }

    /**
     * Delete/unregister an LLM provider.
     *
     * @param providerName Name of the provider to delete
     */
    suspend fun deleteLlmProvider(
        providerName: String
    ): ai.ciris.mobile.shared.models.ProviderDeleteResponse {
        val method = "deleteLlmProvider"
        val url = "$baseUrl/v1/system/llm/providers/$providerName"
        logInfo(method, "DELETE $url")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = 10000
                    connectTimeoutMillis = 5000
                }
            }

            val response = client.delete(url) {
                authHeader()?.let { header("Authorization", it) }
            }

            if (!response.status.isSuccess()) {
                client.close()
                throw RuntimeException("Delete provider failed: ${response.status}")
            }

            val body = response.bodyAsText()
            client.close()
            logDebug(method, "Response body: $body")

            val json = Json { ignoreUnknownKeys = true }
            val parsed = json.parseToJsonElement(body).jsonObject
            val data = parsed["data"]?.jsonObject ?: throw RuntimeException("No data in response")

            ai.ciris.mobile.shared.models.ProviderDeleteResponse(
                success = data["success"]?.jsonPrimitive?.boolean ?: false,
                providerName = data["provider_name"]?.jsonPrimitive?.content ?: providerName,
                message = data["message"]?.jsonPrimitive?.content ?: ""
            )
        } catch (e: Exception) {
            logException(method, e, "url=$url")
            throw e
        }
    }


    /**
     * Add a new LLM provider to the bus at runtime.
     *
     * @param providerId Provider type: "openai", "anthropic", "local", etc.
     * @param baseUrl Base URL for the provider API
     * @param name Optional display name (auto-generated if not provided)
     * @param model Optional default model to use
     * @param apiKey Optional API key (empty for local servers)
     * @param priority Provider priority level
     */
    suspend fun addLlmProvider(
        providerId: String,
        providerBaseUrl: String,
        name: String? = null,
        model: String? = null,
        apiKey: String? = null,
        priority: ai.ciris.mobile.shared.models.ProviderPriority = ai.ciris.mobile.shared.models.ProviderPriority.FALLBACK
    ): ai.ciris.mobile.shared.models.AddProviderResponse {
        val method = "addLlmProvider"
        val url = "$baseUrl/v1/system/llm/providers"
        logInfo(method, "POST $url (provider=$providerId, priority=${priority.name})")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = 15000
                    connectTimeoutMillis = 5000
                }
            }

            val requestBody = buildJsonObject {
                put("provider_id", providerId)
                put("base_url", providerBaseUrl)
                name?.let { put("name", it) }
                model?.let { put("model", it) }
                // Always include api_key - use "local" for local providers if not specified
                put("api_key", apiKey ?: "local")
                put("priority", priority.name.lowercase())
                put("enabled", true)
            }

            val response = client.post(url) {
                authHeader()?.let { header("Authorization", it) }
                contentType(ContentType.Application.Json)
                setBody(requestBody.toString())
            }

            if (!response.status.isSuccess()) {
                client.close()
                // READ THE REASON THE SERVER SENT (CIRISAgent#1065).
                //
                // This threw the bare status, so a user adding Groq saw
                // "400 failed request" and had nothing to act on — while the
                // server was returning a `detail` naming the exact conflict.
                val detail = try {
                    val err = Json.parseToJsonElement(response.bodyAsText()).jsonObject
                    (err["detail"] ?: err["error"])?.jsonPrimitive?.contentOrNull
                } catch (_: Exception) {
                    null
                }
                throw RuntimeException(detail ?: "Add provider failed: ${response.status}")
            }

            val body = response.bodyAsText()
            client.close()
            logDebug(method, "Response body: $body")

            val json = Json { ignoreUnknownKeys = true }
            val parsed = json.parseToJsonElement(body).jsonObject
            val data = parsed["data"]?.jsonObject ?: throw RuntimeException("No data in response")

            val priorityStr = data["priority"]?.jsonPrimitive?.content ?: "fallback"
            val resultPriority = when (priorityStr.lowercase()) {
                "critical" -> ai.ciris.mobile.shared.models.ProviderPriority.CRITICAL
                "high" -> ai.ciris.mobile.shared.models.ProviderPriority.HIGH
                "normal" -> ai.ciris.mobile.shared.models.ProviderPriority.NORMAL
                "low" -> ai.ciris.mobile.shared.models.ProviderPriority.LOW
                else -> ai.ciris.mobile.shared.models.ProviderPriority.FALLBACK
            }

            ai.ciris.mobile.shared.models.AddProviderResponse(
                success = data["success"]?.jsonPrimitive?.boolean ?: false,
                providerName = data["provider_name"]?.jsonPrimitive?.content ?: "",
                providerId = data["provider_id"]?.jsonPrimitive?.content ?: providerId,
                baseUrl = data["base_url"]?.jsonPrimitive?.content ?: providerBaseUrl,
                priority = resultPriority,
                message = data["message"]?.jsonPrimitive?.content ?: ""
            )
        } catch (e: Exception) {
            logException(method, e, "providerId=$providerId, baseUrl=$providerBaseUrl")
            throw e
        }
    }

    /**
     * Disable CIRIS services (switch to BYOK mode).
     * Calls the dedicated API endpoint that:
     * - Sets CIRIS_SERVICES_DISABLED=true in .env (persists across restarts)
     * - Unregisters CIRIS providers from memory (immediate effect)
     * - Disables CIRIS hosted tools
     */
    suspend fun disableCirisServices(): ai.ciris.mobile.shared.models.SimpleResponse {
        val method = "disableCirisServices"
        val url = "$baseUrl/v1/system/llm/ciris-services/disable"
        logInfo(method, "POST $url")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = 10000
                    connectTimeoutMillis = 5000
                }
            }

            val response = client.post(url) {
                contentType(ContentType.Application.Json)
                accessToken?.let { bearerAuth(it) }
            }

            val responseBody = response.bodyAsText()
            logInfo(method, "Response ${response.status}: $responseBody")

            if (response.status.isSuccess()) {
                // Parse response to get message
                val jsonResponse = Json.parseToJsonElement(responseBody).jsonObject
                val data = jsonResponse["data"]?.jsonObject
                val disabled = data?.get("disabled")?.jsonPrimitive?.boolean ?: true
                val message = data?.get("message")?.jsonPrimitive?.contentOrNull
                    ?: "CIRIS services disabled"

                ai.ciris.mobile.shared.models.SimpleResponse(
                    success = disabled,
                    message = message
                )
            } else {
                logError(method, "Failed: ${response.status}")
                ai.ciris.mobile.shared.models.SimpleResponse(
                    success = false,
                    message = "Failed to disable CIRIS services: ${response.status}"
                )
            }
        } catch (e: Exception) {
            logException(method, e, "disabling CIRIS services")
            ai.ciris.mobile.shared.models.SimpleResponse(
                success = false,
                message = e.message ?: "Unknown error"
            )
        }
    }

    /**
     * Get CIRIS services status (whether they are disabled or enabled).
     * Returns true if services are ENABLED (not disabled).
     */
    suspend fun getCirisServicesStatus(): Boolean {
        val method = "getCirisServicesStatus"
        val url = "$baseUrl/v1/system/llm/ciris-services/status"
        logInfo(method, "GET $url")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = 10000
                    connectTimeoutMillis = 5000
                }
            }

            val response = client.get(url) {
                accessToken?.let { bearerAuth(it) }
            }

            val responseBody = response.bodyAsText()
            logInfo(method, "Response ${response.status}: $responseBody")
            client.close()

            if (response.status.isSuccess()) {
                // Parse response - disabled=true means services are OFF
                val jsonResponse = Json.parseToJsonElement(responseBody).jsonObject
                val data = jsonResponse["data"]?.jsonObject
                val disabled = data?.get("disabled")?.jsonPrimitive?.boolean ?: false
                // Return true if ENABLED (not disabled)
                !disabled
            } else {
                logWarn(method, "Failed to get status: ${response.status}, assuming enabled")
                true // Default to enabled if we can't get status
            }
        } catch (e: Exception) {
            logException(method, e, "getting CIRIS services status")
            true // Default to enabled on error
        }
    }

    /**
     * Delete a provider by name.
     */
    suspend fun deleteProvider(name: String) {
        val method = "deleteProvider"
        val url = "$baseUrl/v1/system/llm/providers/$name"
        logInfo(method, "DELETE $url")

        val client = HttpClient {
            install(ContentNegotiation) {
                json(Json {
                    ignoreUnknownKeys = true
                    isLenient = true
                })
            }
            install(HttpTimeout) {
                requestTimeoutMillis = 10000
                connectTimeoutMillis = 5000
            }
        }

        val response = client.delete(url) {
            authHeader()?.let { header("Authorization", it) }
        }

        client.close()

        if (response.status.value !in 200..299) {
            val body = response.bodyAsText()
            throw RuntimeException("Failed to delete provider: ${response.status.value} - $body")
        }
    }

    // ===== Audit API =====

        /**
         * Get audit entries with optional filtering.
         */
        suspend fun getAuditEntries(
            severity: String? = null,
            outcome: String? = null,
            actor: String? = null,
            eventType: String? = null,
            limit: Int = 100,
            offset: Int = 0
        ): AuditEntriesData {
            val method = "getAuditEntries"
            // AGENT-only: the agent audit feed is 404 on a bare node.
            if (nodeSkip(method)) return AuditEntriesData(
                entries = emptyList(),
                total = 0,
                offset = offset,
                limit = limit,
            )
            logDebug(method, "Fetching audit entries: severity=$severity, outcome=$outcome, limit=$limit, offset=$offset")

            return try {
                val response = auditApi.queryAuditEntriesV1AuditEntriesGet(
                    startTime = null,
                    endTime = null,
                    actor = actor,
                    eventType = eventType,
                    entityId = null,
                    search = null,
                    severity = severity,
                    outcome = outcome,
                    limit = limit,
                    offset = offset,
                    authorization = authHeader()
                )
                logDebug(method, "Response: status=${response.status}")

                if (!response.success) {
                    logError(method, "API returned non-success status: ${response.status}")
                    throw RuntimeException("API error: HTTP ${response.status}")
                }

                val body = response.body()
                val data = body.`data` ?: throw RuntimeException("API returned null data")
                logDebug(method, "Fetched ${data.propertyEntries.size} audit entries, total=${data.total}")

                AuditEntriesData(
                    entries = data.propertyEntries.map { entry ->
                        // Debug: Log raw entry context for audit troubleshooting
                        val ctx = entry.context
                        logDebug(method, "Entry ${entry.id}: action=${entry.action}, " +
                            "ctx.outcome=${ctx.outcome}, ctx.result=${ctx.result}, ctx.error=${ctx.error}")

                        // Use outcome from API response (preferred), fall back to inference
                        val finalOutcome = ctx.outcome ?: ctx.result?.let { result ->
                            when {
                                result.contains("success", ignoreCase = true) -> "success"
                                result.contains("fail", ignoreCase = true) -> "failure"
                                result.contains("error", ignoreCase = true) -> "failure"
                                else -> result
                            }
                        } ?: if (ctx.error != null) "failure" else null

                        logDebug(method, "Entry ${entry.id}: finalOutcome=$finalOutcome")

                        AuditEntryApiData(
                            id = entry.id,
                            action = entry.action,
                            actor = entry.actor,
                            timestamp = entry.timestamp ?: "",
                            context = AuditContextApiData(
                                entityId = ctx.entityId,
                                entityType = ctx.entityType,
                                operation = ctx.operation,
                                description = ctx.description,
                                requestId = ctx.requestId,
                                correlationId = ctx.correlationId,
                                userId = ctx.userId,
                                ipAddress = ctx.ipAddress,
                                userAgent = ctx.userAgent,
                                result = ctx.result,
                                error = ctx.error,
                                outcome = finalOutcome,
                                // Parse metadata (contains tool parameters, etc.)
                                metadata = try {
                                    ctx.metadata?.let { meta ->
                                        kotlinx.serialization.json.buildJsonObject {
                                            (meta as? Map<*, *>)?.forEach { (key, value) ->
                                                if (key is String && value != null) {
                                                    put(key, kotlinx.serialization.json.JsonPrimitive(value.toString()))
                                                }
                                            }
                                        }
                                    }
                                } catch (e: Exception) {
                                    null // Fallback if metadata parsing fails
                                }
                            ),
                            signature = entry.signature,
                            hashChain = entry.hashChain,
                            storageSources = entry.storageSources
                        )
                    },
                    total = data.total,
                    offset = data.offset ?: 0,
                    limit = data.limit ?: 100
                )
            } catch (e: Exception) {
                logException(method, e)
                throw e
            }
        }

    // ===== Logs API (via Telemetry) =====

        /**
         * Get system logs with optional filtering.
         */
        suspend fun getSystemLogs(
            level: String? = null,
            service: String? = null,
            limit: Int = 100
        ): SystemLogsData {
            val method = "getSystemLogs"
            logInfo(method, "Fetching system logs: level=$level, service=$service, limit=$limit")

            return try {
                val response = telemetryApi.getSystemLogsV1TelemetryLogsGet(
                    startTime = null,
                    endTime = null,
                    level = level,
                    service = service,
                    limit = limit,
                    authorization = authHeader()
                )
                logDebug(method, "Response: status=${response.status}")

                if (!response.success) {
                    logError(method, "API returned non-success status: ${response.status}")
                    throw RuntimeException("API error: HTTP ${response.status}")
                }

                val body = response.body()
                val data = body.`data` ?: throw RuntimeException("API returned null data")
                logInfo(method, "Fetched ${data.logs.size} logs, total=${data.total}")

                SystemLogsData(
                    logs = data.logs.map { log ->
                        SystemLogApiData(
                            timestamp = log.timestamp ?: "",
                            level = log.level,
                            service = log.service,
                            message = log.message,
                            context = log.context?.let { ctx ->
                                mapOf(
                                    "traceId" to (ctx.traceId ?: ""),
                                    "userId" to (ctx.userId ?: ""),
                                    "entityId" to (ctx.entityId ?: "")
                                ).filterValues { v -> v.isNotEmpty() }
                            },
                            traceId = log.traceId
                        )
                    },
                    total = data.total,
                    hasMore = data.hasMore ?: false
                )
            } catch (e: Exception) {
                logException(method, e)
                throw e
            }
        }

    // ===== Memory API =====

        /**
         * Get memory statistics.
         */
        suspend fun getMemoryStats(): MemoryStatsApiData {
            val method = "getMemoryStats"
            logInfo(method, "Fetching memory stats")

            return try {
                val response = memoryApi.getStatsV1MemoryStatsGet(authHeader())
                logDebug(method, "Response: status=${response.status}")

                if (!response.success) {
                    logError(method, "API returned non-success status: ${response.status}")
                    throw RuntimeException("API error: HTTP ${response.status}")
                }

                val body = response.body()
                val data = body.`data` ?: throw RuntimeException("API returned null data")
                logInfo(method, "Memory stats: totalNodes=${data.totalNodes}, recent24h=${data.recentNodes24h}")

                MemoryStatsApiData(
                    totalNodes = data.totalNodes,
                    nodesByType = data.nodesByType,
                    nodesByScope = data.nodesByScope,
                    recentNodes24h = data.recentNodes24h,
                    oldestNodeDate = data.oldestNodeDate,
                    newestNodeDate = data.newestNodeDate
                )
            } catch (e: Exception) {
                logException(method, e)
                throw e
            }
        }

        /**
         * Get memory timeline nodes.
         */
        suspend fun getMemoryTimeline(
            hours: Int = 24,
            scope: String? = null,
            nodeType: String? = null
        ): List<ai.ciris.mobile.shared.ui.screens.MemoryNodeData> {
            val method = "getMemoryTimeline"
            logInfo(method, "Fetching memory timeline: hours=$hours, scope=$scope, type=$nodeType")

            return try {
                val response = memoryApi.getTimelineV1MemoryTimelineGet(
                    hours = hours,
                    scope = scope,
                    type = nodeType,
                    authorization = authHeader()
                )
                logDebug(method, "Response: status=${response.status}")

                if (!response.success) {
                    logError(method, "API returned non-success status: ${response.status}")
                    throw RuntimeException("API error: HTTP ${response.status}")
                }

                val body = response.body()
                val data = body.`data` ?: throw RuntimeException("API returned null data")
                logInfo(method, "Fetched timeline with ${data.memories.size} memories")

                data.memories.map { node ->
                    ai.ciris.mobile.shared.ui.screens.MemoryNodeData(
                        id = node.id,
                        type = node.type.value,
                        scope = node.scope.value,
                        contentPreview = (node.attributes.content ?: "").take(200),
                        attributesJson = buildString {
                            appendLine("content: ${(node.attributes.content ?: "").take(500)}")
                            appendLine("description: ${node.attributes.description}")
                            appendLine("source: ${node.attributes.source}")
                            node.attributes.confidence?.let { c -> appendLine("confidence: $c") }
                        },
                        createdAt = node.updatedAt?.toString(),
                        updatedAt = node.updatedAt?.toString()
                    )
                }
            } catch (e: Exception) {
                logException(method, e)
                throw e
            }
        }

        /**
         * Query memory nodes by search text.
         */
        suspend fun queryMemory(
            query: String,
            scope: String? = null,
            nodeType: String? = null,
            limit: Int = 50
        ): List<ai.ciris.mobile.shared.ui.screens.MemoryNodeData> {
            val method = "queryMemory"
            logInfo(method, "Querying memory: query='$query', scope=$scope, type=$nodeType, limit=$limit")

            return try {
                val request = ai.ciris.api.models.QueryRequest(
                    query = query,
                    scope = scope?.let { ai.ciris.api.models.GraphScope.valueOf(it.uppercase()) },
                    type = nodeType?.let { ai.ciris.api.models.NodeType.valueOf(it.uppercase()) },
                    limit = limit
                )
                val response = memoryApi.queryMemoryV1MemoryQueryPost(request, authHeader())
                logDebug(method, "Response: status=${response.status}")

                if (!response.success) {
                    logError(method, "API returned non-success status: ${response.status}")
                    throw RuntimeException("API error: HTTP ${response.status}")
                }

                val body = response.body()
                val data = body.`data` ?: throw RuntimeException("API returned null data")
                logInfo(method, "Query returned ${data.size} nodes")

                data.map { node ->
                    ai.ciris.mobile.shared.ui.screens.MemoryNodeData(
                        id = node.id,
                        type = node.type.value,
                        scope = node.scope.value,
                        contentPreview = (node.attributes.content ?: "").take(200),
                        attributesJson = buildString {
                            appendLine("content: ${(node.attributes.content ?: "").take(500)}")
                            appendLine("description: ${node.attributes.description}")
                            appendLine("source: ${node.attributes.source}")
                            node.attributes.confidence?.let { c -> appendLine("confidence: $c") }
                        },
                        createdAt = node.updatedAt?.toString(),
                        updatedAt = node.updatedAt?.toString()
                    )
                }
            } catch (e: Exception) {
                logException(method, e)
                throw e
            }
        }

        /**
         * Get a specific memory node by ID.
         */
        suspend fun getMemoryNode(nodeId: String): ai.ciris.mobile.shared.ui.screens.MemoryNodeData {
            val method = "getMemoryNode"
            logInfo(method, "Fetching memory node: $nodeId")

            return try {
                val response = memoryApi.getNodeV1MemoryNodeIdGet(nodeId, authHeader())
                logDebug(method, "Response: status=${response.status}")

                if (!response.success) {
                    logError(method, "API returned non-success status: ${response.status}")
                    throw RuntimeException("API error: HTTP ${response.status}")
                }

                val body = response.body()
                val node = body.`data` ?: throw RuntimeException("API returned null data")
                logInfo(method, "Fetched node: id=${node.id}, type=${node.type}")

                ai.ciris.mobile.shared.ui.screens.MemoryNodeData(
                    id = node.id,
                    type = node.type.value,
                    scope = node.scope.value,
                    contentPreview = (node.attributes.content ?: "").take(200),
                    attributesJson = buildString {
                        appendLine("content: ${node.attributes.content ?: ""}")
                        appendLine("description: ${node.attributes.description}")
                        appendLine("source: ${node.attributes.source}")
                        node.attributes.confidence?.let { c -> appendLine("confidence: $c") }
                        node.attributes.category.let { cat -> appendLine("category: $cat") }
                    },
                    createdAt = node.updatedAt?.toString(),
                    updatedAt = node.updatedAt?.toString()
                )
            } catch (e: Exception) {
                logException(method, e)
                throw e
            }
        }

        /**
         * Get edges connected to a specific memory node.
         * Returns both incoming and outgoing edges.
         */
        suspend fun getNodeEdges(nodeId: String): List<ai.ciris.api.models.GraphEdge> {
            val method = "getNodeEdges"
            logInfo(method, "Fetching edges for node: $nodeId")

            return try {
                val response = memoryApi.getNodeEdgesV1MemoryNodeIdEdgesGet(nodeId, authHeader())
                logDebug(method, "Response: status=${response.status}")

                if (!response.success) {
                    logError(method, "API returned non-success status: ${response.status}")
                    throw RuntimeException("API error: HTTP ${response.status}")
                }

                val body = response.body()
                val edges = body.`data` ?: emptyList()
                logInfo(method, "Fetched ${edges.size} edges for node $nodeId")

                edges
            } catch (e: Exception) {
                logException(method, e)
                throw e
            }
        }

        /**
         * Get graph data for visualization: nodes and their edges.
         * Fetches timeline nodes and then gets edges for all of them.
         */
        suspend fun getGraphData(
            hours: Int = 24,
            scope: String? = null,  // null = ALL SCOPES (multi-scope cylinder)
            nodeType: String? = null,
            limit: Int = 1000,
            includeMetrics: Boolean = false  // Exclude telemetry by default for performance
        ): GraphDataResponse {
            val method = "getGraphData"
            val totalStart = kotlinx.datetime.Clock.System.now().toEpochMilliseconds()
            logInfo(method, ">>> START: hours=$hours, scope=${scope ?: "ALL_SCOPES"}, type=$nodeType, limit=$limit")

            return try {
                // Single API call - timeline now includes edges!
                // Note: include_metrics=true to get all nodes including telemetry
                val timelineStart = kotlinx.datetime.Clock.System.now().toEpochMilliseconds()
                val timelineUrl = buildString {
                    append("$baseUrl/v1/memory/timeline?hours=$hours&include_edges=true&include_metrics=$includeMetrics")
                    scope?.let { append("&scope=$it") }
                    nodeType?.let { append("&type=$it") }
                }
                logInfo(method, "Fetching timeline: $timelineUrl")

                val client = HttpClient {
                    httpClientConfig(this)
                }
                val timelineResponse: io.ktor.client.statement.HttpResponse = client.get(timelineUrl) {
                    headers {
                        append("Authorization", authHeader() ?: "")
                    }
                }
                client.close()
                val timelineMs = kotlinx.datetime.Clock.System.now().toEpochMilliseconds() - timelineStart

                if (!timelineResponse.status.isSuccess()) {
                    logError(method, "API returned non-success status: ${timelineResponse.status}")
                    throw RuntimeException("API error: HTTP ${timelineResponse.status}")
                }

                val timelineBody: ai.ciris.api.models.SuccessResponseTimelineResponse = timelineResponse.body()
                val timelineData = timelineBody.`data` ?: throw RuntimeException("API returned null data")
                val nodes = timelineData.memories.take(limit)

                // Edges now included in timeline response (batch fetched on server)
                val edges = timelineData.edges
                val nodeIds = nodes.map { it.id }.toSet()

                // Filter edges to only include those between visible nodes
                val visibleEdges = edges.filter { edge ->
                    nodeIds.contains(edge.source) && nodeIds.contains(edge.target)
                }

                val totalMs = kotlinx.datetime.Clock.System.now().toEpochMilliseconds() - totalStart
                logInfo(method, "<<< DONE in ${totalMs}ms (single API call)")
                logInfo(method, "    Nodes: ${nodes.size} (${nodes.groupBy { it.scope }.mapValues { it.value.size }})")
                logInfo(method, "    Edges: ${edges.size} total, ${visibleEdges.size} visible")
                logInfo(method, "    Edge types: ${edges.groupBy { it.relationship }.mapValues { it.value.size }}")

                if (visibleEdges.isEmpty() && edges.isEmpty()) {
                    logInfo(method, "    INFO: No edges found - nodes may not have relationships yet")
                }

                GraphDataResponse(
                    nodes = nodes,
                    edges = visibleEdges
                )
            } catch (e: Exception) {
                logException(method, e)
                throw e
            }
        }

    // ===== Services API =====

    override suspend fun getServices(): ServicesResponse {
    val method = "getServices"
        logInfo(method, "Fetching services status")

        return try {
            val response = systemApi.getServicesStatusV1SystemServicesGet(authHeader())
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")

            // Group services by type into global services map
            // The API returns a flat list of ServiceStatus objects
            val globalServices = mutableMapOf<String, List<ServiceProviderData>>()
            data.services.groupBy { it.type }.forEach { (serviceType, services) ->
                globalServices[serviceType] = services.map { service ->
                    ServiceProviderData(
                        name = service.name,
                        priority = "NORMAL",
                        priorityGroup = 0,
                        strategy = "FALLBACK",
                        circuitBreakerState = if (service.healthy) "closed" else "open",
                        capabilities = emptyList()
                    )
                }
            }

            logInfo(method, "Services fetched: ${data.totalServices} total, ${data.healthyServices} healthy")

            ServicesResponse(
                globalServices = globalServices,
                handlers = emptyMap() // Handler-specific services not in current API
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    // ===== Environment API =====

    override suspend fun getContextEnrichment(): ContextEnrichmentResponse {
        val method = "getContextEnrichment"
        logInfo(method, "Fetching context enrichment cache")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json { ignoreUnknownKeys = true; isLenient = true })
                }
            }

            val response = client.get("$baseUrl/v1/system/adapters/context-enrichment?refresh=true") {
                header("Authorization", "Bearer $accessToken")
            }

            if (response.status != HttpStatusCode.OK) {
                logError(method, "API returned non-success status: ${response.status}")
                client.close()
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val jsonString = response.bodyAsText()
            client.close()

            val json = Json.parseToJsonElement(jsonString).jsonObject
            val data = json["data"]?.jsonObject ?: throw RuntimeException("API returned null data")

            // Parse entries
            val entriesObj = data["entries"]?.jsonObject ?: JsonObject(emptyMap())
            val entries = mutableMapOf<String, Any>()
            for ((key, value) in entriesObj) {
                entries[key] = when {
                    value is JsonObject -> value.toString()
                    value is JsonArray -> value.toString()
                    value.jsonPrimitive.isString -> value.jsonPrimitive.content
                    else -> value.toString()
                }
            }

            // Parse stats
            val statsObj = data["stats"]?.jsonObject
            val stats = EnrichmentCacheStatsData(
                entries = statsObj?.get("entry_count")?.jsonPrimitive?.int ?: 0,
                hits = statsObj?.get("hits")?.jsonPrimitive?.int ?: 0,
                misses = statsObj?.get("misses")?.jsonPrimitive?.int ?: 0,
                hitRatePct = statsObj?.get("hit_rate_pct")?.jsonPrimitive?.double ?: 0.0,
                startupPopulated = statsObj?.get("startup_populated")?.jsonPrimitive?.boolean ?: false
            )

            logInfo(method, "Context enrichment fetched: ${entries.size} entries, hitRate=${stats.hitRatePct}%")
            ContextEnrichmentResponse(entries = entries, stats = stats)
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    override suspend fun queryEnvironmentItems(): List<EnvironmentGraphNodeData> {
        val method = "queryEnvironmentItems"
        logInfo(method, "Querying environment items")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json { ignoreUnknownKeys = true; isLenient = true })
                }
            }

            val response = client.post("$baseUrl/v1/memory/query") {
                header("Authorization", "Bearer $accessToken")
                contentType(ContentType.Application.Json)
                setBody(buildJsonObject {
                    put("scope", "environment")  // GraphScope enum values are lowercase
                    put("limit", 100)
                })
            }

            if (response.status != HttpStatusCode.OK) {
                logError(method, "API returned non-success status: ${response.status}")
                client.close()
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val jsonString = response.bodyAsText()
            client.close()

            val json = Json.parseToJsonElement(jsonString).jsonObject
            val dataArray = json["data"]?.jsonArray ?: JsonArray(emptyList())

            val items = dataArray.mapNotNull { element ->
                val nodeObj = element.jsonObject
                try {
                    val attrsObj = nodeObj["attributes"]?.jsonObject ?: JsonObject(emptyMap())
                    val attributes = mutableMapOf<String, Any>()
                    for ((k, v) in attrsObj) {
                        attributes[k] = when {
                            v is JsonObject -> v.toString()
                            v is JsonArray -> v.toString()
                            v.jsonPrimitive.isString -> v.jsonPrimitive.content
                            v.jsonPrimitive.intOrNull != null -> v.jsonPrimitive.int
                            v.jsonPrimitive.doubleOrNull != null -> v.jsonPrimitive.double
                            else -> v.toString()
                        }
                    }
                    EnvironmentGraphNodeData(
                        id = nodeObj["id"]?.jsonPrimitive?.content ?: "",
                        type = nodeObj["type"]?.jsonPrimitive?.content ?: "OBJECT",
                        attributes = attributes,
                        createdAt = nodeObj["updated_at"]?.jsonPrimitive?.contentOrNull,
                        communityShared = false
                    )
                } catch (e: Exception) {
                    logWarn(method, "Failed to parse item: ${e.message}")
                    null
                }
            }

            logInfo(method, "Fetched ${items.size} environment items")
            items
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    override suspend fun createEnvironmentItem(
        name: String,
        category: String,
        quantity: Int,
        condition: String,
        notes: String?
    ): EnvironmentGraphNodeData {
        val method = "createEnvironmentItem"
        logInfo(method, "Creating environment item: $name")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json { ignoreUnknownKeys = true; isLenient = true })
                }
            }

            val nodeId = "item_${kotlinx.datetime.Clock.System.now().toEpochMilliseconds()}"
            val attributes = buildJsonObject {
                put("name", name)
                put("category", category)
                put("quantity", quantity)
                put("condition", condition)
                notes?.let { put("notes", it) }
            }

            val response = client.post("$baseUrl/v1/memory/store") {
                header("Authorization", "Bearer $accessToken")
                contentType(ContentType.Application.Json)
                setBody(buildJsonObject {
                    put("node", buildJsonObject {
                        put("id", nodeId)
                        put("type", "concept")  // NodeType.CONCEPT for environment items
                        put("scope", "environment")  // GraphScope.ENVIRONMENT
                        put("attributes", attributes)
                    })
                })
            }

            if (response.status != HttpStatusCode.OK) {
                logError(method, "API returned non-success status: ${response.status}")
                client.close()
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            client.close()
            logInfo(method, "Created environment item: $nodeId")

            EnvironmentGraphNodeData(
                id = nodeId,
                type = "CONCEPT",
                attributes = mapOf(
                    "name" to name,
                    "category" to category,
                    "quantity" to quantity,
                    "condition" to condition
                ).let { if (notes != null) it + ("notes" to notes) else it },
                createdAt = null,
                communityShared = false
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    override suspend fun deleteEnvironmentItem(nodeId: String): Boolean {
        val method = "deleteEnvironmentItem"
        logInfo(method, "Deleting environment item: $nodeId")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json { ignoreUnknownKeys = true; isLenient = true })
                }
            }

            // Pass scope=environment to delete from correct graph scope
            val response = client.delete("$baseUrl/v1/memory/$nodeId?scope=environment") {
                header("Authorization", "Bearer $accessToken")
            }

            client.close()

            if (response.status == HttpStatusCode.OK) {
                logInfo(method, "Deleted environment item: $nodeId")
                true
            } else {
                logError(method, "Failed to delete: ${response.status}")
                false
            }
        } catch (e: Exception) {
            logException(method, e)
            false
        }
    }

    // ===== Runtime Control API =====

    override suspend fun getRuntimeState(): RuntimeStateResponse {
        val method = "getRuntimeState"
        logDebug(method, "Fetching runtime state via 'state' action")

        return try {
            val request = ai.ciris.api.models.RuntimeAction(reason = null)
            val response = systemApi.controlRuntimeV1SystemRuntimeActionPost(
                action = "state",
                runtimeAction = request,
                authorization = authHeader()
            )
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")

            logInfo(method, "Runtime state: processorState=${data.processorState}, " +
                    "cognitiveState=${data.cognitiveState}, queueDepth=${data.queueDepth}")

            RuntimeStateResponse(
                processorState = data.processorState,
                cognitiveState = data.cognitiveState ?: "WORK",
                queueDepth = data.queueDepth ?: 0,
                activeTasks = emptyList() // Active tasks not in current API response
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    override suspend fun pauseRuntime(): RuntimeControlResponse {
        val method = "pauseRuntime"
        logInfo(method, "Pausing runtime")

        return try {
            val request = ai.ciris.api.models.RuntimeAction(reason = "Mobile app pause request")
            val response = systemApi.controlRuntimeV1SystemRuntimeActionPost(
                action = "pause",
                runtimeAction = request,
                authorization = authHeader()
            )
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")

            logInfo(method, "Runtime paused: processorState=${data.processorState}")

            RuntimeControlResponse(
                processorState = data.processorState,
                message = data.message
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    override suspend fun resumeRuntime(): RuntimeControlResponse {
        val method = "resumeRuntime"
        logInfo(method, "Resuming runtime")

        return try {
            val request = ai.ciris.api.models.RuntimeAction(reason = "Mobile app resume request")
            val response = systemApi.controlRuntimeV1SystemRuntimeActionPost(
                action = "resume",
                runtimeAction = request,
                authorization = authHeader()
            )
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")

            logInfo(method, "Runtime resumed: processorState=${data.processorState}")

            RuntimeControlResponse(
                processorState = data.processorState,
                message = data.message
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    override suspend fun singleStepProcessor(): SingleStepResponse {
        val method = "singleStepProcessor"
        logInfo(method, "Executing single step")

        return try {
            // Single step uses 'step' action
            val request = ai.ciris.api.models.RuntimeAction(reason = "Mobile app single step")
            val response = systemApi.controlRuntimeV1SystemRuntimeActionPost(
                action = "step",
                runtimeAction = request,
                authorization = authHeader()
            )
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")

            logInfo(method, "Single step completed: currentStep=${data.currentStep}, message=${data.message}")

            SingleStepResponse(
                stepPoint = data.currentStep,
                message = data.message,
                processingTimeMs = null, // Not in API response
                tokensUsed = null // Not in API response
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    // ===== Users API =====

    /**
     * List users with optional filtering and pagination.
     */
    suspend fun listUsers(
        page: Int = 1,
        pageSize: Int = 20,
        search: String? = null,
        authType: String? = null,
        apiRole: ai.ciris.api.models.APIRole? = null,
        waRole: ai.ciris.api.models.WARole? = null,
        isActive: Boolean? = null
    ): ai.ciris.api.models.PaginatedResponseUserSummary {
        val method = "listUsers"
        logInfo(method, "Listing users: page=$page, pageSize=$pageSize, search=$search, authType=$authType, apiRole=$apiRole")

        return try {
            val response = usersApi.listUsersV1UsersGet(
                page = page,
                pageSize = pageSize,
                search = search,
                authType = authType,
                apiRole = apiRole,
                waRole = waRole,
                isActive = isActive,
                authorization = authHeader()
            )
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            logInfo(method, "Users: total=${body.total}, page=${body.page}/${body.pages}")

            body
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * Get a specific user by ID.
     */
    suspend fun getUser(userId: String): ai.ciris.api.models.UserDetail {
        val method = "getUser"
        logInfo(method, "Fetching user: $userId")

        return try {
            val response = usersApi.getUserV1UsersUserIdGet(userId, authHeader())
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            logInfo(method, "User fetched: userId=${body.userId}, username=${body.username}, role=${body.apiRole}")

            body
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    // ===== Tickets API =====

    /**
     * List all tickets with optional filtering.
     */
    suspend fun listTickets(
        sop: String? = null,
        ticketType: String? = null,
        statusFilter: String? = null,
        email: String? = null,
        limit: Int? = 50
    ): List<TicketData> {
        val method = "listTickets"
        logInfo(method, "Listing tickets: sop=$sop, type=$ticketType, status=$statusFilter, limit=$limit")

        return try {
            val response = ticketsApi.listAllTicketsV1TicketsGet(
                sop = sop,
                ticketType = ticketType,
                statusFilter = statusFilter,
                email = email,
                limit = limit
            )
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val tickets = response.body()
            logInfo(method, "Fetched ${tickets.size} tickets")

            tickets.map { ticket ->
                TicketData(
                    ticketId = ticket.ticketId,
                    sop = ticket.sop,
                    ticketType = ticket.ticketType,
                    status = ticket.status,
                    priority = ticket.priority,
                    email = ticket.email,
                    userIdentifier = ticket.userIdentifier,
                    submittedAt = ticket.submittedAt,
                    deadline = ticket.deadline,
                    lastUpdated = ticket.lastUpdated,
                    completedAt = ticket.completedAt,
                    notes = ticket.notes,
                    automated = ticket.automated,
                    metadata = ticket.metadata
                )
            }
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * Get a specific ticket by ID.
     */
    suspend fun getTicket(ticketId: String): TicketData {
        val method = "getTicket"
        logInfo(method, "Fetching ticket: $ticketId")

        return try {
            val response = ticketsApi.getTicketByIdV1TicketsTicketIdGet(ticketId)
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val ticket = response.body()
            logInfo(method, "Ticket fetched: ${ticket.ticketId}, status=${ticket.status}")

            TicketData(
                ticketId = ticket.ticketId,
                sop = ticket.sop,
                ticketType = ticket.ticketType,
                status = ticket.status,
                priority = ticket.priority,
                email = ticket.email,
                userIdentifier = ticket.userIdentifier,
                submittedAt = ticket.submittedAt,
                deadline = ticket.deadline,
                lastUpdated = ticket.lastUpdated,
                completedAt = ticket.completedAt,
                notes = ticket.notes,
                automated = ticket.automated,
                metadata = ticket.metadata
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * Update a ticket's status (and optionally its notes).
     *
     * Used by the HITL approval surface to **promote** an agent proposal
     * (`blocked` → `pending`, which is what actually starts the work) or to
     * refuse it (`blocked` → `cancelled`). Granting a budget does neither —
     * approving money and starting work are separate decisions.
     *
     * @return true on success; false when the server refused (the caller
     *   surfaces a message rather than throwing into a poll loop).
     */
    suspend fun updateTicketStatus(ticketId: String, status: String, notes: String? = null): Boolean {
        val method = "updateTicketStatus"
        logInfo(method, "Updating ticket $ticketId -> status=$status")

        return try {
            val request = ai.ciris.api.models.UpdateTicketRequest(
                status = status,
                notes = notes
            )
            val response = ticketsApi.updateExistingTicketV1TicketsTicketIdPatch(ticketId, request)
            logDebug(method, "Response: status=${response.status}")
            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                return false
            }
            true
        } catch (e: Exception) {
            logException(method, e, "ticketId=$ticketId status=$status")
            false
        }
    }

    /**
     * Issue a human-approved budget envelope against a proposal ticket.
     *
     * `POST /v1/tickets/{ticket_id}/budget/grant` — requires the AUTHORITY role
     * (level 3; ADMIN at level 2 is not sufficient). This is the *issuance
     * event* for the budget envelope described in #938/#939: it is what turns a
     * fail-closed denial into a bounded permission.
     *
     * Issued through a raw Ktor call rather than the generated SDK because the
     * endpoint post-dates the current OpenAPI snapshot. Wire shapes and the
     * status→error mapping live in
     * [ai.ciris.mobile.shared.approvals.BudgetApprovalSeam]; this method only
     * moves bytes.
     */
    suspend fun grantTicketBudget(
        ticketId: String,
        amount: String,
        currency: String,
        purpose: String,
        expiresInHours: Int
    ): ai.ciris.mobile.shared.approvals.BudgetGrantOutcome {
        val method = "grantTicketBudget"
        logInfo(method, "Granting budget on ticket=$ticketId amount=$amount $currency expiry=${expiresInHours}h")

        val client = HttpClient {
            install(ContentNegotiation) {
                json(Json {
                    ignoreUnknownKeys = true
                    isLenient = true
                })
            }
        }

        return try {
            val path = ai.ciris.mobile.shared.approvals.BudgetApprovalSeam.grantPath(ticketId)
            val response = client.post("$baseUrl$path") {
                header("Authorization", "Bearer $accessToken")
                contentType(ContentType.Application.Json)
                setBody(
                    ai.ciris.mobile.shared.approvals.BudgetApprovalSeam.buildGrantBody(
                        amount = amount,
                        currency = currency,
                        purpose = purpose,
                        expiresInHours = expiresInHours
                    )
                )
            }
            val statusCode = response.status.value
            val bodyText = response.bodyAsText()
            logDebug(method, "Response: status=$statusCode")

            if (statusCode !in 200..299) {
                val error = ai.ciris.mobile.shared.approvals.BudgetApprovalSeam
                    .classifyHttpError(statusCode, bodyText)
                logError(method, "Grant refused: status=$statusCode error=$error")
                return ai.ciris.mobile.shared.approvals.BudgetGrantOutcome(
                    ok = false,
                    error = error,
                    message = extractDetail(bodyText)
                )
            }

            val root = Json.parseToJsonElement(bodyText).jsonObject
            val data = root["data"]?.jsonObject ?: root
            val granted = ai.ciris.mobile.shared.approvals.BudgetApprovalSeam.parseGrantResponse(data)
                ?: return ai.ciris.mobile.shared.approvals.BudgetGrantOutcome(
                    ok = false,
                    error = ai.ciris.mobile.shared.approvals.BudgetGrantError.UNKNOWN,
                    message = "Server accepted the grant but returned an unrecognized body"
                )

            logInfo(method, "Budget granted: ${granted.grantedAmount} ${granted.grantedCurrency}, signed=${granted.signed}")
            ai.ciris.mobile.shared.approvals.BudgetGrantOutcome(ok = true, granted = granted)
        } catch (e: Exception) {
            logException(method, e, "ticketId=$ticketId")
            ai.ciris.mobile.shared.approvals.BudgetGrantOutcome(
                ok = false,
                error = ai.ciris.mobile.shared.approvals.BudgetGrantError.UNKNOWN,
                message = e.message
            )
        } finally {
            client.close()
        }
    }

    /**
     * Read the full budget state of a ticket, including remaining trust headroom.
     *
     * `GET /v1/tickets/{ticket_id}/budget` (OBSERVER). The headroom it returns is
     * resolved through the wallet tool service's own `_resolve_trust_envelope` —
     * the same code the spend gate runs — so the figure shown to an operator
     * cannot drift from the figure enforced when money moves. Approving an
     * amount with no view of the remaining envelope is not meaningful consent,
     * which is why this is a separate read rather than an inference from
     * ticket metadata.
     *
     * Returns null when the endpoint is absent or the body is unrecognized; the
     * caller then falls back to what ticket metadata already provided rather
     * than blanking a dialog the operator is reading.
     */
    suspend fun getTicketBudget(
        ticketId: String
    ): ai.ciris.mobile.shared.approvals.TicketBudgetState? {
        val method = "getTicketBudget"
        logInfo(method, "Fetching budget state for ticket=$ticketId")

        val client = HttpClient {
            install(ContentNegotiation) {
                json(Json {
                    ignoreUnknownKeys = true
                    isLenient = true
                })
            }
        }

        return try {
            val path = ai.ciris.mobile.shared.approvals.BudgetApprovalSeam.budgetPath(ticketId)
            val response = client.get("$baseUrl$path") {
                header("Authorization", "Bearer $accessToken")
            }
            val statusCode = response.status.value
            val bodyText = response.bodyAsText()
            logDebug(method, "Response: status=$statusCode")

            if (statusCode !in 200..299) {
                logWarn(method, "Budget state unavailable: status=$statusCode")
                return null
            }

            val root = Json.parseToJsonElement(bodyText).jsonObject
            val data = root["data"]?.jsonObject ?: root
            ai.ciris.mobile.shared.approvals.BudgetApprovalSeam.parseTicketBudgetState(data)
        } catch (e: Exception) {
            // Non-fatal by construction: headroom is an enhancement to the
            // dialog, never a precondition for rendering it.
            logWarn(method, "Failed to fetch budget state for $ticketId: ${e.message}")
            null
        } finally {
            client.close()
        }
    }

    /** Pull FastAPI's `detail` out of an error body, when it is a plain string. */
    private fun extractDetail(body: String?): String? {
        if (body.isNullOrBlank()) return null
        return runCatching {
            Json.parseToJsonElement(body).jsonObject["detail"]?.jsonPrimitive?.contentOrNull
        }.getOrNull()
    }

    /**
     * List supported SOPs for this agent.
     */
    suspend fun listSupportedSops(): List<String> {
        val method = "listSupportedSops"
        logInfo(method, "Listing supported SOPs")

        return try {
            val response = ticketsApi.listSupportedSopsV1TicketsSopsGet()
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val sops = response.body().filterNotNull()
            logInfo(method, "Supported SOPs: $sops")

            sops
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * Get metadata for a specific SOP (stages, required fields, deadline, etc.)
     */
    suspend fun getSopMetadata(sop: String): SOPMetadataData {
        val method = "getSopMetadata"
        logInfo(method, "Fetching SOP metadata for: $sop")

        return try {
            val response = ticketsApi.getSopMetadataV1TicketsSopsSopGet(sop)
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val metadata = response.body()
            val result = SOPMetadataData(
                sop = metadata.sop,
                ticketType = metadata.ticketType,
                requiredFields = metadata.requiredFields,
                deadlineDays = metadata.deadlineDays,
                priorityDefault = metadata.priorityDefault,
                description = metadata.description ?: "",
                stageCount = metadata.stages.size
            )
            logInfo(method, "SOP metadata: $sop, deadline=${result.deadlineDays} days, ${result.stageCount} stages")

            result
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * Create a new ticket with a specific SOP.
     */
    suspend fun createTicket(
        sop: String,
        email: String,
        userIdentifier: String? = null,
        priority: Int? = null,
        notes: String? = null
    ): TicketData {
        val method = "createTicket"
        logInfo(method, "Creating ticket: sop=$sop, email=$email")

        return try {
            val request = ai.ciris.api.models.CreateTicketRequest(
                sop = sop,
                email = email,
                userIdentifier = userIdentifier,
                priority = priority,
                notes = notes
            )

            val response = ticketsApi.createNewTicketV1TicketsPost(request)
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val ticket = response.body()
            val result = TicketData(
                ticketId = ticket.ticketId,
                sop = ticket.sop,
                ticketType = ticket.ticketType ?: "dsar",
                status = ticket.status,
                priority = ticket.priority,
                email = ticket.email,
                userIdentifier = ticket.userIdentifier,
                submittedAt = ticket.submittedAt,
                deadline = ticket.deadline,
                lastUpdated = ticket.lastUpdated,
                completedAt = ticket.completedAt,
                automated = ticket.automated ?: false,
                notes = ticket.notes
            )
            logInfo(method, "Created ticket: ${result.ticketId}")

            result
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * Get ticket statistics summary.
     */
    suspend fun getTicketStats(): TicketStatsData {
        val method = "getTicketStats"
        logInfo(method, "Fetching ticket statistics")

        return try {
            // Fetch all tickets and compute stats
            val allTickets = listTickets(limit = 1000)

            val pending = allTickets.count { it.status == "pending" }
            val inProgress = allTickets.count { it.status == "in_progress" }
            val completed = allTickets.count { it.status == "completed" }
            val failed = allTickets.count { it.status == "failed" || it.status == "cancelled" }
            val urgent = allTickets.count { it.priority >= 8 }

            val stats = TicketStatsData(
                total = allTickets.size,
                pending = pending,
                inProgress = inProgress,
                completed = completed,
                failed = failed,
                urgent = urgent
            )
            logInfo(method, "Ticket stats: total=${stats.total}, pending=$pending, inProgress=$inProgress, completed=$completed")

            stats
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    // ===== Play Integrity (Android Device Attestation) =====

    /**
     * Get a nonce for Play Integrity verification from Python backend.
     * The backend calls CIRISVerify FFI to get the nonce from the registry.
     */
    suspend fun getPlayIntegrityNonce(): PlayIntegrityNonceResult {
        val method = "getPlayIntegrityNonce"
        logInfo(method, "Requesting Play Integrity nonce from Python API")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json { ignoreUnknownKeys = true })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = 30000
                    connectTimeoutMillis = 15000
                    socketTimeoutMillis = 30000
                }
            }

            val response = client.get("$baseUrl/v1/setup/play-integrity/nonce") {
                headers {
                    accessToken?.let { append(HttpHeaders.Authorization, "Bearer $it") }
                }
            }

            client.close()

            if (response.status.isSuccess()) {
                val body = response.bodyAsText()
                logDebug(method, "Response body: $body")

                // Parse response - expect {"data": {"nonce": "..."}}
                val json = Json { ignoreUnknownKeys = true }
                val parsed = json.decodeFromString<PlayIntegrityNonceApiResponse>(body)
                val nonce = parsed.data?.get("nonce")

                if (nonce != null) {
                    logInfo(method, "Got nonce: ${nonce.take(20)}...")
                    PlayIntegrityNonceResult(nonce = nonce)
                } else {
                    logError(method, "No nonce in response")
                    PlayIntegrityNonceResult(error = "No nonce in response")
                }
            } else {
                val errorBody = response.bodyAsText()
                logError(method, "HTTP ${response.status}: $errorBody")
                PlayIntegrityNonceResult(error = "HTTP ${response.status}: $errorBody")
            }
        } catch (e: Exception) {
            logException(method, e)
            PlayIntegrityNonceResult(error = e.message ?: "Unknown error")
        }
    }

    /**
     * Verify a Play Integrity token via Python backend.
     * The backend calls CIRISVerify FFI to verify the token with the registry.
     */
    suspend fun verifyPlayIntegrity(token: String, nonce: String): PlayIntegrityVerifyResult {
        val method = "verifyPlayIntegrity"
        logInfo(method, "Verifying Play Integrity token via Python API")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json { ignoreUnknownKeys = true })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = 45000
                    connectTimeoutMillis = 15000
                    socketTimeoutMillis = 45000
                }
            }

            val response = client.post("$baseUrl/v1/setup/play-integrity/verify") {
                headers {
                    accessToken?.let { append(HttpHeaders.Authorization, "Bearer $it") }
                }
                contentType(ContentType.Application.Json)
                setBody("""{"token": "$token", "nonce": "$nonce"}""")
            }

            client.close()

            if (response.status.isSuccess()) {
                val body = response.bodyAsText()
                logDebug(method, "Response body: $body")

                val json = Json { ignoreUnknownKeys = true }
                val parsed = json.decodeFromString<PlayIntegrityVerifyApiResponse>(body)
                val data = parsed.data

                if (data != null) {
                    logInfo(method, "Verification result: verified=${data.verified}, verdict=${data.verdict}")
                    PlayIntegrityVerifyResult(
                        verified = data.verified,
                        verdict = data.verdict,
                        meetsStrongIntegrity = data.meetsStrongIntegrity,
                        meetsDeviceIntegrity = data.meetsDeviceIntegrity,
                        meetsBasicIntegrity = data.meetsBasicIntegrity
                    )
                } else {
                    logError(method, "No data in response")
                    PlayIntegrityVerifyResult(error = "No data in response")
                }
            } else {
                val errorBody = response.bodyAsText()
                logError(method, "HTTP ${response.status}: $errorBody")
                PlayIntegrityVerifyResult(error = "HTTP ${response.status}: $errorBody")
            }
        } catch (e: Exception) {
            logException(method, e)
            PlayIntegrityVerifyResult(error = e.message ?: "Unknown error")
        }
    }

    /**
     * Report Play Integrity token acquisition failure.
     * Called when Google Play Integrity API fails (e.g., error -16).
     * This allows CIRISVerify to mark device attestation as failed (not pending).
     * Added in CIRISVerify 1.5.3.
     */
    suspend fun reportPlayIntegrityFailed(errorCode: Int, errorMessage: String): Boolean {
        val method = "reportPlayIntegrityFailed"
        logInfo(method, "Reporting Play Integrity failure: code=$errorCode")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json { ignoreUnknownKeys = true })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = 15000
                    connectTimeoutMillis = 10000
                    socketTimeoutMillis = 15000
                }
            }

            // Properly escape error message for JSON (handles newlines, quotes, control chars)
            val escapedMessage = errorMessage
                .replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t")

            val response = client.post("$baseUrl/v1/setup/play-integrity/failed") {
                headers {
                    accessToken?.let { append(HttpHeaders.Authorization, "Bearer $it") }
                }
                contentType(ContentType.Application.Json)
                setBody("""{"error_code": $errorCode, "error_message": "$escapedMessage"}""")
            }

            client.close()

            if (response.status.isSuccess()) {
                logInfo(method, "Successfully reported Play Integrity failure")
                true
            } else {
                val errorBody = response.bodyAsText()
                logError(method, "Failed to report: HTTP ${response.status}: $errorBody")
                false
            }
        } catch (e: Exception) {
            logException(method, e)
            false
        }
    }

    // ===== Scheduler Methods =====

    /**
     * List scheduled tasks.
     */
    suspend fun getScheduledTasks(
        status: String? = null,
        limit: Int = 50
    ): ScheduledTasksListData {
        val method = "getScheduledTasks"
        logInfo(method, "Fetching scheduled tasks (status=$status, limit=$limit)")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json { ignoreUnknownKeys = true })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = 30000
                    connectTimeoutMillis = 15000
                    socketTimeoutMillis = 30000
                }
            }

            val urlBuilder = StringBuilder("$baseUrl/v1/scheduler/tasks?limit=$limit")
            if (status != null) {
                urlBuilder.append("&status=$status")
            }

            val response = client.get(urlBuilder.toString()) {
                headers {
                    accessToken?.let { append(HttpHeaders.Authorization, "Bearer $it") }
                }
            }

            client.close()

            if (response.status.isSuccess()) {
                val body = response.bodyAsText()
                logDebug(method, "Response body: $body")

                val json = Json { ignoreUnknownKeys = true }
                val parsed = json.decodeFromString<ScheduledTasksApiResponse>(body)
                val data = parsed.data

                if (data != null) {
                    logInfo(method, "Fetched ${data.tasks.size} tasks")
                    data
                } else {
                    logWarn(method, "No data in response, returning empty list")
                    ScheduledTasksListData(emptyList(), 0, 0, 0)
                }
            } else {
                val errorBody = response.bodyAsText()
                logError(method, "HTTP ${response.status}: $errorBody")
                throw Exception("Failed to fetch scheduled tasks: HTTP ${response.status}")
            }
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * Get scheduler statistics.
     */
    suspend fun getSchedulerStats(): SchedulerStatsData {
        val method = "getSchedulerStats"
        logInfo(method, "Fetching scheduler stats")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json { ignoreUnknownKeys = true })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = 30000
                    connectTimeoutMillis = 15000
                    socketTimeoutMillis = 30000
                }
            }

            val response = client.get("$baseUrl/v1/scheduler/stats") {
                headers {
                    accessToken?.let { append(HttpHeaders.Authorization, "Bearer $it") }
                }
            }

            client.close()

            if (response.status.isSuccess()) {
                val body = response.bodyAsText()
                logDebug(method, "Response body: $body")

                val json = Json { ignoreUnknownKeys = true }
                val parsed = json.decodeFromString<SchedulerStatsApiResponse>(body)
                val data = parsed.data

                if (data != null) {
                    logInfo(method, "Stats: pending=${data.tasksPending}, completed=${data.tasksCompletedTotal}")
                    data
                } else {
                    logWarn(method, "No data in response, returning defaults")
                    SchedulerStatsData(0, 0, 0, 0, 0, 0, 0.0)
                }
            } else {
                val errorBody = response.bodyAsText()
                logError(method, "HTTP ${response.status}: $errorBody")
                throw Exception("Failed to fetch scheduler stats: HTTP ${response.status}")
            }
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * Create a new scheduled task.
     */
    suspend fun createScheduledTask(
        name: String,
        goalDescription: String,
        triggerPrompt: String,
        deferUntil: String? = null,
        scheduleCron: String? = null
    ): ScheduledTaskData {
        val method = "createScheduledTask"
        logInfo(method, "Creating scheduled task: $name")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json { ignoreUnknownKeys = true })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = 30000
                    connectTimeoutMillis = 15000
                    socketTimeoutMillis = 30000
                }
            }

            val requestBody = buildString {
                append("{")
                append("\"name\":\"${name.replace("\"", "\\\"")}\"")
                append(",\"goal_description\":\"${goalDescription.replace("\"", "\\\"")}\"")
                append(",\"trigger_prompt\":\"${triggerPrompt.replace("\"", "\\\"")}\"")
                if (deferUntil != null) {
                    append(",\"defer_until\":\"$deferUntil\"")
                }
                if (scheduleCron != null) {
                    append(",\"schedule_cron\":\"$scheduleCron\"")
                }
                append("}")
            }

            val response = client.post("$baseUrl/v1/scheduler/tasks") {
                headers {
                    accessToken?.let { append(HttpHeaders.Authorization, "Bearer $it") }
                }
                contentType(ContentType.Application.Json)
                setBody(requestBody)
            }

            client.close()

            if (response.status.isSuccess()) {
                val body = response.bodyAsText()
                logDebug(method, "Response body: $body")

                val json = Json { ignoreUnknownKeys = true }
                val parsed = json.decodeFromString<ScheduledTaskApiResponse>(body)
                val data = parsed.data

                if (data != null) {
                    logInfo(method, "Created task: ${data.taskId}")
                    data
                } else {
                    throw Exception("No task data in response")
                }
            } else {
                val errorBody = response.bodyAsText()
                logError(method, "HTTP ${response.status}: $errorBody")
                throw Exception("Failed to create task: $errorBody")
            }
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * Cancel a scheduled task.
     */
    suspend fun cancelScheduledTask(taskId: String): Boolean {
        val method = "cancelScheduledTask"
        logInfo(method, "Cancelling task: $taskId")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json { ignoreUnknownKeys = true })
                }
                install(HttpTimeout) {
                    requestTimeoutMillis = 30000
                    connectTimeoutMillis = 15000
                    socketTimeoutMillis = 30000
                }
            }

            val response = client.delete("$baseUrl/v1/scheduler/tasks/$taskId") {
                headers {
                    accessToken?.let { append(HttpHeaders.Authorization, "Bearer $it") }
                }
            }

            client.close()

            if (response.status.isSuccess()) {
                logInfo(method, "Task cancelled successfully")
                true
            } else {
                val errorBody = response.bodyAsText()
                logError(method, "HTTP ${response.status}: $errorBody")
                false
            }
        } catch (e: Exception) {
            logException(method, e)
            false
        }
    }

    // ===== Telemetry Export Destinations API =====

    /**
     * Get all telemetry export destinations.
     */
    suspend fun getExportDestinations(): List<ExportDestination> {
        val method = "getExportDestinations"
        logInfo(method, "Fetching export destinations")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = 30000
                connectTimeoutMillis = 10000
            }
        }

        return try {
            val response = client.get("$baseUrl/v1/telemetry/export/destinations") {
                authHeader()?.let { header("Authorization", it) }
            }

            logDebug(method, "Response: status=${response.status}")

            if (!response.status.isSuccess()) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val apiResponse: DestinationsListApiResponse = response.body()
            val data = apiResponse.data ?: throw RuntimeException("API returned null data")
            logInfo(method, "Fetched ${data.total} export destinations")

            data.destinations
        } catch (e: Exception) {
            logException(method, e)
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Get a specific export destination by ID.
     */
    suspend fun getExportDestination(destinationId: String): ExportDestination {
        val method = "getExportDestination"
        logInfo(method, "Fetching export destination: $destinationId")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = 30000
                connectTimeoutMillis = 10000
            }
        }

        return try {
            val response = client.get("$baseUrl/v1/telemetry/export/destinations/$destinationId") {
                authHeader()?.let { header("Authorization", it) }
            }

            logDebug(method, "Response: status=${response.status}")

            if (!response.status.isSuccess()) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val apiResponse: ExportDestinationResponse = response.body()
            apiResponse.data ?: throw RuntimeException("API returned null data")
        } catch (e: Exception) {
            logException(method, e)
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Create a new export destination.
     */
    suspend fun createExportDestination(destination: ExportDestinationCreate): ExportDestination {
        val method = "createExportDestination"
        logInfo(method, "Creating export destination: ${destination.name}")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = 30000
                connectTimeoutMillis = 10000
            }
        }

        return try {
            val response = client.post("$baseUrl/v1/telemetry/export/destinations") {
                authHeader()?.let { header("Authorization", it) }
                contentType(ContentType.Application.Json)
                setBody(destination)
            }

            logDebug(method, "Response: status=${response.status}")

            if (!response.status.isSuccess()) {
                val errorBody = response.bodyAsText()
                logError(method, "API returned non-success status: ${response.status}, body=$errorBody")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val apiResponse: ExportDestinationResponse = response.body()
            val data = apiResponse.data ?: throw RuntimeException("API returned null data")
            logInfo(method, "Created export destination: ${data.id}")

            data
        } catch (e: Exception) {
            logException(method, e)
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Update an existing export destination.
     */
    suspend fun updateExportDestination(destinationId: String, update: ExportDestinationUpdate): ExportDestination {
        val method = "updateExportDestination"
        logInfo(method, "Updating export destination: $destinationId")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = 30000
                connectTimeoutMillis = 10000
            }
        }

        return try {
            val response = client.put("$baseUrl/v1/telemetry/export/destinations/$destinationId") {
                authHeader()?.let { header("Authorization", it) }
                contentType(ContentType.Application.Json)
                setBody(update)
            }

            logDebug(method, "Response: status=${response.status}")

            if (!response.status.isSuccess()) {
                val errorBody = response.bodyAsText()
                logError(method, "API returned non-success status: ${response.status}, body=$errorBody")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val apiResponse: ExportDestinationResponse = response.body()
            val data = apiResponse.data ?: throw RuntimeException("API returned null data")
            logInfo(method, "Updated export destination: ${data.id}")

            data
        } catch (e: Exception) {
            logException(method, e)
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Delete an export destination.
     */
    suspend fun deleteExportDestination(destinationId: String): Boolean {
        val method = "deleteExportDestination"
        logInfo(method, "Deleting export destination: $destinationId")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = 30000
                connectTimeoutMillis = 10000
            }
        }

        return try {
            val response = client.delete("$baseUrl/v1/telemetry/export/destinations/$destinationId") {
                authHeader()?.let { header("Authorization", it) }
            }

            logDebug(method, "Response: status=${response.status}")

            if (!response.status.isSuccess()) {
                val errorBody = response.bodyAsText()
                logError(method, "API returned non-success status: ${response.status}, body=$errorBody")
                return false
            }

            logInfo(method, "Deleted export destination: $destinationId")
            true
        } catch (e: Exception) {
            logException(method, e)
            false
        } finally {
            client.close()
        }
    }

    /**
     * Test connectivity to an export destination.
     */
    suspend fun testExportDestination(destinationId: String): TestResult {
        val method = "testExportDestination"
        logInfo(method, "Testing export destination: $destinationId")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = 30000
                connectTimeoutMillis = 10000
            }
        }

        return try {
            val response = client.post("$baseUrl/v1/telemetry/export/destinations/$destinationId/test") {
                authHeader()?.let { header("Authorization", it) }
            }

            logDebug(method, "Response: status=${response.status}")

            if (!response.status.isSuccess()) {
                val errorBody = response.bodyAsText()
                logError(method, "API returned non-success status: ${response.status}, body=$errorBody")
                return TestResult(
                    success = false,
                    statusCode = response.status.value,
                    message = "API error: HTTP ${response.status}",
                    latencyMs = null
                )
            }

            val apiResponse: TestResultApiResponse = response.body()
            val data = apiResponse.data ?: throw RuntimeException("API returned null data")
            logInfo(method, "Test result: success=${data.success}, message=${data.message}")

            data
        } catch (e: Exception) {
            logException(method, e)
            TestResult(
                success = false,
                statusCode = null,
                message = "Error: ${e.message}",
                latencyMs = null
            )
        } finally {
            client.close()
        }
    }

    // ===== My Data API (DSAR Self-Service) =====

    /**
     * Get lens identifier and accord metrics status.
     * Returns the hashed agent ID used in CIRISLens traces.
     */
    suspend fun getLensIdentifier(): LensIdentifierData {
        val method = "getLensIdentifier"
        logInfo(method, "Fetching lens identifier")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = 15000
                connectTimeoutMillis = 10000
            }
        }

        return try {
            val response = client.get("$baseUrl/v1/my-data/lens-identifier") {
                authHeader()?.let { header("Authorization", it) }
            }

            logDebug(method, "Response: status=${response.status}")

            if (!response.status.isSuccess()) {
                val errorBody = response.bodyAsText()
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status} - $errorBody")
            }

            val apiResponse: MyDataApiResponse = response.body()
            val data = apiResponse.data ?: throw RuntimeException("API returned null data")
            logInfo(method, "Lens identifier fetched: hash=${data.agentIdHash?.take(8)}...")

            LensIdentifierData(
                agentIdHash = data.agentIdHash ?: "",
                agentId = data.agentId ?: "",
                consentGiven = data.consentGiven ?: false,
                consentTimestamp = data.consentTimestamp,
                traceLevel = data.traceLevel,
                tracesSent = data.tracesSent ?: 0,
                endpointUrl = data.endpointUrl
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Request deletion of CIRISLens traces (DSAR Article 17 self-service).
     * This is irreversible - all traces associated with this agent are deleted.
     */
    suspend fun deleteLensTraces(reason: String? = null): LensDeletionResult {
        val method = "deleteLensTraces"
        logInfo(method, "Requesting deletion of lens traces")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = 30000
                connectTimeoutMillis = 10000
            }
        }

        return try {
            val response = client.delete("$baseUrl/v1/my-data/lens-traces") {
                authHeader()?.let { header("Authorization", it) }
                contentType(ContentType.Application.Json)
                setBody(LensDeletionRequest(confirm = true, reason = reason))
            }

            logDebug(method, "Response: status=${response.status}")

            if (!response.status.isSuccess()) {
                val errorBody = response.bodyAsText()
                logError(method, "API returned non-success status: ${response.status}")
                return LensDeletionResult(
                    success = false,
                    agentIdHash = null,
                    status = "error",
                    message = "API error: HTTP ${response.status}",
                    lensRequestAccepted = false,
                    localConsentRevoked = false
                )
            }

            val apiResponse: DeletionApiResponse = response.body()
            val data = apiResponse.data
            logInfo(method, "Deletion result: status=${data?.status}, lensAccepted=${data?.lensRequestAccepted}")

            LensDeletionResult(
                success = apiResponse.success ?: false,
                agentIdHash = data?.agentIdHash,
                status = data?.status ?: "unknown",
                message = data?.message ?: apiResponse.message ?: "Unknown response",
                lensRequestAccepted = data?.lensRequestAccepted ?: false,
                localConsentRevoked = data?.localConsentRevoked ?: false
            )
        } catch (e: Exception) {
            logException(method, e)
            LensDeletionResult(
                success = false,
                agentIdHash = null,
                status = "error",
                message = "Error: ${e.message}",
                lensRequestAccepted = false,
                localConsentRevoked = false
            )
        } finally {
            client.close()
        }
    }

    /**
     * Get current accord metrics settings.
     */
    suspend fun getAccordSettings(): AccordSettingsData {
        val method = "getAccordSettings"
        logInfo(method, "Fetching accord settings")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = 15000
                connectTimeoutMillis = 10000
            }
        }

        return try {
            val response = client.get("$baseUrl/v1/my-data/accord-settings") {
                authHeader()?.let { header("Authorization", it) }
            }

            logDebug(method, "Response: status=${response.status}")

            if (!response.status.isSuccess()) {
                val errorBody = response.bodyAsText()
                logError(method, "API returned non-success status: ${response.status}, body: $errorBody")
                // 404 means adapter not loaded from API's perspective
                if (response.status.value == 404) {
                    logWarn(method, "Accord adapter not found by API - may not be registered with RuntimeAdapterManager")
                }
                throw RuntimeException("API error: HTTP ${response.status} - $errorBody")
            }

            // Log raw response for debugging
            val rawBody = response.bodyAsText()
            logDebug(method, "Raw response body: ${rawBody.take(500)}")

            // Re-parse since we consumed the body
            val apiResponse: AccordSettingsApiResponse = jsonConfig.decodeFromString(rawBody)
            val data = apiResponse.data
            if (data == null) {
                logError(method, "API returned success but data is null. Full response: $rawBody")
                throw RuntimeException("API returned null data")
            }
            logInfo(method, "Accord settings: consent=${data.consentGiven}, level=${data.traceLevel}, " +
                    "eventsSent=${data.eventsSent}, agentIdHash=${data.agentIdHash?.take(8)}...")

            AccordSettingsData(
                agentIdHash = data.agentIdHash ?: "",
                consentGiven = data.consentGiven ?: false,
                consentTimestamp = data.consentTimestamp,
                traceLevel = data.traceLevel,
                endpointUrl = data.endpointUrl,
                eventsSent = data.eventsSent ?: 0,
                eventsReceived = data.eventsReceived ?: 0,
                eventsQueued = data.eventsQueued ?: 0
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        } finally {
            client.close()
        }
    }

    /**
     * Get the CIRIS capacity (ratchet) score for this agent's template.
     *
     * Used by the Interact-screen cell visualization as ambient state —
     * the five CIRIS factor scores drive visual dials (nucleus opacity,
     * bus-arc crispness, breathing steadiness, opening churn, mote warmth).
     *
     * Proxied through the agent backend, which caches for 15 minutes
     * against the enrichment cache. Safe to call on every Interact entry.
     */
    suspend fun getCapacity(): CapacityData {
        val method = "getCapacity"
        logInfo(method, "Fetching CIRIS capacity (scope=both)")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                // Generous timeouts: backend lens call can take 8s, plus
                // Chaquopy async overhead on Android. Socket timeout must
                // match request timeout or Ktor defaults to 10s.
                requestTimeoutMillis = 20000
                connectTimeoutMillis = 10000
                socketTimeoutMillis = 20000
            }
        }

        return try {
            // scope=both returns fleet (composite_score/factors) AND the
            // per-occurrence local_score. Fleet-only clients stay
            // compatible — the backend ignores unknown scope values
            // as a 400, but this known value is always safe.
            val response = client.get("$baseUrl/v1/my-data/capacity?scope=both") {
                authHeader()?.let { header("Authorization", it) }
            }

            if (!response.status.isSuccess()) {
                val errorBody = response.bodyAsText()
                logError(method, "API returned non-success: ${response.status} body=${errorBody.take(200)}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val apiResponse: CapacityApiResponse = response.body()
            val data = apiResponse.data ?: throw RuntimeException("API returned null data")
            val factors = data.factors

            logInfo(method, "Capacity: ${data.agentName} ${data.category} " +
                    "fleet=${data.compositeScore} local=${data.localScore} cached=${data.cached}")

            CapacityData(
                agentName = data.agentName ?: "",
                compositeScore = data.compositeScore ?: 0.0,
                fragilityIndex = data.fragilityIndex ?: 0.0,
                category = data.category ?: "moderate",
                c = factors?.C?.score ?: 0.0,
                iInt = factors?.iInt?.score ?: 0.0,
                r = factors?.R?.score ?: 0.0,
                iInc = factors?.iInc?.score ?: 0.0,
                s = factors?.S?.score ?: 0.0,
                windowStart = data.metadata?.windowStart,
                windowEnd = data.metadata?.windowEnd,
                cached = data.cached ?: false,
                localScore = data.localScore,
                localCategory = data.localCategory,
            )
        } finally {
            client.close()
        }
    }

    /**
     * Update accord metrics settings (consent and/or trace level).
     */
    suspend fun updateAccordSettings(
        consentGiven: Boolean? = null,
        traceLevel: String? = null
    ): AccordSettingsUpdateResult {
        val method = "updateAccordSettings"
        logInfo(method, "Updating accord settings: consent=$consentGiven, level=$traceLevel")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = 15000
                connectTimeoutMillis = 10000
            }
        }

        return try {
            val response = client.put("$baseUrl/v1/my-data/accord-settings") {
                authHeader()?.let { header("Authorization", it) }
                contentType(ContentType.Application.Json)
                setBody(AccordSettingsUpdateRequest(
                    consentGiven = consentGiven,
                    traceLevel = traceLevel
                ))
            }

            logDebug(method, "Response: status=${response.status}")

            if (!response.status.isSuccess()) {
                val errorBody = response.bodyAsText()
                logError(method, "API returned non-success status: ${response.status}")
                return AccordSettingsUpdateResult(
                    success = false,
                    message = "API error: HTTP ${response.status}",
                    changes = emptyList()
                )
            }

            val apiResponse: AccordUpdateApiResponse = response.body()
            logInfo(method, "Settings updated: ${apiResponse.data?.changes}")

            AccordSettingsUpdateResult(
                success = apiResponse.success ?: false,
                message = apiResponse.message ?: "Settings updated",
                changes = apiResponse.data?.changes ?: emptyList()
            )
        } catch (e: Exception) {
            logException(method, e)
            AccordSettingsUpdateResult(
                success = false,
                message = "Error: ${e.message}",
                changes = emptyList()
            )
        } finally {
            client.close()
        }
    }

    // ===== Data Management API (Admin-protected) =====

    /**
     * Reset account data while PRESERVING signing key.
     *
     * This operation:
     * - Deletes databases, logs, and cached data
     * - Deletes .env configuration (triggers setup wizard)
     * - PRESERVES the signing key (wallet access maintained)
     *
     * Requires ADMIN role.
     *
     * @param reason Optional reason for reset (for audit logging)
     * @return ResetAccountResult with success/failure status
     */
    suspend fun resetAccount(reason: String = "User requested reset"): ResetAccountResult {
        val method = "resetAccount"
        logInfo(method, "Requesting account reset (preserving signing key)")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = 30000
                connectTimeoutMillis = 10000
            }
        }

        return try {
            val response = client.post("$baseUrl/v1/system/data/reset-account") {
                authHeader()?.let { header("Authorization", it) }
                contentType(ContentType.Application.Json)
                setBody(buildJsonObject {
                    put("confirm", true)
                    put("reason", reason)
                })
            }

            logDebug(method, "Response: status=${response.status}")

            if (!response.status.isSuccess()) {
                val errorBody = response.bodyAsText()
                logError(method, "API returned non-success status: ${response.status}, body=$errorBody")
                return ResetAccountResult(
                    success = false,
                    message = "API error: HTTP ${response.status}",
                    signingKeyPreserved = false
                )
            }

            val apiResponse: ResetAccountApiResponse = response.body()
            // Note: SuccessResponse wrapper doesn't have top-level success - it's in data
            val dataSuccess = apiResponse.data?.success ?: false
            logInfo(method, "Reset result: success=$dataSuccess, preserved=${apiResponse.data?.signingKeyPreserved}")

            ResetAccountResult(
                success = dataSuccess,
                message = apiResponse.data?.message ?: apiResponse.message ?: "Unknown response",
                signingKeyPreserved = apiResponse.data?.signingKeyPreserved ?: true
            )
        } catch (e: Exception) {
            logException(method, e)
            ResetAccountResult(
                success = false,
                message = "Error: ${e.message}",
                signingKeyPreserved = false
            )
        } finally {
            client.close()
        }
    }

    /**
     * DANGER: Wipe signing key and ALL data.
     *
     * WARNING: THIS ACTION IS IRREVERSIBLE!
     *
     * This operation:
     * - DESTROYS the signing key (wallet access PERMANENTLY LOST)
     * - Deletes ALL data (databases, logs, cache)
     * - Deletes .env configuration
     *
     * Any funds in the wallet will be LOST FOREVER.
     *
     * Requires ADMIN role.
     *
     * @param reason Optional reason for wipe (for audit logging)
     * @return WipeSigningKeyResult with success/failure status
     */
    suspend fun wipeSigningKey(reason: String = "User requested complete identity wipe"): WipeSigningKeyResult {
        val method = "wipeSigningKey"
        logWarn(method, "DANGER: Requesting signing key wipe - wallet access will be DESTROYED")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = 30000
                connectTimeoutMillis = 10000
            }
        }

        return try {
            val response = client.post("$baseUrl/v1/system/data/wipe-signing-key") {
                authHeader()?.let { header("Authorization", it) }
                contentType(ContentType.Application.Json)
                setBody(buildJsonObject {
                    put("confirm", true)
                    put("confirm_wallet_loss", true)
                    put("reason", reason)
                })
            }

            logDebug(method, "Response: status=${response.status}")

            if (!response.status.isSuccess()) {
                val errorBody = response.bodyAsText()
                logError(method, "API returned non-success status: ${response.status}, body=$errorBody")
                return WipeSigningKeyResult(
                    success = false,
                    message = "API error: HTTP ${response.status}",
                    walletAccessDestroyed = false
                )
            }

            val apiResponse: WipeSigningKeyApiResponse = response.body()
            // Note: SuccessResponse wrapper doesn't have top-level success - it's in data
            val dataSuccess = apiResponse.data?.success ?: false
            logWarn(method, "Wipe result: success=$dataSuccess, walletDestroyed=${apiResponse.data?.walletAccessDestroyed}")

            WipeSigningKeyResult(
                success = dataSuccess,
                message = apiResponse.data?.message ?: apiResponse.message ?: "Unknown response",
                walletAccessDestroyed = apiResponse.data?.walletAccessDestroyed ?: true
            )
        } catch (e: Exception) {
            logException(method, e)
            WipeSigningKeyResult(
                success = false,
                message = "Error: ${e.message}",
                walletAccessDestroyed = false
            )
        } finally {
            client.close()
        }
    }

    /**
     * Update the user's preferred language on the backend.
     * Call this when the user changes language in settings to sync with server.
     *
     * @param languageCode ISO 639-1 language code (e.g., 'en', 'am', 'es')
     * @return true if successful, false otherwise
     */
    suspend fun updateUserLanguage(languageCode: String): Boolean {
        val method = "updateUserLanguage"
        logInfo(method, "Updating user language to: $languageCode")

        return try {
            val request = ai.ciris.api.models.UpdateUserSettingsRequest(
                preferredLanguage = languageCode
            )
            val response = usersApi.updateMySettingsV1UsersMeSettingsPut(
                updateUserSettingsRequest = request,
                authorization = authHeader()
            )
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                return false
            }

            logInfo(method, "User language updated successfully to: $languageCode")
            true
        } catch (e: Exception) {
            logException(method, e, "languageCode=$languageCode")
            false
        }
    }

    // ===== Location Search API =====

    /**
     * Search for cities by name (typeahead autocomplete).
     * Uses GeoNames cities15000 data (33K+ cities with population > 15,000).
     *
     * @param query Search query (city name or partial)
     * @param countryCode Optional ISO 3166-1 alpha-2 country code to filter by
     * @param limit Maximum number of results (1-50, default 10)
     * @return LocationSearchResponse with matching cities
     */
    override suspend fun searchLocations(
        query: String,
        countryCode: String?,
        limit: Int
    ): LocationSearchResponse {
        val method = "searchLocations"
        logInfo(method, "Searching locations: query=$query, countryCode=$countryCode, limit=$limit")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = 10000
                connectTimeoutMillis = 5000
            }
        }

        return try {
            val urlBuilder = StringBuilder("$baseUrl/v1/setup/location-search?q=${query.encodeURLParameter()}")
            if (countryCode != null) {
                urlBuilder.append("&country=$countryCode")
            }
            urlBuilder.append("&limit=$limit")

            val response = client.get(urlBuilder.toString())

            if (!response.status.isSuccess()) {
                logError(method, "API returned error: ${response.status}")
                return LocationSearchResponse(results = emptyList(), query = query, count = 0)
            }

            val body = response.body<LocationSearchApiResponse>()
            logDebug(method, "Found ${body.count} results for query: $query")

            LocationSearchResponse(
                results = body.results.map { result ->
                    LocationResultData(
                        city = result.city,
                        region = result.region,
                        country = result.country,
                        countryCode = result.countryCode,
                        latitude = result.latitude,
                        longitude = result.longitude,
                        population = result.population,
                        timezone = result.timezone,
                        displayName = result.displayName
                    )
                },
                query = body.query,
                count = body.count
            )
        } catch (e: Exception) {
            logException(method, e, "query=$query")
            LocationSearchResponse(results = emptyList(), query = query, count = 0)
        }
    }

    /**
     * Get list of all countries with currency information.
     * Returns 252 countries sorted alphabetically by name.
     */
    override suspend fun getCountries(): CountriesResponse {
        val method = "getCountries"
        logDebug(method, "Fetching countries list")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = 15000
                connectTimeoutMillis = 10000
            }
        }

        return try {
            val response = client.get("$baseUrl/v1/setup/countries")

            if (!response.status.isSuccess()) {
                logError(method, "API returned error: ${response.status}")
                return CountriesResponse(countries = emptyList(), count = 0)
            }

            val body = response.body<CountriesApiResponse>()
            logDebug(method, "Got ${body.count} countries")

            CountriesResponse(
                countries = body.countries.map { country ->
                    CountryInfoData(
                        code = country.code,
                        name = country.name,
                        currencyCode = country.currencyCode,
                        currencyName = country.currencyName
                    )
                },
                count = body.count
            )
        } catch (e: Exception) {
            logException(method, e)
            CountriesResponse(countries = emptyList(), count = 0)
        }
    }

    /**
     * Update user's location in the .env file.
     */
    override suspend fun updateUserLocation(location: LocationResultData): UpdateLocationResult {
        val method = "updateUserLocation"
        logInfo(method, "Updating user location to: ${location.displayName}")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = 10000
                connectTimeoutMillis = 5000
            }
        }

        // Use a proper @Serializable data class instead of Map<String, Any>
        // to avoid "Serializer for subclass 'LinkedHashMap' is not found" errors
        @Serializable
        data class LocationUpdateRequest(
            val city: String,
            val region: String,
            val country: String,
            @SerialName("country_code") val countryCode: String,
            val latitude: Double,
            val longitude: Double,
            val timezone: String
        )

        val requestBody = LocationUpdateRequest(
            city = location.city,
            region = location.region ?: "",
            country = location.country,
            countryCode = location.countryCode,
            latitude = location.latitude,
            longitude = location.longitude,
            timezone = location.timezone ?: ""
        )

        return try {
            val response = client.post("$baseUrl/v1/setup/location") {
                header("Authorization", authHeader())
                contentType(ContentType.Application.Json)
                setBody(requestBody)
            }

            if (!response.status.isSuccess()) {
                logError(method, "API returned error: ${response.status}")
                return UpdateLocationResult(
                    success = false,
                    message = "API error: ${response.status}",
                    locationDisplay = ""
                )
            }

            @Serializable
            data class LocationUpdateResponse(
                val success: Boolean,
                val message: String,
                @SerialName("location_display") val locationDisplay: String
            )

            val body = response.body<LocationUpdateResponse>()
            logInfo(method, "Location updated: ${body.locationDisplay}")

            UpdateLocationResult(
                success = body.success,
                message = body.message,
                locationDisplay = body.locationDisplay
            )
        } catch (e: Exception) {
            logException(method, e)
            UpdateLocationResult(
                success = false,
                message = "Failed to update location: ${e.message}",
                locationDisplay = ""
            )
        }
    }

    /**
     * Get current location from .env file.
     */
    override suspend fun getCurrentLocation(): CurrentLocationData {
        val method = "getCurrentLocation"
        logDebug(method, "Fetching current location from backend")

        val client = HttpClient {
            install(ContentNegotiation) { json(jsonConfig) }
            install(HttpTimeout) {
                requestTimeoutMillis = 10000
                connectTimeoutMillis = 5000
            }
        }

        return try {
            val response = client.get("$baseUrl/v1/setup/location") {
                header("Authorization", authHeader())
            }

            if (!response.status.isSuccess()) {
                logWarn(method, "API returned error: ${response.status}")
                return CurrentLocationData(configured = false)
            }

            @Serializable
            data class CurrentLocationResponse(
                val configured: Boolean,
                val city: String? = null,
                val region: String? = null,
                val country: String? = null,
                val latitude: Double? = null,
                val longitude: Double? = null,
                val timezone: String? = null,
                @SerialName("display_name") val displayName: String? = null
            )

            val body = response.body<CurrentLocationResponse>()
            logDebug(method, "Location configured=${body.configured}, display=${body.displayName}")

            CurrentLocationData(
                configured = body.configured,
                city = body.city,
                region = body.region,
                country = body.country,
                latitude = body.latitude,
                longitude = body.longitude,
                timezone = body.timezone,
                displayName = body.displayName
            )
        } catch (e: Exception) {
            logException(method, e)
            CurrentLocationData(configured = false)
        }
    }

    // ===== Skill Import API =====

    /**
     * Preview an OpenClaw skill import without committing.
     */
    suspend fun previewSkillImport(skillMdContent: String, sourceUrl: String? = null): ai.ciris.mobile.shared.models.SkillPreviewData {
        val method = "previewSkillImport"
        val url = "$baseUrl/v1/system/adapters/import-skill/preview"
        val auth = authHeader()
        logInfo(method, "POST $url")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
            }
            val body = buildJsonObject {
                put("skill_md_content", JsonPrimitive(skillMdContent))
                sourceUrl?.let { put("source_url", JsonPrimitive(it)) }
            }

            val response: HttpResponse = client.post(url) {
                auth?.let { headers { append("Authorization", it) } }
                contentType(ContentType.Application.Json)
                setBody(body.toString())
            }

            if (response.status.value !in 200..299) {
                val errorBody = response.body<String>()
                client.close()
                throw Exception("Preview failed: $errorBody")
            }

            val responseText = response.body<String>()
            client.close()

            val json = Json { ignoreUnknownKeys = true }
            val obj = json.parseToJsonElement(responseText).jsonObject

            ai.ciris.mobile.shared.models.SkillPreviewData(
                name = obj["name"]?.jsonPrimitive?.content ?: "",
                description = obj["description"]?.jsonPrimitive?.content ?: "",
                version = obj["version"]?.jsonPrimitive?.content ?: "",
                moduleName = obj["module_name"]?.jsonPrimitive?.content ?: "",
                tools = obj["tools"]?.jsonArray?.map { it.jsonPrimitive.content } ?: emptyList(),
                requiredEnvVars = obj["required_env_vars"]?.jsonArray?.map { it.jsonPrimitive.content } ?: emptyList(),
                requiredBinaries = obj["required_binaries"]?.jsonArray?.map { it.jsonPrimitive.content } ?: emptyList(),
                hasSupportingFiles = obj["has_supporting_files"]?.jsonPrimitive?.boolean ?: false,
                sourceUrl = obj["source_url"]?.jsonPrimitive?.contentOrNull,
                instructionsPreview = obj["instructions_preview"]?.jsonPrimitive?.content ?: ""
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * Validate an OpenClaw skill without importing.
     *
     * Parses the SKILL.md content, runs security scans, and returns
     * validation results without writing any files. Used by Skill Studio
     * for real-time validation feedback.
     */
    suspend fun validateSkill(skillMdContent: String): ai.ciris.mobile.shared.models.SkillValidateResult {
        val method = "validateSkill"
        val url = "$baseUrl/v1/system/adapters/import-skill/validate"
        val auth = authHeader()
        logInfo(method, "POST $url")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
            }
            val body = buildJsonObject {
                put("skill_md_content", JsonPrimitive(skillMdContent))
            }

            val response: HttpResponse = client.post(url) {
                auth?.let { headers { append("Authorization", it) } }
                contentType(ContentType.Application.Json)
                setBody(body.toString())
            }

            if (response.status.value !in 200..299) {
                val errorBody = response.body<String>()
                client.close()
                throw Exception("Validation failed: $errorBody")
            }

            val responseText = response.body<String>()
            client.close()

            val json = Json { ignoreUnknownKeys = true }
            val obj = json.parseToJsonElement(responseText).jsonObject

            // Parse security report
            val securityObj = obj["security"]?.jsonObject
            val security = ai.ciris.mobile.shared.models.SecurityReport(
                totalFindings = securityObj?.get("total_findings")?.jsonPrimitive?.intOrNull ?: 0,
                criticalCount = securityObj?.get("critical_count")?.jsonPrimitive?.intOrNull ?: 0,
                highCount = securityObj?.get("high_count")?.jsonPrimitive?.intOrNull ?: 0,
                mediumCount = securityObj?.get("medium_count")?.jsonPrimitive?.intOrNull ?: 0,
                lowCount = securityObj?.get("low_count")?.jsonPrimitive?.intOrNull ?: 0,
                safeToImport = securityObj?.get("safe_to_import")?.jsonPrimitive?.boolean ?: true,
                summary = securityObj?.get("summary")?.jsonPrimitive?.content ?: "",
                findings = securityObj?.get("findings")?.jsonArray?.map { findingEl ->
                    val finding = findingEl.jsonObject
                    ai.ciris.mobile.shared.models.SecurityFinding(
                        severity = finding["severity"]?.jsonPrimitive?.content ?: "info",
                        category = finding["category"]?.jsonPrimitive?.content ?: "",
                        title = finding["title"]?.jsonPrimitive?.content ?: "",
                        description = finding["description"]?.jsonPrimitive?.content ?: "",
                        evidence = finding["evidence"]?.jsonPrimitive?.contentOrNull,
                        recommendation = finding["recommendation"]?.jsonPrimitive?.content ?: ""
                    )
                } ?: emptyList()
            )

            // Parse preview if present
            val previewObj = obj["preview"]?.jsonObject
            val preview = previewObj?.let {
                ai.ciris.mobile.shared.models.SkillPreviewData(
                    name = it["name"]?.jsonPrimitive?.content ?: "",
                    description = it["description"]?.jsonPrimitive?.content ?: "",
                    version = it["version"]?.jsonPrimitive?.content ?: "",
                    moduleName = it["module_name"]?.jsonPrimitive?.content ?: "",
                    tools = it["tools"]?.jsonArray?.map { t -> t.jsonPrimitive.content } ?: emptyList(),
                    requiredEnvVars = it["required_env_vars"]?.jsonArray?.map { e -> e.jsonPrimitive.content } ?: emptyList(),
                    requiredBinaries = it["required_binaries"]?.jsonArray?.map { b -> b.jsonPrimitive.content } ?: emptyList(),
                    hasSupportingFiles = it["has_supporting_files"]?.jsonPrimitive?.boolean ?: false,
                    sourceUrl = it["source_url"]?.jsonPrimitive?.contentOrNull,
                    instructionsPreview = it["instructions_preview"]?.jsonPrimitive?.content ?: "",
                    security = security
                )
            }

            ai.ciris.mobile.shared.models.SkillValidateResult(
                valid = obj["valid"]?.jsonPrimitive?.boolean ?: false,
                errors = obj["errors"]?.jsonArray?.map { it.jsonPrimitive.content } ?: emptyList(),
                warnings = obj["warnings"]?.jsonArray?.map { it.jsonPrimitive.content } ?: emptyList(),
                security = security,
                preview = preview
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * Import an OpenClaw skill as a CIRIS adapter.
     */
    suspend fun importSkill(skillMdContent: String, sourceUrl: String? = null, autoLoad: Boolean = true): ai.ciris.mobile.shared.models.SkillImportResult {
        val method = "importSkill"
        val url = "$baseUrl/v1/system/adapters/import-skill"
        val auth = authHeader()
        logInfo(method, "POST $url")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
            }
            val body = buildJsonObject {
                put("skill_md_content", JsonPrimitive(skillMdContent))
                sourceUrl?.let { put("source_url", JsonPrimitive(it)) }
                put("auto_load", JsonPrimitive(autoLoad))
            }

            val response: HttpResponse = client.post(url) {
                auth?.let { headers { append("Authorization", it) } }
                contentType(ContentType.Application.Json)
                setBody(body.toString())
            }

            if (response.status.value !in 200..299) {
                val errorBody = response.body<String>()
                client.close()
                throw Exception("Import failed: $errorBody")
            }

            val responseText = response.body<String>()
            client.close()

            val json = Json { ignoreUnknownKeys = true }
            val obj = json.parseToJsonElement(responseText).jsonObject

            // Parse preview sub-object if present
            val previewObj = obj["preview"]?.jsonObject
            val preview = previewObj?.let {
                ai.ciris.mobile.shared.models.SkillPreviewData(
                    name = it["name"]?.jsonPrimitive?.content ?: "",
                    description = it["description"]?.jsonPrimitive?.content ?: "",
                    version = it["version"]?.jsonPrimitive?.content ?: "",
                    moduleName = it["module_name"]?.jsonPrimitive?.content ?: "",
                    tools = it["tools"]?.jsonArray?.map { t -> t.jsonPrimitive.content } ?: emptyList(),
                    requiredEnvVars = it["required_env_vars"]?.jsonArray?.map { t -> t.jsonPrimitive.content } ?: emptyList(),
                    requiredBinaries = it["required_binaries"]?.jsonArray?.map { t -> t.jsonPrimitive.content } ?: emptyList(),
                    hasSupportingFiles = it["has_supporting_files"]?.jsonPrimitive?.boolean ?: false,
                    sourceUrl = it["source_url"]?.jsonPrimitive?.contentOrNull,
                    instructionsPreview = it["instructions_preview"]?.jsonPrimitive?.content ?: ""
                )
            }

            ai.ciris.mobile.shared.models.SkillImportResult(
                success = obj["success"]?.jsonPrimitive?.boolean ?: false,
                moduleName = obj["module_name"]?.jsonPrimitive?.content ?: "",
                adapterPath = obj["adapter_path"]?.jsonPrimitive?.content ?: "",
                toolsCreated = obj["tools_created"]?.jsonArray?.map { it.jsonPrimitive.content } ?: emptyList(),
                message = obj["message"]?.jsonPrimitive?.content ?: "",
                autoLoaded = obj["auto_loaded"]?.jsonPrimitive?.boolean ?: false,
                preview = preview
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * List all previously imported skills.
     */
    suspend fun listImportedSkills(): List<ai.ciris.mobile.shared.models.ImportedSkillData> {
        val method = "listImportedSkills"
        val url = "$baseUrl/v1/system/adapters/imported-skills"
        val auth = authHeader()
        logInfo(method, "GET $url")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
            }
            val response: HttpResponse = client.get(url) {
                auth?.let { headers { append("Authorization", it) } }
            }

            if (response.status.value !in 200..299) {
                client.close()
                throw Exception("Failed to list imported skills: ${response.status}")
            }

            val responseText = response.body<String>()
            client.close()

            val json = Json { ignoreUnknownKeys = true }
            val obj = json.parseToJsonElement(responseText).jsonObject
            val skills = obj["skills"]?.jsonArray?.map { skillJson ->
                val s = skillJson.jsonObject
                ai.ciris.mobile.shared.models.ImportedSkillData(
                    moduleName = s["module_name"]?.jsonPrimitive?.content ?: "",
                    originalSkillName = s["original_skill_name"]?.jsonPrimitive?.content ?: "",
                    version = s["version"]?.jsonPrimitive?.content ?: "",
                    description = s["description"]?.jsonPrimitive?.content ?: "",
                    adapterPath = s["adapter_path"]?.jsonPrimitive?.content ?: "",
                    sourceUrl = s["source_url"]?.jsonPrimitive?.contentOrNull
                )
            } ?: emptyList()

            logInfo(method, "Found ${skills.size} imported skills")
            skills
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
    }

    /**
     * Delete a previously imported skill.
     */
    suspend fun deleteImportedSkill(moduleName: String): Boolean {
        val method = "deleteImportedSkill"
        val url = "$baseUrl/v1/system/adapters/imported-skills/$moduleName"
        val auth = authHeader()
        logInfo(method, "DELETE $url")

        return try {
            val client = HttpClient {
                install(ContentNegotiation) {
                    json(Json {
                        ignoreUnknownKeys = true
                        isLenient = true
                    })
                }
            }
            val response: HttpResponse = client.delete(url) {
                auth?.let { headers { append("Authorization", it) } }
            }
            client.close()
            response.status.value in 200..299
        } catch (e: Exception) {
            logException(method, e)
            false
        }
    }

    // ─── The operator surface (/v1/node/state) — CIRISServer #356/#369/#370 ───
    //
    // One read that answers "how is this node?": persist's node-state fold, edge's
    // withhold ledger, the trace-plane liveness band (#369) and the ingest refusal
    // rate (#370). `src/operator_surface.rs`. OWNER-gated.
    //
    // WHY THIS ONE RETURNS A RESULT INSTEAD OF THROWING, unlike its neighbours:
    // the surface's entire purpose is that "could not ask" and "there is nothing"
    // must not render the same. An unreachable node and a `red` node are exactly
    // that pair one level up — `red` is a real reading FROM A REACHABLE NODE — and
    // an exception erases which one happened by the time the UI sees it. So the
    // read outcome is modelled, not thrown: NodeStateReadout has five arms and the
    // caller must handle each.

    /**
     * Read the composed operator surface — `GET {nodeUrl}/v1/node/state`.
     *
     * Never throws for a reachable-but-unhappy node: a refusal (401/403/owner
     * unbound) is [NodeStateReadout.Refused], an undecodable body is
     * [NodeStateReadout.Malformed], and no answer at all is
     * [NodeStateReadout.Unreachable]. Only [NodeStateReadout.Present] carries a
     * band, and only then does `green`/`yellow`/`red`/`unknown` mean anything.
     */
    suspend fun getNodeOperatorState(
        nodeUrl: String = baseUrl,
        token: String? = accessToken,
    ): ai.ciris.mobile.shared.models.NodeStateReadout {
        val method = "getNodeOperatorState"
        val client = federationHttpClient()
        return try {
            val response = client.get("$nodeUrl/v1/node/state") {
                token?.let { header("Authorization", "Bearer $it") }
            }
            val raw = response.bodyAsText()
            val status = response.status.value
            when {
                // The node answered and declined. It is UP. Not a health reading,
                // and emphatically not `red`.
                status == 401 || status == 403 ->
                    ai.ciris.mobile.shared.models.NodeStateReadout.Refused(
                        status = status,
                        detail = raw.take(300),
                    )
                // No such route: an older build with no operator surface. A
                // version gap, not a refusal and not ill health.
                status == 404 -> ai.ciris.mobile.shared.models.NodeStateReadout.NotOffered
                !response.status.isSuccess() ->
                    ai.ciris.mobile.shared.models.NodeStateReadout.Unreachable(
                        detail = "HTTP $status: ${raw.take(300)}",
                    )
                raw.isBlank() ->
                    ai.ciris.mobile.shared.models.NodeStateReadout.Malformed("empty body")
                else -> try {
                    ai.ciris.mobile.shared.models.NodeStateReadout.Present(
                        decodeFederationEnvelope(
                            raw,
                            ai.ciris.mobile.shared.models.NodeOperatorState.serializer(),
                        ),
                    )
                } catch (e: Exception) {
                    logException(method, e, "nodeUrl=$nodeUrl, decode")
                    ai.ciris.mobile.shared.models.NodeStateReadout.Malformed(
                        "${e::class.simpleName}: ${e.message}",
                    )
                }
            }
        } catch (e: Exception) {
            // No answer at all: transport, DNS, refused connection, timeout. THE
            // fifth state — it must not be dressed as a band.
            logException(method, e, "nodeUrl=$nodeUrl")
            ai.ciris.mobile.shared.models.NodeStateReadout.Unreachable(
                detail = "${e::class.simpleName}: ${e.message ?: "no response"}",
            )
        } finally {
            client.close()
        }
    }

    override fun close() {
    logInfo("close", "Closing CIRISApiClient")
    }
}

// ===== Scheduler Data Models =====

@Serializable
data class ScheduledTasksApiResponse(
    val data: ScheduledTasksListData? = null
)

@Serializable
data class SchedulerStatsApiResponse(
    val data: SchedulerStatsData? = null
)

@Serializable
data class ScheduledTaskApiResponse(
    val data: ScheduledTaskData? = null
)

@Serializable
data class ScheduledTasksListData(
    val tasks: List<ScheduledTaskData> = emptyList(),
    val total: Int = 0,
    @SerialName("active_count")
    val activeCount: Int = 0,
    @SerialName("recurring_count")
    val recurringCount: Int = 0
)

@Serializable
data class ScheduledTaskData(
    @SerialName("task_id")
    val taskId: String,
    val name: String,
    @SerialName("goal_description")
    val goalDescription: String,
    val status: String,
    @SerialName("defer_until")
    val deferUntil: String? = null,
    @SerialName("schedule_cron")
    val scheduleCron: String? = null,
    @SerialName("created_at")
    val createdAt: String,
    @SerialName("last_triggered_at")
    val lastTriggeredAt: String? = null,
    @SerialName("deferral_count")
    val deferralCount: Int = 0,
    @SerialName("is_recurring")
    val isRecurring: Boolean = false
) {
    /**
     * Human-friendly display of schedule.
     */
    val scheduleDisplay: String
        get() = when {
            scheduleCron != null -> cronToHumanReadable(scheduleCron)
            deferUntil != null -> "One-time: $deferUntil"
            else -> "No schedule"
        }

    /**
     * Human-friendly status display.
     */
    val statusDisplay: String
        get() = when (status.uppercase()) {
            "PENDING" -> "Scheduled"
            "ACTIVE" -> "Active"
            "COMPLETE" -> "Completed"
            "FAILED" -> "Failed"
            "CANCELLED" -> "Cancelled"
            else -> status
        }

    private fun cronToHumanReadable(cron: String): String {
        // Simple cron parsing for common patterns
        val parts = cron.split(" ")
        if (parts.size < 5) return cron

        val minute = parts[0]
        val hour = parts[1]
        val dayOfMonth = parts[2]
        val month = parts[3]
        val dayOfWeek = parts[4]

        return when {
            // Daily at specific time
            minute != "*" && hour != "*" && dayOfMonth == "*" && month == "*" && dayOfWeek == "*" ->
                "Daily at $hour:${minute.padStart(2, '0')}"
            // Weekly on specific day
            minute != "*" && hour != "*" && dayOfWeek != "*" ->
                "Weekly on ${dayOfWeekName(dayOfWeek)} at $hour:${minute.padStart(2, '0')}"
            // Every N minutes
            minute.startsWith("*/") && hour == "*" ->
                "Every ${minute.removePrefix("*/")} minutes"
            // Every N hours
            minute == "0" && hour.startsWith("*/") ->
                "Every ${hour.removePrefix("*/")} hours"
            else -> cron
        }
    }

    private fun dayOfWeekName(day: String): String = when (day) {
        "0", "7" -> "Sunday"
        "1" -> "Monday"
        "2" -> "Tuesday"
        "3" -> "Wednesday"
        "4" -> "Thursday"
        "5" -> "Friday"
        "6" -> "Saturday"
        else -> day
    }
}

@Serializable
data class SchedulerStatsData(
    @SerialName("tasks_scheduled_total")
    val tasksScheduledTotal: Int = 0,
    @SerialName("tasks_completed_total")
    val tasksCompletedTotal: Int = 0,
    @SerialName("tasks_failed_total")
    val tasksFailedTotal: Int = 0,
    @SerialName("tasks_pending")
    val tasksPending: Int = 0,
    @SerialName("recurring_tasks")
    val recurringTasks: Int = 0,
    @SerialName("oneshot_tasks")
    val oneshotTasks: Int = 0,
    @SerialName("scheduler_uptime_seconds")
    val schedulerUptimeSeconds: Double = 0.0
)

// ===== Play Integrity Data Models =====

@Serializable
data class PlayIntegrityNonceApiResponse(
    val data: Map<String, String>? = null
)

@Serializable
data class PlayIntegrityVerifyApiResponse(
    val data: PlayIntegrityVerifyData? = null
)

@Serializable
data class PlayIntegrityVerifyData(
    val verified: Boolean = false,
    val verdict: String? = null,
    @SerialName("meets_strong_integrity")
    val meetsStrongIntegrity: Boolean = false,
    @SerialName("meets_device_integrity")
    val meetsDeviceIntegrity: Boolean = false,
    @SerialName("meets_basic_integrity")
    val meetsBasicIntegrity: Boolean = false
)

data class PlayIntegrityNonceResult(
    val nonce: String? = null,
    val error: String? = null
)

data class PlayIntegrityVerifyResult(
    val verified: Boolean = false,
    val verdict: String? = null,
    val meetsStrongIntegrity: Boolean = false,
    val meetsDeviceIntegrity: Boolean = false,
    val meetsBasicIntegrity: Boolean = false,
    val error: String? = null
)

// ===== Config Data Models =====

data class ConfigListData(
    val configs: List<ConfigItemData>,
    val total: Int
)

// ===== Consent Data Models =====

data class ConsentStatusData(
    val hasConsent: Boolean,
    val userId: String,
    val stream: String?,
    val grantedAt: String?,
    val expiresAt: String?
)

data class ConsentStreamsData(
    val streams: Map<String, StreamMetadataData>,
    val default: String
)

data class StreamMetadataData(
    val name: String,
    val description: String,
    val durationDays: Int?,
    val autoForget: Boolean,
    val learningEnabled: Boolean,
    val identityRemoved: Boolean,
    val requiresCategories: Boolean
)

data class ConsentGrantData(
    val userId: String,
    val stream: String,
    val grantedAt: String,
    val expiresAt: String?
)

data class ConsentImpactReportData(
    val userId: String,
    val totalInteractions: Int,
    val patternsContributed: Int,
    val usersHelped: Int,
    val impactScore: Double
)

data class ConsentAuditEntryApiData(
    val entryId: String,
    val userId: String,
    val timestamp: String,
    val previousStream: String,
    val newStream: String,
    val initiatedBy: String,
    val reason: String?
)

data class PartnershipStatusData(
    val status: String,
    val requestedAt: String?,
    val decidedAt: String?,
    val reason: String?
)

// ===== System Data Models =====

/**
 * System warning that requires user attention.
 */
/**
 * Outcome of [CIRISApiClient.linkOAuthIdentity].
 *
 * [linked] is false for a re-link, which is a no-op — the node says so rather
 * than reporting a success indistinguishable from the first time.
 */
data class OAuthLinkResult(
    val provider: String,
    val linked: Boolean,
    val isPrimary: Boolean,
)

data class SystemWarning(
    val code: String,
    val message: String,
    val severity: String = "warning",
    val actionUrl: String? = null
)

data class SystemHealthData(
    val status: String,
    val cognitiveState: String,
    val warnings: List<SystemWarning> = emptyList(),
    val degradedMode: Boolean = false  // True when no working LLM provider
)

/**
 * Structured server health from `/v1/health` — the facts the universal client's
 * node-vs-agent gate keys off (see [ai.ciris.mobile.shared.models.ClientMode]).
 * A bare node reports `role="fabric-node"` with no [cognitiveState] and an empty
 * service map; an agent enriches the endpoint with [cognitiveState] + services.
 */
data class NodeHealth(
    val status: String,
    val role: String?,
    val version: String?,
    val cognitiveState: String?,
    val serviceCount: Int
)

data class UnifiedTelemetryData(
    val health: String,
    val uptime: String,
    val cognitiveState: String,
    val memoryMb: Int,
    val memoryPercent: Int,
    val cpuPercent: Int,
    val diskUsedMb: Double,
    val servicesOnline: Int,
    val servicesTotal: Int,
    val services: Map<String, ServiceInfoData>
)

data class ServiceInfoData(
    val healthy: Boolean,
    val available: Boolean,
    val serviceType: String?,
    val capabilities: List<String>
)

data class EnvironmentalMetricsData(
    val carbonGrams: Double,
    val energyKwh: Double,
    val costCents: Double,
    val tokensLastHour: Int,
    val tokens24h: Int
)

data class ProcessorStatusData(
    val isPaused: Boolean,
    val cognitiveState: String,
    val queueDepth: Int
)

data class ChannelsData(
    val channels: List<ChannelInfoData>
)

data class ChannelInfoData(
    val channelId: String,
    val displayName: String,
    val channelType: String,
    val isActive: Boolean,
    val messageCount: Int,
    val lastActivity: String?
)

// ===== Wise Authority Data Models =====

data class WAStatusData(
    val serviceHealthy: Boolean,
    val activeWAs: Int,
    val pendingDeferrals: Int,
    val deferrals24h: Int,
    val averageResolutionTimeMinutes: Double,
    val timestamp: String?,
    val subscribers: List<String> = emptyList()
)

data class DeferralData(
    val deferralId: String,
    val createdAt: String,
    val deferredBy: String,
    val taskId: String,
    val thoughtId: String,
    val reason: String,
    val channelId: String?,
    val userId: String?,
    val priority: String,
    val assignedWaId: String?,
    val requiresRole: String?,
    val status: String,
    val resolution: String?,
    val resolvedAt: String?,
    val question: String?,
    val context: Map<String, String>?,
    val timeoutAt: String?
)

data class ResolveDeferralData(
    val deferralId: String,
    val success: Boolean,
    val resolvedAt: String
)

// ===== Audit Data Models =====

data class AuditEntriesData(
    val entries: List<AuditEntryApiData>,
    val total: Int,
    val offset: Int = 0,
    val limit: Int = 100
)

data class AuditEntryApiData(
    val id: String,
    val action: String,
    val actor: String,
    val timestamp: String,
    val context: AuditContextApiData?,
    val signature: String? = null,
    val hashChain: String? = null,
    val storageSources: List<String>? = null
)

@Serializable
data class AuditContextApiData(
    @SerialName("entity_id") val entityId: String? = null,
    @SerialName("entity_type") val entityType: String? = null,
    val operation: String? = null,
    val description: String? = null,
    @SerialName("request_id") val requestId: String? = null,
    @SerialName("correlation_id") val correlationId: String? = null,
    @SerialName("user_id") val userId: String? = null,
    @SerialName("ip_address") val ipAddress: String? = null,
    @SerialName("user_agent") val userAgent: String? = null,
    val result: String? = null,
    val error: String? = null,
    val metadata: JsonObject? = null,  // Dynamic JSON object for additional metadata
    // Additional fields used by AuditViewModel
    val outcome: String? = null,
    val details: String? = null,
    val service: String? = null
)

// ===== Logs Data Models =====

data class SystemLogsData(
    val logs: List<SystemLogApiData>,
    val total: Int,
    val hasMore: Boolean
)

data class SystemLogApiData(
    val timestamp: String,
    val level: String,
    val service: String,
    val message: String,
    val context: Map<String, String>? = null,
    val traceId: String? = null
)

// ===== Memory Data Models =====

data class MemoryStatsApiData(
    val totalNodes: Int,
    val nodesByType: Map<String, Int>,
    val nodesByScope: Map<String, Int>,
    val recentNodes24h: Int,
    val oldestNodeDate: String? = null,
    val newestNodeDate: String? = null
)

/**
 * Response containing graph visualization data (nodes and edges).
 */
data class GraphDataResponse(
    val nodes: List<ai.ciris.api.models.GraphNode>,
    val edges: List<ai.ciris.api.models.GraphEdge>
)

// ===== Tickets Data Models =====

/**
 * Ticket data for display in the UI.
 */
data class TicketData(
    val ticketId: String,
    val sop: String,
    val ticketType: String,
    val status: String,
    val priority: Int,
    val email: String,
    val userIdentifier: String?,
    val submittedAt: String,
    val deadline: String?,
    val lastUpdated: String,
    val completedAt: String?,
    val notes: String?,
    val automated: Boolean,
    /**
     * Raw ticket metadata. Carries the reserved budget-envelope keys
     * (`__proposal__`, `__requested_budget__`, `__granted_budget__`,
     * `__budget_spent__`) that the HITL approval surface reads via
     * [ai.ciris.mobile.shared.approvals.BudgetApprovalSeam]. Defaulted so
     * existing construction sites are unaffected.
     */
    val metadata: Map<String, JsonElement> = emptyMap()
) {
    /**
     * Check if this ticket is urgent (priority >= 8)
     */
    val isUrgent: Boolean get() = priority >= 8

    /**
     * Human-readable status
     */
    val displayStatus: String get() = when (status) {
        "pending" -> "Pending"
        "in_progress" -> "In Progress"
        "completed" -> "Completed"
        "cancelled" -> "Cancelled"
        "failed" -> "Failed"
        else -> status.replaceFirstChar { it.uppercase() }
    }

    /**
     * Human-readable ticket type
     */
    val displayType: String get() = when (ticketType.lowercase()) {
        "dsar" -> "DSAR"
        "access" -> "Access Request"
        "delete" -> "Delete Request"
        "export" -> "Export Request"
        "correct" -> "Correction Request"
        else -> ticketType.replaceFirstChar { it.uppercase() }
    }
}

/**
 * Ticket statistics summary.
 */
data class TicketStatsData(
    val total: Int,
    val pending: Int,
    val inProgress: Int,
    val completed: Int,
    val failed: Int,
    val urgent: Int
)

/**
 * SOP (Standard Operating Procedure) metadata.
 */
data class SOPMetadataData(
    val sop: String,
    val ticketType: String,
    val requiredFields: List<String>,
    val deadlineDays: Int?,
    val priorityDefault: Int,
    val description: String,
    val stageCount: Int
) {
    /**
     * Human-friendly display name for the SOP.
     */
    val displayName: String
        get() = when (sop) {
            "DSAR_ACCESS" -> "Data Access Request"
            "DSAR_DELETE" -> "Data Deletion Request"
            "DSAR_EXPORT" -> "Data Export Request"
            "DSAR_RECTIFY" -> "Data Rectification Request"
            else -> sop.replace("_", " ")
        }

    /**
     * Short description of the GDPR article.
     */
    val gdprArticle: String?
        get() = when (sop) {
            "DSAR_ACCESS" -> "GDPR Article 15"
            "DSAR_DELETE" -> "GDPR Article 17"
            "DSAR_EXPORT" -> "GDPR Article 20"
            "DSAR_RECTIFY" -> "GDPR Article 16"
            else -> null
        }
}

// ===== Tools Data Models =====

/**
 * Tool information from the system.
 */
data class ToolInfoData(
    val name: String,
    val description: String,
    val provider: String,
    val category: String,
    val cost: Double,
    val whenToUse: String?,
    val parameters: Map<String, String>?
)

/**
 * Tools metadata.
 */
data class ToolsMetadataData(
    val providers: List<String>,
    val providerCount: Int,
    val totalTools: Int
)

/**
 * Result of fetching tools.
 */
data class ToolsResult(
    val tools: List<ToolInfoData>,
    val metadata: ToolsMetadataData?
)

// ===== My Data API (DSAR Self-Service) Data Models =====

/**
 * API response wrapper for my-data endpoints.
 */
@Serializable
data class MyDataApiResponse(
    val success: Boolean? = null,
    val data: MyDataPayload? = null,
    val message: String? = null
)

@Serializable
data class MyDataPayload(
    @SerialName("agent_id_hash")
    val agentIdHash: String? = null,
    @SerialName("agent_id")
    val agentId: String? = null,
    @SerialName("consent_given")
    val consentGiven: Boolean? = null,
    @SerialName("consent_timestamp")
    val consentTimestamp: String? = null,
    @SerialName("trace_level")
    val traceLevel: String? = null,
    @SerialName("traces_sent")
    val tracesSent: Int? = null,
    @SerialName("endpoint_url")
    val endpointUrl: String? = null,
    @SerialName("events_sent")
    val eventsSent: Int? = null
)

/**
 * Lens identifier data (user-facing).
 */
data class LensIdentifierData(
    val agentIdHash: String,
    val agentId: String,
    val consentGiven: Boolean,
    val consentTimestamp: String?,
    val traceLevel: String?,
    val tracesSent: Int,
    val endpointUrl: String?
)

/**
 * Request body for lens trace deletion.
 */
@Serializable
data class LensDeletionRequest(
    val confirm: Boolean,
    val reason: String? = null
)

/**
 * API response for deletion.
 */
@Serializable
data class DeletionApiResponse(
    val success: Boolean? = null,
    val data: DeletionPayload? = null,
    val message: String? = null
)

@Serializable
data class DeletionPayload(
    @SerialName("agent_id_hash")
    val agentIdHash: String? = null,
    val status: String? = null,
    val message: String? = null,
    @SerialName("lens_request_accepted")
    val lensRequestAccepted: Boolean? = null,
    @SerialName("local_consent_revoked")
    val localConsentRevoked: Boolean? = null
)

/**
 * Lens deletion result (user-facing).
 */
data class LensDeletionResult(
    val success: Boolean,
    val agentIdHash: String?,
    val status: String,
    val message: String,
    val lensRequestAccepted: Boolean,
    val localConsentRevoked: Boolean
)

/**
 * API response for accord settings GET.
 */
@Serializable
data class AccordSettingsApiResponse(
    val success: Boolean? = null,
    val data: AccordSettingsPayload? = null,
    val message: String? = null
)

@Serializable
data class AccordSettingsPayload(
    @SerialName("agent_id_hash")
    val agentIdHash: String? = null,
    @SerialName("consent_given")
    val consentGiven: Boolean? = null,
    @SerialName("consent_timestamp")
    val consentTimestamp: String? = null,
    @SerialName("trace_level")
    val traceLevel: String? = null,
    @SerialName("endpoint_url")
    val endpointUrl: String? = null,
    @SerialName("events_sent")
    val eventsSent: Int? = null,
    @SerialName("events_received")
    val eventsReceived: Int? = null,
    @SerialName("events_queued")
    val eventsQueued: Int? = null
)

/**
 * Accord settings data (user-facing).
 */
data class AccordSettingsData(
    val agentIdHash: String,
    val consentGiven: Boolean,
    val consentTimestamp: String?,
    val traceLevel: String?,
    val endpointUrl: String?,
    val eventsSent: Int,
    val eventsReceived: Int,
    val eventsQueued: Int
)

/**
 * Request body for accord settings update.
 */
@Serializable
data class AccordSettingsUpdateRequest(
    @SerialName("consent_given")
    val consentGiven: Boolean? = null,
    @SerialName("trace_level")
    val traceLevel: String? = null
)

/**
 * API response for accord settings update.
 */
@Serializable
data class AccordUpdateApiResponse(
    val success: Boolean? = null,
    val data: AccordUpdatePayload? = null,
    val message: String? = null
)

@Serializable
data class AccordUpdatePayload(
    val changes: List<String>? = null
)

/**
 * Accord settings update result (user-facing).
 */
data class AccordSettingsUpdateResult(
    val success: Boolean,
    val message: String,
    val changes: List<String>
)

// ===== CIRIS Capacity (Ratchet) Models =====
//
// Capacity = the C/I_int/R/I_inc/S score tuple that CIRISLens computes for
// each agent template over a 7-day window. Surfaced to the USER via the
// cell-viz ambient dials; NEVER injected into the agent's reasoning context
// (Goodhart / self-monitoring anxiety).

@Serializable
data class CapacityApiResponse(
    val success: Boolean? = null,
    val data: CapacityPayload? = null,
    val message: String? = null
)

@Serializable
data class CapacityPayload(
    @SerialName("agent_name")
    val agentName: String? = null,
    @SerialName("composite_score")
    val compositeScore: Double? = null,
    @SerialName("fragility_index")
    val fragilityIndex: Double? = null,
    val category: String? = null,
    val factors: CapacityFactorsPayload? = null,
    val metadata: CapacityMetadataPayload? = null,
    val cached: Boolean? = null,
    // Backend per-occurrence scores — populated when the request uses
    // ?scope=local|both. Null when scope=fleet (the default).
    @SerialName("local_score")
    val localScore: Double? = null,
    @SerialName("local_category")
    val localCategory: String? = null,
)

@Serializable
data class CapacityFactorsPayload(
    val C: CapacityFactorPayload? = null,
    @SerialName("I_int")
    val iInt: CapacityFactorPayload? = null,
    val R: CapacityFactorPayload? = null,
    @SerialName("I_inc")
    val iInc: CapacityFactorPayload? = null,
    val S: CapacityFactorPayload? = null
)

@Serializable
data class CapacityFactorPayload(
    val score: Double? = null,
    @SerialName("trace_count")
    val traceCount: Int? = null,
    val confidence: String? = null
    // components intentionally omitted — lens adds new fields over time and we
    // don't want to break parsing when it does. The five top-level scores
    // are the only thing the viz needs.
)

@Serializable
data class CapacityMetadataPayload(
    @SerialName("window_start")
    val windowStart: String? = null,
    @SerialName("window_end")
    val windowEnd: String? = null,
    @SerialName("total_traces")
    val totalTraces: Int? = null,
    @SerialName("non_exempt_traces")
    val nonExemptTraces: Int? = null
)

/**
 * User-facing CIRIS capacity reading. All five factor scores are in [0, 1]
 * and safe to feed directly into visual dials.
 */
data class CapacityData(
    val agentName: String,
    val compositeScore: Double,
    val fragilityIndex: Double,
    val category: String,  // high_capacity | healthy | moderate | high_fragility
    val c: Double,          // Core identity / Consistency
    val iInt: Double,       // Integrity
    val r: Double,          // Resilience / Reliability
    val iInc: Double,       // Incompleteness / Incalibration (humility)
    val s: Double,          // Signalling gratitude / Steering
    val windowStart: String?,
    val windowEnd: String?,
    val cached: Boolean,
    /** This-occurrence score in [0, 1]; null when the request was scope=fleet. */
    val localScore: Double? = null,
    /** This-occurrence category; null when the request was scope=fleet. */
    val localCategory: String? = null,
)

// ===== Data Management API Models =====

/**
 * Result of reset account operation (preserves signing key).
 */
data class ResetAccountResult(
    val success: Boolean,
    val message: String,
    val signingKeyPreserved: Boolean
)

/**
 * API response for reset account.
 */
@Serializable
data class ResetAccountApiResponse(
    val success: Boolean? = null,
    val message: String? = null,
    val data: ResetAccountApiData? = null
)

@Serializable
data class ResetAccountApiData(
    val success: Boolean? = null,
    val message: String? = null,
    @SerialName("signing_key_preserved")
    val signingKeyPreserved: Boolean? = null
)

/**
 * Result of wipe signing key operation (DANGER: destroys wallet access).
 */
data class WipeSigningKeyResult(
    val success: Boolean,
    val message: String,
    val walletAccessDestroyed: Boolean
)

/**
 * API response for wipe signing key.
 */
@Serializable
data class WipeSigningKeyApiResponse(
    val success: Boolean? = null,
    val message: String? = null,
    val data: WipeSigningKeyApiData? = null
)

@Serializable
data class WipeSigningKeyApiData(
    val success: Boolean? = null,
    val message: String? = null,
    @SerialName("wallet_access_destroyed")
    val walletAccessDestroyed: Boolean? = null
)

// ===== Location Search API Models =====

/**
 * API response for location search.
 */
@Serializable
data class LocationSearchApiResponse(
    val results: List<LocationResultApiData> = emptyList(),
    val query: String,
    val count: Int
)

/**
 * Location result from API (snake_case).
 */
@Serializable
data class LocationResultApiData(
    val city: String,
    val region: String? = null,
    val country: String,
    @SerialName("country_code")
    val countryCode: String,
    val latitude: Double,
    val longitude: Double,
    val population: Int,
    val timezone: String? = null,
    @SerialName("display_name")
    val displayName: String
)

/**
 * API response for countries list.
 */
@Serializable
data class CountriesApiResponse(
    val countries: List<CountryInfoApiData> = emptyList(),
    val count: Int
)

/**
 * Country info from API (snake_case).
 */
@Serializable
data class CountryInfoApiData(
    val code: String,
    val name: String,
    @SerialName("currency_code")
    val currencyCode: String? = null,
    @SerialName("currency_name")
    val currencyName: String? = null
)
