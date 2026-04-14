# LLM Settings - Functional Specification Document

## Overview

The LLM Settings screen provides comprehensive configuration of the LLMBus - CIRIS's intelligent multi-provider LLM orchestration system. This screen exposes all configurable capabilities including:

- Multiple LLM providers with priority management
- Distribution strategies for load balancing
- Local inference server discovery and management
- Circuit breaker status and configuration
- Domain-specific routing (general, legal, financial)
- Rate limit and cooldown settings

## Design Philosophy

Following the Skill Studio pattern:
- **Card-based collapsible sections** for progressive disclosure
- **Read-mode first** - show current configuration clearly
- **Edit-on-demand** - tap to expand and edit sections
- **Real-time status** - show circuit breaker state, rate limits

---

## Data Models

### LLMProviderConfig
```kotlin
data class LLMProviderConfig(
    val id: String,                    // Unique provider instance ID
    val providerId: String,            // Provider type: "openai", "anthropic", "local_inference", etc.
    val displayName: String,           // "OpenAI GPT-4o", "Jetson llama.cpp", etc.
    val priority: ProviderPriority,    // CRITICAL, HIGH, NORMAL, LOW, FALLBACK
    val baseUrl: String?,              // Custom base URL (null = use default)
    val model: String,                 // Model name
    val apiKeySet: Boolean,            // Whether API key is configured
    val domain: String?,               // Domain routing: "general", "legal", "financial", null=all
    val enabled: Boolean,              // Whether this provider is active
    val circuitBreakerState: CircuitState, // CLOSED, OPEN, HALF_OPEN
    val isRateLimited: Boolean,        // Currently in rate limit cooldown
    val rateLimitCooldownRemaining: Int? // Seconds remaining in cooldown
)

enum class ProviderPriority {
    CRITICAL,  // 0 - Always try first, never skip
    HIGH,      // 1 - Primary providers
    NORMAL,    // 2 - Standard providers
    LOW,       // 3 - Use when others unavailable
    FALLBACK   // 9 - Last resort
}

enum class CircuitState {
    CLOSED,    // Normal operation
    OPEN,      // Failing, not accepting requests
    HALF_OPEN  // Testing if recovered
}
```

### DistributionStrategy
```kotlin
enum class DistributionStrategy {
    ROUND_ROBIN,    // Rotate through providers at same priority
    LATENCY_BASED,  // Select lowest latency provider (default)
    RANDOM,         // Random selection for load spread
    LEAST_LOADED    // Select provider with fewest active requests
}
```

### DiscoveredLlmServer (existing)
```kotlin
data class DiscoveredLlmServer(
    val id: String,              // "192.168.50.203_8080"
    val label: String,           // "jetson.local (Gemma 4)"
    val url: String,             // "http://192.168.50.203:8080"
    val serverType: String,      // "ollama", "llama_cpp", "vllm", "lmstudio"
    val modelCount: Int,
    val models: List<String>
)
```

### LLMBusStatus
```kotlin
data class LLMBusStatus(
    val distributionStrategy: DistributionStrategy,
    val totalRequests: Long,
    val failedRequests: Long,
    val averageLatencyMs: Float,
    val circuitBreakersOpen: Int,
    val providersAvailable: Int,
    val uptimeSeconds: Long
)
```

---

## UI Structure

### Card-Based Sections

```
┌─────────────────────────────────────────────────────────┐
│ LLM Settings                                    [⟳] [←] │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 📊 Status Overview                            [▼]   │ │
│ │ ─────────────────────────────────────────────────── │ │
│ │ Distribution: LATENCY_BASED      Providers: 3/3    │ │
│ │ Avg Latency: 847ms               Uptime: 4h 23m    │ │
│ │ Circuit Breakers: ● All Closed   Error Rate: 0.2%  │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 🔧 Providers                              3 active  │ │
│ │                                             [▼]     │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 🌐 Local Servers                        1 detected  │ │
│ │                                             [▼]     │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ ⚙️ Advanced Settings                         [▼]    │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 🔑 Authentication                            [▼]    │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Section 1: Status Overview (Always Visible)
Shows real-time LLMBus metrics:
- Distribution strategy badge
- Active providers count
- Average latency
- Circuit breaker summary (colored indicator)
- Error rate percentage
- Uptime

### Section 2: Providers (Expandable)
When collapsed: "3 active providers"
When expanded:

```
┌─────────────────────────────────────────────────────────┐
│ 🔧 Providers                                      [▲]  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ ┌───────────────────────────────────────────────────┐   │
│ │ ● OpenAI GPT-4o                         [HIGH] ⚡  │   │
│ │   Model: gpt-4o    Latency: 650ms    ✓ Active     │   │
│ │   [Edit] [Disable]                                │   │
│ └───────────────────────────────────────────────────┘   │
│                                                         │
│ ┌───────────────────────────────────────────────────┐   │
│ │ ● Anthropic Claude                    [NORMAL]    │   │
│ │   Model: claude-sonnet-4    Latency: 920ms        │   │
│ │   [Edit] [Disable]                                │   │
│ └───────────────────────────────────────────────────┘   │
│                                                         │
│ ┌───────────────────────────────────────────────────┐   │
│ │ ○ Groq Llama                        [FALLBACK] ⏸  │   │
│ │   Model: llama-3.3-70b    Circuit: OPEN (45s)     │   │
│ │   [Edit] [Enable]                                 │   │
│ └───────────────────────────────────────────────────┘   │
│                                                         │
│           [+ Add Provider]                              │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Provider Card Elements:**
- Status indicator (●=healthy, ○=disabled, ⚠=circuit open)
- Provider name and model
- Priority badge (CRITICAL, HIGH, NORMAL, LOW, FALLBACK)
- Performance indicator (⚡=fastest)
- Latency or circuit breaker state
- Edit/Disable actions

**Add Provider Flow:**
1. Tap [+ Add Provider]
2. Select provider type from list
3. Configure API key, model, base URL
4. Set priority level
5. Optionally set domain restriction
6. Save

### Section 3: Local Servers (Expandable)
When collapsed: "1 detected" or "None found"
When expanded:

```
┌─────────────────────────────────────────────────────────┐
│ 🌐 Local Servers                                  [▲]  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [🔍 Discover Servers]           Last scan: 2m ago     │
│                                                         │
│ ┌───────────────────────────────────────────────────┐   │
│ │ jetson.local:8080                    [LLAMA.CPP]  │   │
│ │ http://192.168.50.203:8080                        │   │
│ │ Models: gemma-4-e4b (1)                           │   │
│ │                                                   │   │
│ │ [Add as Provider]                                 │   │
│ └───────────────────────────────────────────────────┘   │
│                                                         │
│ ┌───────────────────────────────────────────────────┐   │
│ │ localhost:11434                        [OLLAMA]   │   │
│ │ http://127.0.0.1:11434                            │   │
│ │ Models: llama3.2, phi-4, gemma2 (3)               │   │
│ │                                                   │   │
│ │ [✓ Added as Fallback]                             │   │
│ └───────────────────────────────────────────────────┘   │
│                                                         │
│  Can't find your server?                                │
│  [Start Local Server]  (Requires Ollama/llama.cpp)     │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Section 4: Advanced Settings (Expandable)
When collapsed: Shows distribution strategy
When expanded:

```
┌─────────────────────────────────────────────────────────┐
│ ⚙️ Advanced Settings                              [▲]  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Distribution Strategy                                   │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ ○ Round Robin                                       │ │
│ │ ● Latency Based (Recommended)                       │ │
│ │ ○ Random                                            │ │
│ │ ○ Least Loaded                                      │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ Circuit Breaker Settings                                │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ Failure Threshold:    [  5  ] failures              │ │
│ │ Recovery Timeout:     [ 60  ] seconds               │ │
│ │ Success to Close:     [  3  ] successes             │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ Rate Limit Settings                                     │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ Default Cooldown:     [ 60  ] seconds               │ │
│ │ Max Retries:          [ 10  ]                       │ │
│ │ Max Wait Time:        [ 90  ] seconds               │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│                              [Save Advanced Settings]   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Section 5: Authentication (Expandable)
Same as current CirisJwtInfoCard - shows CIRIS token status.

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/setup/llm-config` | GET | Get current LLM configuration |
| `/v1/setup/llm-config` | PUT | Update LLM configuration |
| `/v1/setup/models/{provider}` | GET | Get models for provider |
| `/v1/setup/list-models` | POST | List models from live API |
| `/v1/setup/validate-llm` | POST | Validate LLM config |
| `/v1/setup/discover-local-llm` | POST | Discover local servers |
| `/v1/setup/start-local-server` | POST | Start local server |
| `/v1/system/llm/status` | GET | **NEW** Get LLMBus status |
| `/v1/system/llm/providers` | GET | **NEW** List all providers with status |
| `/v1/system/llm/providers` | POST | **NEW** Add provider |
| `/v1/system/llm/providers/{id}` | PUT | **NEW** Update provider |
| `/v1/system/llm/providers/{id}` | DELETE | **NEW** Remove provider |
| `/v1/system/llm/distribution` | PUT | **NEW** Update distribution strategy |

### New Endpoint Schemas

**GET /v1/system/llm/status**
```json
{
  "distribution_strategy": "latency_based",
  "total_requests": 1523,
  "failed_requests": 12,
  "average_latency_ms": 847.5,
  "circuit_breakers_open": 0,
  "providers_available": 3,
  "uptime_seconds": 15780
}
```

**GET /v1/system/llm/providers**
```json
{
  "providers": [
    {
      "id": "openai_primary",
      "provider_id": "openai",
      "display_name": "OpenAI GPT-4o",
      "priority": "HIGH",
      "base_url": null,
      "model": "gpt-4o",
      "api_key_set": true,
      "domain": null,
      "enabled": true,
      "circuit_breaker_state": "CLOSED",
      "is_rate_limited": false,
      "stats": {
        "total_requests": 980,
        "failed_requests": 5,
        "average_latency_ms": 650.2
      }
    }
  ]
}
```

**POST /v1/system/llm/providers**
```json
{
  "provider_id": "anthropic",
  "priority": "NORMAL",
  "base_url": null,
  "model": "claude-sonnet-4-20250514",
  "api_key": "sk-ant-...",
  "domain": null,
  "enabled": true
}
```

---

## Implementation Phases

### Phase 1: MVP (Status + Basic Provider Management)
1. Create LLMSettingsViewModel with status state
2. Implement Status Overview section
3. Show existing providers from config
4. Add Edit flow for single provider
5. Wire to existing `/v1/setup/llm-config` endpoint

### Phase 2: Multi-Provider (Priority Management)
1. Add new backend endpoints for provider CRUD
2. Implement Providers section with priority badges
3. Add/Remove provider flows
4. Reorder by priority (drag or buttons)
5. Circuit breaker status display

### Phase 3: Local Discovery (Network Scanning)
1. Implement Local Servers section
2. Integrate with existing discovery endpoint
3. "Add as Provider" flow
4. Start local server flow (requires Ollama/llama.cpp)

### Phase 4: Advanced Settings
1. Distribution strategy selection
2. Circuit breaker configuration
3. Rate limit settings
4. Domain routing per provider

---

## ViewModel State

```kotlin
// LLMSettingsViewModel.kt
class LLMSettingsViewModel(...) : ViewModel() {
    // Screen state
    sealed class ScreenState {
        object Loading : ScreenState()
        data class Ready(
            val status: LLMBusStatus,
            val providers: List<LLMProviderConfig>,
            val discoveredServers: List<DiscoveredLlmServer>,
            val isCirisProxy: Boolean
        ) : ScreenState()
        data class Error(val message: String) : ScreenState()
    }

    val screenState: StateFlow<ScreenState>

    // Section expansion state
    val providersExpanded: StateFlow<Boolean>
    val localServersExpanded: StateFlow<Boolean>
    val advancedExpanded: StateFlow<Boolean>
    val authExpanded: StateFlow<Boolean>

    // Operations
    val isDiscovering: StateFlow<Boolean>
    val isSaving: StateFlow<Boolean>

    // Edit mode
    val editingProvider: StateFlow<LLMProviderConfig?>

    // Actions
    fun refresh()
    fun toggleSection(section: Section)
    fun discoverLocalServers()
    fun addProvider(config: ProviderConfigInput)
    fun updateProvider(id: String, config: ProviderConfigInput)
    fun removeProvider(id: String)
    fun setDistributionStrategy(strategy: DistributionStrategy)
    fun addDiscoveredServerAsProvider(server: DiscoveredLlmServer, priority: ProviderPriority)
    fun startLocalServer(type: String, model: String, port: Int)
}
```

---

## Localization Keys

```json
{
  "mobile.llm_settings_title": "LLM Configuration",
  "mobile.llm_settings_status": "Status Overview",
  "mobile.llm_settings_providers": "Providers",
  "mobile.llm_settings_providers_count": "{count} active",
  "mobile.llm_settings_local_servers": "Local Servers",
  "mobile.llm_settings_local_detected": "{count} detected",
  "mobile.llm_settings_local_none": "None found",
  "mobile.llm_settings_advanced": "Advanced Settings",
  "mobile.llm_settings_auth": "Authentication",

  "mobile.llm_distribution_round_robin": "Round Robin",
  "mobile.llm_distribution_latency": "Latency Based (Recommended)",
  "mobile.llm_distribution_random": "Random",
  "mobile.llm_distribution_least_loaded": "Least Loaded",

  "mobile.llm_priority_critical": "Critical",
  "mobile.llm_priority_high": "High",
  "mobile.llm_priority_normal": "Normal",
  "mobile.llm_priority_low": "Low",
  "mobile.llm_priority_fallback": "Fallback",

  "mobile.llm_circuit_closed": "Healthy",
  "mobile.llm_circuit_open": "Circuit Open ({seconds}s)",
  "mobile.llm_circuit_half_open": "Testing Recovery",

  "mobile.llm_discover_servers": "Discover Servers",
  "mobile.llm_discovering": "Scanning network...",
  "mobile.llm_add_as_provider": "Add as Provider",
  "mobile.llm_added_as": "Added as {priority}",
  "mobile.llm_start_local": "Start Local Server",

  "mobile.llm_add_provider": "Add Provider",
  "mobile.llm_edit_provider": "Edit Provider",
  "mobile.llm_remove_provider": "Remove Provider",
  "mobile.llm_enable": "Enable",
  "mobile.llm_disable": "Disable",

  "mobile.llm_failure_threshold": "Failure Threshold",
  "mobile.llm_recovery_timeout": "Recovery Timeout",
  "mobile.llm_success_threshold": "Success to Close",
  "mobile.llm_rate_limit_cooldown": "Default Cooldown",
  "mobile.llm_max_retries": "Max Retries",
  "mobile.llm_max_wait": "Max Wait Time"
}
```

---

## Success Criteria

1. **Status Visibility** - Users can see LLMBus health at a glance
2. **Multi-Provider** - Users can add/remove/prioritize multiple providers
3. **Local Discovery** - Users can find and add local inference servers
4. **Distribution Control** - Users can choose load balancing strategy
5. **Circuit Breaker Insight** - Users see when providers are failing
6. **Domain Routing** - Power users can assign providers to domains
7. **Rate Limit Awareness** - Users understand cooldown states

---

## Migration from Current Screen

The current `LLMSettingsScreen.kt` will be replaced:

1. **CirisProxyInfoCard** → Shown in Status Overview when `isCirisProxy=true`
2. **ByokConfigSection** → Split into Providers section (primary provider) + Add Provider flow
3. **BackupLlmConfigCard** → Second provider in Providers list with FALLBACK priority
4. **CirisJwtInfoCard** → Moved to Authentication section (unchanged)

The refactor maintains backwards compatibility - existing single-provider configs
appear as the first provider in the list with HIGH priority.
