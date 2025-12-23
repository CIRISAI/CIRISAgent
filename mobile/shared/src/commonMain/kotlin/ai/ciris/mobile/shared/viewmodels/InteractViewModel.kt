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
 * Based on InteractActivity.kt (android/app/src/main/java/ai/ciris/mobile/InteractActivity.kt)
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

    private var pollingJob: Job? = null
    private var statusJob: Job? = null

    companion object {
        private const val POLL_INTERVAL_MS = 2000L // From InteractActivity.kt:78
        private const val STATUS_POLL_INTERVAL_MS = 5000L // From InteractActivity.kt:79
    }

    init {
        startStatusPolling()
        startMessagePolling()
    }

    fun onInputTextChanged(text: String) {
        _inputText.value = text
    }

    fun sendMessage() {
        val text = _inputText.value.trim()
        if (text.isEmpty() || _isSending.value) return

        viewModelScope.launch {
            try {
                _isSending.value = true

                // Add user message immediately
                val userMessage = ChatMessage(
                    id = generateMessageId(),
                    text = text,
                    type = MessageType.USER,
                    timestamp = Clock.System.now()
                )
                _messages.value = (_messages.value + userMessage).takeLast(20)
                _inputText.value = ""

                // Send to API
                val response = apiClient.sendMessage(text)

                // Add agent response
                val agentMessage = ChatMessage(
                    id = response.message_id,
                    text = response.response,
                    type = MessageType.AGENT,
                    timestamp = Clock.System.now(),
                    reasoning = response.reasoning
                )
                _messages.value = (_messages.value + agentMessage).takeLast(20)

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
            } finally {
                _isSending.value = false
            }
        }
    }

    fun shutdown(emergency: Boolean = false) {
        viewModelScope.launch {
            try {
                if (emergency) {
                    apiClient.emergencyShutdown()
                } else {
                    apiClient.initiateShutdown()
                }
            } catch (e: Exception) {
                println("Shutdown failed: ${e.message}")
            }
        }
    }

    private fun startStatusPolling() {
        statusJob = viewModelScope.launch {
            while (isActive) {
                try {
                    val status = apiClient.getSystemStatus()
                    _isConnected.value = status.status == "healthy"
                    _agentStatus.value = status.cognitive_state
                } catch (e: Exception) {
                    _isConnected.value = false
                    _agentStatus.value = "Disconnected"
                }
                delay(STATUS_POLL_INTERVAL_MS)
            }
        }
    }

    private fun startMessagePolling() {
        pollingJob = viewModelScope.launch {
            while (isActive) {
                try {
                    // Poll for new messages
                    // In production, this would check for messages newer than the last one
                    delay(POLL_INTERVAL_MS)
                } catch (e: Exception) {
                    println("Message polling failed: ${e.message}")
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
