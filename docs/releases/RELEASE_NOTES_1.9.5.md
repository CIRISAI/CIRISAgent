# Release Notes - v1.9.5

## Overview
This release adds live provider model listing for the setup wizard, resolves 12 SonarCloud issues across the codebase, and includes mobile stability improvements. The new `POST /v1/setup/list-models` endpoint enables a dynamic model dropdown in the setup wizard by querying LLM providers for their available models and annotating them with CIRIS compatibility data.

## Key Features

### Live Model Listing for Setup Wizard
- **New Endpoint**: `POST /v1/setup/list-models` queries LLM providers for available models in real time
- **7 Providers Supported**: Anthropic, Google, OpenAI, Groq, OpenRouter, Together, and Ollama (local)
- **CIRIS Compatibility Annotations**: Live models are cross-referenced with `MODEL_CAPABILITIES.json` for compatibility, tier, and recommendation data
- **Graceful Fallback**: Falls back to static model data from the capabilities DB when live queries fail (timeout, auth error, SDK unavailable)
- **Model Sorting**: Results sorted by recommended > compatible > unknown > incompatible, alphabetical within groups
- **No Auth Required**: Accessible during first-run setup without authentication

### SonarCloud Compliance
- **8 TODOs Implemented**: Converted existing TODO comments into functional improvements with tests
- **12 Issues Resolved**: Fixed unused parameters, user-controlled URL construction, always-same-return-value, and other code quality issues flagged by SonarCloud on PR

### Mobile Stability
- **Auto Token Refresh**: Mobile app now auto-refreshes auth token on 401 responses
- **Desktop-Only Adapter Filtering**: Added `platform_requirements` to desktop-only adapters so they don't appear on mobile
- **iOS Framework Paths**: Fixed SDK-specific framework paths for iOS builds
- **Production UI Cleanup**: Removed debug UI elements for production release

## Technical Details

### Provider Routing
| Provider | SDK / Method |
|----------|-------------|
| `anthropic` | `AsyncAnthropic().models.list()` with cursor pagination |
| `google` | `genai.Client().aio.models.list()` |
| `local` (Ollama) | `httpx GET /api/tags` (detected via `:11434` in URL) |
| All others | `AsyncOpenAI().models.list()` with auto-resolved base URLs |

### New Schemas
- `LiveModelInfo` - Model data with CIRIS compatibility annotations
- `ListModelsResponse` - Endpoint response with models, source, and fallback error

### Helper Functions (12 total)
- Per-provider listers: `_list_models_openai_compatible`, `_list_models_anthropic`, `_list_models_google`, `_list_models_ollama`
- Cross-reference: `_annotate_models_with_capabilities`
- Sorting: `_sort_models`
- Fallback: `_build_fallback_response`, `_get_static_fallback_models`
- Utilities: `_detect_ollama`, `_get_provider_base_url`, `_fetch_live_models`, `_list_models_for_provider`

### Security
- Ollama base URL sanitized via `urlparse` to prevent user-controlled URL injection (SonarCloud CWE compliance)
- All helper functions use immutable return patterns (no in-place mutation of input parameters)

## API Changes

### New Endpoint
- `POST /v1/setup/list-models` - Query provider API for live model list with CIRIS annotations

### Request
```json
{
  "provider": "anthropic",
  "api_key": "sk-ant-...",
  "base_url": null,
  "model": null
}
```

### Response
```json
{
  "data": {
    "provider": "anthropic",
    "models": [
      {
        "id": "claude-sonnet-4-20250514",
        "display_name": "Claude Sonnet 4",
        "ciris_compatible": true,
        "ciris_recommended": true,
        "tier": "default",
        "context_window": 200000,
        "source": "both"
      }
    ],
    "total_count": 15,
    "source": "live",
    "error": null
  }
}
```

## Testing
- 9022 unit tests passing
- 34 new tests for list-models (3 integration + 31 unit)
- QA runner: 6 live provider tests (5 providers + 1 static fallback) all passing
- SonarCloud quality gate passing

## Migration Notes
- No breaking changes
- New endpoint is additive; existing setup flow unchanged
- Mobile clients can optionally integrate the model dropdown (see `docs/UIUX_ADAPTER_INSTALLATION_UPDATE.md` Part 4)

## Full Commit History
- `033b54f7` feat(setup): Add POST /v1/setup/list-models for live provider model listing
- `a05ac012` fix(sonar): Address 3 SonarCloud issues from list-models PR
- `f0f24c2b` fix(sonar): Address 9 SonarCloud issues from PR
- `cd37e700` feat: Implement 8 SonarCloud TODOs with tests
- `ecfedb67` fix(mobile): Auto-refresh token on 401 auth errors
- `b24ccf2f` fix(mobile): Add platform_requirements to desktop-only adapters
- `e61044d9` fix(ios): SDK-specific framework paths and simplify migration comments
- `155e5425` fix(mobile): Remove debug UI elements for production release
- `5ddb9823` docs: Update README to reflect stable release status
- `4e3598da` chore(mobile): Bump version to 1.9.5 (versionCode 48)
- `9703b376` docs: Update README to reflect unified KMP mobile codebase
- `1856ce8b` refactor(api): Consolidate duplicate patterns in wa.py and partnership.py
- `9cf8ea32` fix(security): Move workflow permissions to job level
