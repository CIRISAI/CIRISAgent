# Functional Specification Document: Skill Studio

Version: 1.0
Date: April 12, 2026
Status: DRAFT
Author: CIRIS Team

## 1. Overview

**Skill Studio** is a visual editor for creating, editing, and managing OpenClaw SKILL.md files within the CIRIS unified UX. It transforms skill authoring from a text-editing task into a guided, card-based experience with real-time preview, security scanning, and one-click import.

### 1.1 Goals

1. **Lower Barrier to Entry**: Non-developers should be able to create skills without learning YAML frontmatter syntax
2. **Progressive Disclosure**: Show metadata only at startup, reveal full instructions contextually
3. **Real-Time Validation**: Catch errors and security issues before import
4. **Cross-Platform**: Same experience on Android, iOS, Windows, macOS, Linux
5. **Offline-First**: Works without network for local skill editing

### 1.2 Non-Goals

- Full IDE functionality (syntax highlighting, auto-complete)
- Multi-user collaboration features
- Version control integration (beyond import/export)
- Skill execution/testing within the editor

## 2. Architecture

### 2.1 Component Structure

```
shared/
├── viewmodels/
│   └── SkillStudioViewModel.kt     # Business logic, state management
├── models/
│   └── SkillDraft.kt               # Draft skill data model
├── ui/
│   └── screens/
│       ├── SkillStudioScreen.kt    # Main editor screen
│       ├── SkillCardEditor.kt      # Card-based section editors
│       ├── SkillPreviewPane.kt     # Live SKILL.md preview
│       └── SkillSecurityReport.kt  # Security scan results

ciris_engine/logic/adapters/api/routes/system/
└── skill_import.py                 # Already exists - add preview endpoint
```

### 2.2 Data Flow

```
┌─────────────────┐         ┌────────────────────┐         ┌───────────────┐
│  SkillStudio    │   API   │  skill_import.py   │         │   ClawHub     │
│  (KMP Client)   │◄───────►│  /skill/preview    │◄───────►│   (External)  │
│                 │         │  /skill/import     │         │               │
└─────────────────┘         └────────────────────┘         └───────────────┘
        │                            │
        ▼                            ▼
   SkillDraft               OpenClawSkillParser
   (local state)             SecurityScanner
```

## 3. Data Models

### 3.1 SkillDraft (Kotlin)

```kotlin
data class SkillDraft(
    // YAML Frontmatter Fields
    val name: String = "",
    val description: String = "",
    val version: String = "1.0.0",
    val author: String = "",
    val homepage: String = "",
    val license: String = "MIT",
    val tags: List<String> = emptyList(),
    val category: String = "general",

    // Requirements
    val environmentVariables: List<EnvVarRequirement> = emptyList(),
    val requiredBinaries: List<String> = emptyList(),

    // Tool Definitions
    val tools: List<ToolDefinition> = emptyList(),

    // Instructions (Markdown)
    val instructions: String = "",

    // State
    val isDirty: Boolean = false,
    val lastSaved: Long? = null,
    val sourceUrl: String? = null
)

data class EnvVarRequirement(
    val name: String,
    val description: String = "",
    val required: Boolean = true,
    val defaultValue: String? = null
)

data class ToolDefinition(
    val name: String,
    val description: String = "",
    val parameters: List<ToolParameter> = emptyList(),
    val whenToUse: String = "",
    val examples: List<String> = emptyList(),
    val cost: Int = 0
)

data class ToolParameter(
    val name: String,
    val type: String = "string",
    val description: String = "",
    val required: Boolean = true,
    val default: String? = null
)
```

### 3.2 API Models (Python)

The existing `SkillPreviewResponse` and `SecurityReportResponse` in `skill_import.py` already cover preview needs. Add:

```python
class SkillValidateRequest(BaseModel):
    """Request to validate a skill draft without importing."""
    skill_md_content: str = Field(..., description="SKILL.md content to validate")

class SkillValidateResponse(BaseModel):
    """Validation results."""
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    security: SecurityReportResponse
    preview: SkillPreviewResponse
```

## 4. User Interface

### 4.1 Screen Layout

```
┌─────────────────────────────────────────────────────────────┐
│  ◀ Back    Skill Studio                      💾 ⚡ Preview  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  📦 Metadata                                    ▼   │   │
│  │  ───────────────────────────────────────────────────│   │
│  │  Name:        [My Weather Skill_______________]     │   │
│  │  Description: [Get weather forecasts for any____]   │   │
│  │  Version:     [1.0.0] Category: [general ▾]         │   │
│  │  Tags:        [+weather] [+api] [+ Add Tag]         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  🔧 Tools (1)                                   ▼   │   │
│  │  ───────────────────────────────────────────────────│   │
│  │  ┌───────────────────────────────────────────┐      │   │
│  │  │ get_weather                          ✏️ 🗑️ │      │   │
│  │  │ Get current weather for a location        │      │   │
│  │  └───────────────────────────────────────────┘      │   │
│  │  [+ Add Tool]                                       │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  🔑 Environment Variables (1)                   ▼   │   │
│  │  ───────────────────────────────────────────────────│   │
│  │  WEATHER_API_KEY: API key for weather service       │   │
│  │  [+ Add Variable]                                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  📝 Instructions                                ▼   │   │
│  │  ───────────────────────────────────────────────────│   │
│  │  # Weather Skill                                    │   │
│  │                                                     │   │
│  │  This skill provides weather information using      │   │
│  │  the OpenWeatherMap API.                           │   │
│  │                                                     │   │
│  │  ## When to Use                                     │   │
│  │  When the user asks about weather, forecasts...     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Card-Based Editing

Each section is a collapsible card:

| Card | Default State | Contents |
|------|---------------|----------|
| Metadata | Expanded | Name, description, version, category, tags |
| Tools | Collapsed (show count) | List of tool definitions with inline edit |
| Environment | Collapsed (show count) | Required env vars and descriptions |
| Binaries | Collapsed (show count) | Required binary dependencies |
| Instructions | Collapsed (show preview) | Full markdown editor |

### 4.3 Tool Definition Dialog

When editing a tool:

```
┌─────────────────────────────────────────────────────────┐
│  Edit Tool: get_weather                          ✕     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Name:         [get_weather_________________]           │
│  Description:  [Get current weather conditions__]       │
│  Cost:         [0] credits                              │
│                                                         │
│  When to Use:                                           │
│  ┌───────────────────────────────────────────────────┐ │
│  │ Use when the user asks about weather, temperature,│ │
│  │ or forecasts for a specific location.             │ │
│  └───────────────────────────────────────────────────┘ │
│                                                         │
│  Parameters:                                            │
│  ┌─────────────────────────────────────────────────┐   │
│  │ location (string) *required                      │   │
│  │   City name or coordinates                       │   │
│  ├─────────────────────────────────────────────────┤   │
│  │ units (string) default: "metric"                 │   │
│  │   Temperature units (metric/imperial)            │   │
│  └─────────────────────────────────────────────────┘   │
│  [+ Add Parameter]                                      │
│                                                         │
│                              [Cancel]  [Save Tool]      │
└─────────────────────────────────────────────────────────┘
```

### 4.4 Preview Pane

Side-by-side or bottom sheet preview showing:

1. **Generated SKILL.md** - Raw markdown output
2. **Security Report** - Real-time security scan results
3. **Import Preview** - What tools will be created

```
┌─────────────────────────────────────────────────────────┐
│  Preview                                        [Copy] │
├─────────────────────────────────────────────────────────┤
│  📄 SKILL.md  │  🔒 Security  │  📦 Import             │
│  ─────────────┴───────────────┴─────────────────────── │
│                                                         │
│  ---                                                    │
│  name: My Weather Skill                                 │
│  description: Get weather forecasts for any location    │
│  version: 1.0.0                                         │
│  category: general                                      │
│  tags: [weather, api]                                   │
│  env_vars:                                              │
│    - WEATHER_API_KEY: API key for weather service       │
│  tools:                                                 │
│    - name: get_weather                                  │
│      description: Get current weather conditions        │
│      parameters:                                        │
│        location:                                        │
│          type: string                                   │
│          required: true                                 │
│          description: City name or coordinates          │
│  ---                                                    │
│                                                         │
│  # Weather Skill                                        │
│  ...                                                    │
└─────────────────────────────────────────────────────────┘
```

## 5. User Flows

### 5.1 Create New Skill

```
1. Navigate to Tools tab
2. Tap "+" (Add) → "Create Skill"
3. Skill Studio opens with empty draft
4. Fill in metadata (name, description)
5. Add tools with parameters
6. Add required env vars
7. Write instructions in markdown
8. Preview → Security check passes
9. "Import as Adapter" → Skill imported
10. Redirected to Tools tab showing new tools
```

### 5.2 Edit Existing Skill

```
1. Navigate to Tools tab
2. Long-press on skill-based tool
3. "Edit Source Skill" option
4. Skill Studio opens with loaded content
5. Make changes
6. Preview → "Update Adapter"
7. Adapter reloaded with changes
```

### 5.3 Import from ClawHub

```
1. Skill Studio → Menu → "Import from URL"
2. Enter ClawHub URL
3. Skill loaded and parsed
4. Review security scan results
5. Make modifications if needed
6. "Import as Adapter"
```

### 5.4 Export to Clipboard/File

```
1. Skill Studio with draft
2. Preview tab → "Copy SKILL.md"
3. Content copied to clipboard
-or-
2. Menu → "Export to File"
3. File saved to ~/ciris/skills/
```

## 6. API Endpoints

### 6.1 Existing Endpoints (No Changes)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/system/skills/import` | POST | Import skill from content/URL/path |
| `/v1/system/skills/preview` | POST | Preview skill before import |
| `/v1/system/skills/imported` | GET | List imported skills |

### 6.2 New Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/system/skills/validate` | POST | Validate skill content (no import) |
| `/v1/system/skills/drafts` | GET | List saved drafts (local) |
| `/v1/system/skills/drafts` | POST | Save draft (local) |
| `/v1/system/skills/drafts/{id}` | DELETE | Delete draft |

## 7. State Management

### 7.1 SkillStudioViewModel

```kotlin
class SkillStudioViewModel(
    private val apiClient: CIRISApiClient,
    private val skillDraftStorage: SkillDraftStorage
) : ViewModel() {

    sealed class ScreenState {
        object Loading : ScreenState()
        data class Editing(val draft: SkillDraft) : ScreenState()
        data class Preview(val markdown: String, val security: SecurityReport) : ScreenState()
        data class Error(val message: String) : ScreenState()
    }

    private val _state = MutableStateFlow<ScreenState>(ScreenState.Loading)
    val state: StateFlow<ScreenState> = _state.asStateFlow()

    // Draft management
    fun createNewDraft()
    fun loadDraft(id: String)
    fun loadFromUrl(url: String)
    fun saveDraft()
    fun discardChanges()

    // Editing
    fun updateMetadata(name: String, description: String, ...)
    fun addTool(tool: ToolDefinition)
    fun updateTool(index: Int, tool: ToolDefinition)
    fun removeTool(index: Int)
    fun addEnvVar(envVar: EnvVarRequirement)
    fun updateInstructions(markdown: String)

    // Preview & Import
    fun generatePreview(): String  // Generates SKILL.md
    suspend fun validateDraft(): ValidationResult
    suspend fun importAsAdapter(): ImportResult
}
```

### 7.2 Local Draft Storage

Drafts stored in platform-specific secure storage:

| Platform | Storage |
|----------|---------|
| Android | EncryptedSharedPreferences |
| iOS | Keychain |
| Desktop | Application data directory |

## 8. Security Considerations

### 8.1 Client-Side Validation

- Max skill name length: 50 characters
- Max description length: 500 characters
- Max tool count: 20
- Max parameter count per tool: 10
- Max instruction length: 50,000 characters

### 8.2 Server-Side Security Scan

Existing `SecurityScanner` in skill_import.py handles:
- Command injection patterns
- Sensitive data exposure
- Privilege escalation attempts
- Network access patterns
- File system access patterns

### 8.3 Path Security

The existing `_resolve_to_allowed_path()` function (recently fixed) ensures:
- No path traversal attacks
- No access to sensitive directories (.ssh, .gnupg, etc.)
- Proper base directory containment

## 9. Localization

All UI strings use the existing localization system:

```kotlin
// New keys to add to localization/{lang}.json
"mobile.skill_studio_title" -> "Skill Studio"
"mobile.skill_studio_metadata" -> "Metadata"
"mobile.skill_studio_tools" -> "Tools"
"mobile.skill_studio_env_vars" -> "Environment Variables"
"mobile.skill_studio_instructions" -> "Instructions"
"mobile.skill_studio_preview" -> "Preview"
"mobile.skill_studio_import" -> "Import as Adapter"
"mobile.skill_studio_validate" -> "Validate"
"mobile.skill_studio_new_skill" -> "New Skill"
"mobile.skill_studio_add_tool" -> "Add Tool"
"mobile.skill_studio_add_param" -> "Add Parameter"
"mobile.skill_studio_add_env_var" -> "Add Variable"
```

## 10. Testing Strategy

### 10.1 Unit Tests

| Component | Tests |
|-----------|-------|
| SkillDraft | Serialization, validation |
| SkillStudioViewModel | State transitions, CRUD operations |
| SKILL.md generator | Frontmatter formatting, escaping |

### 10.2 Integration Tests

| Flow | Test |
|------|------|
| Create → Preview → Import | Full workflow with mock API |
| Load from URL → Edit → Import | URL fetching and modification |
| Security scan failure | Blocked import, error display |

### 10.3 E2E Tests (Desktop Test Mode)

```bash
# Create skill via UI automation
curl -X POST http://localhost:8091/act -d '{"testTag":"btn_add_skill","action":"click"}'
curl -X POST http://localhost:8091/act -d '{"testTag":"input_skill_name","action":"input","text":"Test Skill"}'
curl -X POST http://localhost:8091/act -d '{"testTag":"btn_add_tool","action":"click"}'
# ... continue workflow
```

## 11. Implementation Phases

### Phase 1: Core Editor (MVP)

1. SkillDraft model and ViewModel
2. Basic card-based editor UI
3. SKILL.md generation
4. Integration with existing `/skill/preview` endpoint
5. Import functionality

### Phase 2: Polish

1. Tool definition dialog
2. Parameter editor
3. Live preview pane
4. Local draft persistence
5. Security report display

### Phase 3: Advanced Features

1. Import from ClawHub URL
2. Export to file
3. Edit existing imported skills
4. Template library (common skill patterns)

## 12. Dependencies

### 12.1 Existing Dependencies

- `ToolsViewModel`, `ToolsScreen` - Navigation integration
- `CIRISApiClient` - API communication
- `skill_import.py` - Backend parsing and import
- `OpenClawSkillParser` - SKILL.md parsing
- `SecurityScanner` - Security validation

### 12.2 New Dependencies

None required - builds on existing infrastructure.

## 13. Open Questions

1. **Draft Auto-Save**: How frequently? On blur? On timer?
2. **Template Skills**: Should we bundle starter templates?
3. **Skill Marketplace**: Future ClawHub publishing integration?
4. **Skill Versioning**: Track versions of user-created skills?

## 14. Appendix: SKILL.md Format Reference

Based on OpenClaw specification:

```yaml
---
name: skill-name
description: Short description
version: 1.0.0
category: general|communication|memory|system|secrets
tags: [tag1, tag2]
author: Author Name
homepage: https://example.com
license: MIT

env_vars:
  - API_KEY: Description of API key

required_binaries:
  - binary_name

tools:
  - name: tool_name
    description: What it does
    parameters:
      param_name:
        type: string|number|boolean|array|object
        required: true|false
        description: Parameter description
        default: optional_default
    when_to_use: When to invoke this tool
    examples:
      - "Example usage"
    cost: 0
---

# Skill Instructions

Markdown content describing how to use the skill...
```
