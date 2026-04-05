package ai.ciris.mobile.shared.models

/**
 * Data models for OpenClaw skill import feature.
 */

/** Preview data returned before committing an import. */
data class SkillPreviewData(
    val name: String,
    val description: String,
    val version: String,
    val moduleName: String,
    val tools: List<String>,
    val requiredEnvVars: List<String>,
    val requiredBinaries: List<String>,
    val hasSupportingFiles: Boolean,
    val sourceUrl: String?,
    val instructionsPreview: String
)

/** Result of importing a skill. */
data class SkillImportResult(
    val success: Boolean,
    val moduleName: String,
    val adapterPath: String,
    val toolsCreated: List<String>,
    val message: String,
    val autoLoaded: Boolean,
    val preview: SkillPreviewData?
)

/** Info about a previously imported skill. */
data class ImportedSkillData(
    val moduleName: String,
    val originalSkillName: String,
    val version: String,
    val description: String,
    val adapterPath: String,
    val sourceUrl: String?
)
