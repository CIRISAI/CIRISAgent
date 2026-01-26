package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.AuditContextApiData
import ai.ciris.mobile.shared.api.CIRISApiClient
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
        println("[$TAG][$level][$method] $message")
    }

    private fun logDebug(method: String, message: String) = log("DEBUG", method, message)
    private fun logInfo(method: String, message: String) = log("INFO", method, message)
    @Suppress("unused")
    private fun logWarn(method: String, message: String) = log("WARN", method, message)
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    // State
    private val _state = MutableStateFlow(AuditScreenState())
    val state: StateFlow<AuditScreenState> = _state.asStateFlow()

    init {
        logInfo("init", "AuditViewModel initialized")
        fetchAuditEntries()
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
                    AuditEntryData(
                        id = entry.id,
                        action = entry.action,
                        actor = entry.actor,
                        timestamp = entry.timestamp ?: "",
                        outcome = entry.context?.outcome ?: "unknown",
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
        if (context == null) return ""
        return try {
            buildString {
                context.details?.let { appendLine("Details: $it") }
                context.entityId?.let { appendLine("Entity: $it") }
                context.service?.let { appendLine("Service: $it") }
                context.ipAddress?.let { appendLine("IP: $it") }
            }
        } catch (e: Exception) {
            ""
        }
    }

    override fun onCleared() {
        logInfo("onCleared", "ViewModel cleared")
        super.onCleared()
    }
}
