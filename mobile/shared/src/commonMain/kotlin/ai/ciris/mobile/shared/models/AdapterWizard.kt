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
 * Result of executing a configuration step.
 */
data class ConfigStepResultData(
    val success: Boolean,
    val message: String?,
    val nextStepIndex: Int?,
    val isComplete: Boolean,
    val nextStep: ConfigStepData?
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
