package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.ui.screens.ConfigItem
import ai.ciris.mobile.shared.ui.screens.ConfigScreenData
import ai.ciris.mobile.shared.ui.screens.ConfigSection
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.jsonPrimitive

/**
 * ViewModel for ConfigScreen
 * Handles configuration management operations
 *
 * Features:
 * - Load and organize configurations by section
 * - Search and filter configurations
 * - Update and delete configuration values
 */
class ConfigViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "ConfigViewModel"
    }

    private fun log(level: String, method: String, message: String) {
        println("[$TAG][$level][$method] $message")
    }

    private fun logDebug(method: String, message: String) = log("DEBUG", method, message)
    private fun logInfo(method: String, message: String) = log("INFO", method, message)
    private fun logWarn(method: String, message: String) = log("WARN", method, message)
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    // Config data state
    private val _configData = MutableStateFlow(ConfigScreenData())
    val configData: StateFlow<ConfigScreenData> = _configData.asStateFlow()

    // Loading state
    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    // Search query
    private val _searchQuery = MutableStateFlow("")
    val searchQuery: StateFlow<String> = _searchQuery.asStateFlow()

    // Selected category filter
    private val _selectedCategory = MutableStateFlow<String?>(null)
    val selectedCategory: StateFlow<String?> = _selectedCategory.asStateFlow()

    // Expanded sections
    private val _expandedSections = MutableStateFlow<Set<String>>(emptySet())
    val expandedSections: StateFlow<Set<String>> = _expandedSections.asStateFlow()

    // Error state
    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    // Success message
    private val _successMessage = MutableStateFlow<String?>(null)
    val successMessage: StateFlow<String?> = _successMessage.asStateFlow()

    init {
        logInfo("init", "ConfigViewModel initialized")
        loadConfigs()
    }

    /**
     * Load all configurations from API
     */
    fun loadConfigs() {
        val method = "loadConfigs"
        logInfo(method, "Loading configurations")

        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null

            try {
                val response = apiClient.listConfigs()
                logDebug(method, "API response received: ${response.configs.size} configs")

                // Organize configs into sections
                val sections = organizeConfigs(response.configs)
                logInfo(method, "Organized into ${sections.size} sections")

                _configData.value = ConfigScreenData(
                    sections = sections,
                    totalConfigs = response.total
                )
            } catch (e: Exception) {
                logError(method, "Failed to load configs: ${e::class.simpleName}: ${e.message}")
                _error.value = "Failed to load configurations: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Update search query
     */
    fun updateSearchQuery(query: String) {
        _searchQuery.value = query
    }

    /**
     * Select category filter
     */
    fun selectCategory(category: String?) {
        _selectedCategory.value = category
    }

    /**
     * Toggle section expansion
     */
    fun toggleSection(sectionName: String) {
        val current = _expandedSections.value.toMutableSet()
        if (current.contains(sectionName)) {
            current.remove(sectionName)
        } else {
            current.add(sectionName)
        }
        _expandedSections.value = current
    }

    /**
     * Update a configuration value
     */
    fun updateConfig(key: String, value: String) {
        val method = "updateConfig"
        logInfo(method, "Updating config: $key")

        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null

            try {
                apiClient.updateConfig(key, value, "Updated via mobile app")
                logInfo(method, "Config updated successfully")
                _successMessage.value = "Configuration \"$key\" updated"
                loadConfigs() // Reload to show updated value
            } catch (e: Exception) {
                logError(method, "Failed to update config: ${e::class.simpleName}: ${e.message}")
                _error.value = "Failed to update configuration: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Delete a configuration
     */
    fun deleteConfig(key: String) {
        val method = "deleteConfig"
        logInfo(method, "Deleting config: $key")

        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null

            try {
                apiClient.deleteConfig(key)
                logInfo(method, "Config deleted successfully")
                _successMessage.value = "Configuration \"$key\" deleted"
                loadConfigs() // Reload to reflect deletion
            } catch (e: Exception) {
                logError(method, "Failed to delete config: ${e::class.simpleName}: ${e.message}")
                _error.value = "Failed to delete configuration: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
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

    /**
     * Refresh configurations
     */
    fun refresh() {
        loadConfigs()
    }

    /**
     * Organize flat config list into sections
     */
    private fun organizeConfigs(configs: List<ConfigItemData>): List<ConfigSection> {
        val method = "organizeConfigs"
        val sectionMap = mutableMapOf<String, MutableList<ConfigItem>>()
        val sectionCategories = mutableMapOf<String, String?>()

        configs.forEach { config ->
            val parts = config.key.split(".")
            val sectionName = if (config.key.startsWith("adapter.") && parts.size >= 3) {
                "adapter.${parts[1]}"
            } else {
                parts.firstOrNull() ?: "default"
            }

            // Determine category
            val category = when {
                config.key.startsWith("adapter") -> "adapters"
                config.key.startsWith("service") -> "services"
                config.key.startsWith("security") || config.key.startsWith("auth") -> "security"
                config.key.startsWith("database") || config.key.startsWith("db") -> "database"
                config.key.startsWith("limit") || config.key.startsWith("rate") -> "limits"
                config.key.startsWith("workflow") || config.key.startsWith("task") -> "workflow"
                config.key.startsWith("telemetry") || config.key.startsWith("metric") -> "telemetry"
                else -> null
            }

            if (!sectionMap.containsKey(sectionName)) {
                sectionMap[sectionName] = mutableListOf()
                sectionCategories[sectionName] = category
            }

            sectionMap[sectionName]?.add(
                ConfigItem(
                    key = config.key,
                    displayValue = config.displayValue,
                    updatedAt = config.updatedAt ?: "Unknown",
                    updatedBy = config.updatedBy,
                    isSensitive = config.isSensitive
                )
            )
        }

        return sectionMap.entries
            .sortedBy { it.key }
            .map { (name, items) ->
                ConfigSection(
                    name = name,
                    items = items.sortedBy { it.key },
                    category = sectionCategories[name]
                )
            }
    }
}

/**
 * Internal data class for config items from API
 */
data class ConfigItemData(
    val key: String,
    val displayValue: String,
    val updatedAt: String?,
    val updatedBy: String,
    val isSensitive: Boolean
)
