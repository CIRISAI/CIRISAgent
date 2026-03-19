package ai.ciris.mobile.shared.viewmodels

import ai.ciris.api.models.DocumentPayload
import ai.ciris.api.models.ImagePayload
import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.ReasoningEvent
import ai.ciris.mobile.shared.api.ReasoningStreamClient
import ai.ciris.mobile.shared.ui.screens.graph.PipelineState
import ai.ciris.mobile.shared.auth.TokenManager
import ai.ciris.mobile.shared.models.ActionDetails
import ai.ciris.mobile.shared.models.ActionType
import ai.ciris.mobile.shared.models.ChatMessage
import ai.ciris.mobile.shared.models.MessageType
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.PickedFile
import ai.ciris.mobile.shared.platform.TestAutomation
import ai.ciris.mobile.shared.platform.createEnvFileUpdater
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.datetime.Clock

/**
 * A bubble emoji that floats up from the agent icon
 */
data class BubbleEmoji(
    val id: Long,
    val emoji: String
)

/**
 * A timeline event - minimal storage (emoji + timestamp + event type)
 */
data class TimelineEvent(
    val emoji: String,
    val eventType: String, // action name for display
    val timestamp: Long // epoch millis
)

/**
 * Agent processing state for the icon
 */
enum class AgentProcessingState {
    IDLE,       // 💭 - not processing
    PROCESSING  // 🔄 - actively processing
}

/**
 * Shared ViewModel for chat interface
 * Ported from Android InteractFragment.kt
 *
 * Features:
 * - Message history polling
 * - Agent status monitoring
 * - Processing status tracking via SSE bubbles
 * - Message submission
 * - Shutdown controls
 */
/**
 * LLM health status for status bar display
 */
data class LlmHealthStatus(
    val provider: String = "unknown",
    val isHealthy: Boolean = false,
    val model: String = "unknown",
    val isCirisProxy: Boolean = false
)

/**
 * Credit status for status bar display
 */
data class CreditStatus(
    val hasCredit: Boolean = false,
    val creditsRemaining: Int = 0,
    val freeUsesRemaining: Int = 0,
    val planName: String? = null,
    val isLoaded: Boolean = false
)

/**
 * Trust status for trust shield display
 */
data class TrustStatus(
    val maxLevel: Int = 0,
    val isLoaded: Boolean = false,
    val keyStatus: String = "none",
    val attestationStatus: String = "not_attempted",
    val levelPending: Boolean = false  // True when waiting for Play Integrity
)

class InteractViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "InteractViewModel"
        private const val POLL_INTERVAL_MS = 3000L
        private const val STATUS_POLL_INTERVAL_MS = 5000L
        private const val HEALTH_POLL_INTERVAL_MS = 30000L  // Less frequent health checks
        private const val TRUST_PENDING_POLL_INTERVAL_MS = 5000L  // Fast polling when Play Integrity pending
        private const val MAX_BUBBLES = 8
        private const val BUBBLE_LIFETIME_MS = 2000L
        private const val MAX_TIMELINE_EVENTS = 100
        private const val SSE_RECONNECT_BASE_MS = 1000L
        private const val SSE_RECONNECT_MAX_MS = 30000L
    }

    // Device attestation callback for triggering Play Integrity at startup
    private var deviceAttestationCallback: ai.ciris.mobile.shared.DeviceAttestationCallback? = null
    private var deviceAttestationTriggered = false  // Track if we've already triggered it

    /**
     * Set the device attestation callback for Play Integrity.
     * Should be called after ViewModel creation from CIRISApp.
     */
    fun setDeviceAttestationCallback(callback: ai.ciris.mobile.shared.DeviceAttestationCallback?) {
        logInfo("setDeviceAttestationCallback", "Device attestation callback ${if (callback != null) "SET" else "CLEARED"}")
        deviceAttestationCallback = callback
    }

    private fun log(level: String, method: String, message: String) {
        val fullMessage = "[$method] $message"
        when (level) {
            "DEBUG" -> PlatformLogger.d(TAG, fullMessage)
            "INFO" -> PlatformLogger.i(TAG, fullMessage)
            "WARN" -> PlatformLogger.w(TAG, fullMessage)
            "ERROR" -> PlatformLogger.e(TAG, fullMessage)
            else -> PlatformLogger.i(TAG, fullMessage)
        }
    }

    private fun logDebug(method: String, message: String) = log("DEBUG", method, message)
    private fun logInfo(method: String, message: String) = log("INFO", method, message)
    private fun logWarn(method: String, message: String) = log("WARN", method, message)
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    private val _messages = MutableStateFlow<List<ChatMessage>>(emptyList())
    val messages: StateFlow<List<ChatMessage>> = _messages.asStateFlow()

    private val _inputText = MutableStateFlow("")
    val inputText: StateFlow<String> = _inputText.asStateFlow()

    private val _isConnected = MutableStateFlow(false)
    val isConnected: StateFlow<Boolean> = _isConnected.asStateFlow()

    private val _agentStatus = MutableStateFlow("Initializing...")
    val agentStatus: StateFlow<String> = _agentStatus.asStateFlow()

    private val _isSending = MutableStateFlow(false)
    val isSending: StateFlow<Boolean> = _isSending.asStateFlow()

    private val _isLoading = MutableStateFlow(true)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _processingStatus = MutableStateFlow("")
    val processingStatus: StateFlow<String> = _processingStatus.asStateFlow()

    private val _authError = MutableStateFlow<String?>(null)
    val authError: StateFlow<String?> = _authError.asStateFlow()

    // Bubble emoji state - emojis float up from agent icon
    private val _bubbleEmojis = MutableStateFlow<List<BubbleEmoji>>(emptyList())
    val bubbleEmojis: StateFlow<List<BubbleEmoji>> = _bubbleEmojis.asStateFlow()

    // Agent processing state for icon
    private val _agentProcessingState = MutableStateFlow(AgentProcessingState.IDLE)
    val agentProcessingState: StateFlow<AgentProcessingState> = _agentProcessingState.asStateFlow()

    // SSE stream connected
    private val _sseConnected = MutableStateFlow(false)
    val sseConnected: StateFlow<Boolean> = _sseConnected.asStateFlow()

    // Timeline events - minimal storage for bubble net
    private val _timelineEvents = MutableStateFlow<List<TimelineEvent>>(emptyList())
    val timelineEvents: StateFlow<List<TimelineEvent>> = _timelineEvents.asStateFlow()

    // H3ERE pipeline scaffolding state - tracks which pipeline stages are active
    private val _pipelineState = MutableStateFlow(PipelineState())
    val pipelineState: StateFlow<PipelineState> = _pipelineState.asStateFlow()

    // Show timeline popup
    private val _showTimeline = MutableStateFlow(false)
    val showTimeline: StateFlow<Boolean> = _showTimeline.asStateFlow()

    // Show emoji legend popup
    private val _showLegend = MutableStateFlow(false)
    val showLegend: StateFlow<Boolean> = _showLegend.asStateFlow()

    // LLM health status for status bar
    private val _llmHealth = MutableStateFlow(LlmHealthStatus())
    val llmHealth: StateFlow<LlmHealthStatus> = _llmHealth.asStateFlow()

    // Credit status for status bar (only shown when isCirisProxy)
    private val _creditStatus = MutableStateFlow(CreditStatus())
    val creditStatus: StateFlow<CreditStatus> = _creditStatus.asStateFlow()

    // Trust status for shield display
    private val _trustStatus = MutableStateFlow(TrustStatus())
    val trustStatus: StateFlow<TrustStatus> = _trustStatus.asStateFlow()

    // File attachments for current message
    private val _attachedFiles = MutableStateFlow<List<PickedFile>>(emptyList())
    val attachedFiles: StateFlow<List<PickedFile>> = _attachedFiles.asStateFlow()

    private var pollingJob: Job? = null
    private var statusJob: Job? = null
    private var healthJob: Job? = null
    private var trustPollJob: Job? = null  // Separate fast polling for trust when pending
    private var sseJob: Job? = null
    private var isFirstLoad = true
    private var authErrorCount = 0
    private var bubbleIdCounter = 0L
    private var sseReconnectDelay = SSE_RECONNECT_BASE_MS

    // SSE client for reasoning stream
    private val sseClient = ReasoningStreamClient(
        baseUrl = apiClient.baseUrl,
        getToken = { apiClient.getAccessToken() }
    )

    // Track if polling has been started (to avoid duplicate starts)
    private var pollingStarted = false

    init {
        logInfo("init", "InteractViewModel initialized (polling deferred until token available)")
        // NOTE: Don't auto-start polling here - wait for startPolling() to be called
        // after auth token is set. This avoids 401 errors during startup.
    }

    /**
     * Start all polling and SSE streams.
     * Call this after the auth token has been set on the API client.
     */
    fun startPolling() {
        if (pollingStarted) {
            logDebug("startPolling", "Polling already started, skipping")
            return
        }
        logInfo("startPolling", "Starting polling and SSE streams")
        pollingStarted = true
        startStatusPolling()
        startMessagePolling()
        startHealthPolling()
        startSseStream()
        startFileInjectionObserver()
    }

    fun onInputTextChanged(text: String) {
        _inputText.value = text
    }

    /**
     * Add a file attachment to the current message.
     * Validates size and count limits before adding.
     */
    fun addAttachment(file: PickedFile) {
        val method = "addAttachment"
        val current = _attachedFiles.value
        if (current.size >= PickedFile.MAX_ATTACHMENTS) {
            logWarn(method, "Max attachments (${PickedFile.MAX_ATTACHMENTS}) reached, ignoring ${file.name}")
            return
        }
        if (file.sizeBytes > PickedFile.MAX_FILE_SIZE_BYTES) {
            logWarn(method, "File ${file.name} exceeds max size (${file.sizeBytes} > ${PickedFile.MAX_FILE_SIZE_BYTES})")
            return
        }
        logInfo(method, "Adding attachment: ${file.name} (${file.mediaType}, ${file.sizeBytes} bytes)")
        _attachedFiles.value = current + file
    }

    fun removeAttachment(index: Int) {
        val current = _attachedFiles.value
        if (index in current.indices) {
            logInfo("removeAttachment", "Removing attachment at index $index: ${current[index].name}")
            _attachedFiles.value = current.filterIndexed { i, _ -> i != index }
        }
    }

    fun clearAttachments() {
        _attachedFiles.value = emptyList()
    }

    /**
     * Observe test automation file injection requests.
     * When the test server injects a file, add it as an attachment.
     */
    private fun startFileInjectionObserver() {
        if (!TestAutomation.isEnabled()) return
        val method = "startFileInjectionObserver"
        logInfo(method, "Starting file injection observer for test automation")

        viewModelScope.launch {
            TestAutomation.fileInjectionRequests.collect { file ->
                if (file != null) {
                    logInfo(method, "Test automation injected file: ${file.name} (${file.mediaType})")
                    addAttachment(file)
                    TestAutomation.clearFileInjectionRequest()
                }
            }
        }
    }

    /**
     * Send message to agent
     */
    fun sendMessage() {
        val method = "sendMessage"
        val text = _inputText.value.trim()
        val files = _attachedFiles.value

        if (text.isEmpty() && files.isEmpty()) {
            logDebug(method, "Ignoring empty message with no attachments")
            return
        }
        if (_isSending.value) {
            logDebug(method, "Already sending, ignoring")
            return
        }

        logInfo(method, "Sending message: '${text.take(50)}...' with ${files.size} attachments")

        viewModelScope.launch {
            try {
                _isSending.value = true
                _processingStatus.value = "Sending message..."
                _inputText.value = ""
                _attachedFiles.value = emptyList()

                // Build attachment payloads
                val imagePayloads = files.filter { it.isImage }.map { file ->
                    ImagePayload(
                        data = file.dataBase64,
                        mediaType = file.mediaType,
                        filename = file.name
                    )
                }.ifEmpty { null }

                val documentPayloads = files.filter { it.isDocument }.map { file ->
                    DocumentPayload(
                        data = file.dataBase64,
                        mediaType = file.mediaType,
                        filename = file.name
                    )
                }.ifEmpty { null }

                // Add user message to chat immediately
                val displayText = if (text.isNotEmpty()) text else "Sent ${files.size} file${if (files.size > 1) "s" else ""}"
                val userMessage = ChatMessage(
                    id = generateMessageId(),
                    text = displayText,
                    type = MessageType.USER,
                    timestamp = Clock.System.now(),
                    attachmentCount = files.size,
                    attachmentNames = files.map { it.name },
                    hasImageAttachments = files.any { it.isImage },
                    hasDocumentAttachments = files.any { it.isDocument }
                )
                _messages.value = (_messages.value + userMessage).takeLast(50)

                logDebug(method, "Calling apiClient.sendMessage with ${imagePayloads?.size ?: 0} images, ${documentPayloads?.size ?: 0} documents")
                val response = apiClient.sendMessage(
                    message = if (text.isNotEmpty()) text else "Please review the attached file(s).",
                    images = imagePayloads,
                    documents = documentPayloads
                )
                logInfo(method, "Message sent successfully: messageId=${response.message_id}")

                // Add agent response to chat
                val agentResponse = response.response
                if (!agentResponse.isNullOrBlank()) {
                    logInfo(method, "Agent response: '${agentResponse.take(100)}...'")
                    val agentMessage = ChatMessage(
                        id = response.message_id,
                        text = agentResponse,
                        type = MessageType.AGENT,
                        timestamp = Clock.System.now(),
                        reasoning = response.reasoning
                    )
                    _messages.value = (_messages.value + agentMessage).takeLast(50)
                    _processingStatus.value = ""
                } else {
                    logWarn(method, "Empty response from agent")
                    _processingStatus.value = "Waiting for response..."
                }

            } catch (e: Exception) {
                logError(method, "Failed to send message: ${e::class.simpleName}: ${e.message}")
                logError(method, "Stack trace: ${e.stackTraceToString().take(500)}")

                // Check if this is a timeout error - suppress it since responses come via SSE
                val errorMsg = e.message ?: ""
                val isTimeoutError = errorMsg.contains("timeout", ignoreCase = true) ||
                                     errorMsg.contains("30000", ignoreCase = true) ||
                                     e::class.simpleName?.contains("Timeout", ignoreCase = true) == true

                if (isTimeoutError) {
                    // Timeout is expected for async processing - message will arrive via SSE
                    logInfo(method, "Timeout during send - response will arrive via SSE")
                    _processingStatus.value = "Processing..."
                } else {
                    val errorMessage = ChatMessage(
                        id = generateMessageId(),
                        text = "Failed to send message: ${e.message}",
                        type = MessageType.SYSTEM,
                        timestamp = Clock.System.now()
                    )
                    _messages.value = (_messages.value + errorMessage).takeLast(20)
                    _processingStatus.value = ""
                }
            } finally {
                _isSending.value = false
            }
        }
    }

    /**
     * Initiate shutdown
     */
    fun shutdown(emergency: Boolean = false) {
        val method = "shutdown"
        logInfo(method, "Initiating shutdown: emergency=$emergency")

        viewModelScope.launch {
            try {
                if (emergency) {
                    logWarn(method, "Emergency shutdown triggered")
                    apiClient.emergencyShutdown()
                } else {
                    logInfo(method, "Graceful shutdown triggered")
                    apiClient.initiateShutdown()
                }

                val statusMsg = if (emergency) "Emergency shutdown initiated" else "Shutdown initiated"
                logInfo(method, statusMsg)
                _processingStatus.value = statusMsg

                delay(3000)
                _processingStatus.value = ""

            } catch (e: Exception) {
                logError(method, "Shutdown failed: ${e::class.simpleName}: ${e.message}")
                _processingStatus.value = "Shutdown failed: ${e.message}"
                delay(3000)
                _processingStatus.value = ""
            }
        }
    }

    /**
     * Poll for agent status
     * Fast polls (200ms) until cognitive_state is available, then switches to normal interval
     */
    private fun startStatusPolling() {
        val method = "startStatusPolling"
        logInfo(method, "Starting status polling (fast until agent ready)")

        statusJob = viewModelScope.launch {
            var pollCount = 0
            var agentReady = false  // True once we get a real cognitive_state
            val FAST_POLL_MS = 200L

            while (isActive) {
                pollCount++
                try {
                    val status = apiClient.getSystemStatus()
                    val wasConnected = _isConnected.value
                    _isConnected.value = status.status == "healthy"

                    // Check if we got a real cognitive state
                    val cognitiveState = status.cognitive_state
                    if (cognitiveState != null) {
                        _agentStatus.value = cognitiveState.uppercase()
                        if (!agentReady) {
                            agentReady = true
                            logInfo(method, "Agent ready with state: ${_agentStatus.value}")
                        }
                    } else {
                        _agentStatus.value = "Starting..."
                    }

                    if (_isConnected.value != wasConnected) {
                        logInfo(method, "Connection state changed: ${wasConnected} -> ${_isConnected.value}")
                    }
                    if (pollCount % 10 == 0) {
                        logDebug(method, "Status poll #$pollCount: connected=${_isConnected.value}, state=${_agentStatus.value}")
                    }
                } catch (e: Exception) {
                    if (_isConnected.value) {
                        logError(method, "Status poll failed: ${e::class.simpleName}: ${e.message}")
                    }
                    _isConnected.value = false
                    _agentStatus.value = "Disconnected"
                }

                // Fast poll until agent ready, then normal interval
                delay(if (agentReady) STATUS_POLL_INTERVAL_MS else FAST_POLL_MS)
            }
        }
    }

    /**
     * Poll for LLM health, credits, and trust status (less frequent)
     * Fast polls (2s) until LLM health is loaded, then switches to normal interval.
     * Note: Using 2s to avoid rate limiting (429) from the /setup/config endpoint.
     */
    private fun startHealthPolling() {
        val method = "startHealthPolling"
        logInfo(method, "Starting health polling (fast until LLM ready)")

        healthJob = viewModelScope.launch {
            var llmReady = false  // True once LLM health is loaded successfully
            val FAST_HEALTH_POLL_MS = 2000L  // 2 seconds - avoid rate limiting

            while (isActive) {
                fetchHealthData()

                // Check if LLM health was loaded (provider is not "unknown" anymore)
                if (!llmReady && _llmHealth.value.provider != "unknown") {
                    llmReady = true
                    logInfo(method, "LLM health ready: provider=${_llmHealth.value.provider}")
                }

                // Fast poll until LLM ready, then normal interval
                delay(if (llmReady) HEALTH_POLL_INTERVAL_MS else FAST_HEALTH_POLL_MS)
            }
        }

        // Start separate fast trust polling for when Play Integrity is pending
        startTrustPendingPolling()
    }

    /**
     * Fast polling for trust status when Play Integrity is pending.
     * Polls every 5 seconds until Play Integrity completes, then stops.
     * Also triggers Play Integrity automatically if levelPending=true.
     */
    private fun startTrustPendingPolling() {
        val method = "startTrustPendingPolling"
        logInfo(method, "Starting trust pending polling (interval=${TRUST_PENDING_POLL_INTERVAL_MS}ms)")

        trustPollJob = viewModelScope.launch {
            // Wait a bit for initial health fetch to complete
            delay(2000)

            while (isActive) {
                // Fetch fresh trust status
                fetchTrustStatus()
                val currentTrust = _trustStatus.value

                // If levelPending is true, trigger Play Integrity if not already triggered
                if (currentTrust.levelPending) {
                    if (!deviceAttestationTriggered && deviceAttestationCallback != null) {
                        logInfo(method, "Level pending=true, triggering Play Integrity automatically...")
                        deviceAttestationTriggered = true
                        deviceAttestationCallback?.onDeviceAttestationRequested { result ->
                            logInfo(method, "Play Integrity completed: $result")
                        }
                    }
                    logDebug(method, "Level pending=true (level=${currentTrust.maxLevel}), continuing fast poll...")
                    delay(TRUST_PENDING_POLL_INTERVAL_MS)
                } else {
                    // Play Integrity is complete, stop fast polling
                    logInfo(method, "Level pending=false (level=${currentTrust.maxLevel}/5), stopping fast poll")
                    break
                }
            }
        }
    }

    /**
     * Fetch just trust status (for fast polling when pending)
     */
    private suspend fun fetchTrustStatus() {
        val method = "fetchTrustStatus"
        try {
            val verifyStatus = apiClient.getVerifyStatus()
            val previousLevel = _trustStatus.value.maxLevel
            val previousPending = _trustStatus.value.levelPending
            _trustStatus.value = TrustStatus(
                maxLevel = verifyStatus.maxLevel,
                isLoaded = verifyStatus.loaded,
                keyStatus = verifyStatus.keyStatus,
                attestationStatus = verifyStatus.attestationStatus,
                levelPending = verifyStatus.levelPending
            )
            if (verifyStatus.maxLevel != previousLevel) {
                logInfo(method, "Trust level changed: $previousLevel -> ${verifyStatus.maxLevel}")
            }
            if (verifyStatus.levelPending != previousPending) {
                logInfo(method, "Level pending changed: $previousPending -> ${verifyStatus.levelPending}")
            }
        } catch (e: Exception) {
            logWarn(method, "Failed to fetch trust status: ${e.message}")
        }
    }

    /**
     * Fetch LLM health, credits, and trust status
     */
    private suspend fun fetchHealthData() {
        val method = "fetchHealthData"
        try {
            // Fetch LLM config for health status
            // First try API, fall back to local .env file if API fails (e.g., 401)
            var configLoaded = false
            try {
                val config = apiClient.getLlmConfig()
                _llmHealth.value = LlmHealthStatus(
                    provider = config.provider,
                    isHealthy = config.apiKeySet || config.isCirisProxy,
                    model = config.model,
                    isCirisProxy = config.isCirisProxy
                )
                logDebug(method, "LLM health from API: provider=${config.provider}, isCirisProxy=${config.isCirisProxy}")
                configLoaded = true

                // Only fetch credits if using CIRIS proxy
                if (config.isCirisProxy) {
                    try {
                        val credits = apiClient.getCredits()
                        _creditStatus.value = CreditStatus(
                            hasCredit = credits.hasCredit,
                            creditsRemaining = credits.creditsRemaining,
                            freeUsesRemaining = credits.freeUsesRemaining,
                            planName = credits.planName,
                            isLoaded = true
                        )
                        logDebug(method, "Credits: remaining=${credits.creditsRemaining}")
                    } catch (e: Exception) {
                        logWarn(method, "Failed to fetch credits: ${e.message}")
                    }
                }
            } catch (e: Exception) {
                logWarn(method, "Failed to fetch LLM config from API: ${e.message}")
            }

            // Fallback: Read from local .env file if API failed
            if (!configLoaded && _llmHealth.value.provider == "unknown") {
                try {
                    val envConfig = createEnvFileUpdater().readLlmConfig()
                    if (envConfig != null) {
                        _llmHealth.value = LlmHealthStatus(
                            provider = envConfig.provider,
                            isHealthy = envConfig.apiKeySet || envConfig.isCirisProxy,
                            model = envConfig.model ?: "unknown",
                            isCirisProxy = envConfig.isCirisProxy
                        )
                        logInfo(method, "LLM health from .env fallback: provider=${envConfig.provider}, isCirisProxy=${envConfig.isCirisProxy}")
                    }
                } catch (e: Exception) {
                    logWarn(method, "Failed to read LLM config from .env: ${e.message}")
                }
            }

            // Fetch trust status (uses cached attestation from auth service)
            try {
                val verifyStatus = apiClient.getVerifyStatus()
                _trustStatus.value = TrustStatus(
                    maxLevel = verifyStatus.maxLevel,  // Use backend's authoritative level
                    isLoaded = verifyStatus.loaded,
                    keyStatus = verifyStatus.keyStatus,
                    attestationStatus = verifyStatus.attestationStatus,
                    levelPending = verifyStatus.levelPending
                )
                logDebug(method, "Trust: level=${verifyStatus.maxLevel}/5, keyStatus=${verifyStatus.keyStatus}, pending=${verifyStatus.levelPending}")
            } catch (e: Exception) {
                logWarn(method, "Failed to fetch trust status: ${e.message}")
            }
        } catch (e: Exception) {
            logWarn(method, "Health polling error: ${e.message}")
        }
    }

    /**
     * Refresh trust status (called when opening trust page)
     * Also restarts fast polling if Play Integrity is still pending.
     */
    fun refreshTrustStatus() {
        viewModelScope.launch {
            try {
                val verifyStatus = apiClient.getVerifyStatus()
                val previousLevel = _trustStatus.value.maxLevel
                _trustStatus.value = TrustStatus(
                    maxLevel = verifyStatus.maxLevel,  // Use backend's authoritative level
                    isLoaded = verifyStatus.loaded,
                    keyStatus = verifyStatus.keyStatus,
                    attestationStatus = verifyStatus.attestationStatus,
                    levelPending = verifyStatus.levelPending
                )

                // Log level change
                if (verifyStatus.maxLevel != previousLevel) {
                    logInfo("refreshTrustStatus", "Trust level changed: $previousLevel -> ${verifyStatus.maxLevel}")
                }

                // Restart fast polling if still pending and job isn't active
                if (verifyStatus.levelPending) {
                    if (trustPollJob?.isActive != true) {
                        logInfo("refreshTrustStatus", "Restarting fast trust polling (levelPending=true)")
                        startTrustPendingPolling()
                    }
                }
            } catch (e: Exception) {
                logWarn("refreshTrustStatus", "Failed: ${e.message}")
            }
        }
    }

    /**
     * Poll for message history and audit actions
     */
    private fun startMessagePolling() {
        val method = "startMessagePolling"
        logInfo(method, "Starting message polling (interval=${POLL_INTERVAL_MS}ms)")

        pollingJob = viewModelScope.launch {
            while (isActive) {
                try {
                    fetchHistory()
                    // Also fetch audit actions to show in timeline
                    fetchAuditActions()
                } catch (e: Exception) {
                    logError(method, "Message polling failed: ${e::class.simpleName}: ${e.message}")
                } finally {
                    if (isFirstLoad) {
                        logInfo(method, "First load complete")
                        _isLoading.value = false
                        isFirstLoad = false
                    }
                }
                delay(POLL_INTERVAL_MS)
            }
        }
    }

    /**
     * Fetch message history from API
     */
    fun clearAuthError() {
        _authError.value = null
        authErrorCount = 0
    }

    private suspend fun fetchHistory() {
        val method = "fetchHistory"
        try {
            val messages = apiClient.getMessages(limit = 50)
            // Success - clear any auth error
            if (_authError.value != null) {
                logInfo(method, "Auth restored, clearing error")
                _authError.value = null
                authErrorCount = 0
            }
            if (messages.isNotEmpty()) {
                logDebug(method, "Fetched ${messages.size} messages from API")
                // Deduplicate by ID (API might return same message from multiple channels)
                val deduplicatedMessages = messages
                    .distinctBy { it.id }
                    .sortedBy { it.timestamp }
                    .takeLast(50)

                // Check if there are new messages
                val existingIds = _messages.value.map { it.id }.toSet()
                val newMessages = deduplicatedMessages.filter { it.id !in existingIds }
                if (newMessages.isNotEmpty()) {
                    logInfo(method, "Adding ${newMessages.size} new messages to chat")
                    // Merge with existing messages to preserve action entries
                    // Use content + timestamp window deduplication for USER messages
                    // (local ID vs server ID differ, but we don't want to collapse
                    // legitimately repeated messages like "ok" sent at different times)
                    val allMessages = (_messages.value + deduplicatedMessages)
                        .distinctBy { msg ->
                            when (msg.type) {
                                MessageType.USER -> {
                                    // Dedupe USER messages by content + timestamp window (5 sec)
                                    // This handles local-vs-server ID mismatch while preserving
                                    // intentionally repeated messages sent at different times
                                    val timestampWindow = msg.timestamp.toEpochMilliseconds() / 5000 // 5-second buckets
                                    "USER:${msg.text}:$timestampWindow"
                                }
                                MessageType.AGENT -> {
                                    // Dedupe AGENT messages by content + timestamp window (10 sec)
                                    // Local response (from sendMessage) and server history have different IDs
                                    val timestampWindow = msg.timestamp.toEpochMilliseconds() / 10000 // 10-second buckets
                                    "AGENT:${msg.text}:$timestampWindow"
                                }
                                else -> msg.id // ACTION messages use ID
                            }
                        }
                        .sortedBy { it.timestamp }
                        .takeLast(50)
                    _messages.value = allMessages
                }
            }
        } catch (e: Exception) {
            // Check for auth errors (401)
            val errorMessage = e.message ?: ""
            val isAuthError = errorMessage.contains("401") ||
                              errorMessage.contains("Unauthorized", ignoreCase = true) ||
                              errorMessage.contains("authentication", ignoreCase = true)

            if (isAuthError) {
                authErrorCount++
                logWarn(method, "Auth error #$authErrorCount: $errorMessage")
                // On first auth error, trigger automatic token refresh via TokenManager
                if (authErrorCount == 1) {
                    logInfo(method, "Triggering automatic token refresh via TokenManager")
                    TokenManager.shared?.on401Error()
                }
                // Only show error after 3 consecutive failures to avoid flashing during token refresh
                if (authErrorCount >= 3 && _authError.value == null) {
                    logError(method, "Persistent auth error (3+ failures) - showing UI notification")
                    _authError.value = "Session expired. Please sign in again."
                }
            } else {
                logWarn(method, "Non-auth error: ${e::class.simpleName}: $errorMessage")
            }

            // Log on first load
            if (isFirstLoad) {
                logWarn(method, "Failed to fetch history on first load: ${e.message}")
            }
        }
    }

    // Track action IDs we've already added to avoid duplicates
    private val addedActionIds = mutableSetOf<String>()

    /**
     * Fetch recent audit actions and add them to the chat timeline.
     * Called on load and during polling to keep timeline up to date.
     */
    private suspend fun fetchAuditActions() {
        val method = "fetchAuditActions"

        try {
            // Fetch recent audit entries (all types, we'll filter by action types)
            val entries = apiClient.getAuditEntries(
                limit = 50,
                offset = 0
            )

            if (entries.entries.isEmpty()) {
                return
            }

            val newActionMessages = mutableListOf<ChatMessage>()

            // Get current message IDs to check if actions need re-adding after history refresh
            val currentMessageIds = _messages.value.map { it.id }.toSet()

            logDebug(method, "Processing ${entries.entries.size} entries, currentMessageIds=${currentMessageIds.size}")
            for (entry in entries.entries) {
                val actionMessageId = "action_${entry.id}"

                // Skip if already in current messages (already displayed)
                if (actionMessageId in currentMessageIds) {
                    continue
                }

                // Check if this is one of the 10 action types
                val actionType = ActionType.fromAuditEventType(entry.action)
                if (actionType == null) {
                    continue
                }

                // Skip SPEAK and TASK_COMPLETE - not interesting for timeline display
                // SPEAK is already shown as a chat message, TASK_COMPLETE is just a marker
                if (actionType == ActionType.SPEAK || actionType == ActionType.TASK_COMPLETE) {
                    continue
                }

                logDebug(method, "ADD ${entry.id}: ${actionType.name} from '${entry.action}'")


                // Track that we've processed this entry (for SSE deduplication)
                addedActionIds.add(entry.id)

                // Extract details from metadata
                val metadata = entry.context?.metadata
                val outcome = entry.context?.outcome
                    ?: metadata?.get("outcome")?.jsonPrimitiveContent()
                    ?: "success"
                val description = entry.context?.description
                    ?: metadata?.get("description")?.jsonPrimitiveContent()

                // Build action-specific details
                val actionDetails = buildActionDetails(actionType, outcome, entry.id, description, metadata)

                // Parse timestamp
                val timestamp = try {
                    kotlinx.datetime.Instant.parse(entry.timestamp)
                } catch (e: Exception) {
                    Clock.System.now()
                }

                val actionMessage = ChatMessage(
                    id = "action_${entry.id}",
                    text = actionType.displayName,
                    type = MessageType.ACTION,
                    timestamp = timestamp,
                    actionDetails = actionDetails
                )

                newActionMessages.add(actionMessage)
            }

            if (newActionMessages.isNotEmpty()) {
                logInfo(method, "Adding ${newActionMessages.size} action entries to timeline")

                // Merge with existing messages, sort by timestamp, keep last 50
                val allMessages = (_messages.value + newActionMessages)
                    .distinctBy { it.id }
                    .sortedBy { it.timestamp }
                    .takeLast(50)

                _messages.value = allMessages
            }

        } catch (e: Exception) {
            // Don't log errors on every poll, only on first failure
            if (isFirstLoad) {
                logWarn(method, "Failed to fetch audit actions: ${e.message}")
            }
        }
    }

    /**
     * Build ActionDetails from audit entry metadata
     */
    private fun buildActionDetails(
        actionType: ActionType,
        outcome: String,
        auditEntryId: String,
        description: String?,
        metadata: kotlinx.serialization.json.JsonObject?
    ): ActionDetails {
        return when (actionType) {
            ActionType.TOOL -> {
                val toolName = metadata?.get("tool_name")?.jsonPrimitiveContent() ?: "Unknown Tool"
                val toolAdapter = metadata?.get("tool_adapter")?.jsonPrimitiveContent() ?: "unknown"
                val toolParameters = parseToolParameters(metadata?.get("tool_parameters"))

                ActionDetails(
                    actionType = actionType,
                    outcome = outcome,
                    auditEntryId = auditEntryId,
                    description = description,
                    toolName = toolName,
                    toolAdapter = toolAdapter,
                    toolParameters = toolParameters
                )
            }
            ActionType.MEMORIZE, ActionType.RECALL, ActionType.FORGET -> {
                val memoryKey = metadata?.get("memory_key")?.jsonPrimitiveContent()
                    ?: metadata?.get("key")?.jsonPrimitiveContent()
                val memoryContent = metadata?.get("content")?.jsonPrimitiveContent()
                    ?: metadata?.get("value")?.jsonPrimitiveContent()

                ActionDetails(
                    actionType = actionType,
                    outcome = outcome,
                    auditEntryId = auditEntryId,
                    description = description,
                    memoryKey = memoryKey,
                    memoryContent = memoryContent
                )
            }
            ActionType.DEFER -> {
                val deferReason = metadata?.get("reason")?.jsonPrimitiveContent()
                    ?: metadata?.get("defer_reason")?.jsonPrimitiveContent()
                val deferTarget = metadata?.get("target")?.jsonPrimitiveContent()
                    ?: metadata?.get("wise_authority")?.jsonPrimitiveContent()

                ActionDetails(
                    actionType = actionType,
                    outcome = outcome,
                    auditEntryId = auditEntryId,
                    description = description,
                    deferReason = deferReason,
                    deferTarget = deferTarget
                )
            }
            ActionType.REJECT -> {
                val rejectReason = metadata?.get("reason")?.jsonPrimitiveContent()
                    ?: metadata?.get("reject_reason")?.jsonPrimitiveContent()

                ActionDetails(
                    actionType = actionType,
                    outcome = outcome,
                    auditEntryId = auditEntryId,
                    description = description,
                    rejectReason = rejectReason
                )
            }
            ActionType.PONDER -> {
                val ponderTopic = metadata?.get("topic")?.jsonPrimitiveContent()
                    ?: metadata?.get("ponder_topic")?.jsonPrimitiveContent()

                // Parse ponder_questions from the double-encoded parameters JSON string
                val ponderQuestions = parsePonderQuestions(metadata?.get("parameters"))

                ActionDetails(
                    actionType = actionType,
                    outcome = outcome,
                    auditEntryId = auditEntryId,
                    description = description,
                    ponderTopic = ponderTopic,
                    ponderQuestions = ponderQuestions
                )
            }
            else -> {
                // SPEAK, OBSERVE, TASK_COMPLETE - just basic details
                ActionDetails(
                    actionType = actionType,
                    outcome = outcome,
                    auditEntryId = auditEntryId,
                    description = description
                )
            }
        }
    }

    /**
     * Trigger an immediate refresh of audit actions when an SSE emoji event is received.
     * This provides live updates to the timeline when actions occur.
     */
    private fun fetchAndAddLatestAction(actionType: ActionType) {
        val method = "fetchAndAddLatestAction"
        logDebug(method, "SSE triggered refresh for ${actionType.name}")

        // Trigger immediate fetch of audit actions
        viewModelScope.launch {
            // Small delay to allow audit entry to be written
            delay(500)
            fetchAuditActions()
        }
    }

    /**
     * Helper to extract string content from JsonElement
     */
    private fun kotlinx.serialization.json.JsonElement?.jsonPrimitiveContent(): String? {
        return when (this) {
            is kotlinx.serialization.json.JsonPrimitive -> this.content
            else -> this?.toString()
        }
    }

    /**
     * Parse tool parameters from a JSON element (may be string or object)
     */
    private fun parseToolParameters(element: kotlinx.serialization.json.JsonElement?): Map<String, String> {
        if (element == null) return emptyMap()

        val parameters = mutableMapOf<String, String>()
        try {
            val paramsContent = when (element) {
                is kotlinx.serialization.json.JsonPrimitive -> element.content
                is kotlinx.serialization.json.JsonObject -> {
                    // Already an object, extract directly
                    element.forEach { (key, value) ->
                        parameters[key] = value.jsonPrimitiveContent() ?: value.toString()
                    }
                    return parameters
                }
                else -> element.toString()
            }

            // Parse JSON string - handle double-quoted strings like "{...}"
            var jsonToParse = paramsContent.trim()
            // Strip outer quotes if present (double-encoded JSON)
            if (jsonToParse.startsWith("\"") && jsonToParse.endsWith("\"")) {
                jsonToParse = jsonToParse.drop(1).dropLast(1)
            }
            // Unescape escaped quotes and backslashes
            jsonToParse = jsonToParse
                .replace("\\\"", "\"")
                .replace("\\\\", "\\")

            if (jsonToParse.startsWith("{")) {
                val parsed = kotlinx.serialization.json.Json.parseToJsonElement(jsonToParse)
                if (parsed is kotlinx.serialization.json.JsonObject) {
                    parsed.forEach { (key, value) ->
                        parameters[key] = when (value) {
                            is kotlinx.serialization.json.JsonPrimitive -> value.content
                            else -> value.toString()
                        }
                    }
                }
            }
        } catch (e: Exception) {
            // Ignore parse errors - return empty parameters
        }
        return parameters
    }

    /**
     * Parse ponder questions from double-encoded parameters JSON.
     * The parameters field contains a JSON string like:
     * "{\"ponder_questions\": \"[\\\"Question 1\\\", \\\"Question 2\\\"]\", ...}"
     */
    private fun parsePonderQuestions(parametersElement: kotlinx.serialization.json.JsonElement?): List<String> {
        if (parametersElement == null) return emptyList()

        try {
            // First, get the parameters string
            val parametersStr = parametersElement.jsonPrimitiveContent() ?: return emptyList()

            // Parse the outer JSON
            val paramsJson = kotlinx.serialization.json.Json.parseToJsonElement(parametersStr)
            if (paramsJson !is kotlinx.serialization.json.JsonObject) return emptyList()

            // Get the ponder_questions field (which is also a JSON-encoded string)
            val questionsElement = paramsJson["ponder_questions"] ?: return emptyList()
            val questionsStr = when (questionsElement) {
                is kotlinx.serialization.json.JsonPrimitive -> questionsElement.content
                else -> questionsElement.toString()
            }

            // Parse the questions array
            val questionsJson = kotlinx.serialization.json.Json.parseToJsonElement(questionsStr)
            if (questionsJson !is kotlinx.serialization.json.JsonArray) return emptyList()

            return questionsJson.mapNotNull { element ->
                when (element) {
                    is kotlinx.serialization.json.JsonPrimitive -> element.content
                    else -> null
                }
            }
        } catch (e: Exception) {
            logDebug("parsePonderQuestions", "Failed to parse: ${e.message}")
            return emptyList()
        }
    }

    /**
     * Update processing status
     */
    fun updateProcessingStatus(eventType: String, action: String? = null) {
        val method = "updateProcessingStatus"
        logDebug(method, "Event: $eventType, action: $action")

        val statusText = when (eventType) {
            "thought_start" -> "Thinking..."
            "snapshot_and_context" -> "Gathering context..."
            "dma_results" -> "Evaluating..."
            "aspdma_result" -> "Selecting action: ${action ?: "..."}"
            "conscience_result" -> "Checking ethics..."
            "action_result" -> {
                when {
                    action?.contains("speak") == true -> "Speaking..."
                    action?.contains("task_complete") == true -> "Complete"
                    action?.contains("memorize") == true -> "Saving to memory..."
                    action?.contains("recall") == true -> "Recalling..."
                    action?.contains("tool") == true -> "Using tool..."
                    action?.contains("ponder") == true -> "Pondering..."
                    action?.contains("defer") == true -> "Deferred"
                    else -> "Executing: ${action ?: "action"}"
                }
            }
            "idle" -> "Idle"
            else -> eventType.replace("_", " ").replaceFirstChar { it.uppercase() }
        }

        _processingStatus.value = statusText

        if (eventType == "action_result" &&
            (action?.contains("task_complete") == true || action?.contains("task_reject") == true)) {
            viewModelScope.launch {
                delay(3000)
                if (_processingStatus.value == statusText) {
                    _processingStatus.value = ""
                }
            }
        }
    }

    private fun generateMessageId(): String {
        return "msg_${Clock.System.now().toEpochMilliseconds()}"
    }

    /**
     * Toggle timeline visibility
     */
    fun toggleTimeline() {
        _showTimeline.value = !_showTimeline.value
    }

    /**
     * Toggle emoji legend visibility
     */
    fun toggleLegend() {
        _showLegend.value = !_showLegend.value
    }

    /**
     * Start SSE stream for live reasoning events with robust reconnection
     */
    private fun startSseStream() {
        val method = "startSseStream"
        logInfo(method, "Starting SSE reasoning stream")

        sseJob = viewModelScope.launch {
            while (isActive) {
                try {
                    sseClient.connect().collect { event ->
                        when (event) {
                            is ReasoningEvent.Connected -> {
                                logInfo(method, "SSE connected")
                                _sseConnected.value = true
                                sseReconnectDelay = SSE_RECONNECT_BASE_MS // Reset on success
                            }
                            is ReasoningEvent.Disconnected -> {
                                logInfo(method, "SSE disconnected")
                                _sseConnected.value = false
                                _agentProcessingState.value = AgentProcessingState.IDLE
                            }
                            is ReasoningEvent.PipelineStep -> {
                                // Update pipeline scaffolding visualization
                                val now = Clock.System.now().toEpochMilliseconds()
                                if (event.isNewThought) {
                                    // New thought round - reset then activate
                                    _pipelineState.value = _pipelineState.value
                                        .reset()
                                        .activate(event.eventType, now)
                                } else {
                                    _pipelineState.value = _pipelineState.value
                                        .activate(event.eventType, now)
                                }
                            }
                            is ReasoningEvent.Emoji -> {
                                // Add bubble emoji (floats up and disappears)
                                addBubbleEmoji(event.emoji)

                                // Add to timeline (persists for bubble net)
                                addTimelineEvent(event.emoji, event.eventType)

                                // Check if this is one of the 10 CIRIS action emojis
                                val actionType = ActionType.fromEmoji(event.emoji)
                                if (actionType != null) {
                                    fetchAndAddLatestAction(actionType)
                                }

                                // Update processing state and status text
                                if (event.isComplete) {
                                    _agentProcessingState.value = AgentProcessingState.IDLE
                                    // Clear processing status text when task completes
                                    _processingStatus.value = ""
                                } else {
                                    _agentProcessingState.value = AgentProcessingState.PROCESSING
                                }
                            }
                        }
                    }
                } catch (e: Exception) {
                    logError(method, "SSE error: ${e.message}")
                    _sseConnected.value = false
                }

                // Exponential backoff reconnection
                logInfo(method, "Reconnecting in ${sseReconnectDelay}ms...")
                delay(sseReconnectDelay)
                sseReconnectDelay = (sseReconnectDelay * 2).coerceAtMost(SSE_RECONNECT_MAX_MS)
            }
        }
    }

    /**
     * Add a bubble emoji that floats up
     */
    private fun addBubbleEmoji(emoji: String) {
        val bubbleId = bubbleIdCounter++
        val bubble = BubbleEmoji(id = bubbleId, emoji = emoji)

        // Add to list (keep max bubbles)
        _bubbleEmojis.value = (_bubbleEmojis.value + bubble).takeLast(MAX_BUBBLES)

        // Remove after animation completes
        viewModelScope.launch {
            delay(BUBBLE_LIFETIME_MS)
            _bubbleEmojis.value = _bubbleEmojis.value.filter { it.id != bubbleId }
        }
    }

    /**
     * Add event to timeline (minimal storage for bubble net)
     */
    private fun addTimelineEvent(emoji: String, eventType: String) {
        val event = TimelineEvent(
            emoji = emoji,
            eventType = formatEventTypeName(eventType),
            timestamp = Clock.System.now().toEpochMilliseconds()
        )
        _timelineEvents.value = (_timelineEvents.value + event).takeLast(MAX_TIMELINE_EVENTS)
    }

    /**
     * Format event type for display (e.g., "action_result" -> "Action Result")
     */
    private fun formatEventTypeName(eventType: String): String {
        return eventType
            .replace("_", " ")
            .split(" ")
            .joinToString(" ") { word ->
                word.replaceFirstChar { it.uppercase() }
            }
    }

    /**
     * Clear timeline events
     */
    fun clearTimeline() {
        _timelineEvents.value = emptyList()
    }

    override fun onCleared() {
        logInfo("onCleared", "ViewModel cleared, cancelling jobs")
        super.onCleared()
        pollingJob?.cancel()
        statusJob?.cancel()
        healthJob?.cancel()
        trustPollJob?.cancel()
        sseJob?.cancel()
    }
}
