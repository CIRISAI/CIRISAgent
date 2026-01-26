package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * SessionsViewModel - Cognitive Session Management
 * Ported from Android SessionsFragment.kt
 *
 * Features:
 * - Current cognitive state monitoring via polling
 * - Initiate DREAM, PLAY, SOLITUDE sessions
 * - Return to WORK state
 * - State transition handling with confirmation
 */
class SessionsViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "SessionsViewModel"
        private const val POLL_INTERVAL_MS = 3000L
    }

    private fun log(level: String, method: String, message: String) {
        println("[$TAG][$level][$method] $message")
    }

    private fun logDebug(method: String, message: String) = log("DEBUG", method, message)
    private fun logInfo(method: String, message: String) = log("INFO", method, message)
    private fun logWarn(method: String, message: String) = log("WARN", method, message)
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    // Current cognitive state
    private val _currentState = MutableStateFlow("WORK")
    val currentState: StateFlow<String> = _currentState.asStateFlow()

    // Previous cognitive state (after transitions)
    private val _previousState = MutableStateFlow<String?>(null)
    val previousState: StateFlow<String?> = _previousState.asStateFlow()

    // Loading/processing state
    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    // Transition in progress
    private val _isTransitioning = MutableStateFlow(false)
    val isTransitioning: StateFlow<Boolean> = _isTransitioning.asStateFlow()

    // Status message for UI feedback
    private val _statusMessage = MutableStateFlow<String?>(null)
    val statusMessage: StateFlow<String?> = _statusMessage.asStateFlow()

    // Error message
    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage: StateFlow<String?> = _errorMessage.asStateFlow()

    // Polling job
    private var pollingJob: Job? = null

    init {
        logInfo("init", "SessionsViewModel initialized")
        refresh()
        startPolling()
    }

    /**
     * Refresh current cognitive state from API
     */
    fun refresh() {
        val method = "refresh"
        logInfo(method, "Fetching current cognitive state")
        _isLoading.value = true
        _errorMessage.value = null

        viewModelScope.launch {
            try {
                logDebug(method, "Calling apiClient.getSystemStatus()")
                val status = apiClient.getSystemStatus()
                val cognitiveState = status.cognitive_state ?: "UNKNOWN"

                logInfo(method, "Got cognitive state: $cognitiveState (status: ${status.status})")

                if (_currentState.value != cognitiveState) {
                    logInfo(method, "State changed: ${_currentState.value} -> $cognitiveState")
                    _previousState.value = _currentState.value
                }
                _currentState.value = cognitiveState

            } catch (e: Exception) {
                logError(method, "Failed to fetch cognitive state: ${e::class.simpleName}: ${e.message}")
                logError(method, "Stack trace: ${e.stackTraceToString().take(500)}")
                _errorMessage.value = "Failed to fetch state: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Start polling for state updates
     */
    private fun startPolling() {
        val method = "startPolling"
        logInfo(method, "Starting state polling (interval=${POLL_INTERVAL_MS}ms)")

        pollingJob = viewModelScope.launch {
            var pollCount = 0
            while (isActive) {
                delay(POLL_INTERVAL_MS)
                pollCount++
                try {
                    val status = apiClient.getSystemStatus()
                    val cognitiveState = status.cognitive_state ?: "UNKNOWN"

                    if (_currentState.value != cognitiveState) {
                        logInfo(method, "Poll #$pollCount: State changed ${_currentState.value} -> $cognitiveState")
                        _previousState.value = _currentState.value
                        _currentState.value = cognitiveState
                    } else if (pollCount % 10 == 0) {
                        logDebug(method, "Poll #$pollCount: State unchanged ($cognitiveState)")
                    }
                } catch (e: Exception) {
                    if (pollCount % 10 == 0) {
                        logWarn(method, "Poll #$pollCount failed: ${e.message}")
                    }
                }
            }
        }
    }

    /**
     * Stop polling
     */
    private fun stopPolling() {
        val method = "stopPolling"
        logInfo(method, "Stopping state polling")
        pollingJob?.cancel()
        pollingJob = null
    }

    /**
     * Initiate a cognitive session transition
     * @param targetState The target state (DREAM, PLAY, SOLITUDE, WORK)
     */
    fun initiateSession(targetState: String) {
        val method = "initiateSession"
        logInfo(method, "Initiating session transition: ${_currentState.value} -> $targetState")

        if (_isTransitioning.value) {
            logWarn(method, "Transition already in progress, ignoring")
            return
        }

        _isTransitioning.value = true
        _errorMessage.value = null
        _statusMessage.value = "Transitioning to $targetState..."

        viewModelScope.launch {
            try {
                val reason = "Requested via KMP Sessions UI"
                logDebug(method, "Calling apiClient.transitionCognitiveState: targetState=$targetState, reason=$reason")
                val response = apiClient.transitionCognitiveState(targetState, reason)

                logInfo(method, "Transition response: success=${response.success}, currentState=${response.currentState}, message=${response.message}")

                if (response.success) {
                    _previousState.value = response.previousState
                    _currentState.value = response.currentState
                    _statusMessage.value = "Transitioned to ${response.currentState}"
                    logInfo(method, "Successfully transitioned to ${response.currentState}")

                    // Clear status message after delay
                    delay(3000)
                    if (_statusMessage.value?.contains("Transitioned") == true) {
                        _statusMessage.value = null
                    }
                } else {
                    logWarn(method, "Transition not initiated: ${response.message}")
                    _statusMessage.value = response.message
                    _errorMessage.value = response.message
                }

            } catch (e: Exception) {
                logError(method, "Transition failed: ${e::class.simpleName}: ${e.message}")
                logError(method, "Stack trace: ${e.stackTraceToString().take(500)}")

                val errorMsg = when {
                    e.message?.contains("400") == true -> "Invalid state requested"
                    e.message?.contains("401") == true -> "Authentication required"
                    e.message?.contains("503") == true -> "State transition not supported"
                    else -> "Failed to transition: ${e.message}"
                }
                _errorMessage.value = errorMsg
                _statusMessage.value = errorMsg
            } finally {
                _isTransitioning.value = false
            }
        }
    }

    /**
     * Clear error message
     */
    fun clearError() {
        logDebug("clearError", "Clearing error message")
        _errorMessage.value = null
    }

    /**
     * Clear status message
     */
    fun clearStatus() {
        logDebug("clearStatus", "Clearing status message")
        _statusMessage.value = null
    }

    /**
     * Check if a specific state is currently active
     */
    fun isStateActive(state: String): Boolean {
        return _currentState.value.equals(state, ignoreCase = true)
    }

    /**
     * Check if session initiation is enabled
     * Can only initiate sessions from WORK state
     */
    fun canInitiateSession(targetState: String): Boolean {
        val canInitiate = _currentState.value == "WORK" && targetState != "WORK"
        logDebug("canInitiateSession", "Target: $targetState, Current: ${_currentState.value}, CanInitiate: $canInitiate")
        return canInitiate
    }

    /**
     * Check if return to work is available
     * Available when not in WORK, WAKEUP, or SHUTDOWN states
     */
    fun canReturnToWork(): Boolean {
        val current = _currentState.value
        val canReturn = current !in listOf("WORK", "WAKEUP", "SHUTDOWN", "UNKNOWN")
        logDebug("canReturnToWork", "Current: $current, CanReturn: $canReturn")
        return canReturn
    }

    override fun onCleared() {
        logInfo("onCleared", "ViewModel cleared, stopping polling")
        super.onCleared()
        stopPolling()
    }
}

/**
 * Data class for state transition response
 * Used internally to parse API response
 */
data class StateTransitionResult(
    val success: Boolean,
    val message: String,
    val currentState: String,
    val previousState: String? = null
)
