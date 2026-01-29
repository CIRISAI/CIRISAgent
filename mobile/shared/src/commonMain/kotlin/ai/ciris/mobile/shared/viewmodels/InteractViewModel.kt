package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.ReasoningEvent
import ai.ciris.mobile.shared.api.ReasoningStreamClient
import ai.ciris.mobile.shared.models.ChatMessage
import ai.ciris.mobile.shared.models.MessageType
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
class InteractViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "InteractViewModel"
        private const val POLL_INTERVAL_MS = 3000L
        private const val STATUS_POLL_INTERVAL_MS = 5000L
        private const val MAX_BUBBLES = 8
        private const val BUBBLE_LIFETIME_MS = 2000L
        private const val MAX_TIMELINE_EVENTS = 100
        private const val SSE_RECONNECT_BASE_MS = 1000L
        private const val SSE_RECONNECT_MAX_MS = 30000L
    }

    private fun log(level: String, method: String, message: String) {
        println("[$TAG][$level][$method] $message")
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

    // Show timeline popup
    private val _showTimeline = MutableStateFlow(false)
    val showTimeline: StateFlow<Boolean> = _showTimeline.asStateFlow()

    // Show emoji legend popup
    private val _showLegend = MutableStateFlow(false)
    val showLegend: StateFlow<Boolean> = _showLegend.asStateFlow()

    private var pollingJob: Job? = null
    private var statusJob: Job? = null
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

    init {
        logInfo("init", "InteractViewModel initialized")
        startStatusPolling()
        startMessagePolling()
        startSseStream()
    }

    fun onInputTextChanged(text: String) {
        _inputText.value = text
    }

    /**
     * Send message to agent
     */
    fun sendMessage() {
        val method = "sendMessage"
        val text = _inputText.value.trim()

        if (text.isEmpty()) {
            logDebug(method, "Ignoring empty message")
            return
        }
        if (_isSending.value) {
            logDebug(method, "Already sending, ignoring")
            return
        }

        logInfo(method, "Sending message: '${text.take(50)}...'")

        viewModelScope.launch {
            try {
                _isSending.value = true
                _processingStatus.value = "Sending message..."
                _inputText.value = ""

                // Add user message to chat immediately
                val userMessage = ChatMessage(
                    id = generateMessageId(),
                    text = text,
                    type = MessageType.USER,
                    timestamp = Clock.System.now()
                )
                _messages.value = (_messages.value + userMessage).takeLast(50)

                logDebug(method, "Calling apiClient.sendMessage")
                val response = apiClient.sendMessage(text)
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
     */
    private fun startStatusPolling() {
        val method = "startStatusPolling"
        logInfo(method, "Starting status polling (interval=${STATUS_POLL_INTERVAL_MS}ms)")

        statusJob = viewModelScope.launch {
            var pollCount = 0
            while (isActive) {
                pollCount++
                try {
                    val status = apiClient.getSystemStatus()
                    val wasConnected = _isConnected.value
                    _isConnected.value = status.status == "healthy"
                    _agentStatus.value = status.cognitive_state ?: "Unknown"

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
                delay(STATUS_POLL_INTERVAL_MS)
            }
        }
    }

    /**
     * Poll for message history
     */
    private fun startMessagePolling() {
        val method = "startMessagePolling"
        logInfo(method, "Starting message polling (interval=${POLL_INTERVAL_MS}ms)")

        pollingJob = viewModelScope.launch {
            while (isActive) {
                try {
                    fetchHistory()
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
                    _messages.value = deduplicatedMessages
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
                            is ReasoningEvent.Emoji -> {
                                // Add bubble emoji (floats up and disappears)
                                addBubbleEmoji(event.emoji)

                                // Add to timeline (persists for bubble net)
                                addTimelineEvent(event.emoji, event.eventType)

                                // Update processing state
                                if (event.isComplete) {
                                    _agentProcessingState.value = AgentProcessingState.IDLE
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
        sseJob?.cancel()
    }
}
