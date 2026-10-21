# Skill Studio Implementation Diagrams

## 1. Navigation & Screen Flow

```mermaid
flowchart TD
    subgraph Main["Main App Navigation"]
        Tools[Tools Screen]
        Adapters[Adapters Screen]
    end

    subgraph SkillStudio["Skill Studio"]
        SS_List[Skill Drafts List]
        SS_Edit[Skill Editor]
        SS_Preview[Preview Pane]
        SS_Import[Import Dialog]
        SS_Security[Security Report]
    end

    Tools -->|"+ Create Skill"| SS_List
    Tools -->|"Edit Skill Tool"| SS_Edit
    Adapters -->|"Import Skill"| SS_Import

    SS_List -->|"New"| SS_Edit
    SS_List -->|"Select Draft"| SS_Edit
    SS_Edit -->|"Preview"| SS_Preview
    SS_Edit -->|"Import"| SS_Security
    SS_Preview -->|"Back"| SS_Edit
    SS_Security -->|"Confirm"| SS_Import
    SS_Security -->|"Cancel"| SS_Edit
    SS_Import -->|"Success"| Tools
    SS_Import -->|"Failure"| SS_Edit
```

## 2. UI Component Hierarchy

```mermaid
flowchart TD
    subgraph SkillStudioScreen["SkillStudioScreen.kt"]
        TopBar[TopAppBar]
        Content[Main Content]
        FAB[FloatingActionButton]
    end

    subgraph TopBar
        BackBtn[btn_skill_back]
        Title["Skill Studio"]
        PreviewBtn[btn_skill_preview]
        ImportBtn[btn_skill_import]
    end

    subgraph Content
        LazyColumn[LazyColumn]
    end

    subgraph LazyColumn
        MetadataCard[MetadataCard]
        ToolsCard[ToolsListCard]
        EnvVarsCard[EnvVarsCard]
        BinariesCard[BinariesCard]
        InstructionsCard[InstructionsCard]
    end

    subgraph MetadataCard["card_metadata"]
        input_skill_name[input_skill_name]
        input_skill_desc[input_skill_description]
        input_skill_version[input_skill_version]
        chip_category[chip_category]
        chip_tags[chip_tags]
    end

    subgraph ToolsCard["card_tools"]
        tool_list[tool_list_items]
        btn_add_tool[btn_add_tool]
    end

    subgraph EnvVarsCard["card_env_vars"]
        env_list[env_var_list_items]
        btn_add_env[btn_add_env_var]
    end

    subgraph InstructionsCard["card_instructions"]
        input_instructions[input_instructions_md]
    end

    FAB -->|"+ Add Tool"| ToolDialog

    subgraph ToolDialog["dialog_edit_tool"]
        input_tool_name[input_tool_name]
        input_tool_desc[input_tool_description]
        input_tool_when[input_tool_when_to_use]
        params_list[tool_params_list]
        btn_add_param[btn_add_parameter]
        btn_save_tool[btn_save_tool]
        btn_cancel_tool[btn_cancel_tool]
    end
```

## 3. State Machine

```mermaid
stateDiagram-v2
    [*] --> Empty: Launch

    Empty --> Editing: Create New / Load Draft

    state Editing {
        [*] --> MetadataFocus
        MetadataFocus --> ToolsFocus: Expand Tools
        ToolsFocus --> MetadataFocus: Collapse Tools
        MetadataFocus --> EnvFocus: Expand Env Vars
        EnvFocus --> MetadataFocus: Collapse Env
        MetadataFocus --> InstructionsFocus: Expand Instructions
        InstructionsFocus --> MetadataFocus: Collapse Instructions

        ToolsFocus --> EditingTool: Add/Edit Tool
        EditingTool --> ToolsFocus: Save/Cancel
    }

    Editing --> Previewing: Preview Button
    Previewing --> Editing: Back

    Editing --> Validating: Import Button
    Validating --> SecurityReview: Validation Complete
    SecurityReview --> Importing: User Confirms
    SecurityReview --> Editing: User Cancels / Issues Found

    Importing --> Success: Import OK
    Importing --> Error: Import Failed

    Success --> [*]: Navigate to Tools
    Error --> Editing: Show Error

    Editing --> Saving: Auto-save / Manual Save
    Saving --> Editing: Save Complete
```

## 4. API Interaction Sequence

```mermaid
sequenceDiagram
    participant UI as SkillStudioScreen
    participant VM as SkillStudioViewModel
    participant API as CIRISApiClient
    participant BE as skill_import.py

    Note over UI,BE: Create New Skill Flow
    UI->>VM: createNewDraft()
    VM->>VM: _state.update(Editing(emptyDraft))

    Note over UI,BE: Edit Metadata
    UI->>VM: updateMetadata(name, desc, ...)
    VM->>VM: _state.update(draft.copy(...))

    Note over UI,BE: Add Tool
    UI->>VM: addTool(toolDef)
    VM->>VM: draft.tools.add(toolDef)

    Note over UI,BE: Preview (Generate SKILL.md)
    UI->>VM: generatePreview()
    VM->>VM: buildSkillMd(draft)
    VM-->>UI: previewMarkdown

    Note over UI,BE: Validate Before Import
    UI->>VM: validateDraft()
    VM->>API: POST /v1/system/skills/validate
    API->>BE: validate_skill(content)
    BE->>BE: SecurityScanner.scan()
    BE-->>API: ValidationResponse
    API-->>VM: SecurityReport
    VM-->>UI: showSecurityReport()

    Note over UI,BE: Import as Adapter
    UI->>VM: importAsAdapter()
    VM->>API: POST /v1/system/skills/import
    API->>BE: import_skill(content)
    BE->>BE: SkillToAdapterConverter.convert()
    BE-->>API: ImportResponse
    API-->>VM: ImportResult
    VM-->>UI: navigateToTools()
```

## 5. Data Flow

```mermaid
flowchart LR
    subgraph UI["UI Layer (Compose)"]
        Screen[SkillStudioScreen]
        Dialogs[Tool/Env Dialogs]
    end

    subgraph State["State Layer"]
        VM[SkillStudioViewModel]
        StateFlow[StateFlow<ScreenState>]
        Draft[SkillDraft]
    end

    subgraph Network["Network Layer"]
        Client[CIRISApiClient]
        Ktor[Ktor HTTP]
    end

    subgraph Backend["Backend (Python)"]
        Routes[skill_import.py routes]
        Parser[OpenClawSkillParser]
        Scanner[SkillSecurityScanner]
        Converter[SkillToAdapterConverter]
    end

    subgraph Storage["Local Storage"]
        Prefs[EncryptedPrefs/Keychain]
        DraftDB[Draft Database]
    end

    Screen -->|"User Input"| VM
    Dialogs -->|"Tool/Env Data"| VM
    VM -->|"Update State"| StateFlow
    StateFlow -->|"Collect"| Screen

    VM -->|"API Calls"| Client
    Client -->|"HTTP"| Ktor
    Ktor -->|"REST"| Routes

    Routes -->|"Parse"| Parser
    Routes -->|"Scan"| Scanner
    Routes -->|"Convert"| Converter

    VM -->|"Save Draft"| DraftDB
    DraftDB -->|"Load Draft"| VM
```

## 6. SkillDraft Data Model

```mermaid
classDiagram
    class SkillDraft {
        +String name
        +String description
        +String version
        +String author
        +String homepage
        +String license
        +List~String~ tags
        +String category
        +List~EnvVarRequirement~ environmentVariables
        +List~String~ requiredBinaries
        +List~ToolDefinition~ tools
        +String instructions
        +Boolean isDirty
        +Long? lastSaved
        +String? sourceUrl
        +toSkillMd(): String
    }

    class EnvVarRequirement {
        +String name
        +String description
        +Boolean required
        +String? defaultValue
    }

    class ToolDefinition {
        +String name
        +String description
        +List~ToolParameter~ parameters
        +String whenToUse
        +List~String~ examples
        +Int cost
    }

    class ToolParameter {
        +String name
        +String type
        +String description
        +Boolean required
        +String? default
    }

    class SecurityReport {
        +Int totalFindings
        +Int criticalCount
        +Int highCount
        +Int mediumCount
        +Boolean safeToImport
        +String summary
        +List~SecurityFinding~ findings
    }

    class SecurityFinding {
        +String severity
        +String category
        +String title
        +String description
        +String? evidence
        +String recommendation
    }

    SkillDraft "1" *-- "*" EnvVarRequirement
    SkillDraft "1" *-- "*" ToolDefinition
    ToolDefinition "1" *-- "*" ToolParameter
    SecurityReport "1" *-- "*" SecurityFinding
```

## 7. Screen Layouts

### 7.1 Main Editor Screen

```
┌─────────────────────────────────────────────────────────────┐
│  ◀ [btn_skill_back]   Skill Studio    👁 [btn_skill_preview] │
│                                        📥 [btn_skill_import] │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  📦 Metadata [card_metadata]                   ▼    │   │
│  │  ─────────────────────────────────────────────────  │   │
│  │  Name: [input_skill_name___________________]        │   │
│  │  Desc: [input_skill_description____________]        │   │
│  │  Ver:  [input_skill_version] Cat: [chip_category]   │   │
│  │  Tags: [chip_tags_container_______________]         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  🔧 Tools (2) [card_tools]                     ▶    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  🔑 Environment Variables (1) [card_env_vars]  ▶    │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  📝 Instructions [card_instructions]           ▼    │   │
│  │  ─────────────────────────────────────────────────  │   │
│  │  [input_instructions_md                           ] │   │
│  │  [                                                ] │   │
│  │  [# Weather Skill                                 ] │   │
│  │  [                                                ] │   │
│  │  [This skill provides weather information...      ] │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│                                         [fab_add_tool] (+)  │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 Tools Card Expanded

```
┌─────────────────────────────────────────────────────────────┐
│  🔧 Tools (2) [card_tools]                             ▼   │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  ┌───────────────────────────────────────────────────┐     │
│  │ [item_tool_0]                                     │     │
│  │ 🔧 get_weather                       [btn_edit] ✏️│     │
│  │    Get current weather for a location [btn_del] 🗑️│     │
│  │    Params: location (string), units (string)      │     │
│  └───────────────────────────────────────────────────┘     │
│                                                             │
│  ┌───────────────────────────────────────────────────┐     │
│  │ [item_tool_1]                                     │     │
│  │ 🔧 get_forecast                      [btn_edit] ✏️│     │
│  │    Get 5-day weather forecast        [btn_del] 🗑️│     │
│  │    Params: location (string), days (int)          │     │
│  └───────────────────────────────────────────────────┘     │
│                                                             │
│  [btn_add_tool] + Add Tool                                  │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 Tool Edit Dialog

```
┌─────────────────────────────────────────────────────────────┐
│  Edit Tool [dialog_edit_tool]                          ✕   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Name [input_tool_name]:                                    │
│  [get_weather_____________________________________]         │
│                                                             │
│  Description [input_tool_description]:                      │
│  [Get current weather conditions for a location___]         │
│                                                             │
│  Cost [input_tool_cost]:                                    │
│  [0] credits                                                │
│                                                             │
│  When to Use [input_tool_when_to_use]:                     │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ Use when the user asks about current weather,         │ │
│  │ temperature, or conditions for a specific location.   │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  Parameters [list_tool_params]:                            │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ location (string) *required          [btn_edit] [🗑️]  │ │
│  │   City name or coordinates                            │ │
│  ├───────────────────────────────────────────────────────┤ │
│  │ units (string) default: "metric"     [btn_edit] [🗑️]  │ │
│  │   Temperature units (metric/imperial)                 │ │
│  └───────────────────────────────────────────────────────┘ │
│  [btn_add_parameter] + Add Parameter                        │
│                                                             │
│                       [btn_cancel_tool] Cancel              │
│                       [btn_save_tool] Save Tool             │
└─────────────────────────────────────────────────────────────┘
```

### 7.4 Preview Screen

```
┌─────────────────────────────────────────────────────────────┐
│  ◀ [btn_preview_back]  Preview         [btn_copy_md] Copy  │
├─────────────────────────────────────────────────────────────┤
│  [tab_skill_md] SKILL.md │ [tab_security] Security │       │
│  ═══════════════════════   ────────────────────────        │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ ---                                                   │ │
│  │ name: weather-skill                                   │ │
│  │ description: Get weather forecasts for any location   │ │
│  │ version: 1.0.0                                        │ │
│  │ category: general                                     │ │
│  │ tags: [weather, api]                                  │ │
│  │ metadata:                                             │ │
│  │   openclaw:                                           │ │
│  │     requires:                                         │ │
│  │       env: [WEATHER_API_KEY]                          │ │
│  │     skill_key: weather                                │ │
│  │ ---                                                   │ │
│  │                                                       │ │
│  │ # Weather Skill                                       │ │
│  │                                                       │ │
│  │ This skill provides weather information using         │ │
│  │ the OpenWeatherMap API.                              │ │
│  │                                                       │ │
│  │ ## Tools                                              │ │
│  │                                                       │ │
│  │ ### get_weather                                       │ │
│  │ Get current weather for a location.                   │ │
│  │ - location (string, required): City or coords         │ │
│  │ - units (string, default: metric)                     │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│                              [btn_import_now] Import Now    │
└─────────────────────────────────────────────────────────────┘
```

### 7.5 Security Report Screen

```
┌─────────────────────────────────────────────────────────────┐
│  ◀ [btn_security_back]  Security Report                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  ✅ SAFE TO IMPORT                                    │ │
│  │  ─────────────────────────────────────────────────    │ │
│  │  No critical or high severity issues found.           │ │
│  │                                                       │ │
│  │  📊 Summary:                                          │ │
│  │  • Critical: 0  • High: 0  • Medium: 1  • Low: 2     │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  ⚠️ MEDIUM: Undeclared network access                 │ │
│  │  ─────────────────────────────────────────────────    │ │
│  │  This skill uses 'curl' but doesn't list it          │ │
│  │  in requirements.                                     │ │
│  │                                                       │ │
│  │  Evidence: curl https://api.openweathermap.org        │ │
│  │                                                       │ │
│  │  Recommendation: Add 'curl' to required binaries     │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  ℹ️ LOW: Uses secret not listed in requirements       │ │
│  │  ─────────────────────────────────────────────────    │ │
│  │  Instructions mention 'WEATHER_API_KEY' but it's     │ │
│  │  already declared. (False positive)                   │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│         [btn_cancel_import] Cancel                          │
│         [btn_confirm_import] Import Anyway                  │
└─────────────────────────────────────────────────────────────┘
```

## 8. Test Tags Reference

| Element | Test Tag | Type |
|---------|----------|------|
| Back button | `btn_skill_back` | IconButton |
| Preview button | `btn_skill_preview` | IconButton |
| Import button | `btn_skill_import` | Button |
| Metadata card | `card_metadata` | Card |
| Skill name input | `input_skill_name` | TextField |
| Skill description | `input_skill_description` | TextField |
| Skill version | `input_skill_version` | TextField |
| Category chip | `chip_category` | FilterChip |
| Tags container | `chip_tags_container` | FlowRow |
| Tools card | `card_tools` | Card |
| Tool item | `item_tool_{index}` | ListItem |
| Add tool button | `btn_add_tool` | Button |
| Edit tool button | `btn_edit_tool_{index}` | IconButton |
| Delete tool button | `btn_delete_tool_{index}` | IconButton |
| Env vars card | `card_env_vars` | Card |
| Add env var button | `btn_add_env_var` | Button |
| Instructions card | `card_instructions` | Card |
| Instructions input | `input_instructions_md` | TextField |
| FAB add tool | `fab_add_tool` | FAB |
| Tool dialog | `dialog_edit_tool` | AlertDialog |
| Tool name input | `input_tool_name` | TextField |
| Tool description | `input_tool_description` | TextField |
| Tool when to use | `input_tool_when_to_use` | TextField |
| Tool cost input | `input_tool_cost` | TextField |
| Params list | `list_tool_params` | LazyColumn |
| Add param button | `btn_add_parameter` | Button |
| Save tool button | `btn_save_tool` | Button |
| Cancel tool button | `btn_cancel_tool` | TextButton |
| Preview tabs | `tab_skill_md`, `tab_security` | Tab |
| Copy MD button | `btn_copy_md` | IconButton |
| Import now button | `btn_import_now` | Button |
| Security back | `btn_security_back` | IconButton |
| Cancel import | `btn_cancel_import` | TextButton |
| Confirm import | `btn_confirm_import` | Button |

## 9. API Endpoints

| Endpoint | Method | Request | Response | Purpose |
|----------|--------|---------|----------|---------|
| `/v1/system/skills/validate` | POST | `{skill_md_content: str}` | `ValidationResponse` | Validate without import |
| `/v1/system/skills/import` | POST | `SkillImportRequest` | `SkillImportResponse` | Import as adapter |
| `/v1/system/skills/preview` | POST | `{skill_md_content: str}` | `SkillPreviewResponse` | Get preview info |
| `/v1/system/skills/imported` | GET | - | `ImportedSkillsListResponse` | List imported skills |
| `/v1/system/skills/drafts` | GET | - | `{drafts: [SkillDraft]}` | List local drafts |
| `/v1/system/skills/drafts` | POST | `SkillDraft` | `{id: str}` | Save draft |
| `/v1/system/skills/drafts/{id}` | DELETE | - | `{success: bool}` | Delete draft |

## 10. Implementation Checklist

### Backend (Python)
- [ ] Add `/v1/system/skills/validate` endpoint
- [ ] Add draft storage endpoints (local SQLite)
- [ ] Update security scanner if needed

### Shared Module (Kotlin)
- [ ] `SkillDraft.kt` - Data model
- [ ] `SkillStudioViewModel.kt` - Business logic
- [ ] `SkillStudioState.kt` - State definitions
- [ ] Add API methods to `CIRISApiClient.kt`

### UI (Compose)
- [ ] `SkillStudioScreen.kt` - Main editor
- [ ] `MetadataCard.kt` - Name/desc/version editing
- [ ] `ToolsCard.kt` - Tools list with expand/collapse
- [ ] `ToolEditDialog.kt` - Add/edit tool dialog
- [ ] `ParameterEditDialog.kt` - Add/edit parameter dialog
- [ ] `EnvVarsCard.kt` - Environment variables
- [ ] `InstructionsCard.kt` - Markdown instructions
- [ ] `SkillPreviewScreen.kt` - SKILL.md preview
- [ ] `SecurityReportScreen.kt` - Security findings

### Navigation
- [ ] Add routes to navigation graph
- [ ] Connect from Tools screen
- [ ] Connect from Adapters screen

### Testing
- [ ] Unit tests for SkillDraft
- [ ] Unit tests for SkillStudioViewModel
- [ ] E2E tests using desktop test mode
