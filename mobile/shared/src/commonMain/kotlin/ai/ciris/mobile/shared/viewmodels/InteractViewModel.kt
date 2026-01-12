package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
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
 * Shared ViewModel for chat interface
 * Ported from Android InteractFragment.kt
 *
 * Features:
 * - Message history polling
 * - Agent status monitoring
 * - Processing status tracking
 * - Message submission
 * - Shutdown controls
 */
class InteractViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

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

    private var pollingJob: Job? = null
    private var statusJob: Job? = null
    private var isFirstLoad = true

    companion object {
        private const val POLL_INTERVAL_MS = 3000L // From InteractFragment.kt:135
        private const val STATUS_POLL_INTERVAL_MS = 5000L // From InteractFragment.kt:136
    }

    init {
        startStatusPolling()
        startMessagePolling()
    }

    fun onInputTextChanged(text: String) {
        _inputText.value = text
    }

    /**
     * Send message to agent
     * From InteractFragment.kt:980-1112
     */
    fun sendMessage() {
        val text = _inputText.value.trim()
        if (text.isEmpty() || _isSending.value) return

        viewModelScope.launch {
            try {
                _isSending.value = true
                _processingStatus.value = "Sending message..."

                // Clear input immediately for better UX
                _inputText.value = ""

                // Send to API using /v1/agent/message endpoint
                val response = apiClient.sendMessage(text)

                // Show processing status
                _processingStatus.value = "Processing..."

                // The message will appear in history via polling
                // This matches Android behavior where we don't add messages optimistically

            } catch (e: Exception) {
                println("Failed to send message: ${e.message}")
                // Add error message
                val errorMessage = ChatMessage(
                    id = generateMessageId(),
                    text = "Failed to send message: ${e.message}",
                    type = MessageType.SYSTEM,
                    timestamp = Clock.System.now()
                )
                _messages.value = (_messages.value + errorMessage).takeLast(20)
                _processingStatus.value = ""
            } finally {
                _isSending.value = false
            }
        }
    }

    /**
     * Initiate shutdown
     * From InteractFragment.kt:1149-1191
     */
    fun shutdown(emergency: Boolean = false) {
        viewModelScope.launch {
            try {
                val reason = if (emergency) {
                    "Emergency stop triggered by user"
                } else {
                    "User requested graceful shutdown"
                }

                if (emergency) {
                    apiClient.emergencyShutdown()
                } else {
                    apiClient.initiateShutdown()
                }

                // Show status message
                val statusMsg = if (emergency) {
                    "Emergency shutdown initiated"
                } else {
                    "Shutdown initiated"
                }
                _processingStatus.value = statusMsg

                // Clear after delay
                delay(3000)
                _processingStatus.value = ""

            } catch (e: Exception) {
                println("Shutdown failed: ${e.message}")
                _processingStatus.value = "Shutdown failed: ${e.message}"
                delay(3000)
                _processingStatus.value = ""
            }
        }
    }

    /**
     * Poll for agent status
     * From InteractFragment.kt:300-307 and 678-709
     */
    private fun startStatusPolling() {
        statusJob = viewModelScope.launch {
            while (isActive) {
                try {
                    val status = apiClient.getSystemStatus()
                    _isConnected.value = status.status == "healthy"
                    _agentStatus.value = status.cognitive_state ?: "Unknown"
                } catch (e: Exception) {
                    _isConnected.value = false
                    _agentStatus.value = "Disconnected"
                }
                delay(STATUS_POLL_INTERVAL_MS)
            }
        }
    }

    /**
     * Poll for message history
     * From InteractFragment.kt:291-298 and 564-609
     */
    private fun startMessagePolling() {
        pollingJob = viewModelScope.launch {
            while (isActive) {
                try {
                    fetchHistory()
                } catch (e: Exception) {
                    println("Message polling failed: ${e.message}")
                } finally {
                    if (isFirstLoad) {
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
     * From InteractFragment.kt:588-609
     */
    private suspend fun fetchHistory() {
        try {
            // Fetch last 20 messages from API
            // NOTE: This is a placeholder - actual implementation would call
            // apiClient.getHistory(channelId = "mobile_app", limit = 20)
            // For now, we just maintain the current messages

            // In production, parse history response and update messages:
            // val historyResponse = apiClient.getHistory(...)
            // val newMessages = historyResponse.messages.map { ... }
            // _messages.value = newMessages

        } catch (e: Exception) {
            println("Failed to fetch history: ${e.message}")
        }
    }

    /**
     * Update processing status
     * From InteractFragment.kt:525-562
     */
    fun updateProcessingStatus(eventType: String, action: String? = null) {
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

        // Auto-hide after completion
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

    override fun onCleared() {
        super.onCleared()
        pollingJob?.cancel()
        statusJob?.cancel()
    }
}
