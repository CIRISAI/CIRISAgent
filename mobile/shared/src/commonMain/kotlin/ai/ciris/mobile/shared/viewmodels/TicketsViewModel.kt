package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.TicketData
import ai.ciris.mobile.shared.api.TicketStatsData
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Filter options for tickets list.
 */
data class TicketsFilter(
    val status: String? = null,
    val ticketType: String? = null,
    val sop: String? = null,
    val searchQuery: String? = null,
    val limit: Int = 50
)

/**
 * State for the Tickets screen.
 */
data class TicketsScreenState(
    val tickets: List<TicketData> = emptyList(),
    val stats: TicketStatsData? = null,
    val supportedSops: List<String> = emptyList(),
    val filter: TicketsFilter = TicketsFilter(),
    val isLoading: Boolean = false,
    val isRefreshing: Boolean = false,
    val error: String? = null,
    val selectedTicket: TicketData? = null
)

/**
 * ViewModel for the Tickets screen.
 *
 * Features:
 * - Fetches tickets from /v1/tickets/
 * - Supports filtering by status, type, SOP
 * - Shows ticket statistics summary
 * - Displays supported SOPs
 */
class TicketsViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "TicketsViewModel"
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
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    // State
    private val _state = MutableStateFlow(TicketsScreenState())
    val state: StateFlow<TicketsScreenState> = _state.asStateFlow()
    private var dataLoadStarted = false

    init {
        logInfo("init", "TicketsViewModel initialized (data load deferred)")
    }

    /**
     * Start ticket data loading.
     * Must be called explicitly when the screen becomes visible.
     */
    fun startPolling() {
        val method = "startPolling"
        if (dataLoadStarted) {
            logDebug(method, "Data load already started, skipping")
            return
        }
        dataLoadStarted = true
        logInfo(method, "Starting ticket data loading")
        refresh()
    }

    /**
     * Stop polling (for lifecycle management)
     */
    fun stopPolling() {
        val method = "stopPolling"
        logInfo(method, "Stopping ticket polling")
        dataLoadStarted = false
    }

    /**
     * Refresh all ticket data.
     */
    fun refresh() {
        val method = "refresh"
        logInfo(method, "Refreshing tickets data")

        viewModelScope.launch {
            _state.update { it.copy(isRefreshing = true, error = null) }

            try {
                // Fetch supported SOPs first
                fetchSupportedSops()

                // Fetch tickets and stats
                fetchTickets()
                fetchStats()

                _state.update { it.copy(isRefreshing = false) }
            } catch (e: Exception) {
                logError(method, "Failed to refresh: ${e.message}")
                _state.update {
                    it.copy(
                        isRefreshing = false,
                        error = "Failed to refresh: ${e.message}"
                    )
                }
            }
        }
    }

    /**
     * Update filter and refetch tickets.
     */
    fun updateFilter(newFilter: TicketsFilter) {
        val method = "updateFilter"
        logInfo(method, "Filter changed: status=${newFilter.status}, type=${newFilter.ticketType}")
        _state.update { it.copy(filter = newFilter) }
        fetchTickets()
    }

    /**
     * Select a ticket for detail view.
     */
    fun selectTicket(ticket: TicketData?) {
        _state.update { it.copy(selectedTicket = ticket) }
    }

    /**
     * Filter by status.
     */
    fun filterByStatus(status: String?) {
        updateFilter(_state.value.filter.copy(status = status))
    }

    /**
     * Filter by ticket type.
     */
    fun filterByType(ticketType: String?) {
        updateFilter(_state.value.filter.copy(ticketType = ticketType))
    }

    /**
     * Search tickets by email.
     */
    fun search(query: String?) {
        updateFilter(_state.value.filter.copy(searchQuery = query))
    }

    private fun fetchTickets() {
        val method = "fetchTickets"
        val filter = _state.value.filter
        logDebug(method, "Fetching tickets: status=${filter.status}, type=${filter.ticketType}")

        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, error = null) }

            try {
                val tickets = apiClient.listTickets(
                    sop = filter.sop,
                    ticketType = filter.ticketType,
                    statusFilter = filter.status,
                    email = filter.searchQuery,
                    limit = filter.limit
                )

                logInfo(method, "Fetched ${tickets.size} tickets")

                _state.update {
                    it.copy(
                        tickets = tickets,
                        isLoading = false,
                        error = null
                    )
                }
            } catch (e: Exception) {
                logError(method, "Failed to fetch tickets: ${e.message}")
                _state.update {
                    it.copy(
                        isLoading = false,
                        error = "Failed to load tickets: ${e.message}"
                    )
                }
            }
        }
    }

    private fun fetchStats() {
        val method = "fetchStats"
        logDebug(method, "Fetching ticket stats")

        viewModelScope.launch {
            try {
                val stats = apiClient.getTicketStats()
                logInfo(method, "Stats: total=${stats.total}, pending=${stats.pending}")

                _state.update { it.copy(stats = stats) }
            } catch (e: Exception) {
                logError(method, "Failed to fetch stats: ${e.message}")
                // Don't set error - stats are optional
            }
        }
    }

    private suspend fun fetchSupportedSops() {
        val method = "fetchSupportedSops"
        logDebug(method, "Fetching supported SOPs")

        try {
            val sops = apiClient.listSupportedSops()
            logInfo(method, "Supported SOPs: $sops")

            _state.update { it.copy(supportedSops = sops) }
        } catch (e: Exception) {
            logError(method, "Failed to fetch SOPs: ${e.message}")
            // Don't set error - SOPs are optional
        }
    }

    override fun onCleared() {
        logInfo("onCleared", "ViewModel cleared")
        super.onCleared()
    }
}
