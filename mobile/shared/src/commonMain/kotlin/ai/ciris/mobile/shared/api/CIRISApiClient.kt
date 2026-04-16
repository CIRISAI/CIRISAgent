package ai.ciris.mobile.shared.api

import ai.ciris.mobile.shared.models.*
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
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.intOrNull
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
    baseUrl: String = "http://127.0.0.1:8080",
    private var accessToken: String? = null
) : CIRISApiClientProtocol {

    /**
     * Current effective base URL - can be updated dynamically.
     * Note: Some generated API methods may still use the original URL until
     * a new CIRISApiClient instance is created.
     */
    var baseUrl: String = baseUrl
        private set

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

            val body = response.body()
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
     * @return List of ModelInfo with id and display name, sorted by CIRIS compatibility
     */
    suspend fun listModels(
        provider: String,
        apiKey: String,
        baseUrl: String? = null
    ): List<ModelInfo> {
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
                return emptyList()
            }

            val body = response.body<ListModelsApiResponse>()
            val data = body.data ?: return emptyList()

            val models = data.models?.map { model ->
                ModelInfo(
                    id = model.id ?: "",
                    displayName = model.displayName ?: model.id ?: "Unknown",
                    cirisCompatible = model.cirisCompatible ?: false,
                    cirisRecommended = model.cirisRecommended ?: false,
                    contextWindow = model.contextWindow
                )
            } ?: emptyList()

            logInfo(method, "Listed ${models.size} models from ${data.source ?: "unknown"}")
            models
        } catch (e: Exception) {
            logException(method, e)
            emptyList()
        }
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
        val models: List<LiveModelInfo>? = null
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
        logDebug(method, "Fetching CIRISVerify status (hasPlayIntegrity=${playIntegrityToken != null})")

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
            } else if (refresh) {
                // Force re-attestation via FFI
                "$baseUrl/v1/auth/attestation?refresh=true"
            } else {
                // Cached attestation from auth service - instant response
                "$baseUrl/v1/auth/attestation"
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

    /**
     * Initiate device auth with a CIRISNode.
     * Calls POST /v1/setup/connect-node on the local agent API.
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
            val response = client.post("$baseUrl/v1/setup/connect-node") {
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
     * Calls GET /v1/setup/connect-node/status on the local agent API.
     */
    suspend fun pollNodeAuthStatus(deviceCode: String, portalUrl: String): NodeAuthPollResult {
        val method = "pollNodeAuthStatus"
        logInfo(method, "========== POLL START ==========")
        logInfo(method, "deviceCode: ${deviceCode.take(16)}...")
        logInfo(method, "portalUrl: $portalUrl")
        logInfo(method, "baseUrl: $baseUrl")
        val fullUrl = "$baseUrl/v1/setup/connect-node/status"
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
     * Calls POST /v1/setup/reset-device-auth on the local agent API.
     * Used when user backs out of NODE_AUTH flow to clear stale server state.
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
            val response = client.post("$baseUrl/v1/setup/reset-device-auth") {
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
                        SetupCompletionResult(
                            success = false,
                            message = "Setup failed",
                            error = "Server error ($statusCode)"
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
        logInfo(method, "Fetching system health")

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

            logInfo(method, "System health: status=$status, cognitiveState=$cognitiveState, warnings=${warnings.size}, degradedMode=$degradedMode")

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
                throw RuntimeException("Add provider failed: ${response.status}")
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
                    automated = ticket.automated
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
                automated = ticket.automated
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
        }
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
    val automated: Boolean
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
