package ai.ciris.mobile.shared.models

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Data models for OpenClaw skill import and Skill Studio.
 */

// ============================================================================
// Security Models
// ============================================================================

/** A single security finding from skill scanning. */
@Serializable
data class SecurityFinding(
    val severity: String,
    val category: String,
    val title: String,
    val description: String,
    val evidence: String? = null,
    val recommendation: String = ""
)

/** Security scan report for a skill. */
@Serializable
data class SecurityReport(
    @SerialName("total_findings") val totalFindings: Int = 0,
    @SerialName("critical_count") val criticalCount: Int = 0,
    @SerialName("high_count") val highCount: Int = 0,
    @SerialName("medium_count") val mediumCount: Int = 0,
    @SerialName("low_count") val lowCount: Int = 0,
    @SerialName("safe_to_import") val safeToImport: Boolean = true,
    val summary: String = "",
    val findings: List<SecurityFinding> = emptyList()
)

// ============================================================================
// Import/Preview Models
// ============================================================================

/** Preview data returned before committing an import. */
@Serializable
data class SkillPreviewData(
    val name: String,
    val description: String,
    val version: String,
    @SerialName("module_name") val moduleName: String,
    val tools: List<String> = emptyList(),
    @SerialName("required_env_vars") val requiredEnvVars: List<String> = emptyList(),
    @SerialName("required_binaries") val requiredBinaries: List<String> = emptyList(),
    @SerialName("has_supporting_files") val hasSupportingFiles: Boolean = false,
    @SerialName("source_url") val sourceUrl: String? = null,
    @SerialName("instructions_preview") val instructionsPreview: String = "",
    val security: SecurityReport? = null
)

/** Result of importing a skill. */
@Serializable
data class SkillImportResult(
    val success: Boolean,
    @SerialName("module_name") val moduleName: String = "",
    @SerialName("adapter_path") val adapterPath: String = "",
    @SerialName("tools_created") val toolsCreated: List<String> = emptyList(),
    val message: String = "",
    @SerialName("auto_loaded") val autoLoaded: Boolean = false,
    val preview: SkillPreviewData? = null
)

/** Info about a previously imported skill. */
@Serializable
data class ImportedSkillData(
    @SerialName("module_name") val moduleName: String,
    @SerialName("original_skill_name") val originalSkillName: String,
    val version: String,
    val description: String,
    @SerialName("adapter_path") val adapterPath: String,
    @SerialName("source_url") val sourceUrl: String? = null
)

/** Result of validating a skill (without importing). */
@Serializable
data class SkillValidateResult(
    val valid: Boolean,
    val errors: List<String> = emptyList(),
    val warnings: List<String> = emptyList(),
    val security: SecurityReport,
    val preview: SkillPreviewData? = null
)

// ============================================================================
// Skill Studio Draft Models (local editing)
// ============================================================================

/** Category for skills. */
enum class SkillCategory(val value: String, val displayName: String) {
    GENERAL("general", "General"),
    COMMUNICATION("communication", "Communication"),
    MEMORY("memory", "Memory"),
    SYSTEM("system", "System"),
    SECRETS("secrets", "Secrets"),
    AUTOMATION("automation", "Automation"),
    DATA("data", "Data"),
    DEVELOPMENT("development", "Development")
}

/** Parameter type for tool parameters. */
enum class ParameterType(val value: String, val displayName: String) {
    STRING("string", "String"),
    NUMBER("number", "Number"),
    INTEGER("integer", "Integer"),
    BOOLEAN("boolean", "Boolean"),
    ARRAY("array", "Array"),
    OBJECT("object", "Object")
}

/** A tool parameter definition. */
data class ToolParameter(
    val name: String,
    val type: ParameterType = ParameterType.STRING,
    val description: String = "",
    val required: Boolean = true,
    val default: String? = null
)

/** A tool definition within a skill. */
data class ToolDefinition(
    val name: String,
    val description: String = "",
    val parameters: List<ToolParameter> = emptyList(),
    val whenToUse: String = "",
    val examples: List<String> = emptyList(),
    val cost: Int = 0
)

/** An environment variable requirement. */
data class EnvVarRequirement(
    val name: String,
    val description: String = "",
    val required: Boolean = true,
    val defaultValue: String? = null
)

/**
 * A draft skill being edited in Skill Studio.
 *
 * This is the local representation of an OpenClaw SKILL.md file
 * that can be edited visually before generating the markdown.
 */
data class SkillDraft(
    // Metadata
    val name: String = "",
    val description: String = "",
    val version: String = "1.0.0",
    val author: String = "",
    val homepage: String = "",
    val license: String = "MIT",
    val tags: List<String> = emptyList(),
    val category: SkillCategory = SkillCategory.GENERAL,

    // Requirements
    val environmentVariables: List<EnvVarRequirement> = emptyList(),
    val requiredBinaries: List<String> = emptyList(),

    // Tools
    val tools: List<ToolDefinition> = emptyList(),

    // Instructions (Markdown body)
    val instructions: String = "",

    // State
    val isDirty: Boolean = false,
    val lastSaved: Long? = null,
    val sourceUrl: String? = null,
    val localId: String? = null
) {
    /**
     * Generate SKILL.md content from this draft.
     */
    fun toSkillMd(): String = buildString {
        appendLine("---")
        appendLine("name: $name")
        if (description.isNotBlank()) appendLine("description: $description")
        appendLine("version: $version")
        if (author.isNotBlank()) appendLine("author: $author")
        if (homepage.isNotBlank()) appendLine("homepage: $homepage")
        if (license.isNotBlank()) appendLine("license: $license")
        appendLine("category: ${category.value}")
        if (tags.isNotEmpty()) {
            appendLine("tags: [${tags.joinToString(", ")}]")
        }

        // OpenClaw metadata block
        if (environmentVariables.isNotEmpty() || requiredBinaries.isNotEmpty()) {
            appendLine("metadata:")
            appendLine("  openclaw:")
            if (environmentVariables.isNotEmpty() || requiredBinaries.isNotEmpty()) {
                appendLine("    requires:")
                if (environmentVariables.isNotEmpty()) {
                    appendLine("      env: [${environmentVariables.joinToString(", ") { it.name }}]")
                }
                if (requiredBinaries.isNotEmpty()) {
                    appendLine("      bins: [${requiredBinaries.joinToString(", ")}]")
                }
            }
        }
        appendLine("---")
        appendLine()

        // Instructions body
        append(instructions)

        // Auto-generate tool documentation if not in instructions
        if (tools.isNotEmpty() && !instructions.contains("## Tools")) {
            appendLine()
            appendLine()
            appendLine("## Tools")
            appendLine()
            for (tool in tools) {
                appendLine("### ${tool.name}")
                appendLine(tool.description)
                if (tool.whenToUse.isNotBlank()) {
                    appendLine()
                    appendLine("**When to use:** ${tool.whenToUse}")
                }
                if (tool.parameters.isNotEmpty()) {
                    appendLine()
                    appendLine("**Parameters:**")
                    for (param in tool.parameters) {
                        val reqMark = if (param.required) " *required*" else ""
                        val defVal = param.default?.let { " (default: $it)" } ?: ""
                        appendLine("- `${param.name}` (${param.type.value})$reqMark$defVal: ${param.description}")
                    }
                }
                appendLine()
            }
        }
    }

    /**
     * Validate the draft and return any errors.
     */
    fun validate(): List<String> = buildList {
        if (name.isBlank()) add("Skill name is required")
        if (name.contains(" ")) add("Skill name should use hyphens, not spaces")
        if (name.isNotBlank() && !name.matches(Regex("^[a-z0-9-]+$"))) {
            add("Skill name should only contain lowercase letters, numbers, and hyphens")
        }
        if (description.isBlank()) add("Description is required")
        if (instructions.isBlank()) add("Instructions are required")

        for ((index, tool) in tools.withIndex()) {
            if (tool.name.isBlank()) add("Tool #${index + 1} is missing a name")
            if (tool.description.isBlank()) add("Tool '${tool.name}' is missing a description")
        }

        for ((index, env) in environmentVariables.withIndex()) {
            if (env.name.isBlank()) add("Environment variable #${index + 1} is missing a name")
            if (env.name.isNotBlank() && !env.name.matches(Regex("^[A-Z][A-Z0-9_]*$"))) {
                add("Environment variable '${env.name}' should be UPPER_SNAKE_CASE")
            }
        }
    }
}
