package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.*
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Screen state for Skill Studio.
 */
sealed class SkillStudioScreenState {
    /** Loading drafts or skill data */
    object Loading : SkillStudioScreenState()

    /** Editing a skill draft */
    data class Editing(
        val draft: SkillDraft,
        val expandedCards: Set<String> = setOf("metadata"),
        val validationErrors: List<String> = emptyList()
    ) : SkillStudioScreenState()

    /** Showing preview of generated SKILL.md */
    data class Preview(
        val draft: SkillDraft,
        val markdown: String,
        val activeTab: PreviewTab = PreviewTab.SKILL_MD
    ) : SkillStudioScreenState()

    /** Showing security report before import */
    data class SecurityReview(
        val draft: SkillDraft,
        val report: SecurityReport
    ) : SkillStudioScreenState()

    /** Import in progress */
    data class Importing(val draft: SkillDraft) : SkillStudioScreenState()

    /** Import succeeded */
    data class ImportSuccess(
        val moduleName: String,
        val toolsCreated: List<String>
    ) : SkillStudioScreenState()

    /** Error state */
    data class Error(
        val message: String,
        val draft: SkillDraft? = null
    ) : SkillStudioScreenState()
}

enum class PreviewTab { SKILL_MD, SECURITY }

/**
 * Dialog state for editing tools/parameters.
 */
sealed class SkillStudioDialogState {
    object None : SkillStudioDialogState()

    data class EditTool(
        val tool: ToolDefinition,
        val isNew: Boolean,
        val index: Int = -1
    ) : SkillStudioDialogState()

    data class EditParameter(
        val parameter: ToolParameter,
        val isNew: Boolean,
        val index: Int = -1,
        val toolIndex: Int = -1
    ) : SkillStudioDialogState()

    data class EditEnvVar(
        val envVar: EnvVarRequirement,
        val isNew: Boolean,
        val index: Int = -1
    ) : SkillStudioDialogState()

    data class AddTag(val currentTags: List<String>) : SkillStudioDialogState()

    data class ConfirmDelete(
        val itemType: String,
        val itemName: String,
        val onConfirm: () -> Unit
    ) : SkillStudioDialogState()
}

/**
 * ViewModel for Skill Studio - visual SKILL.md editor.
 *
 * Manages:
 * - Draft creation and editing
 * - SKILL.md generation
 * - Security scanning via API
 * - Import as adapter
 */
class SkillStudioViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "SkillStudioViewModel"
    }

    private fun log(level: String, method: String, message: String) {
        val fullMessage = "[$method] $message"
        when (level) {
            "DEBUG" -> PlatformLogger.d(TAG, fullMessage)
            "INFO" -> PlatformLogger.i(TAG, fullMessage)
            "WARN" -> PlatformLogger.w(TAG, fullMessage)
            "ERROR" -> PlatformLogger.e(TAG, fullMessage)
        }
    }

    // Main screen state
    private val _state = MutableStateFlow<SkillStudioScreenState>(SkillStudioScreenState.Loading)
    val state: StateFlow<SkillStudioScreenState> = _state.asStateFlow()

    // Dialog state
    private val _dialogState = MutableStateFlow<SkillStudioDialogState>(SkillStudioDialogState.None)
    val dialogState: StateFlow<SkillStudioDialogState> = _dialogState.asStateFlow()

    // ========================================================================
    // Draft Management
    // ========================================================================

    /**
     * Create a new empty draft.
     */
    fun createNewDraft() {
        log("INFO", "createNewDraft", "Creating new skill draft")
        _state.value = SkillStudioScreenState.Editing(
            draft = SkillDraft(),
            expandedCards = setOf("metadata")
        )
    }

    /**
     * Load a draft from a source URL (ClawHub, GitHub, etc).
     */
    fun loadFromUrl(url: String) {
        log("INFO", "loadFromUrl", "Loading skill from: $url")
        viewModelScope.launch {
            _state.value = SkillStudioScreenState.Loading
            try {
                // For now, create empty draft with source URL set
                // TODO: Add API to fetch SKILL.md content from URL
                _state.value = SkillStudioScreenState.Editing(
                    draft = SkillDraft(sourceUrl = url),
                    expandedCards = setOf("metadata")
                )
            } catch (e: Exception) {
                log("ERROR", "loadFromUrl", "Failed to load: ${e.message}")
                _state.value = SkillStudioScreenState.Error(
                    message = "Failed to load skill: ${e.message}"
                )
            }
        }
    }

    /**
     * Load a draft from SKILL.md content (paste from clipboard).
     */
    fun loadFromContent(content: String) {
        log("INFO", "loadFromContent", "Parsing skill content (${content.length} chars)")
        viewModelScope.launch {
            _state.value = SkillStudioScreenState.Loading
            try {
                // Validate and parse the content via API
                val result = apiClient.validateSkill(content)
                if (result.preview != null) {
                    // Create draft from preview data
                    val preview = result.preview
                    _state.value = SkillStudioScreenState.Editing(
                        draft = SkillDraft(
                            name = preview.name,
                            description = preview.description,
                            version = preview.version,
                            sourceUrl = preview.sourceUrl,
                            instructions = preview.instructionsPreview,
                            // Note: Full tool/env var parsing would need server-side support
                            requiredBinaries = preview.requiredBinaries
                        ),
                        expandedCards = setOf("metadata")
                    )
                } else {
                    _state.value = SkillStudioScreenState.Error(
                        message = result.errors.firstOrNull() ?: "Invalid skill content"
                    )
                }
            } catch (e: Exception) {
                log("ERROR", "loadFromContent", "Failed to parse: ${e.message}")
                _state.value = SkillStudioScreenState.Error(
                    message = "Failed to parse skill: ${e.message}"
                )
            }
        }
    }

    // ========================================================================
    // Metadata Editing
    // ========================================================================

    fun updateName(name: String) {
        updateDraft { it.copy(name = name.lowercase().replace(" ", "-"), isDirty = true) }
    }

    fun updateDescription(description: String) {
        updateDraft { it.copy(description = description, isDirty = true) }
    }

    fun updateVersion(version: String) {
        updateDraft { it.copy(version = version, isDirty = true) }
    }

    fun updateAuthor(author: String) {
        updateDraft { it.copy(author = author, isDirty = true) }
    }

    fun updateHomepage(homepage: String) {
        updateDraft { it.copy(homepage = homepage, isDirty = true) }
    }

    fun updateCategory(category: SkillCategory) {
        updateDraft { it.copy(category = category, isDirty = true) }
    }

    fun addTag(tag: String) {
        updateDraft {
            val normalized = tag.lowercase().trim()
            if (normalized.isNotBlank() && normalized !in it.tags) {
                it.copy(tags = it.tags + normalized, isDirty = true)
            } else it
        }
        _dialogState.value = SkillStudioDialogState.None
    }

    fun removeTag(tag: String) {
        updateDraft { it.copy(tags = it.tags - tag, isDirty = true) }
    }

    fun updateInstructions(instructions: String) {
        updateDraft { it.copy(instructions = instructions, isDirty = true) }
    }

    // ========================================================================
    // Tool Editing
    // ========================================================================

    fun showAddToolDialog() {
        _dialogState.value = SkillStudioDialogState.EditTool(
            tool = ToolDefinition(name = ""),
            isNew = true
        )
    }

    fun showEditToolDialog(index: Int) {
        val current = getCurrentDraft() ?: return
        if (index in current.tools.indices) {
            _dialogState.value = SkillStudioDialogState.EditTool(
                tool = current.tools[index],
                isNew = false,
                index = index
            )
        }
    }

    fun saveTool(tool: ToolDefinition) {
        val dialogState = _dialogState.value
        if (dialogState is SkillStudioDialogState.EditTool) {
            updateDraft {
                val newTools = if (dialogState.isNew) {
                    it.tools + tool
                } else {
                    it.tools.toMutableList().apply { set(dialogState.index, tool) }
                }
                it.copy(tools = newTools, isDirty = true)
            }
        }
        _dialogState.value = SkillStudioDialogState.None
    }

    fun deleteTool(index: Int) {
        updateDraft {
            it.copy(
                tools = it.tools.toMutableList().apply { removeAt(index) },
                isDirty = true
            )
        }
    }

    // ========================================================================
    // Parameter Editing (within Tool dialog)
    // ========================================================================

    fun showAddParameterDialog(toolIndex: Int) {
        _dialogState.value = SkillStudioDialogState.EditParameter(
            parameter = ToolParameter(name = ""),
            isNew = true,
            toolIndex = toolIndex
        )
    }

    fun showEditParameterDialog(toolIndex: Int, paramIndex: Int) {
        val current = getCurrentDraft() ?: return
        if (toolIndex in current.tools.indices) {
            val tool = current.tools[toolIndex]
            if (paramIndex in tool.parameters.indices) {
                _dialogState.value = SkillStudioDialogState.EditParameter(
                    parameter = tool.parameters[paramIndex],
                    isNew = false,
                    index = paramIndex,
                    toolIndex = toolIndex
                )
            }
        }
    }

    fun saveParameter(parameter: ToolParameter) {
        val dialogState = _dialogState.value
        if (dialogState is SkillStudioDialogState.EditParameter) {
            updateDraft { draft ->
                val toolIndex = dialogState.toolIndex
                if (toolIndex in draft.tools.indices) {
                    val tool = draft.tools[toolIndex]
                    val newParams = if (dialogState.isNew) {
                        tool.parameters + parameter
                    } else {
                        tool.parameters.toMutableList().apply { set(dialogState.index, parameter) }
                    }
                    val newTools = draft.tools.toMutableList().apply {
                        set(toolIndex, tool.copy(parameters = newParams))
                    }
                    draft.copy(tools = newTools, isDirty = true)
                } else draft
            }
        }
        // Go back to tool dialog
        showEditToolDialog(
            (dialogState as? SkillStudioDialogState.EditParameter)?.toolIndex ?: 0
        )
    }

    fun deleteParameter(toolIndex: Int, paramIndex: Int) {
        updateDraft { draft ->
            if (toolIndex in draft.tools.indices) {
                val tool = draft.tools[toolIndex]
                val newParams = tool.parameters.toMutableList().apply { removeAt(paramIndex) }
                val newTools = draft.tools.toMutableList().apply {
                    set(toolIndex, tool.copy(parameters = newParams))
                }
                draft.copy(tools = newTools, isDirty = true)
            } else draft
        }
    }

    // ========================================================================
    // Environment Variable Editing
    // ========================================================================

    fun showAddEnvVarDialog() {
        _dialogState.value = SkillStudioDialogState.EditEnvVar(
            envVar = EnvVarRequirement(name = ""),
            isNew = true
        )
    }

    fun showEditEnvVarDialog(index: Int) {
        val current = getCurrentDraft() ?: return
        if (index in current.environmentVariables.indices) {
            _dialogState.value = SkillStudioDialogState.EditEnvVar(
                envVar = current.environmentVariables[index],
                isNew = false,
                index = index
            )
        }
    }

    fun saveEnvVar(envVar: EnvVarRequirement) {
        val dialogState = _dialogState.value
        if (dialogState is SkillStudioDialogState.EditEnvVar) {
            updateDraft {
                val newEnvVars = if (dialogState.isNew) {
                    it.environmentVariables + envVar
                } else {
                    it.environmentVariables.toMutableList().apply { set(dialogState.index, envVar) }
                }
                it.copy(environmentVariables = newEnvVars, isDirty = true)
            }
        }
        _dialogState.value = SkillStudioDialogState.None
    }

    fun deleteEnvVar(index: Int) {
        updateDraft {
            it.copy(
                environmentVariables = it.environmentVariables.toMutableList().apply { removeAt(index) },
                isDirty = true
            )
        }
    }

    // ========================================================================
    // Binary Editing
    // ========================================================================

    fun addBinary(binary: String) {
        updateDraft {
            val normalized = binary.trim()
            if (normalized.isNotBlank() && normalized !in it.requiredBinaries) {
                it.copy(requiredBinaries = it.requiredBinaries + normalized, isDirty = true)
            } else it
        }
    }

    fun removeBinary(binary: String) {
        updateDraft { it.copy(requiredBinaries = it.requiredBinaries - binary, isDirty = true) }
    }

    // ========================================================================
    // Card Expansion
    // ========================================================================

    fun toggleCardExpansion(cardId: String) {
        val current = _state.value
        if (current is SkillStudioScreenState.Editing) {
            val newExpanded = if (cardId in current.expandedCards) {
                current.expandedCards - cardId
            } else {
                current.expandedCards + cardId
            }
            _state.value = current.copy(expandedCards = newExpanded)
        }
    }

    // ========================================================================
    // Preview & Validation
    // ========================================================================

    fun showPreview() {
        val current = getCurrentDraft() ?: return
        val errors = current.validate()

        if (errors.isNotEmpty()) {
            _state.value = SkillStudioScreenState.Editing(
                draft = current,
                expandedCards = ((_state.value as? SkillStudioScreenState.Editing)?.expandedCards ?: emptySet()),
                validationErrors = errors
            )
            return
        }

        val markdown = current.toSkillMd()
        _state.value = SkillStudioScreenState.Preview(
            draft = current,
            markdown = markdown
        )
    }

    fun setPreviewTab(tab: PreviewTab) {
        val current = _state.value
        if (current is SkillStudioScreenState.Preview) {
            _state.value = current.copy(activeTab = tab)
        }
    }

    fun backToEditing() {
        val draft = when (val current = _state.value) {
            is SkillStudioScreenState.Preview -> current.draft
            is SkillStudioScreenState.SecurityReview -> current.draft
            is SkillStudioScreenState.Error -> current.draft
            else -> return
        }

        if (draft != null) {
            _state.value = SkillStudioScreenState.Editing(
                draft = draft,
                expandedCards = setOf("metadata")
            )
        }
    }

    // ========================================================================
    // Import
    // ========================================================================

    fun validateAndShowSecurityReport() {
        val current = getCurrentDraft() ?: return

        viewModelScope.launch {
            _state.value = SkillStudioScreenState.Loading
            try {
                val markdown = current.toSkillMd()
                val response = apiClient.validateSkill(markdown)

                _state.value = SkillStudioScreenState.SecurityReview(
                    draft = current,
                    report = response.security
                )
            } catch (e: Exception) {
                log("ERROR", "validateAndShowSecurityReport", "Validation failed: ${e.message}")
                _state.value = SkillStudioScreenState.Error(
                    message = "Validation failed: ${e.message}",
                    draft = current
                )
            }
        }
    }

    fun importAsAdapter() {
        val current = when (val state = _state.value) {
            is SkillStudioScreenState.SecurityReview -> state.draft
            is SkillStudioScreenState.Preview -> state.draft
            else -> return
        }

        viewModelScope.launch {
            _state.value = SkillStudioScreenState.Importing(current)
            try {
                val markdown = current.toSkillMd()
                val response = apiClient.importSkill(markdown, sourceUrl = current.sourceUrl, autoLoad = true)

                if (response.success) {
                    log("INFO", "importAsAdapter", "Import succeeded: ${response.moduleName}")
                    _state.value = SkillStudioScreenState.ImportSuccess(
                        moduleName = response.moduleName,
                        toolsCreated = response.toolsCreated
                    )
                } else {
                    _state.value = SkillStudioScreenState.Error(
                        message = response.message,
                        draft = current
                    )
                }
            } catch (e: Exception) {
                log("ERROR", "importAsAdapter", "Import failed: ${e.message}")
                _state.value = SkillStudioScreenState.Error(
                    message = "Import failed: ${e.message}",
                    draft = current
                )
            }
        }
    }

    // ========================================================================
    // Dialog Management
    // ========================================================================

    fun dismissDialog() {
        _dialogState.value = SkillStudioDialogState.None
    }

    fun showAddTagDialog() {
        val current = getCurrentDraft() ?: return
        _dialogState.value = SkillStudioDialogState.AddTag(current.tags)
    }

    // ========================================================================
    // Helpers
    // ========================================================================

    private fun getCurrentDraft(): SkillDraft? {
        return when (val current = _state.value) {
            is SkillStudioScreenState.Editing -> current.draft
            is SkillStudioScreenState.Preview -> current.draft
            is SkillStudioScreenState.SecurityReview -> current.draft
            is SkillStudioScreenState.Importing -> current.draft
            is SkillStudioScreenState.Error -> current.draft
            else -> null
        }
    }

    private fun updateDraft(transform: (SkillDraft) -> SkillDraft) {
        val current = _state.value
        if (current is SkillStudioScreenState.Editing) {
            _state.value = current.copy(draft = transform(current.draft))
        }
    }
}
