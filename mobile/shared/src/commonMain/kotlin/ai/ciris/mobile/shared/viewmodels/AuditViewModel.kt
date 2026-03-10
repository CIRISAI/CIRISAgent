package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.AuditContextApiData
import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.ui.screens.AuditEntryData
import ai.ciris.mobile.shared.ui.screens.AuditFilter
import ai.ciris.mobile.shared.ui.screens.AuditScreenState
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * ViewModel for the Audit screen.
 *
 * Features:
 * - Fetches audit entries from /v1/audit/entries
 * - Supports filtering by severity, outcome, actor
 * - Pagination with load more
 * - Maps API responses to display models
 */
class AuditViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "AuditViewModel"
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
    @Suppress("unused")
    private fun logWarn(method: String, message: String) = log("WARN", method, message)
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    // State
    private val _state = MutableStateFlow(AuditScreenState())
    val state: StateFlow<AuditScreenState> = _state.asStateFlow()
    private var dataLoadStarted = false

    init {
        logInfo("init", "AuditViewModel initialized (data load deferred until startPolling() called)")
        // NOTE: Don't auto-load here - wait for startPolling() to be called
        // when the screen becomes visible and has a valid auth token
    }

    /**
     * Start audit data loading.
     * Must be called explicitly when the screen becomes visible.
     */
    fun startPolling() {
        val method = "startPolling"
        if (dataLoadStarted) {
            logDebug(method, "Data load already started, skipping")
            return
        }
        dataLoadStarted = true
        logInfo(method, "Starting audit data loading")
        fetchAuditEntries()
    }

    /**
     * Stop polling (for lifecycle management)
     */
    fun stopPolling() {
        val method = "stopPolling"
        logInfo(method, "Stopping audit polling")
        dataLoadStarted = false // Allow restart
    }

    /**
     * Refresh audit entries from API
     */
    fun refresh() {
        val method = "refresh"
        logInfo(method, "Refreshing audit entries")
        _state.update { it.copy(filter = it.filter.copy(offset = 0)) }
        fetchAuditEntries(clearExisting = true)
    }

    /**
     * Load more entries (pagination)
     */
    fun loadMore() {
        val method = "loadMore"
        val currentState = _state.value
        if (currentState.isLoading || !currentState.hasMore) {
            logDebug(method, "Skipping load more: isLoading=${currentState.isLoading}, hasMore=${currentState.hasMore}")
            return
        }

        logInfo(method, "Loading more entries, current offset=${currentState.filter.offset}")
        val newOffset = currentState.filter.offset + currentState.filter.limit
        _state.update { it.copy(filter = it.filter.copy(offset = newOffset)) }
        fetchAuditEntries(clearExisting = false)
    }

    /**
     * Update filter and refetch
     */
    fun updateFilter(newFilter: AuditFilter) {
        val method = "updateFilter"
        logInfo(method, "Filter changed: severity=${newFilter.severity}, outcome=${newFilter.outcome}, limit=${newFilter.limit}")
        _state.update { it.copy(filter = newFilter.copy(offset = 0)) }
        fetchAuditEntries(clearExisting = true)
    }

    /**
     * Fetch audit entries from API
     */
    private fun fetchAuditEntries(clearExisting: Boolean = true) {
        val method = "fetchAuditEntries"
        val filter = _state.value.filter
        logDebug(method, "Fetching entries: severity=${filter.severity}, outcome=${filter.outcome}, " +
                "limit=${filter.limit}, offset=${filter.offset}")

        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, error = null) }

            try {
                val entries = apiClient.getAuditEntries(
                    severity = filter.severity,
                    outcome = filter.outcome,
                    actor = filter.actor,
                    eventType = filter.eventType,
                    limit = filter.limit,
                    offset = filter.offset
                )

                logInfo(method, "Fetched ${entries.entries.size} entries, total=${entries.total}")

                val displayEntries = entries.entries.map { entry ->
                    // Debug: Log outcome extraction for troubleshooting
                    val extractedOutcome = entry.context?.outcome ?: "unknown"
                    logDebug(method, "Entry ${entry.id}: action=${entry.action}, " +
                        "context.outcome=${entry.context?.outcome}, " +
                        "context.result=${entry.context?.result}, " +
                        "extractedOutcome=$extractedOutcome")

                    AuditEntryData(
                        id = entry.id,
                        action = entry.action,
                        actor = entry.actor,
                        timestamp = entry.timestamp ?: "",
                        outcome = extractedOutcome,
                        hashChain = entry.hashChain,
                        signature = entry.signature,
                        storageSources = entry.storageSources,
                        contextJson = formatContextJson(entry.context)
                    )
                }

                _state.update { current ->
                    val allEntries = if (clearExisting) {
                        displayEntries
                    } else {
                        current.entries + displayEntries
                    }
                    current.copy(
                        entries = allEntries,
                        totalEntries = entries.total,
                        hasMore = allEntries.size < entries.total,
                        isLoading = false,
                        error = null
                    )
                }
            } catch (e: Exception) {
                logError(method, "Failed to fetch audit entries: ${e::class.simpleName}: ${e.message}")
                _state.update {
                    it.copy(
                        isLoading = false,
                        error = "Failed to load audit entries: ${e.message}"
                    )
                }
            }
        }
    }

    private fun formatContextJson(context: AuditContextApiData?): String {
        val method = "formatContextJson"
        if (context == null) {
            logDebug(method, "Context is null, returning empty string")
            return ""
        }
        logDebug(method, "Formatting context: description=${context.description}, " +
            "result=${context.result}, metadata=${context.metadata?.keys}")
        return try {
            buildString {
                // Primary action details
                context.description?.let { appendLine("Description: $it") }
                context.operation?.let { appendLine("Operation: $it") }
                context.details?.let { appendLine("Details: $it") }

                // Result info
                context.result?.let { appendLine("Result: $it") }
                context.error?.let { appendLine("Error: $it") }

                // Entity info
                context.entityId?.let { appendLine("Entity: $it") }
                context.entityType?.let { appendLine("Type: $it") }

                // Service info
                context.service?.let { appendLine("Service: $it") }

                // Correlation
                context.correlationId?.let { appendLine("Correlation: ${it.take(16)}...") }
                context.requestId?.let { appendLine("Request: ${it.take(16)}...") }

                // User/Source
                context.userId?.let { appendLine("User: $it") }
                context.ipAddress?.let { appendLine("IP: $it") }

                // Metadata (tool parameters, etc.)
                context.metadata?.let { meta ->
                    if (meta.isNotEmpty()) {
                        appendLine("Parameters:")
                        meta.forEach { (key, value) ->
                            // Extract actual value from JsonPrimitive to avoid escaped quotes
                            val displayValue = when {
                                value is kotlinx.serialization.json.JsonPrimitive && value.isString ->
                                    value.content // Get string content without quotes
                                value is kotlinx.serialization.json.JsonPrimitive ->
                                    value.content // Numbers, booleans, etc.
                                else -> value.toString() // Arrays/objects as JSON
                            }
                            appendLine("  $key: $displayValue")
                        }
                    }
                }
            }.trim()
        } catch (e: Exception) {
            logError("formatContextJson", "Error formatting context: ${e.message}")
            ""
        }
    }

    override fun onCleared() {
        logInfo("onCleared", "ViewModel cleared")
        super.onCleared()
    }
}
