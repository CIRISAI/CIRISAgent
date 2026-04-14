# LLM Settings - Functional Specification Document

## Overview

The LLM Settings screen provides comprehensive configuration of the LLMBus - CIRIS's intelligent multi-provider LLM orchestration system. This screen exposes **ALL** configurable capabilities of the LLMBus runtime:

### Per-Provider Controls (Required for EVERY provider type)
| Control | Type | Description |
|---------|------|-------------|
| **Status** | Display | Current state, health, latency, error rate, rate limit status |
| **Priority** | Toggle | CRITICAL → HIGH → NORMAL → LOW → FALLBACK |
| **Circuit Breaker** | Toggle | Enable/disable CB, or reset when OPEN |
| **Active** | Toggle | Enable/disable provider entirely |

### Bus-Level Configuration
- Distribution strategies (ROUND_ROBIN, LATENCY_BASED, RANDOM, LEAST_LOADED)
- Selection strategies within priority groups (FALLBACK, ROUND_ROBIN)
- Circuit breaker global configuration
- Rate limit global settings

### Discovery & Management
- Local inference server discovery (Ollama, llama.cpp, vLLM, LM Studio)
- Domain-specific routing (general, legal, financial)
- Provider CRUD operations

## Design Philosophy

Following the Skill Studio pattern:
- **Card-based collapsible sections** for progressive disclosure
- **Read-mode first** - show current configuration clearly
- **Edit-on-demand** - tap to expand and edit sections
- **Real-time status** - show circuit breaker state, rate limits
- **Uniform controls** - every provider type gets the same 4 controls

---

## Data Models

### LLMProviderConfig
```kotlin
data class LLMProviderConfig(
    // Identity
    val id: String,                    // Unique provider instance ID (e.g., "OpenAIService_140234567890")
    val providerId: String,            // Provider type: "openai", "anthropic", "local_inference", etc.
    val displayName: String,           // "OpenAI GPT-4o", "Jetson llama.cpp", etc.
    val baseUrl: String?,              // Custom base URL (null = use default)
    val model: String,                 // Model name
    val apiKeySet: Boolean,            // Whether API key is configured
    val domain: String?,               // Domain routing: "general", "legal", "financial", null=all
    val capabilities: List<String>,    // ["call_llm_structured", "get_available_models", ...]

    // === THE 4 REQUIRED CONTROLS ===

    // 1. Status (Display) - Real-time provider health
    val status: ProviderStatus,

    // 2. Priority (Toggle) - Ordering for selection
    val priority: ProviderPriority,    // CRITICAL, HIGH, NORMAL, LOW, FALLBACK
    val priorityGroup: Int,            // Grouping within priority level (default 0)
    val selectionStrategy: SelectionStrategy, // Strategy within this priority group

    // 3. Circuit Breaker (Toggle) - Fault tolerance
    val circuitBreaker: CircuitBreakerStatus,

    // 4. Active (Toggle) - Provider enabled state
    val enabled: Boolean               // Whether this provider is active
)

// Status (Display) - Comprehensive provider health metrics
data class ProviderStatus(
    val healthy: Boolean,              // Overall health
    val latencyMs: Float?,             // Current average latency
    val totalRequests: Long,           // Total requests handled
    val failedRequests: Long,          // Total failures
    val failureRate: Float,            // 0.0 - 1.0 failure rate
    val successRate: Float,            // 0.0 - 1.0 success rate
    val consecutiveFailures: Int,      // Current consecutive failure count
    val lastRequestTime: String?,      // ISO timestamp of last request
    val lastFailureTime: String?,      // ISO timestamp of last failure
    val isRateLimited: Boolean,        // Currently in rate limit cooldown
    val rateLimitCooldownRemaining: Int? // Seconds remaining in cooldown
)

// Priority (Toggle)
enum class ProviderPriority {
    CRITICAL,  // 0 - Always try first, never skip
    HIGH,      // 1 - Primary providers
    NORMAL,    // 2 - Standard providers
    LOW,       // 3 - Use when others unavailable
    FALLBACK   // 9 - Last resort
}

// Selection strategy within priority groups
enum class SelectionStrategy {
    FALLBACK,    // Use first available provider (default)
    ROUND_ROBIN  // Rotate through providers in the group
}

// Circuit Breaker (Toggle) - Full CB state and configuration
data class CircuitBreakerStatus(
    // Current state
    val state: CircuitState,           // CLOSED, OPEN, HALF_OPEN
    val enabled: Boolean,              // Whether CB is active for this provider

    // Metrics
    val failureCount: Int,             // Current window failure count
    val successCount: Int,             // Current window success count
    val totalCalls: Long,              // Lifetime call count
    val totalFailures: Long,           // Lifetime failure count
    val totalSuccesses: Long,          // Lifetime success count
    val successRate: Float,            // 0.0 - 1.0 success rate
    val consecutiveFailures: Int,      // Current consecutive failures
    val recoveryAttempts: Int,         // Times entered HALF_OPEN
    val stateTransitions: Int,         // Total state changes
    val timeInOpenStateSeconds: Float, // Cumulative time in OPEN state
    val lastFailureAgeSeconds: Float?, // Seconds since last failure

    // Configuration (editable)
    val config: CircuitBreakerConfig
)

data class CircuitBreakerConfig(
    val failureThreshold: Int,         // Failures before opening (default: 5)
    val recoveryTimeoutSeconds: Float, // Time in OPEN before trying HALF_OPEN (default: 10)
    val successThreshold: Int,         // Successes in HALF_OPEN to close (default: 3)
    val timeoutDurationSeconds: Float  // Request timeout (default: 30)
)

enum class CircuitState {
    CLOSED,    // Normal operation - requests pass through
    OPEN,      // Service disabled - requests fail fast
    HALF_OPEN  // Testing recovery - limited requests allowed
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
    // Distribution configuration
    val distributionStrategy: DistributionStrategy,

    // Aggregate metrics (from all providers)
    val totalRequests: Long,
    val failedRequests: Long,
    val averageLatencyMs: Float,
    val errorRate: Float,              // 0.0 - 1.0

    // Provider status
    val providersTotal: Int,           // Total registered providers
    val providersAvailable: Int,       // Healthy providers (CB not OPEN)
    val providersRateLimited: Int,     // Providers in rate limit cooldown

    // Circuit breaker summary
    val circuitBreakersClosed: Int,    // Normal operation
    val circuitBreakersOpen: Int,      // Failing, disabled
    val circuitBreakersHalfOpen: Int,  // Testing recovery

    // Bus health
    val uptimeSeconds: Long,
    val queueDepth: Int,               // Pending async messages

    // Global rate limit settings (editable)
    val rateLimitConfig: RateLimitConfig
)

data class RateLimitConfig(
    val defaultCooldownSeconds: Float, // Default cooldown when rate limited (default: 60)
    val maxRetries: Int,               // Max rate limit retries per request (default: 10)
    val maxWaitTimeSeconds: Float      // Max total wait time for rate limits (default: 90)
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
│ │ OpenAI GPT-4o                              [⋮]    │   │
│ │ ───────────────────────────────────────────────── │   │
│ │ ● Healthy                           gpt-4o        │   │
│ │                                                   │   │
│ │ Priority    [▼ Primary        ]                   │   │
│ │ Protection  [████████] ON      [Reset]            │   │
│ │ Enabled     [████████] ON                         │   │
│ └───────────────────────────────────────────────────┘   │
│                                                         │
│ ┌───────────────────────────────────────────────────┐   │
│ │ Anthropic Claude                           [⋮]    │   │
│ │ ───────────────────────────────────────────────── │   │
│ │ ● Healthy                    claude-sonnet-4      │   │
│ │                                                   │   │
│ │ Priority    [▼ Standard       ]                   │   │
│ │ Protection  [████████] ON      [Reset]            │   │
│ │ Enabled     [████████] ON                         │   │
│ └───────────────────────────────────────────────────┘   │
│                                                         │
│ ┌───────────────────────────────────────────────────┐   │
│ │ Groq Llama                            ⚠    [⋮]    │   │
│ │ ───────────────────────────────────────────────── │   │
│ │ ⚠ Temporarily disabled - recovering soon          │   │
│ │                                                   │   │
│ │ Priority    [▼ Backup         ]                   │   │
│ │ Protection  ⚠ Triggered        [Force Reset]      │   │
│ │ Enabled     [        ] OFF                        │   │
│ └───────────────────────────────────────────────────┘   │
│                                                         │
│           [+ Add Provider]                              │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Provider Card - The 4 Required Controls:**

| Row | Control | Type | User-Facing Label |
|-----|---------|------|-------------------|
| 1 | **Status** | Display | Health indicator with simple message |
| 2 | **Priority** | Dropdown | "Primary", "Standard", "Backup", "Last Resort" |
| 3 | **Protection** | Toggle + Button | On/Off toggle, Reset button when triggered |
| 4 | **Enabled** | Toggle | On/Off switch to use this provider |

**Status Messages (Simple English):**
- ● Healthy - Working normally
- ⚠ Temporarily disabled - Too many errors, recovering soon
- ⚠ Rate limited - Waiting for cooldown
- ○ Disabled - Turned off by user

**Priority Options (Simple English):**
- Primary - Try this one first
- Standard - Normal priority
- Backup - Use when others are busy
- Last Resort - Only if nothing else works

**Protection (Circuit Breaker) States:**
- ON (green) - Active and protecting
- Triggered (yellow) - Paused due to errors, will recover automatically
- [Reset] - Click to manually recover
- [Force Reset] - Click if stuck

**Overflow Menu [⋮] (Advanced Options):**
- View Details - Shows full metrics, latency, error rates
- Configure Protection - Adjust thresholds and timeouts
- Set Domain - Restrict to specific use cases
- Remove Provider

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
When collapsed: Shows "Automatic" or custom strategy name
When expanded:

```
┌─────────────────────────────────────────────────────────┐
│ ⚙️ Advanced Settings                              [▲]  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ How should CIRIS pick which provider to use?            │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ ● Automatic (Recommended)                           │ │
│ │   Picks the fastest available provider              │ │
│ │                                                     │ │
│ │ ○ Round Robin                                       │ │
│ │   Takes turns between providers                     │ │
│ │                                                     │ │
│ │ ○ Random                                            │ │
│ │   Picks randomly to spread the load                 │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ ▶ Protection Settings                         [▼]  │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ ▶ Rate Limit Handling                         [▼]  │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ ▶ Developer Options                           [▼]  │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Expanded: Protection Settings**
```
┌─────────────────────────────────────────────────────────┐
│ ▼ Protection Settings                                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ When a provider has problems, CIRIS will temporarily    │
│ stop using it and try again later.                      │
│                                                         │
│ How sensitive should protection be?                     │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ [        ●        ]                                 │ │
│ │  Relaxed    Normal    Strict                        │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ How long to wait before trying again?                   │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ [      ●          ]                                 │ │
│ │  Quick      Normal      Slow                        │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│                                [Reset to Defaults]      │
└─────────────────────────────────────────────────────────┘
```

**Expanded: Rate Limit Handling**
```
┌─────────────────────────────────────────────────────────┐
│ ▼ Rate Limit Handling                                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ When a provider says "slow down", CIRIS will wait       │
│ and try again automatically.                            │
│                                                         │
│ How patient should CIRIS be?                            │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ [          ●      ]                                 │ │
│ │  Impatient   Normal    Very Patient                 │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│                                [Reset to Defaults]      │
└─────────────────────────────────────────────────────────┘
```

**Expanded: Developer Options**
```
┌─────────────────────────────────────────────────────────┐
│ ▼ Developer Options                                     │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ These settings are for advanced users.                  │
│                                                         │
│ Protection (Circuit Breaker)                            │
│   Failures before pause:        [  5  ]                 │
│   Recovery wait (seconds):      [ 10  ]                 │
│   Successes to resume:          [  3  ]                 │
│   Request timeout (seconds):    [ 30  ]                 │
│                                                         │
│ Rate Limits                                             │
│   Default cooldown (seconds):   [ 60  ]                 │
│   Max retries per request:      [ 10  ]                 │
│   Max total wait (seconds):     [ 90  ]                 │
│                                                         │
│ Selection                                               │
│   Within same priority:    [▼ Use first available ]     │
│   Health checks:           [████████] ON                │
│   Auto-recovery:           [████████] ON                │
│                                                         │
│                                [Reset to Defaults]      │
└─────────────────────────────────────────────────────────┘
```

### Section 5: Authentication (Expandable)
Same as current CirisJwtInfoCard - shows CIRIS token status.

---

## API Endpoints

| Endpoint | Method | Status | Description |
|----------|--------|--------|-------------|
| `/v1/setup/llm/models` | GET | ✅ | Get model capabilities database |
| `/v1/setup/llm/models/{provider}` | GET | ✅ | Get models for provider |
| `/v1/setup/llm/list-models` | POST | ✅ | List models from live API |
| `/v1/setup/llm/validate-llm` | POST | ✅ | Validate LLM config |
| `/v1/setup/llm/discover-local-llm` | POST | ✅ | Discover local servers |
| `/v1/setup/llm/start-local-server` | POST | ✅ | Start local server |
| `/v1/system/llm/status` | GET | ✅ | Get LLMBus status |
| `/v1/system/llm/providers` | GET | ✅ | List all providers with status |
| `/v1/system/llm/distribution` | PUT | ✅ | Update distribution strategy |
| `/v1/system/llm/providers/{name}/circuit-breaker/reset` | POST | ✅ | Reset circuit breaker |
| `/v1/system/llm/providers/{name}/circuit-breaker/config` | PUT | ✅ | Update CB config |
| `/v1/system/llm/providers/{name}/priority` | PUT | ✅ | Update provider priority |
| `/v1/system/llm/providers/{name}` | DELETE | ✅ | Remove provider |

### New Endpoint Schemas

**GET /v1/system/llm/status** - Full LLMBus status
```json
{
  "distribution_strategy": "latency_based",
  "total_requests": 1523,
  "failed_requests": 12,
  "average_latency_ms": 847.5,
  "error_rate": 0.008,
  "providers_total": 3,
  "providers_available": 3,
  "providers_rate_limited": 0,
  "circuit_breakers_closed": 3,
  "circuit_breakers_open": 0,
  "circuit_breakers_half_open": 0,
  "uptime_seconds": 15780,
  "queue_depth": 0,
  "rate_limit_config": {
    "default_cooldown_seconds": 60.0,
    "max_retries": 10,
    "max_wait_time_seconds": 90.0
  }
}
```

**GET /v1/system/llm/providers** - All providers with full status
```json
{
  "providers": [
    {
      "id": "OpenAIService_140234567890",
      "provider_id": "openai",
      "display_name": "OpenAI GPT-4o",
      "base_url": null,
      "model": "gpt-4o",
      "api_key_set": true,
      "domain": null,
      "capabilities": ["call_llm_structured", "get_available_models"],

      "status": {
        "healthy": true,
        "latency_ms": 650.2,
        "total_requests": 980,
        "failed_requests": 5,
        "failure_rate": 0.005,
        "success_rate": 0.995,
        "consecutive_failures": 0,
        "last_request_time": "2026-04-14T15:30:00Z",
        "last_failure_time": "2026-04-14T14:22:00Z",
        "is_rate_limited": false,
        "rate_limit_cooldown_remaining": null
      },

      "priority": "HIGH",
      "priority_group": 0,
      "selection_strategy": "fallback",

      "circuit_breaker": {
        "state": "CLOSED",
        "enabled": true,
        "failure_count": 0,
        "success_count": 12,
        "total_calls": 980,
        "total_failures": 5,
        "total_successes": 975,
        "success_rate": 0.995,
        "consecutive_failures": 0,
        "recovery_attempts": 1,
        "state_transitions": 2,
        "time_in_open_state_seconds": 45.2,
        "last_failure_age_seconds": 4080.0,
        "config": {
          "failure_threshold": 5,
          "recovery_timeout_seconds": 10.0,
          "success_threshold": 3,
          "timeout_duration_seconds": 30.0
        }
      },

      "enabled": true
    }
  ]
}
```

**POST /v1/system/llm/providers** - Add new provider
```json
{
  "provider_id": "anthropic",
  "priority": "NORMAL",
  "priority_group": 0,
  "selection_strategy": "fallback",
  "base_url": null,
  "model": "claude-sonnet-4-20250514",
  "api_key": "sk-ant-...",
  "domain": null,
  "enabled": true,
  "circuit_breaker_config": {
    "failure_threshold": 5,
    "recovery_timeout_seconds": 10.0,
    "success_threshold": 3,
    "timeout_duration_seconds": 30.0
  }
}
```

**PUT /v1/system/llm/providers/{id}/priority** - Update priority (toggle)
```json
{
  "priority": "HIGH",
  "priority_group": 0,
  "selection_strategy": "round_robin"
}
```

**PUT /v1/system/llm/providers/{id}/enabled** - Toggle active state
```json
{
  "enabled": false
}
```

**POST /v1/system/llm/providers/{id}/circuit-breaker/reset** - Reset CB
```json
{
  "force": false
}
```

**PUT /v1/system/llm/providers/{id}/circuit-breaker/config** - Update CB config
```json
{
  "failure_threshold": 5,
  "recovery_timeout_seconds": 10.0,
  "success_threshold": 3,
  "timeout_duration_seconds": 30.0
}
```

---

## Implementation Phases

### Phase 1: MVP (Status + Basic Provider Management) ✅ COMPLETE
1. ✅ Create LLMSettingsViewModel with status state
2. ✅ Implement Status Overview section
3. ✅ Show existing providers from config
4. ✅ Add Edit flow for single provider
5. ✅ Wire to existing `/v1/setup/llm-config` endpoint
6. ✅ Backend: `/v1/system/llm/status` endpoint
7. ✅ Backend: `/v1/system/llm/providers` endpoint (GET)

### Phase 2: Multi-Provider (Priority Management) ✅ COMPLETE
1. ✅ Backend: Distribution strategy endpoint
2. ✅ Backend: Circuit breaker reset/config endpoints
3. ✅ Backend: ServiceRegistry has full priority/enabled support
4. ✅ Frontend: Providers section with priority badges (display)
5. ✅ API shim: PUT /system/llm/providers/{name}/priority endpoint
6. ✅ API shim: DELETE /system/llm/providers/{name} endpoint
7. ✅ Frontend: Priority dropdown wired to backend (LLMSettingsViewModel)
8. 🚧 Frontend: "Add as Provider" button (needs POST endpoint + runtime changes)

### Phase 3: Local Discovery (Network Scanning) ✅ COMPLETE
1. ✅ Implement Local Servers section
2. ✅ Backend: `/v1/setup/llm/discover-local-llm` endpoint
3. ✅ Backend: `/v1/setup/llm/start-local-server` endpoint
4. ✅ Frontend: LocalLlmServerDiscovery component
5. ✅ Auto-disable model reasoning on local endpoints (Gemma 4 fix)
6. 🚧 "Add as Provider" flow - needs POST endpoint + hot-reload support

### Phase 4: Advanced Settings ✅ COMPLETE
1. ✅ Distribution strategy selection (radio buttons)
2. ✅ Circuit breaker status display
3. ✅ Circuit breaker reset functionality
4. 🚧 Rate limit settings (backend exists, UI TODO)
5. 🚧 Domain routing per provider (deferred)

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
  "mobile.llm_settings_title": "AI Providers",
  "mobile.llm_settings_status": "Overview",
  "mobile.llm_settings_providers": "Providers",
  "mobile.llm_settings_providers_count": "{count} active",
  "mobile.llm_settings_local_servers": "Local Servers",
  "mobile.llm_settings_local_detected": "{count} found",
  "mobile.llm_settings_local_none": "None found",
  "mobile.llm_settings_advanced": "Advanced",
  "mobile.llm_settings_auth": "Authentication",

  "mobile.llm_distribution_automatic": "Automatic (Recommended)",
  "mobile.llm_distribution_automatic_desc": "Picks the fastest available provider",
  "mobile.llm_distribution_round_robin": "Round Robin",
  "mobile.llm_distribution_round_robin_desc": "Takes turns between providers",
  "mobile.llm_distribution_random": "Random",
  "mobile.llm_distribution_random_desc": "Picks randomly to spread the load",

  "mobile.llm_priority_primary": "Primary",
  "mobile.llm_priority_primary_desc": "Try this one first",
  "mobile.llm_priority_standard": "Standard",
  "mobile.llm_priority_standard_desc": "Normal priority",
  "mobile.llm_priority_backup": "Backup",
  "mobile.llm_priority_backup_desc": "Use when others are busy",
  "mobile.llm_priority_last_resort": "Last Resort",
  "mobile.llm_priority_last_resort_desc": "Only if nothing else works",

  "mobile.llm_status_healthy": "Healthy",
  "mobile.llm_status_healthy_desc": "Working normally",
  "mobile.llm_status_paused": "Temporarily disabled",
  "mobile.llm_status_paused_desc": "Too many errors, recovering soon",
  "mobile.llm_status_rate_limited": "Rate limited",
  "mobile.llm_status_rate_limited_desc": "Waiting for cooldown",
  "mobile.llm_status_disabled": "Disabled",
  "mobile.llm_status_disabled_desc": "Turned off by user",

  "mobile.llm_protection": "Protection",
  "mobile.llm_protection_on": "Active and protecting",
  "mobile.llm_protection_triggered": "Paused due to errors",
  "mobile.llm_protection_reset": "Reset",
  "mobile.llm_protection_force_reset": "Force Reset",

  "mobile.llm_discover_servers": "Find Servers",
  "mobile.llm_discovering": "Searching...",
  "mobile.llm_add_as_provider": "Add as Provider",
  "mobile.llm_added_as": "Added as {priority}",
  "mobile.llm_start_local": "Start Local Server",

  "mobile.llm_add_provider": "Add Provider",
  "mobile.llm_edit_provider": "Edit",
  "mobile.llm_remove_provider": "Remove",
  "mobile.llm_enable": "Enable",
  "mobile.llm_disable": "Disable",
  "mobile.llm_enabled": "Enabled",
  "mobile.llm_view_details": "View Details",
  "mobile.llm_configure_protection": "Configure Protection",
  "mobile.llm_set_domain": "Set Domain",

  "mobile.llm_advanced_protection": "Protection Settings",
  "mobile.llm_advanced_protection_desc": "When a provider has problems, CIRIS will temporarily stop using it and try again later.",
  "mobile.llm_advanced_sensitivity": "How sensitive should protection be?",
  "mobile.llm_advanced_sensitivity_relaxed": "Relaxed",
  "mobile.llm_advanced_sensitivity_normal": "Normal",
  "mobile.llm_advanced_sensitivity_strict": "Strict",
  "mobile.llm_advanced_recovery": "How long to wait before trying again?",
  "mobile.llm_advanced_recovery_quick": "Quick",
  "mobile.llm_advanced_recovery_normal": "Normal",
  "mobile.llm_advanced_recovery_slow": "Slow",

  "mobile.llm_advanced_rate_limit": "Rate Limit Handling",
  "mobile.llm_advanced_rate_limit_desc": "When a provider says 'slow down', CIRIS will wait and try again automatically.",
  "mobile.llm_advanced_patience": "How patient should CIRIS be?",
  "mobile.llm_advanced_patience_impatient": "Impatient",
  "mobile.llm_advanced_patience_normal": "Normal",
  "mobile.llm_advanced_patience_patient": "Very Patient",

  "mobile.llm_advanced_developer": "Developer Options",
  "mobile.llm_advanced_developer_desc": "These settings are for advanced users.",
  "mobile.llm_reset_defaults": "Reset to Defaults"
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

---

## LLMBus Runtime Capability Mapping

This section documents ALL capabilities exposed by the LLMBus runtime and how they map to the UI.

### Per-Provider Capabilities

| Runtime Capability | UI Location | Control Type |
|--------------------|-------------|--------------|
| `enabled` | Provider Card → Enabled | Toggle ON/OFF |
| `priority` (CRITICAL/HIGH/NORMAL/LOW/FALLBACK) | Provider Card → Priority | Dropdown |
| `priority_group` | Provider Card → [⋮] → Details | Number (hidden) |
| `selection_strategy` (FALLBACK/ROUND_ROBIN) | Provider Card → [⋮] → Details | Dropdown (hidden) |
| `circuit_breaker.state` (CLOSED/OPEN/HALF_OPEN) | Provider Card → Protection | Status indicator |
| `circuit_breaker.enabled` | Provider Card → Protection | Toggle ON/OFF |
| `circuit_breaker.reset()` | Provider Card → Protection → Reset | Button |
| `circuit_breaker.force_open()` | Provider Card → [⋮] → Force Disable | Button (hidden) |
| `circuit_breaker.config.*` | Provider Card → [⋮] → Configure Protection | Form (hidden) |
| `is_rate_limited` | Provider Card → Status | Status indicator |
| `rate_limit_cooldown_remaining` | Provider Card → Status | Text |
| `domain` | Provider Card → [⋮] → Set Domain | Dropdown (hidden) |
| `capabilities` | Provider Card → [⋮] → Details | Read-only list |

### Per-Provider Metrics (Display Only)

| Runtime Metric | UI Location | Format |
|----------------|-------------|--------|
| `status.healthy` | Provider Card → Status | ● / ⚠ / ○ icon |
| `status.latency_ms` | Provider Card → [⋮] → Details | "850ms" |
| `status.total_requests` | Provider Card → [⋮] → Details | Number |
| `status.failed_requests` | Provider Card → [⋮] → Details | Number |
| `status.failure_rate` | Provider Card → [⋮] → Details | Percentage |
| `status.success_rate` | Provider Card → [⋮] → Details | Percentage |
| `status.consecutive_failures` | Provider Card → [⋮] → Details | Number |
| `status.last_request_time` | Provider Card → [⋮] → Details | Timestamp |
| `status.last_failure_time` | Provider Card → [⋮] → Details | Timestamp |
| `circuit_breaker.failure_count` | Provider Card → [⋮] → Details | Number |
| `circuit_breaker.success_count` | Provider Card → [⋮] → Details | Number |
| `circuit_breaker.total_calls` | Provider Card → [⋮] → Details | Number |
| `circuit_breaker.recovery_attempts` | Provider Card → [⋮] → Details | Number |
| `circuit_breaker.state_transitions` | Provider Card → [⋮] → Details | Number |
| `circuit_breaker.time_in_open_state_seconds` | Provider Card → [⋮] → Details | Duration |
| `circuit_breaker.last_failure_age_seconds` | Provider Card → [⋮] → Details | Duration |

### Bus-Level Capabilities

| Runtime Capability | UI Location | Control Type |
|--------------------|-------------|--------------|
| `distribution_strategy` | Advanced → Strategy picker | Radio buttons |
| `rate_limit_config.default_cooldown_seconds` | Advanced → Developer → Rate Limits | Number (hidden) |
| `rate_limit_config.max_retries` | Advanced → Developer → Rate Limits | Number (hidden) |
| `rate_limit_config.max_wait_time_seconds` | Advanced → Developer → Rate Limits | Number (hidden) |
| Circuit breaker defaults | Advanced → Developer → Protection | Numbers (hidden) |
| Health check toggle | Advanced → Developer → Selection | Toggle (hidden) |
| Auto-recovery toggle | Advanced → Developer → Selection | Toggle (hidden) |

### Bus-Level Metrics (Display Only)

| Runtime Metric | UI Location | Format |
|----------------|-------------|--------|
| `total_requests` | Status Overview | Number |
| `failed_requests` | Status Overview | Number |
| `average_latency_ms` | Status Overview | "847ms" |
| `error_rate` | Status Overview | Percentage |
| `providers_total` | Status Overview | "3 providers" |
| `providers_available` | Status Overview | "3/3 healthy" |
| `providers_rate_limited` | Status Overview | Number |
| `circuit_breakers_closed` | Status Overview | Number |
| `circuit_breakers_open` | Status Overview | ● indicator |
| `circuit_breakers_half_open` | Status Overview | Number |
| `uptime_seconds` | Status Overview | "4h 23m" |
| `queue_depth` | Status Overview → [⋮] | Number |

### Discovery Capabilities

| Runtime Capability | UI Location | Control Type |
|--------------------|-------------|--------------|
| `discover_local_llm()` | Local Servers → Discover | Button |
| Discovered server list | Local Servers | Card list |
| Add discovered server | Local Servers → Add as Provider | Button |
| Start local server | Local Servers → Start | Button (if supported) |

---

## Verification Checklist

Before implementation is complete, verify all capabilities are exposed:

- [x] Status overview shows bus health summary
- [x] Local server discovery works (`/v1/setup/llm/discover-local-llm`)
- [x] Start local server works (`/v1/setup/llm/start-local-server`)
- [x] Advanced settings expose distribution strategy (radio buttons)
- [x] Circuit breaker reset works (`POST /providers/{name}/circuit-breaker/reset`)
- [x] Circuit breaker config update works (`PUT /providers/{name}/circuit-breaker/config`)
- [x] Model reasoning disabled on local endpoints (Gemma 4 compatibility)
- [x] Every provider shows: Status, Priority, Protection
- [x] Priority dropdown includes all 5 levels (API endpoint + frontend complete)
- [x] Protection shows current state and allows reset
- [ ] Enabled toggle works for all provider types (🚧 needs API shim)
- [ ] "Add as Provider" button for discovered servers (🚧 needs POST endpoint + runtime hot-reload)
- [ ] Developer options expose all numeric configs (🚧 UI TODO)
- [ ] All metrics from `get_service_stats()` are accessible (partial)
- [ ] All metrics from `get_metrics()` are accessible (partial)
- [ ] Rate limit status is visible when active (🚧 UI TODO)
