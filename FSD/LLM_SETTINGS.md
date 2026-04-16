# LLM Settings - Functional Specification Document

## Overview

The LLM Settings screen provides comprehensive configuration of the LLMBus - CIRIS's intelligent multi-provider LLM orchestration system.

### Design Philosophy

**Separation of Concerns:**
- **Adapters** = Services that provide LLM capabilities (e.g., `mobile_local_llm`, `api`)
- **Providers** = Actual LLM endpoints registered with the bus (e.g., `OpenAIService`, `local_primary`)

**Standard CRUD for Everything:**
- All providers are deletable via standard CRUD operations
- CIRIS services toggle uses provider CRUD (no special env var manipulation)
- Adapters use the same CRUD patterns as the Adapters page

**Progressive Disclosure:**
- Status always visible at top
- Sections expand on demand
- Details lazy-loaded on first expand

---

## Screen Layout (Top to Bottom)

```
┌─────────────────────────────────────────────────────────┐
│ LLM Settings                                    [⟳] [←] │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 📊 STATUS                                           │ │
│ │ ─────────────────────────────────────────────────── │ │
│ │ Mode: CIRIS Proxy    Providers: 2/2 healthy        │ │
│ │ Strategy: Automatic  Avg Latency: 847ms            │ │
│ │ Circuit Breakers: ● All Closed                     │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 🔌 ADAPTERS                              2 loaded   │ │
│ │                                             [▼]     │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 🤖 PROVIDERS                             2 active   │ │
│ │                                             [▼]     │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ ➕ ADD PROVIDER                                      │ │
│ │                                             [▼]     │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ ⚙️ ADVANCED                                  [▼]    │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Section 1: Status (Always Visible)

Real-time LLMBus health metrics. Non-collapsible - always shows at top.

```
┌─────────────────────────────────────────────────────────┐
│ 📊 STATUS                                               │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Mode          │ Distribution    │ Providers             │
│ CIRIS Proxy   │ Automatic       │ 2/2 healthy          │
│               │                 │                       │
│ Avg Latency   │ Error Rate      │ Uptime                │
│ 847ms         │ 0.2%            │ 4h 23m               │
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ ● All Circuit Breakers Closed    Automatic (LB)    │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Data Source:** `GET /v1/system/llm/status`

---

## Section 2: Adapters (Collapsible)

Lists LLM-related adapters that provide inference capabilities.

### Collapsed State
```
┌─────────────────────────────────────────────────────────┐
│ 🔌 ADAPTERS                              2 loaded  [▼]  │
└─────────────────────────────────────────────────────────┘
```

### Expanded State
```
┌─────────────────────────────────────────────────────────┐
│ 🔌 ADAPTERS                                        [▲]  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ mobile_local_llm                     ● Running      │ │
│ │ On-device inference (Gemma 4)                       │ │
│ │ Services: llm                                       │ │
│ │                                                     │ │
│ │ [↻ Reload]  [✕ Remove]                              │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ api                                  ● Running      │ │
│ │ CIRIS API endpoint                                  │ │
│ │ Services: communication, llm                        │ │
│ │                                                     │ │
│ │ [↻ Reload]                                          │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ Note: Adapters register providers. Remove an adapter   │
│ to remove all providers it registered.                 │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Adapter Card Actions:**
| Action | Button | Description |
|--------|--------|-------------|
| Reload | `[↻ Reload]` | Reload adapter with current config |
| Remove | `[✕ Remove]` | Unload adapter and its providers |

**Data Source:** `GET /v1/system/adapters` (filtered to LLM-capable adapters)

**CRUD Methods:**
- List: `apiClient.listAdapters()`
- Reload: `apiClient.reloadAdapter(adapterId)`
- Remove: `apiClient.removeAdapter(adapterId)`

---

## Section 3: Providers (Collapsible)

Lists all LLM providers registered with the bus.

### Collapsed State
```
┌─────────────────────────────────────────────────────────┐
│ 🤖 PROVIDERS                             2 active  [▼]  │
└─────────────────────────────────────────────────────────┘
```

### Expanded State
```
┌─────────────────────────────────────────────────────────┐
│ 🤖 PROVIDERS                                       [▲]  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ ciris_primary                            [PRIMARY]  │ │
│ │ ● Healthy                         gpt-4o-mini       │ │
│ │                                                     │ │
│ │ Requests: 1,245  │  Avg: 842ms  │  Success: 99.2%   │ │
│ │ CB: CLOSED ✓     │  Errors: 10  │                   │ │
│ │                                                     │ │
│ │ [▼ Priority]  [↻ Reset CB]  [✕ Delete]              │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ local_primary                           [FALLBACK]  │ │
│ │ ● Healthy                         gemma-4-e2b       │ │
│ │                                                     │ │
│ │ Requests: 45     │  Avg: 3,200ms│  Success: 98.0%   │ │
│ │ CB: CLOSED ✓     │  Errors: 1   │                   │ │
│ │                                                     │
│ │ [▼ Priority]  [↻ Reset CB]  [✕ Delete]              │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ┌─ CIRIS Services ──────────────────────────────────┐   │
│ │ ● Enabled - Using CIRIS proxy for LLM requests    │   │
│ │                                                   │   │
│ │ Disable CIRIS services to use only your own      │   │
│ │ API keys. Both CIRIS providers will be removed.  │   │
│ │                                         [Disable] │   │
│ └───────────────────────────────────────────────────┘   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Provider Card Actions:**
| Action | Button | Description |
|--------|--------|-------------|
| Priority | `[▼ Priority]` | Dropdown: Critical, Primary, Standard, Backup, Fallback |
| Reset CB | `[↻ Reset CB]` | Reset circuit breaker to CLOSED |
| Delete | `[✕ Delete]` | Remove provider from bus |

**IMPORTANT: All Providers Are Deletable**
- No filtering by name prefix (removed `!provider.name.startsWith("ciris_")` check)
- System providers show a confirmation warning but are still deletable
- Deletion uses standard CRUD: `DELETE /v1/system/llm/providers/{name}`

**CIRIS Services Toggle:**
When disabled:
1. Call `deleteProvider("ciris_primary")`
2. Call `deleteProvider("local_primary")` (if exists)
3. Set `CIRIS_SERVICES_DISABLED=true` in env for restart persistence

When re-enabled (requires wizard):
- User must re-run setup wizard from Data Management

**Data Source:** `GET /v1/system/llm/providers`

**CRUD Methods:**
- List: `apiClient.getLlmProviders()`
- Update Priority: `apiClient.updateLlmProviderPriority(name, priority)`
- Reset CB: `apiClient.resetLlmCircuitBreaker(name)`
- Delete: `apiClient.deleteLlmProvider(name)`

---

## Section 4: Add Provider (Collapsible)

Three cards for adding different types of providers.

### Collapsed State
```
┌─────────────────────────────────────────────────────────┐
│ ➕ ADD PROVIDER                                    [▼]  │
└─────────────────────────────────────────────────────────┘
```

### Expanded State
```
┌─────────────────────────────────────────────────────────┐
│ ➕ ADD PROVIDER                                    [▲]  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 📱 LOCAL (On-Device)                                │ │
│ │ ───────────────────────────────────────────────────│ │
│ │ Run inference directly on this device.             │ │
│ │ ⚠️ Requires 64-bit Android with 6GB+ RAM           │ │
│ │                                                     │ │
│ │ Status: ✓ Device capable                           │ │
│ │                                                     │ │
│ │ [Start Local Server]                                │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ 🌐 SERVER (Network Discovery)                       │ │
│ │ ─────────────────────────────────────────────────── │ │
│ │ Find LLM servers on your local network.            │ │
│ │ Supports Ollama, llama.cpp, vLLM, LM Studio.       │ │
│ │                                                     │ │
│ │ Last scan: 2m ago  │  Found: 1 server              │ │
│ │                                                     │ │
│ │ ┌─ jetson.local:8080 (llama.cpp) ───────────────┐  │ │
│ │ │ Models: gemma-4-e4b                           │  │ │
│ │ │ [+ Add as Provider]                           │  │ │
│ │ └───────────────────────────────────────────────┘  │ │
│ │                                                     │ │
│ │ [🔍 Discover Servers]                               │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ ☁️ CLOUD (API Key)                                  │ │
│ │ ─────────────────────────────────────────────────── │ │
│ │ Add a cloud provider with your own API key.        │ │
│ │                                                     │ │
│ │ Provider: [▼ OpenAI            ]                   │ │
│ │ API Key:  [sk-...              ] [👁]              │ │
│ │                                                     │ │
│ │ [Fetch Models]  (after key entry)                  │ │
│ │                                                     │ │
│ │ Model: [▼ gpt-4o ★ Best        ]                   │ │
│ │                                                     │ │
│ │ [+ Add Provider]                                    │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Add Card Types

#### 4.1 Local (On-Device)
For devices capable of local inference (64-bit Android, 6GB+ RAM).

**Flow:**
1. Check device capability via `probeLocalInferenceCapability()`
2. If capable, show "Start Local Server" button
3. On click: `POST /v1/setup/llm/start-local-server`
4. Wait for server startup, then auto-discover
5. Add discovered server as provider

#### 4.2 Server (Network Discovery)
Discovers LLM servers on the local network.

**Flow:**
1. Click "Discover Servers"
2. Call `POST /v1/setup/llm/discover-local-llm`
3. Display discovered servers with model info
4. Click "Add as Provider" to register
5. Call `POST /v1/system/llm/providers` with server details

#### 4.3 Cloud (API Key)
Adds cloud providers with user-provided API keys.

**Flow:**
1. Select provider from dropdown (OpenAI, Anthropic, etc.)
2. Enter API key
3. Click "Fetch Models" to get available models
4. Call `POST /v1/setup/llm/list-models` with credentials
5. Select model from dropdown
6. Click "Add Provider"
7. Call `POST /v1/system/llm/providers` with config

---

## Section 5: Advanced (Collapsible)

### Collapsed State
```
┌─────────────────────────────────────────────────────────┐
│ ⚙️ ADVANCED                                        [▼]  │
└─────────────────────────────────────────────────────────┘
```

### Expanded State
```
┌─────────────────────────────────────────────────────────┐
│ ⚙️ ADVANCED                                        [▲]  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ Distribution Strategy                                   │
│ How should CIRIS pick which provider to use?            │
│                                                         │
│ ○ Automatic (Recommended)                               │
│   Picks the fastest available provider                  │
│                                                         │
│ ○ Round Robin                                           │
│   Takes turns between providers                         │
│                                                         │
│ ○ Random                                                │
│   Picks randomly to spread the load                     │
│                                                         │
│ ○ Least Loaded                                          │
│   Picks provider with fewest active requests            │
│                                                         │
│ ─────────────────────────────────────────────────────── │
│                                                         │
│ Circuit Breaker Defaults                                │
│                                                         │
│ Failures before pause:    [  5  ]                       │
│ Recovery wait (seconds):  [ 10  ]                       │
│ Successes to resume:      [  3  ]                       │
│ Request timeout (seconds):[ 30  ]                       │
│                                                         │
│                         [Reset to Defaults]             │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### Status & Providers

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/system/llm/status` | GET | Get LLMBus aggregate status |
| `/v1/system/llm/providers` | GET | List all providers with metrics |
| `/v1/system/llm/providers` | POST | Add new provider |
| `/v1/system/llm/providers/{name}` | DELETE | Remove provider |
| `/v1/system/llm/providers/{name}/priority` | PUT | Update priority |
| `/v1/system/llm/providers/{name}/circuit-breaker/reset` | POST | Reset CB |
| `/v1/system/llm/distribution` | PUT | Update distribution strategy |

### Discovery & Setup

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/setup/llm/discover-local-llm` | POST | Discover local servers |
| `/v1/setup/llm/start-local-server` | POST | Start on-device server |
| `/v1/setup/llm/list-models` | POST | List models from provider API |
| `/v1/setup/llm/validate-llm` | POST | Validate LLM connection |

### CIRIS Services

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/system/llm/ciris-services/status` | GET | Get CIRIS services enabled status |
| `/v1/system/llm/ciris-services/disable` | POST | Disable CIRIS services |

---

## ViewModel State

```kotlin
class LLMSettingsViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    // === Status ===
    val llmBusStatus: StateFlow<LlmBusStatus?>
    val isLoading: StateFlow<Boolean>

    // === Adapters ===
    val llmAdapters: StateFlow<List<AdapterItem>>

    // === Providers ===
    val llmProviders: StateFlow<List<LlmProviderStatus>>
    private val _expandedProviderIds: MutableSet<String>
    private val _providerDetailsCache: MutableMap<String, ProviderDetails>

    // === Discovery ===
    val discoveredServers: StateFlow<List<DiscoveredLlmServer>>
    val isDiscovering: StateFlow<Boolean>

    // === Section Expansion ===
    val adaptersExpanded: StateFlow<Boolean>
    val providersExpanded: StateFlow<Boolean>
    val addProviderExpanded: StateFlow<Boolean>
    val advancedExpanded: StateFlow<Boolean>

    // === CIRIS Services ===
    val cirisServicesEnabled: StateFlow<Boolean>

    // === Messages ===
    val statusMessage: StateFlow<String?>
    val errorMessage: StateFlow<String?>

    // === Operations ===
    val operationInProgress: StateFlow<Boolean>

    // === Actions ===
    fun loadStatus()
    fun refresh()

    // Adapter CRUD
    fun reloadAdapter(adapterId: String)
    fun removeAdapter(adapterId: String)

    // Provider CRUD
    fun toggleProviderExpanded(providerName: String)
    fun updateProviderPriority(providerName: String, priority: ProviderPriority)
    fun resetCircuitBreaker(providerName: String, force: Boolean = false)
    fun deleteProvider(providerName: String)

    // Add Provider
    fun discoverLocalServers()
    fun startLocalServer(model: String)
    fun addDiscoveredServerAsProvider(server: DiscoveredLlmServer)
    fun addCloudProvider(providerId: String, apiKey: String, model: String?)
    fun fetchModelsForProvider(providerId: String, apiKey: String)

    // Distribution Strategy
    fun updateDistributionStrategy(strategy: DistributionStrategy)

    // CIRIS Services
    fun disableCirisServices()  // Deletes both ciris_primary and local_primary

    // Section toggles
    fun toggleAdaptersExpanded()
    fun toggleProvidersExpanded()
    fun toggleAddProviderExpanded()
    fun toggleAdvancedExpanded()

    // Messages
    fun clearStatusMessage()
    fun clearErrorMessage()
}
```

---

## CIRIS Services Disable Flow

When user disables CIRIS services:

```kotlin
fun disableCirisServices() {
    viewModelScope.launch {
        _operationInProgress.value = true
        try {
            // 1. Delete CIRIS providers via standard CRUD
            val providers = _llmProviders.value

            val cirisProvider = providers.find { it.name == "ciris_primary" }
            if (cirisProvider != null) {
                apiClient.deleteLlmProvider("ciris_primary")
            }

            val localProvider = providers.find { it.name == "local_primary" }
            if (localProvider != null) {
                apiClient.deleteLlmProvider("local_primary")
            }

            // 2. Persist the disabled state for restart
            apiClient.disableCirisServices()

            _cirisServicesEnabled.value = false
            _statusMessage.value = "CIRIS services disabled"

            // 3. Refresh to reflect changes
            loadStatus()

        } catch (e: Exception) {
            _errorMessage.value = "Failed to disable: ${e.message}"
        } finally {
            _operationInProgress.value = false
        }
    }
}
```

---

## Provider Deletion (No Filtering)

**IMPORTANT:** All providers can be deleted. The previous filter has been removed:

```kotlin
// OLD (REMOVED):
if (!provider.name.startsWith("ciris_")) {
    // Show delete button
}

// NEW:
// Always show delete button for all providers
// System providers show a confirmation warning
IconButton(
    onClick = {
        if (provider.isSystemProvider) {
            showDeleteConfirmation(provider)
        } else {
            viewModel.deleteProvider(provider.name)
        }
    }
) {
    Icon(Icons.Filled.Delete, "Remove")
}
```

**System Provider Confirmation:**
```
┌─────────────────────────────────────────────────────────┐
│ Delete System Provider?                                 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│ "ciris_primary" is a CIRIS-managed provider.           │
│                                                         │
│ Deleting it will disable CIRIS proxy functionality     │
│ until you re-run the setup wizard.                     │
│                                                         │
│                        [Cancel]  [Delete Anyway]        │
└─────────────────────────────────────────────────────────┘
```

---

## Rationale

### Why This Redesign?

1. **Adapters vs Providers Confusion**
   - Users didn't understand the relationship between adapters and providers
   - New design makes it explicit: adapters register providers

2. **Delete Button Visibility**
   - Previous `!name.startsWith("ciris_")` filter was confusing
   - Users couldn't delete local providers even when they should be able to
   - New design: all deletable with appropriate warnings

3. **CIRIS Services Toggle**
   - Previous implementation used env var manipulation
   - New design: uses standard provider CRUD (deleteProvider)
   - Cleaner, more predictable behavior

4. **Add Provider UX**
   - Previous: scattered across multiple sections
   - New: single "Add Provider" section with 3 clear cards
   - Each card handles one use case: Local, Server, Cloud

5. **Following Adapters Pattern**
   - Adapters page has proven UX patterns
   - Expandable cards with lazy-loaded details
   - Operation coalescing (prevent concurrent ops)
   - Transient status messages

### Key Changes from Previous Design

| Aspect | Previous | New |
|--------|----------|-----|
| Section order | Status, Providers, Local, Advanced, Auth | Status, Adapters, Providers, Add, Advanced |
| Provider delete | Filtered by name prefix | All deletable with warnings |
| CIRIS disable | Env var manipulation | Standard CRUD (delete providers) |
| Add provider | Mixed into Providers section | Dedicated section with 3 cards |
| Adapter visibility | Hidden/implicit | Explicit section with CRUD |

---

## Implementation Checklist

- [ ] Update LLMSettingsScreen.kt with new layout
- [ ] Add Adapters section with CRUD
- [ ] Remove provider name filtering from delete button
- [ ] Add system provider confirmation dialog
- [ ] Create 3 Add Provider cards (Local, Server, Cloud)
- [ ] Update disableCirisServices() to use provider CRUD
- [ ] Add expandable provider details with lazy loading
- [ ] Add operation coalescing (prevent concurrent ops)
- [ ] Add transient status messages with auto-dismiss
- [ ] Update LLMSettingsViewModel with new methods
- [ ] Add adapter filtering (LLM-capable only)
- [ ] Test provider deletion flow
- [ ] Test CIRIS services disable flow
- [ ] Build and deploy for testing

---

## Success Criteria

1. **Clear Separation** - Users understand adapters vs providers
2. **Full CRUD** - All providers deletable via standard API
3. **CIRIS Toggle** - Disabling removes both CIRIS providers cleanly
4. **Add Provider UX** - Three clear paths: Local, Server, Cloud
5. **Status Visibility** - Health metrics always visible at top
6. **Consistent Patterns** - Follows Adapters page UX patterns
