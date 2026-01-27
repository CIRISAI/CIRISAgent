package ai.ciris.mobile.shared.api

import ai.ciris.mobile.shared.models.*
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.viewmodels.ConfigItemData
import ai.ciris.mobile.shared.viewmodels.SetupCompletionResult
import ai.ciris.mobile.shared.viewmodels.StateTransitionResult
import ai.ciris.api.apis.*
import ai.ciris.api.models.InteractRequest as SdkInteractRequest
import ai.ciris.api.models.LoginRequest as SdkLoginRequest
import ai.ciris.api.models.SetupCompleteRequest as SdkSetupCompleteRequest
import ai.ciris.api.models.ShutdownRequest as SdkShutdownRequest
import ai.ciris.api.models.NativeTokenRequest as SdkNativeTokenRequest
import ai.ciris.api.models.StateTransitionRequest as SdkStateTransitionRequest
import ai.ciris.api.models.ConfigUpdate as SdkConfigUpdate
import ai.ciris.api.models.ConsentRequest as SdkConsentRequest
import io.ktor.client.*
import io.ktor.client.call.*
import io.ktor.client.plugins.*
import io.ktor.client.plugins.contentnegotiation.*
import io.ktor.client.plugins.logging.*
import io.ktor.client.request.*
import io.ktor.serialization.kotlinx.json.*
import kotlinx.datetime.Instant
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * Unified API client for CIRIS backend using the generated OpenAPI SDK.
 * This client wraps the generated API classes and provides a clean interface.
 *
 * All methods include comprehensive error logging for debugging.
 */
class CIRISApiClient(
    val baseUrl: String = "http://localhost:8080",
    private var accessToken: String? = null
) : CIRISApiClientProtocol {

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
            level = LogLevel.ALL // Full logging for debugging
        }
        it.install(HttpTimeout) {
            requestTimeoutMillis = 30000
            connectTimeoutMillis = 10000
            socketTimeoutMillis = 30000
        }
    }

    // Generated API instances
    private val agentApi = AgentApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private val authApi = AuthenticationApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private val setupApi = SetupApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private val systemApi = SystemApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private val telemetryApi = TelemetryApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private val billingApi = BillingApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private val wiseAuthorityApi = WiseAuthorityApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private val configApi = ConfigApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private val consentApi = ConsentApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private val auditApi = AuditApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private val memoryApi = MemoryApi(
        baseUrl = baseUrl,
        httpClientEngine = null,
        httpClientConfig = httpClientConfig,
        jsonSerializer = jsonConfig
    )

    private val usersApi = UsersApi(
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
            logInfo(method, "Bearer token set on all API instances (12 APIs)")
        } catch (e: Exception) {
            logException(method, e, "Failed to set bearer token on API instances")
        }
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
    override suspend fun sendMessage(message: String, channelId: String): InteractResponse {
        val method = "sendMessage"
        logInfo(method, "Sending message: '${message.take(50)}...' to channel=$channelId")
        logDebug(method, "Auth token present: ${accessToken != null}, token: ${maskToken(accessToken)}")

        return try {
            val request = SdkInteractRequest(message = message)
            logDebug(method, "Created SdkInteractRequest")

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
            logInfo(method, "Fetched ${messages.size} messages")
            messages
        } catch (e: Exception) {
            val errorMsg = e.message ?: ""
            val is401 = errorMsg.contains("401") || errorMsg.contains("Unauthorized", ignoreCase = true)
            logException(method, e, "limit=$limit, is401=$is401, tokenPresent=${accessToken != null}, tokenPreview=${maskToken(accessToken)}")
            throw e
        }
    }

    // System Status (from /v1/system/health)
    override suspend fun getSystemStatus(): SystemStatus {
        val method = "getSystemStatus"
        logDebug(method, "Fetching system health")

        return try {
            val response = systemApi.getSystemHealthV1SystemHealthGet()
            logDebug(method, "Response: status=${response.status}")

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")

            val healthyCount = data.services["healthy"]?.get("count") ?: 0
            val unhealthyCount = data.services["unhealthy"]?.get("count") ?: 0

            logInfo(method, "System status: ${data.status}, services: $healthyCount healthy, $unhealthyCount unhealthy")

            SystemStatus(
                status = data.status,
                cognitive_state = data.cognitiveState,
                services_online = healthyCount,
                services_total = healthyCount + unhealthyCount,
                services = emptyMap()
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
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
                oauthEmail = request.oauth_email
            )
            logDebug(method, "Created SdkSetupCompleteRequest")

            val response = setupApi.completeSetupV1SetupCompletePost(sdkRequest)
            logDebug(method, "Response: status=${response.status}")

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")

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
        logInfo(method, "Fetching current LLM configuration")
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

            // Detect if using CIRIS proxy by checking base URL
            val llmBaseUrl = data.llmBaseUrl ?: ""
            val isCirisProxy = llmBaseUrl.contains("ciris", ignoreCase = true) ||
                    llmBaseUrl.contains("llm.ciris", ignoreCase = true) ||
                    llmBaseUrl.contains("proxy", ignoreCase = true)

            logInfo(method, "LLM Config: provider=${data.llmProvider}, model=${data.llmModel}, " +
                    "baseUrl=$llmBaseUrl, isCirisProxy=$isCirisProxy, apiKeySet=${data.llmApiKeySet}")

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

    // ===== Billing API =====

    override suspend fun getCredits(): CreditStatusData {
        val method = "getCredits"
        logInfo(method, "Fetching credit status")

        return try {
            val response = billingApi.getCreditsV1ApiBillingCreditsGet(authHeader())
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            logInfo(method, "Credits: hasCredit=${body.hasCredit}, remaining=${body.creditsRemaining}, " +
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
            logInfo(method, "Adapters: total=${data.totalCount}, running=${data.runningCount}")

            AdaptersListData(
                adapters = data.adapters.map { adapter ->
                    AdapterStatusData(
                        adapterId = adapter.adapterId,
                        adapterType = adapter.adapterType,
                        isRunning = adapter.isRunning
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
                        serviceTypes = module.serviceTypes ?: emptyList(),
                        capabilities = module.capabilities ?: emptyList(),
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
                        serviceTypes = module.serviceTypes ?: emptyList(),
                        capabilities = module.capabilities ?: emptyList(),
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
     * Start an adapter configuration wizard session.
     */
    suspend fun startAdapterConfiguration(adapterType: String): ConfigSessionData {
        val method = "startAdapterConfiguration"
        logInfo(method, "Starting configuration for adapter type: $adapterType")

        return try {
            val response = systemApi.startAdapterConfigurationV1SystemAdaptersAdapterTypeConfigureStartPost(
                adapterType = adapterType,
                authorization = authHeader()
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
                sessionId = data.sessionId,
                adapterType = data.adapterType,
                status = data.status,
                currentStepIndex = data.currentStepIndex,
                totalSteps = data.totalSteps,
                currentStep = data.currentStep?.let { step ->
                    ConfigStepData(
                        stepId = step.stepId,
                        stepType = step.stepType,
                        title = step.title,
                        description = step.description,
                        required = step.required,
                        fields = step.fields?.map { field ->
                            ConfigFieldData(
                                name = field.name,
                                label = field.label,
                                fieldType = field.fieldType,
                                required = field.required,
                                defaultValue = field.defaultValue,
                                helpText = field.helpText
                            )
                        } ?: emptyList()
                    )
                }
            )
        } catch (e: Exception) {
            logException(method, e, "adapterType=$adapterType")
            throw e
        }
    }

    /**
     * Execute a step in the adapter configuration wizard.
     */
    suspend fun executeConfigurationStep(
        sessionId: String,
        stepData: Map<String, String>
    ): ConfigStepResultData {
        val method = "executeConfigurationStep"
        logInfo(method, "Executing config step for session: $sessionId")

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
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")
            // Determine if complete: no next step and not awaiting callback
            val isComplete = data.nextStepIndex == null && data.awaitingCallback != true
            logInfo(method, "Step result: success=${data.success}, nextStep=${data.nextStepIndex}, isComplete=$isComplete")

            ConfigStepResultData(
                success = data.success,
                message = data.error, // error message is the only message from this endpoint
                nextStepIndex = data.nextStepIndex,
                isComplete = isComplete,
                nextStep = null // Next step needs to be fetched from session status
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
            val response = wiseAuthorityApi.getWaStatusV1WaStatusGet(authHeader())
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")
            logInfo(method, "WA Status: healthy=${data.serviceHealthy}, activeWAs=${data.activeWas}, " +
                    "pendingDeferrals=${data.pendingDeferrals}, deferrals24h=${data.deferrals24h}")

            WAStatusData(
                serviceHealthy = data.serviceHealthy,
                activeWAs = data.activeWas,
                pendingDeferrals = data.pendingDeferrals,
                deferrals24h = data.deferrals24h,
                averageResolutionTimeMinutes = data.averageResolutionTimeMinutes,
                timestamp = data.timestamp
            )
        } catch (e: Exception) {
            logException(method, e)
            throw e
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
                        displayValue = config.`value`.toString(),
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
                displayValue = data.`value`.toString(),
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
                displayValue = data.`value`.toString(),
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
            val response = systemApi.getSystemHealthV1SystemHealthGet()
            logDebug(method, "Response: status=${response.status}")

            if (!response.success) {
                logError(method, "API returned non-success status: ${response.status}")
                throw RuntimeException("API error: HTTP ${response.status}")
            }

            val body = response.body()
            val data = body.`data` ?: throw RuntimeException("API returned null data")
            logInfo(method, "System health: status=${data.status}, cognitiveState=${data.cognitiveState}")

            SystemHealthData(
                status = data.status,
                cognitiveState = data.cognitiveState ?: "UNKNOWN"
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

            logInfo(method, "Telemetry: uptime=${data.uptimeSeconds}s, state=${data.cognitiveState}, " +
                    "services=$healthyServices/$healthyServices, " +
                    "cpu=$cpuPercent%, memory=${memoryMb}MB")

            UnifiedTelemetryData(
                health = if (degradedServices == 0) "healthy" else "degraded",
                uptime = "${(data.uptimeSeconds / 3600).toInt()}h ${((data.uptimeSeconds % 3600) / 60).toInt()}m",
                cognitiveState = data.cognitiveState,
                memoryMb = memoryMb.toInt(),
                memoryPercent = 0, // Not available from overview
                cpuPercent = cpuPercent.toInt(),
                diskUsedMb = 0.0, // Not available from overview
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
        logInfo(method, "Fetching environmental metrics")

        // Environmental metrics endpoint may not exist - return stub data
        return try {
            // Return stub data since the endpoint is not available
            EnvironmentalMetricsData(
                carbonGrams = 0.0,
                energyKwh = 0.0,
                costCents = 0.0,
                tokensLastHour = 0,
                tokens24h = 0
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
            // Note: This endpoint may not exist - return empty data if not available
            ChannelsData(channels = emptyList())
        } catch (e: Exception) {
            logException(method, e)
            throw e
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
            logInfo(method, "Fetching audit entries: severity=$severity, outcome=$outcome, limit=$limit, offset=$offset")

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
                logInfo(method, "Fetched ${data.propertyEntries.size} audit entries, total=${data.total}")

                AuditEntriesData(
                    entries = data.propertyEntries.map { entry ->
                        AuditEntryApiData(
                            id = entry.id,
                            action = entry.action,
                            actor = entry.actor,
                            timestamp = entry.timestamp ?: "",
                            context = entry.context.let { ctx ->
                                AuditContextApiData(
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
                                    metadata = null // Skip metadata to avoid parsing issues
                                )
                            },
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
                        createdAt = node.updatedAt,
                        updatedAt = node.updatedAt
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
                        createdAt = node.updatedAt,
                        updatedAt = node.updatedAt
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
                    createdAt = node.updatedAt,
                    updatedAt = node.updatedAt
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
            scope: String? = null,
            nodeType: String? = null,
            limit: Int = 100
        ): GraphDataResponse {
            val method = "getGraphData"
            logInfo(method, "Fetching graph data: hours=$hours, scope=$scope, type=$nodeType, limit=$limit")

            return try {
                // First get the timeline nodes
                val timelineResponse = memoryApi.getTimelineV1MemoryTimelineGet(
                    hours = hours,
                    scope = scope,
                    type = nodeType,
                    authorization = authHeader()
                )

                if (!timelineResponse.success) {
                    logError(method, "API returned non-success status: ${timelineResponse.status}")
                    throw RuntimeException("API error: HTTP ${timelineResponse.status}")
                }

                val timelineBody = timelineResponse.body()
                val timelineData = timelineBody.`data` ?: throw RuntimeException("API returned null data")
                val nodes = timelineData.memories.take(limit)

                logInfo(method, "Fetched ${nodes.size} nodes")

                // Now get edges for all nodes
                // Note: This could be optimized with a batch endpoint
                val allEdges = mutableListOf<ai.ciris.api.models.GraphEdge>()
                val nodeIds = nodes.map { it.id }.toSet()

                // Fetch edges for each node (limit to avoid too many requests)
                val nodesToFetchEdges = nodes.take(50)
                nodesToFetchEdges.forEach { node ->
                    try {
                        val edgesResponse = memoryApi.getNodeEdgesV1MemoryNodeIdEdgesGet(node.id, authHeader())
                        if (edgesResponse.success) {
                            val edges = edgesResponse.body().`data` ?: emptyList()
                            // Only include edges where both nodes are in our node set
                            edges.filter { edge ->
                                nodeIds.contains(edge.source) && nodeIds.contains(edge.target)
                            }.forEach { edge ->
                                // Avoid duplicates
                                if (allEdges.none { it.source == edge.source && it.target == edge.target && it.relationship == edge.relationship }) {
                                    allEdges.add(edge)
                                }
                            }
                        }
                    } catch (e: Exception) {
                        logWarn(method, "Failed to get edges for node ${node.id}: ${e.message}")
                    }
                }

                logInfo(method, "Graph data complete: ${nodes.size} nodes, ${allEdges.size} edges")

                GraphDataResponse(
                    nodes = nodes,
                    edges = allEdges
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

    override fun close() {
    logInfo("close", "Closing CIRISApiClient")
    }
}

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

data class SystemHealthData(
    val status: String,
    val cognitiveState: String
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
    val timestamp: String?
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
    val metadata: JsonObject? = null  // Dynamic JSON object for additional metadata
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
