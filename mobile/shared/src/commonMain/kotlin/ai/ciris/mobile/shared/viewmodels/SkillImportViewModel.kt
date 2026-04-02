package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.models.ImportedSkillData
import ai.ciris.mobile.shared.models.SkillImportResult
import ai.ciris.mobile.shared.models.SkillPreviewData
import ai.ciris.mobile.shared.platform.PlatformLogger
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * ViewModel for OpenClaw skill import feature.
 *
 * Manages three workflows:
 * 1. Browse/manage previously imported skills
 * 2. Preview a SKILL.md before importing
 * 3. Import and auto-load a skill as an adapter
 */
class SkillImportViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    // ===== Imported Skills List =====
    private val _importedSkills = MutableStateFlow<List<ImportedSkillData>>(emptyList())
    val importedSkills: StateFlow<List<ImportedSkillData>> = _importedSkills.asStateFlow()

    // ===== Import Dialog State =====
    private val _showImportDialog = MutableStateFlow(false)
    val showImportDialog: StateFlow<Boolean> = _showImportDialog.asStateFlow()

    private val _skillMdContent = MutableStateFlow("")
    val skillMdContent: StateFlow<String> = _skillMdContent.asStateFlow()

    private val _sourceUrl = MutableStateFlow("")
    val sourceUrl: StateFlow<String> = _sourceUrl.asStateFlow()

    private val _preview = MutableStateFlow<SkillPreviewData?>(null)
    val preview: StateFlow<SkillPreviewData?> = _preview.asStateFlow()

    private val _importResult = MutableStateFlow<SkillImportResult?>(null)
    val importResult: StateFlow<SkillImportResult?> = _importResult.asStateFlow()

    // ===== Loading / Error =====
    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    private val _statusMessage = MutableStateFlow<String?>(null)
    val statusMessage: StateFlow<String?> = _statusMessage.asStateFlow()

    // ===== Import Dialog Phase =====
    enum class ImportPhase { PASTE, PREVIEW, RESULT }

    private val _importPhase = MutableStateFlow(ImportPhase.PASTE)
    val importPhase: StateFlow<ImportPhase> = _importPhase.asStateFlow()

    // ===== Actions =====

    fun fetchImportedSkills() {
        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null
            try {
                _importedSkills.value = apiClient.listImportedSkills()
                PlatformLogger.i("SkillImportVM", "Fetched ${_importedSkills.value.size} imported skills")
            } catch (e: Exception) {
                PlatformLogger.e("SkillImportVM", "Failed to fetch imported skills: ${e.message}")
                _error.value = "Failed to load imported skills: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun openImportDialog() {
        _showImportDialog.value = true
        _importPhase.value = ImportPhase.PASTE
        _skillMdContent.value = ""
        _sourceUrl.value = ""
        _preview.value = null
        _importResult.value = null
        _error.value = null
    }

    fun closeImportDialog() {
        _showImportDialog.value = false
        _importPhase.value = ImportPhase.PASTE
        _preview.value = null
        _importResult.value = null
        _error.value = null
    }

    fun updateSkillMdContent(content: String) {
        _skillMdContent.value = content
    }

    fun updateSourceUrl(url: String) {
        _sourceUrl.value = url
    }

    fun previewSkill() {
        val content = _skillMdContent.value
        if (content.isBlank()) {
            _error.value = "Please paste SKILL.md content"
            return
        }

        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null
            try {
                val url = _sourceUrl.value.ifBlank { null }
                val result = apiClient.previewSkillImport(content, url)
                _preview.value = result
                _importPhase.value = ImportPhase.PREVIEW
                PlatformLogger.i("SkillImportVM", "Preview: ${result.name} v${result.version}")
            } catch (e: Exception) {
                PlatformLogger.e("SkillImportVM", "Preview failed: ${e.message}")
                _error.value = "Preview failed: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun importSkill() {
        val content = _skillMdContent.value
        if (content.isBlank()) return

        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null
            try {
                val url = _sourceUrl.value.ifBlank { null }
                val result = apiClient.importSkill(content, url, autoLoad = true)
                _importResult.value = result
                _importPhase.value = ImportPhase.RESULT

                if (result.success) {
                    _statusMessage.value = result.message
                    // Refresh the list
                    fetchImportedSkills()
                } else {
                    _error.value = "Import failed: ${result.message}"
                }
                PlatformLogger.i("SkillImportVM", "Import result: ${result.message}")
            } catch (e: Exception) {
                PlatformLogger.e("SkillImportVM", "Import failed: ${e.message}")
                _error.value = "Import failed: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun deleteImportedSkill(moduleName: String) {
        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null
            try {
                val success = apiClient.deleteImportedSkill(moduleName)
                if (success) {
                    _statusMessage.value = "Skill '$moduleName' removed"
                    fetchImportedSkills()
                } else {
                    _error.value = "Failed to delete skill"
                }
            } catch (e: Exception) {
                _error.value = "Delete failed: ${e.message}"
            } finally {
                _isLoading.value = false
            }
        }
    }

    fun clearError() {
        _error.value = null
    }

    fun clearStatusMessage() {
        _statusMessage.value = null
    }
}
