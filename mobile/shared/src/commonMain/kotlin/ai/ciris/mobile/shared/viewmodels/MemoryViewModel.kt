package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.ui.screens.MemoryFilter
import ai.ciris.mobile.shared.ui.screens.MemoryNodeData
import ai.ciris.mobile.shared.ui.screens.MemoryScreenState
import ai.ciris.mobile.shared.ui.screens.MemoryStatsData
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * ViewModel for the Memory screen.
 *
 * Features:
 * - Fetches memory stats from /v1/memory/stats
 * - Fetches timeline from /v1/memory/timeline
 * - Search via /v1/memory/query
 * - Node details via /v1/memory/{node_id}
 * - Filtering by scope and node type
 */
class MemoryViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "MemoryViewModel"
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
    private val _state = MutableStateFlow(MemoryScreenState())
    val state: StateFlow<MemoryScreenState> = _state.asStateFlow()

    init {
        logInfo("init", "MemoryViewModel initialized")
        loadInitialData()
    }

    /**
     * Refresh all memory data
     */
    fun refresh() {
        val method = "refresh"
        logInfo(method, "Refreshing memory data")
        loadInitialData()
    }

    /**
     * Search for memory nodes
     */
    fun search(query: String) {
        val method = "search"
        if (query.isBlank()) {
            logDebug(method, "Empty query, clearing search results")
            _state.update { it.copy(searchResults = emptyList(), isSearching = false) }
            return
        }

        logInfo(method, "Searching for: $query")
        viewModelScope.launch {
            _state.update { it.copy(isSearching = true, error = null) }

            try {
                val results = apiClient.queryMemory(
                    query = query,
                    scope = _state.value.filter.scope,
                    nodeType = _state.value.filter.nodeType,
                    limit = 50
                )

                logInfo(method, "Search returned ${results.size} results")

                val displayNodes = results.map { node ->
                    MemoryNodeData(
                        id = node.id,
                        type = node.type,
                        scope = node.scope,
                        contentPreview = node.contentPreview,
                        attributesJson = node.attributesJson,
                        createdAt = node.createdAt,
                        updatedAt = node.updatedAt
                    )
                }

                _state.update { it.copy(searchResults = displayNodes, isSearching = false) }
            } catch (e: Exception) {
                logError(method, "Search failed: ${e::class.simpleName}: ${e.message}")
                _state.update {
                    it.copy(
                        isSearching = false,
                        error = "Search failed: ${e.message}"
                    )
                }
            }
        }
    }

    /**
     * Update filter and refetch timeline
     */
    fun updateFilter(newFilter: MemoryFilter) {
        val method = "updateFilter"
        logInfo(method, "Filter changed: scope=${newFilter.scope}, type=${newFilter.nodeType}, hours=${newFilter.hours}")
        _state.update { it.copy(filter = newFilter, searchResults = emptyList()) }
        viewModelScope.launch { fetchTimeline() }
    }

    /**
     * Select a node to view details
     */
    fun selectNode(nodeId: String) {
        val method = "selectNode"
        logInfo(method, "Selecting node: $nodeId")

        viewModelScope.launch {
            _state.update { it.copy(isLoading = true) }

            try {
                val node = apiClient.getMemoryNode(nodeId)
                logInfo(method, "Loaded node details: id=${node.id}, type=${node.type}")

                _state.update {
                    it.copy(
                        selectedNode = node,
                        isLoading = false
                    )
                }
            } catch (e: Exception) {
                logError(method, "Failed to load node: ${e::class.simpleName}: ${e.message}")
                _state.update {
                    it.copy(
                        isLoading = false,
                        error = "Failed to load node: ${e.message}"
                    )
                }
            }
        }
    }

    /**
     * Clear selected node
     */
    fun clearSelection() {
        val method = "clearSelection"
        logDebug(method, "Clearing node selection")
        _state.update { it.copy(selectedNode = null) }
    }

    /**
     * Load initial data: stats and timeline
     */
    private fun loadInitialData() {
        val method = "loadInitialData"
        logDebug(method, "Loading initial data")

        viewModelScope.launch {
            _state.update { it.copy(isLoading = true, error = null) }

            try {
                // Fetch stats and timeline in parallel
                val statsJob = viewModelScope.launch { fetchStats() }
                val timelineJob = viewModelScope.launch { fetchTimeline() }

                statsJob.join()
                timelineJob.join()

                _state.update { it.copy(isLoading = false) }
            } catch (e: Exception) {
                logError(method, "Failed to load initial data: ${e::class.simpleName}: ${e.message}")
                _state.update {
                    it.copy(
                        isLoading = false,
                        error = "Failed to load memory data: ${e.message}"
                    )
                }
            }
        }
    }

    /**
     * Fetch memory statistics
     */
    private suspend fun fetchStats() {
        val method = "fetchStats"
        logDebug(method, "Fetching memory stats")

        try {
            val stats = apiClient.getMemoryStats()
            logInfo(method, "Stats: totalNodes=${stats.totalNodes}, recent24h=${stats.recentNodes24h}")

            _state.update {
                it.copy(
                    stats = MemoryStatsData(
                        totalNodes = stats.totalNodes,
                        nodesByType = stats.nodesByType,
                        nodesByScope = stats.nodesByScope,
                        recentNodes24h = stats.recentNodes24h
                    )
                )
            }
        } catch (e: Exception) {
            logError(method, "Failed to fetch stats: ${e::class.simpleName}: ${e.message}")
            // Don't fail the whole load for stats failure
        }
    }

    /**
     * Fetch timeline nodes
     */
    private suspend fun fetchTimeline() {
        val method = "fetchTimeline"
        val filter = _state.value.filter
        logDebug(method, "Fetching timeline: scope=${filter.scope}, type=${filter.nodeType}, hours=${filter.hours}")

        try {
            val timeline = apiClient.getMemoryTimeline(
                hours = filter.hours,
                scope = filter.scope,
                nodeType = filter.nodeType
            )

            logInfo(method, "Timeline returned ${timeline.size} nodes")

            _state.update { it.copy(timelineNodes = timeline) }
        } catch (e: Exception) {
            logError(method, "Failed to fetch timeline: ${e::class.simpleName}: ${e.message}")
            throw e
        }
    }

    override fun onCleared() {
        logInfo("onCleared", "ViewModel cleared")
        super.onCleared()
    }
}
