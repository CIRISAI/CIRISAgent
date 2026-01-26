package ai.ciris.mobile.shared.api

import ai.ciris.mobile.shared.models.*
import ai.ciris.mobile.shared.viewmodels.SetupCompletionResult
import ai.ciris.mobile.shared.viewmodels.StateTransitionResult
import ai.ciris.api.apis.*
import ai.ciris.api.models.InteractRequest as SdkInteractRequest
import ai.ciris.api.models.LoginRequest as SdkLoginRequest
import ai.ciris.api.models.SetupCompleteRequest as SdkSetupCompleteRequest
import ai.ciris.api.models.ShutdownRequest as SdkShutdownRequest
import ai.ciris.api.models.NativeTokenRequest as SdkNativeTokenRequest
import ai.ciris.api.models.StateTransitionRequest as SdkStateTransitionRequest
import io.ktor.client.*
import io.ktor.client.plugins.*
import io.ktor.client.plugins.contentnegotiation.*
import io.ktor.client.plugins.logging.*
import io.ktor.serialization.kotlinx.json.*
import kotlinx.datetime.Instant
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive

/**
 * Unified API client for CIRIS backend using the generated OpenAPI SDK.
 * This client wraps the generated API classes and provides a clean interface.
 *
 * All methods include comprehensive error logging for debugging.
 */
class CIRISApiClient(
    private val baseUrl: String = "http://localhost:8080",
    private var accessToken: String? = null
) : CIRISApiClientProtocol {

    companion object {
        private const val TAG = "CIRISApiClient"

        // Mask token for logging (show first 8 and last 4 chars)
        private fun maskToken(token: String?): String {
            if (token == null) return "null"
            if (token.length <= 16) return "***"
            return "${token.take(8)}...${token.takeLast(4)}"
        }
    }

    private fun log(level: String, method: String, message: String) {
        println("[$TAG][$level][$method] $message")
    }

    private fun logDebug(method: String, message: String) = log("DEBUG", method, message)
    private fun logInfo(method: String, message: String) = log("INFO", method, message)
    private fun logWarn(method: String, message: String) = log("WARN", method, message)
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    private fun logException(method: String, e: Exception, context: String = "") {
        val contextStr = if (context.isNotEmpty()) " | Context: $context" else ""
        logError(method, "Exception: ${e::class.simpleName}: ${e.message}$contextStr")
        logError(method, "Stack trace: ${e.stackTraceToString().take(500)}")
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
            logInfo(method, "Bearer token set on all API instances (7 APIs)")
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

    override fun close() {
        logInfo("close", "Closing CIRISApiClient")
    }
}

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
