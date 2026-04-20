package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.ToolInfoData
import ai.ciris.mobile.shared.api.ToolsMetadataData
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * State for the Tools screen.
 */
data class ToolsScreenState(
    val tools: List<ToolInfoData> = emptyList(),
    val metadata: ToolsMetadataData? = null,
    val isLoading: Boolean = false,
    val isRefreshing: Boolean = false,
    val error: String? = null,
    val selectedCategory: String? = null,
    val selectedProvider: String? = null,
    val searchQuery: String = ""
)

/**
 * ViewModel for the Tools screen.
 *
 * Features:
 * - Lists all available tools from all providers
 * - Shows tool details including parameters and when to use
 * - Filters by category and provider
 * - Search functionality
 */
class ToolsViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "ToolsViewModel"
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
    private val _state = MutableStateFlow(ToolsScreenState())
    val state: StateFlow<ToolsScreenState> = _state.asStateFlow()

    private var dataLoadStarted = false

    init {
        logInfo("init", "ToolsViewModel initialized")
    }

    /**
     * Start loading tools data.
     */
    fun startPolling() {
        val method = "startPolling"
        if (dataLoadStarted) {
            logDebug(method, "Data load already started, skipping")
            return
        }
        dataLoadStarted = true
        logInfo(method, "Starting tools data loading")
        _state.update { it.copy(isLoading = true) }
        refresh()
    }

    /**
     * Stop polling (tools don't need continuous polling).
     */
    fun stopPolling() {
        logInfo("stopPolling", "Stopping tools polling")
        dataLoadStarted = false
    }

    /**
     * Refresh tools data.
     */
    fun refresh() {
        val method = "refresh"
        logInfo(method, "Refreshing tools data")

        viewModelScope.launch {
            _state.update { it.copy(isRefreshing = true, error = null) }

            try {
                val result = apiClient.getTools()

                _state.update {
                    it.copy(
                        tools = result.tools,
                        metadata = result.metadata,
                        isLoading = false,
                        isRefreshing = false,
                        error = null
                    )
                }

                logInfo(method, "Loaded ${result.tools.size} tools from ${result.metadata?.providerCount ?: 0} providers")

            } catch (e: Exception) {
                logError(method, "Failed to refresh: ${e.message}")
                _state.update {
                    it.copy(
                        isLoading = false,
                        isRefreshing = false,
                        error = "Failed to load tools: ${e.message}"
                    )
                }
            }
        }
    }

    /**
     * Filter by category.
     */
    fun filterByCategory(category: String?) {
        logDebug("filterByCategory", "Category filter: $category")
        _state.update { it.copy(selectedCategory = category) }
    }

    /**
     * Filter by provider.
     */
    fun filterByProvider(provider: String?) {
        logDebug("filterByProvider", "Provider filter: $provider")
        _state.update { it.copy(selectedProvider = provider) }
    }

    /**
     * Update search query.
     */
    fun updateSearchQuery(query: String) {
        _state.update { it.copy(searchQuery = query) }
    }

    /**
     * Get filtered tools based on current filters.
     */
    fun getFilteredTools(): List<ToolInfoData> {
        val currentState = _state.value
        var filtered = currentState.tools

        // Filter by category
        currentState.selectedCategory?.let { category ->
            filtered = filtered.filter { it.category.equals(category, ignoreCase = true) }
        }

        // Filter by provider
        currentState.selectedProvider?.let { provider ->
            filtered = filtered.filter { it.provider.contains(provider, ignoreCase = true) }
        }

        // Filter by search query
        if (currentState.searchQuery.isNotBlank()) {
            val query = currentState.searchQuery.lowercase()
            filtered = filtered.filter { tool ->
                tool.name.lowercase().contains(query) ||
                tool.description.lowercase().contains(query) ||
                tool.provider.lowercase().contains(query)
            }
        }

        return filtered
    }

    /**
     * Get unique categories from all tools.
     */
    fun getCategories(): List<String> {
        return _state.value.tools.map { it.category }.distinct().sorted()
    }

    /**
     * Get unique providers from all tools.
     */
    fun getProviders(): List<String> {
        return _state.value.metadata?.providers ?: emptyList()
    }

    override fun onCleared() {
        logInfo("onCleared", "ViewModel cleared")
        super.onCleared()
    }
}
