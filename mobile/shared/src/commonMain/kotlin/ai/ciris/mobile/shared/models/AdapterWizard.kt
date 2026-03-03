package ai.ciris.mobile.shared.models

/**
 * Data classes for the adapter configuration wizard flow.
 */

/**
 * Available module/adapter types.
 */
data class ModuleTypesData(
    val coreModules: List<ModuleTypeData>,
    val adapters: List<ModuleTypeData>,
    val totalCore: Int,
    val totalAdapters: Int
)

/**
 * Information about a single module type.
 */
data class ModuleTypeData(
    val moduleId: String,
    val name: String,
    val version: String,
    val description: String?,
    val moduleSource: String,
    val serviceTypes: List<String>,
    val capabilities: List<String>,
    val platformAvailable: Boolean
)

/**
 * Configuration wizard session state.
 */
data class ConfigSessionData(
    val sessionId: String,
    val adapterType: String,
    val status: String,
    val currentStepIndex: Int,
    val totalSteps: Int,
    val currentStep: ConfigStepData?
)

/**
 * A single step in the configuration wizard.
 */
data class ConfigStepData(
    val stepId: String,
    val stepType: String,
    val title: String,
    val description: String?,
    val required: Boolean,
    val fields: List<ConfigFieldData>
)

/**
 * A field within a configuration step.
 */
data class ConfigFieldData(
    val name: String,
    val label: String,
    val fieldType: String,
    val required: Boolean,
    val defaultValue: String?,
    val helpText: String?
)

/**
 * A discovered item from a discovery step (e.g., Home Assistant instance).
 */
data class DiscoveredItemData(
    val id: String,
    val label: String,
    val value: String,
    val metadata: Map<String, String> = emptyMap()
)

/**
 * Result of executing a configuration step.
 */
data class ConfigStepResultData(
    val success: Boolean,
    val message: String?,
    val nextStepIndex: Int?,
    val isComplete: Boolean,
    val nextStep: ConfigStepData?,
    val discoveredItems: List<DiscoveredItemData> = emptyList()
)

/**
 * Result of completing adapter configuration.
 */
data class ConfigCompleteData(
    val success: Boolean,
    val adapterId: String?,
    val message: String?,
    val persisted: Boolean
)

/**
 * Information about an adapter that supports interactive configuration.
 */
data class ConfigurableAdapterData(
    val adapterType: String,
    val name: String,
    val description: String,
    val workflowType: String,
    val stepCount: Int,
    val requiresOauth: Boolean
)

/**
 * Response containing list of configurable adapters.
 */
data class ConfigurableAdaptersData(
    val adapters: List<ConfigurableAdapterData>,
    val totalCount: Int
)

/**
 * Information about an adapter that can be loaded (with or without configuration).
 */
data class LoadableAdapterData(
    val adapterType: String,
    val name: String,
    val description: String,
    val requiresConfiguration: Boolean,
    val workflowType: String?,
    val stepCount: Int,
    val requiresOauth: Boolean,
    val serviceTypes: List<String>,
    val platformAvailable: Boolean,
    // CLI dependency info
    val externalDependencies: List<String> = emptyList(),
    val dependenciesAvailable: Boolean = true,
    val missingDependencies: List<String> = emptyList()
)

/**
 * Response containing all loadable adapters.
 */
data class LoadableAdaptersData(
    val adapters: List<LoadableAdapterData>,
    val totalCount: Int,
    val configurableCount: Int,
    val directLoadCount: Int
)
