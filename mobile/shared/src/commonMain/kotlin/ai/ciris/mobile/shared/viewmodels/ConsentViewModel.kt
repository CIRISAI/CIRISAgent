package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.ui.screens.ConsentAuditEntryData
import ai.ciris.mobile.shared.ui.screens.ConsentImpactData
import ai.ciris.mobile.shared.ui.screens.ConsentScreenData
import ai.ciris.mobile.shared.ui.screens.ConsentStreamInfo
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
 * ViewModel for ConsentScreen
 * Handles consent management operations
 *
 * Features:
 * - Load consent status and available streams
 * - Change consent stream
 * - Request partnership
 * - Load impact data and audit trail
 * - Poll for partnership status when pending
 */
class ConsentViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "ConsentViewModel"
        private const val PARTNERSHIP_POLL_INTERVAL_MS = 5000L
    }

    private fun log(level: String, method: String, message: String) {
        println("[$TAG][$level][$method] $message")
    }

    private fun logDebug(method: String, message: String) = log("DEBUG", method, message)
    private fun logInfo(method: String, message: String) = log("INFO", method, message)
    private fun logWarn(method: String, message: String) = log("WARN", method, message)
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    // Consent data state
    private val _consentData = MutableStateFlow(ConsentScreenData())
    val consentData: StateFlow<ConsentScreenData> = _consentData.asStateFlow()

    // Loading state
    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    // Error state
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    // Success message
    private val _successMessage = MutableStateFlow<String?>(null)
    val successMessage: StateFlow<String?> = _successMessage.asStateFlow()

    // Partnership polling job
    private var partnershipPollJob: Job? = null

    init {
        logInfo("init", "ConsentViewModel initialized")
        loadConsentData()
    }

    /**
     * Load all consent data from API
     */
    fun loadConsentData() {
        val method = "loadConsentData"
        logInfo(method, "Loading consent data")

        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null

            try {
                // Load consent status
                val statusResponse = try {
                    apiClient.getConsentStatus()
                } catch (e: Exception) {
                    if (e.message?.contains("404") == true || e.message?.contains("not found", ignoreCase = true) == true) {
                        logInfo(method, "No consent record found (404), normal for new users")
                        null
                    } else {
                        throw e
                    }
                }

                // Load available streams
                val streamsResponse = apiClient.getConsentStreams()

                // Load partnership status
                val partnershipResponse = try {
                    apiClient.getPartnershipStatus()
                } catch (e: Exception) {
                    logWarn(method, "Failed to load partnership status: ${e.message}")
                    null
                }

                // Load impact data if applicable
                val impactData = if (statusResponse?.stream in listOf("partnered", "anonymous")) {
                    try {
                        apiClient.getConsentImpact()
                    } catch (e: Exception) {
                        logWarn(method, "Failed to load impact data: ${e.message}")
                        null
                    }
                } else null

                // Load audit trail
                val auditEntries = try {
                    apiClient.getConsentAudit(10)
                } catch (e: Exception) {
                    logWarn(method, "Failed to load audit trail: ${e.message}")
                    emptyList()
                }

                // Build stream info list with benefits
                val availableStreams = streamsResponse.streams.map { (id, metadata) ->
                    ConsentStreamInfo(
                        id = id,
                        name = metadata.name,
                        description = metadata.description,
                        durationDays = metadata.durationDays,
                        autoForget = metadata.autoForget,
                        learningEnabled = metadata.learningEnabled,
                        identityRemoved = metadata.identityRemoved,
                        requiresApproval = metadata.requiresCategories,
                        benefits = getStreamBenefits(id)
                    )
                }

                val isPending = partnershipResponse?.status == "pending"

                _consentData.value = ConsentScreenData(
                    hasConsent = statusResponse != null,
                    currentStream = statusResponse?.stream,
                    expiresAt = statusResponse?.expiresAt,
                    partnershipPending = isPending,
                    availableStreams = availableStreams,
                    impactData = impactData?.let {
                        ConsentImpactData(
                            totalInteractions = it.totalInteractions,
                            patternsContributed = it.patternsContributed,
                            usersHelped = it.usersHelped,
                            impactScore = it.impactScore
                        )
                    },
                    auditEntries = auditEntries.map {
                        ConsentAuditEntryData(
                            entryId = it.entryId,
                            timestamp = it.timestamp,
                            previousStream = it.previousStream,
                            newStream = it.newStream,
                            initiatedBy = it.initiatedBy,
                            reason = it.reason
                        )
                    }
                )

                logInfo(method, "Consent data loaded: hasConsent=${statusResponse != null}, " +
                        "stream=${statusResponse?.stream}, partnershipPending=$isPending")

                // Start polling if partnership is pending
                if (isPending) {
                    startPartnershipPolling()
                } else {
                    stopPartnershipPolling()
                }

            } catch (e: Exception) {
                logError(method, "Failed to load consent data: ${e::class.simpleName}: ${e.message}")
                _error.value = "Failed to load consent data: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Change consent stream
     */
    fun changeStream(streamId: String) {
        val method = "changeStream"
        logInfo(method, "Changing consent stream to: $streamId")

        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null

            try {
                apiClient.grantConsent(
                    stream = streamId,
                    categories = emptyList(),
                    reason = "User switched to $streamId consent via mobile app"
                )

                logInfo(method, "Stream changed successfully to $streamId")
                _successMessage.value = "Consent stream changed to ${streamId.uppercase()}"
                loadConsentData() // Reload to show updated status
            } catch (e: Exception) {
                logError(method, "Failed to change stream: ${e::class.simpleName}: ${e.message}")
                _error.value = "Failed to change consent stream: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Request partnership
     */
    fun requestPartnership() {
        val method = "requestPartnership"
        logInfo(method, "Requesting partnership")

        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null

            try {
                apiClient.requestPartnership(
                    reason = "Partnership requested via mobile app"
                )

                logInfo(method, "Partnership request submitted")
                _successMessage.value = "Partnership request submitted. The agent will review your request."

                // Update UI to show pending state
                _consentData.value = _consentData.value.copy(partnershipPending = true)

                // Start polling for status
                startPartnershipPolling()
            } catch (e: Exception) {
                logError(method, "Failed to request partnership: ${e::class.simpleName}: ${e.message}")
                _error.value = "Failed to submit partnership request: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Start polling for partnership status
     */
    private fun startPartnershipPolling() {
        val method = "startPartnershipPolling"
        if (partnershipPollJob?.isActive == true) {
            logDebug(method, "Partnership polling already active")
            return
        }

        logInfo(method, "Starting partnership status polling")
        partnershipPollJob = viewModelScope.launch {
            while (isActive) {
                delay(PARTNERSHIP_POLL_INTERVAL_MS)

                try {
                    val status = apiClient.getPartnershipStatus()
                    logDebug(method, "Partnership status: ${status.status}")

                    if (status.status != "pending") {
                        // Status changed
                        when (status.status) {
                            "accepted" -> {
                                _successMessage.value = "Partnership approved! You now have PARTNERED consent."
                            }
                            "rejected" -> {
                                _error.value = "Partnership request was declined by the agent."
                            }
                        }
                        loadConsentData()
                        break
                    }
                } catch (e: Exception) {
                    logError(method, "Error polling partnership status: ${e.message}")
                    break
                }
            }
        }
    }

    /**
     * Stop partnership polling
     */
    private fun stopPartnershipPolling() {
        partnershipPollJob?.cancel()
        partnershipPollJob = null
    }

    /**
     * Refresh consent data
     */
    fun refresh() {
        loadConsentData()
    }

    /**
     * Clear error state
     */
    fun clearError() {
        _error.value = null
    }

    /**
     * Clear success message
     */
    fun clearSuccess() {
        _successMessage.value = null
    }

    override fun onCleared() {
        super.onCleared()
        stopPartnershipPolling()
    }

    /**
     * Get benefits list for a stream
     */
    private fun getStreamBenefits(streamId: String): List<String> {
        return when (streamId.lowercase()) {
            "temporary" -> listOf(
                "No tracking",
                "Auto-forget in 14 days",
                "No learning"
            )
            "partnered" -> listOf(
                "Mutual growth",
                "Personalized experience",
                "Full features"
            )
            "anonymous" -> listOf(
                "Help others",
                "No identity stored",
                "Statistical contribution"
            )
            else -> emptyList()
        }
    }
}
