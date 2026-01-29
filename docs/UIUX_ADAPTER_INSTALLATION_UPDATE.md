# UI/UX Update: Adapter Installation & Covenant Metrics Integration

**Version:** 1.9.3
**Date:** 2026-01-28
**Status:** Specification

---

## Overview

This document describes UI/UX enhancements for:
1. **Adapter Auto-Discovery & Installation** - New features for discovering and installing adapters with missing dependencies
2. **Setup Wizard Integration** - How to surface adapter installation in the onboarding flow
3. **Covenant Metrics Opt-In** - Adding telemetry consent to setup wizard

---

## Part 1: Adapter Installation Features

### 1.1 New API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/system/adapters/available` | GET | Get discovery report with eligibility status |
| `/v1/system/adapters/{name}/install` | POST | Install missing dependencies |
| `/v1/system/adapters/{name}/check-eligibility` | POST | Recheck after manual installation |

### 1.2 Adapter States

Each discovered adapter has one of three states:

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   ELIGIBLE  │     │ INSTALLABLE  │     │ UNAVAILABLE │
│  (Ready)    │     │ (Can Fix)    │     │ (Manual)    │
└─────────────┘     └──────────────┘     └─────────────┘
     ✅                   ⚠️                    ❌
 All requirements     Has install hints     No auto-fix
   satisfied          for missing deps      available
```

### 1.3 Discovery Report Structure

```json
{
  "eligible": [
    {
      "name": "mcp_filesystem",
      "eligible": true,
      "tools": [{"name": "read_file", "when_to_use": "..."}],
      "service_types": ["TOOL"]
    }
  ],
  "ineligible": [
    {
      "name": "mcp_ffmpeg",
      "eligible": false,
      "eligibility_reason": "Missing binary: ffmpeg",
      "missing_binaries": ["ffmpeg"],
      "can_install": true,
      "install_hints": [
        {
          "id": "brew-ffmpeg",
          "kind": "brew",
          "label": "Install via Homebrew",
          "formula": "ffmpeg",
          "platforms": ["darwin", "linux"]
        },
        {
          "id": "apt-ffmpeg",
          "kind": "apt",
          "label": "Install via apt",
          "package": "ffmpeg",
          "platforms": ["linux"]
        }
      ]
    }
  ],
  "total_discovered": 15,
  "total_eligible": 12,
  "total_installable": 2
}
```

### 1.4 Installation Flow

```
User views adapter list
         │
         ▼
┌─────────────────────────────┐
│  Adapter: mcp_ffmpeg        │
│  Status: ⚠️ Missing ffmpeg  │
│                             │
│  [Install]  [Skip]          │
└─────────────────────────────┘
         │
         ▼ (User clicks Install)
         │
┌─────────────────────────────┐
│  Installing ffmpeg...       │
│  ████████░░░░░░ 60%         │
│                             │
│  Running: brew install ffmpeg│
└─────────────────────────────┘
         │
         ▼
┌─────────────────────────────┐
│  ✅ Installation Complete   │
│                             │
│  ffmpeg installed           │
│  Adapter now eligible       │
│                             │
│  [Enable Adapter]  [Later]  │
└─────────────────────────────┘
```

---

## Part 2: Setup Wizard Integration

### 2.1 Current Wizard Flow

```
Step 1: WELCOME
    │
    ▼
Step 2: LLM_CONFIGURATION
    │
    ▼
Step 3: ACCOUNT_AND_CONFIRMATION
    │
    ▼
Step 4: COMPLETE
```

### 2.2 Proposed Enhanced Flow

```
Step 1: WELCOME
    │
    ▼
Step 2: LLM_CONFIGURATION
    │
    ▼
Step 3: OPTIONAL_FEATURES          ◄── NEW STEP
    │   ├── Covenant Metrics Opt-In
    │   └── Adapter Discovery Preview
    │
    ▼
Step 4: ACCOUNT_AND_CONFIRMATION
    │
    ▼
Step 5: COMPLETE
```

### 2.3 New Step: Optional Features

#### 2.3.1 Mobile UI Mockup

```
┌────────────────────────────────────────┐
│  ← Back                        Step 3/5│
│                                        │
│  ┌────────────────────────────────┐   │
│  │  🎯 Optional Features          │   │
│  │                                │   │
│  │  Customize your CIRIS          │   │
│  │  experience with these         │   │
│  │  optional enhancements.        │   │
│  └────────────────────────────────┘   │
│                                        │
│  ┌────────────────────────────────┐   │
│  │  📊 Help Improve CIRIS         │   │
│  │                                │   │
│  │  Share anonymous usage metrics │   │
│  │  with CIRIS L3C to help        │   │
│  │  improve AI safety research.   │   │
│  │                                │   │
│  │  Data shared:                  │   │
│  │  • Reasoning quality scores    │   │
│  │  • Decision patterns (no text) │   │
│  │  • Performance metrics         │   │
│  │                                │   │
│  │  ⓘ Learn more about our        │   │
│  │    privacy practices           │   │
│  │                                │   │
│  │  ┌──┐                          │   │
│  │  │  │ I agree to share         │   │
│  │  └──┘ anonymous metrics        │   │
│  └────────────────────────────────┘   │
│                                        │
│  ┌────────────────────────────────┐   │
│  │  🔧 Available Adapters         │   │
│  │                                │   │
│  │  12 adapters ready             │   │
│  │  2 can be installed            │   │
│  │  1 requires manual setup       │   │
│  │                                │   │
│  │  [View Adapters →]             │   │
│  └────────────────────────────────┘   │
│                                        │
│  ┌────────────────────────────────┐   │
│  │           [Continue]           │   │
│  └────────────────────────────────┘   │
└────────────────────────────────────────┘
```

#### 2.3.2 Adapter Discovery Card (Expanded)

```
┌────────────────────────────────────────┐
│  🔧 Available Adapters                 │
├────────────────────────────────────────┤
│                                        │
│  ✅ Ready to Use (12)                  │
│  ├── mcp_filesystem                    │
│  ├── mcp_git                           │
│  ├── mcp_web_search                    │
│  └── [Show all...]                     │
│                                        │
│  ⚠️ Can Be Installed (2)               │
│  ┌──────────────────────────────────┐ │
│  │ mcp_ffmpeg                       │ │
│  │ Video/audio processing tools     │ │
│  │ Missing: ffmpeg                  │ │
│  │ [Install Now]                    │ │
│  └──────────────────────────────────┘ │
│  ┌──────────────────────────────────┐ │
│  │ mcp_imagemagick                  │ │
│  │ Image manipulation tools         │ │
│  │ Missing: convert                 │ │
│  │ [Install Now]                    │ │
│  └──────────────────────────────────┘ │
│                                        │
│  ❌ Requires Manual Setup (1)          │
│  ├── discord                           │
│  │   Needs: DISCORD_BOT_TOKEN          │
│  │   [Configure →]                     │
│                                        │
│  [Done]                                │
└────────────────────────────────────────┘
```

### 2.4 State Management

```kotlin
// Add to SetupFormState
data class SetupFormState(
    // ... existing fields ...

    // Covenant Metrics Opt-In (DETAILED level only)
    val covenantMetricsConsent: Boolean = false,

    // Adapter Discovery
    val adapterDiscoveryLoaded: Boolean = false,
    val eligibleAdapters: List<AdapterInfo> = emptyList(),
    val installableAdapters: List<AdapterInfo> = emptyList(),
    val unavailableAdapters: List<AdapterInfo> = emptyList(),
    val installingAdapter: String? = null,
    val installError: String? = null
)
```

### 2.5 API Integration

```kotlin
// SetupViewModel.kt additions

suspend fun loadAdapterDiscovery() {
    _state.update { it.copy(adapterDiscoveryLoaded = false) }

    val response = apiClient.get("/v1/system/adapters/available")
    val report = response.parseAs<AdapterDiscoveryReport>()

    _state.update {
        it.copy(
            adapterDiscoveryLoaded = true,
            eligibleAdapters = report.eligible,
            installableAdapters = report.ineligible.filter { a -> a.canInstall },
            unavailableAdapters = report.ineligible.filter { a -> !a.canInstall }
        )
    }
}

suspend fun installAdapter(adapterName: String) {
    _state.update { it.copy(installingAdapter = adapterName) }

    try {
        val response = apiClient.post(
            "/v1/system/adapters/$adapterName/install",
            body = mapOf("dry_run" to false)
        )
        val result = response.parseAs<InstallResponse>()

        if (result.success && result.nowEligible) {
            // Move from installable to eligible
            loadAdapterDiscovery()
        }
    } catch (e: Exception) {
        _state.update { it.copy(installError = e.message) }
    } finally {
        _state.update { it.copy(installingAdapter = null) }
    }
}
```

---

## Part 3: Covenant Metrics Opt-In

### 3.1 What Is Covenant Metrics?

The Covenant Metrics adapter sends anonymous telemetry to CIRIS L3C to:
- Improve AI safety research
- Calculate CIRIS Capacity Scores
- Detect early warning patterns for AI risks
- Build the Coherence Ratchet training corpus

### 3.2 Data Privacy Level

The covenant metrics adapter uses a single **DETAILED** level that provides meaningful data for AI alignment research while protecting user privacy.

### 3.3 Detailed Level Data

What IS sent:
- Reasoning quality scores (0-1 numeric values)
- Decision patterns (TOOL/SPEAK/PONDER/etc.)
- Performance metrics (latency, token counts)
- Error rates and flags
- Cognitive state transitions
- LLM provider/model identifiers (for cross-provider alignment studies)
- API base URL (anonymized, for model behavior correlation)
- Thought identifiers and timestamps
- Adapter and channel identifiers

What is NEVER sent:
- User messages or chat content
- File contents or paths
- Personal identifiable information (PII)
- API keys or secrets
- Full reasoning text or prompts

### 3.4 Consent UI Component

```kotlin
@Composable
fun CovenantMetricsConsentCard(
    consentGiven: Boolean,
    onConsentChange: (Boolean) -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = Icons.Default.Analytics,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary
                )
                Spacer(modifier = Modifier.width(12.dp))
                Text(
                    "Help Improve AI Alignment",
                    style = MaterialTheme.typography.titleMedium
                )
            }

            Spacer(modifier = Modifier.height(12.dp))

            Text(
                "Share anonymous metrics with CIRIS L3C to advance AI alignment research. " +
                "This includes your API base URL to help study alignment patterns across " +
                "different providers and models.",
                style = MaterialTheme.typography.bodyMedium
            )

            Spacer(modifier = Modifier.height(8.dp))

            // Data disclosure summary
            Text(
                "Data shared:",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            Column(modifier = Modifier.padding(start = 8.dp, top = 4.dp)) {
                DataPointRow("Reasoning quality scores")
                DataPointRow("Decision patterns (no message content)")
                DataPointRow("LLM provider and API base URL")
                DataPointRow("Performance metrics")
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Privacy link
            TextButton(onClick = { openUrl("https://ciris.ai/privacy") }) {
                Icon(Icons.Default.Info, contentDescription = null)
                Spacer(modifier = Modifier.width(4.dp))
                Text("Learn more about our privacy practices")
            }

            Spacer(modifier = Modifier.height(12.dp))

            // Consent checkbox
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.clickable { onConsentChange(!consentGiven) }
            ) {
                Checkbox(
                    checked = consentGiven,
                    onCheckedChange = onConsentChange
                )
                Spacer(modifier = Modifier.width(8.dp))
                Text(
                    "I agree to share anonymous alignment metrics",
                    style = MaterialTheme.typography.bodyMedium
                )
            }
        }
    }
}

@Composable
private fun DataPointRow(text: String) {
    Row(modifier = Modifier.padding(vertical = 2.dp)) {
        Text("•", color = MaterialTheme.colorScheme.primary)
        Spacer(modifier = Modifier.width(8.dp))
        Text(text, style = MaterialTheme.typography.bodySmall)
    }
}
```

### 3.5 Setup Completion Integration

When setup completes, include covenant metrics configuration:

```kotlin
// In SetupViewModel.completeSetup()

val setupRequest = SetupCompleteRequest(
    // ... existing fields ...

    // Add covenant metrics configuration (DETAILED level only)
    enabled_adapters = buildList {
        add("api")  // Always enabled
        if (state.covenantMetricsConsent) {
            add("ciris_covenant_metrics")
        }
    },
    adapter_config = buildMap {
        if (state.covenantMetricsConsent) {
            put("CIRIS_COVENANT_METRICS_CONSENT", "true")
            put("CIRIS_COVENANT_METRICS_CONSENT_TIMESTAMP",
                Instant.now().toString())
            put("CIRIS_COVENANT_METRICS_TRACE_LEVEL", "detailed")
        }
    }
)
```

### 3.6 Backend Setup Route Update

Add to `setup.py` completion handler:

```python
# In _save_setup_config()

if "ciris_covenant_metrics" in enabled_adapters:
    config_lines.extend([
        "",
        "# Covenant Metrics Configuration",
        f"CIRIS_COVENANT_METRICS_CONSENT={adapter_config.get('CIRIS_COVENANT_METRICS_CONSENT', 'false')}",
        f"CIRIS_COVENANT_METRICS_CONSENT_TIMESTAMP={adapter_config.get('CIRIS_COVENANT_METRICS_CONSENT_TIMESTAMP', '')}",
        f"CIRIS_COVENANT_METRICS_TRACE_LEVEL={adapter_config.get('CIRIS_COVENANT_METRICS_TRACE_LEVEL', 'generic')}",
    ])
```

---

## Part 4: Implementation Checklist

### 4.1 Mobile App Changes

- [ ] Add `SetupStep.OPTIONAL_FEATURES` to wizard flow
- [ ] Create `OptionalFeaturesStep` composable
- [ ] Create `CovenantMetricsConsentCard` component (DETAILED level only, no selector)
- [ ] Update `SetupFormState` with `covenantMetricsConsent` field
- [ ] Update `SetupViewModel` with consent handling
- [ ] Update `completeSetup()` to include covenant metrics config
- [ ] Add privacy policy link handler

### 4.2 Backend Changes

- [ ] Ensure `/v1/system/adapters/available` works without auth during setup
- [ ] Add covenant metrics fields to setup completion
- [ ] Update `.env` generation to include covenant metrics config
- [ ] Add adapter installation progress endpoint (optional, for real-time updates)

### 4.3 Testing

- [ ] Unit tests for new wizard step
- [ ] Integration tests for adapter discovery in setup
- [ ] Integration tests for covenant metrics opt-in
- [ ] QA runner tests for full setup flow with adapters
- [ ] Manual testing on Android device

---

## Part 5: UX Guidelines

### 5.1 Consent Language

**DO:**
- Use clear, plain language
- Explain what data is collected
- Provide easy access to privacy policy
- Make opt-in the default state (unchecked)
- Allow changing preference later in settings

**DON'T:**
- Use dark patterns
- Pre-check consent boxes
- Hide the decline option
- Make consent required for basic functionality
- Use technical jargon

### 5.2 Installation UX

**DO:**
- Show clear progress indicators
- Explain what's being installed
- Handle errors gracefully
- Allow skipping installations
- Show success confirmation

**DON'T:**
- Block the wizard on optional installs
- Auto-install without user action
- Hide installation commands
- Fail silently

### 5.3 Adapter Discovery

**DO:**
- Group adapters by state (ready/installable/manual)
- Show tool descriptions
- Indicate platform compatibility
- Allow deferred configuration

**DON'T:**
- Overwhelm with all adapters at once
- Require adapter selection to continue
- Hide eligibility requirements

---

## Appendix A: Data Models

### AdapterDiscoveryReport

```kotlin
@Serializable
data class AdapterDiscoveryReport(
    val eligible: List<AdapterAvailabilityStatus>,
    val ineligible: List<AdapterAvailabilityStatus>,
    val totalDiscovered: Int,
    val totalEligible: Int,
    val totalInstallable: Int
)

@Serializable
data class AdapterAvailabilityStatus(
    val name: String,
    val eligible: Boolean,
    val eligibilityReason: String? = null,
    val missingBinaries: List<String> = emptyList(),
    val missingEnvVars: List<String> = emptyList(),
    val missingConfig: List<String> = emptyList(),
    val platformSupported: Boolean = true,
    val canInstall: Boolean = false,
    val installHints: List<InstallStep> = emptyList(),
    val tools: List<ToolInfo> = emptyList(),
    val serviceTypes: List<String> = emptyList()
)

@Serializable
data class InstallStep(
    val id: String,
    val kind: String,  // brew, apt, pip, npm, etc.
    val label: String,
    val formula: String? = null,
    val package: String? = null,
    val command: String? = null,
    val platforms: List<String> = emptyList()
)

@Serializable
data class InstallResponse(
    val success: Boolean,
    val message: String,
    val installedBinaries: List<String> = emptyList(),
    val nowEligible: Boolean = false
)
```

### CovenantMetricsConfig

```kotlin
@Serializable
data class CovenantMetricsConfig(
    val consentGiven: Boolean = false,
    val consentTimestamp: String? = null,
    // Trace level is always DETAILED - no user selection
    val traceLevel: String = "detailed",
    val endpoint: String = "https://lens.ciris-services-1.ai/lens-api/api/v1",
    val batchSize: Int = 10,
    val flushIntervalSeconds: Int = 60
)
```

---

## Appendix B: Related Files

### Backend
- `ciris_engine/logic/adapters/api/routes/system/adapters.py` - Adapter endpoints
- `ciris_engine/logic/adapters/api/routes/setup.py` - Setup wizard endpoints
- `ciris_engine/logic/services/tool/discovery_service.py` - Discovery service
- `ciris_engine/logic/services/tool/eligibility_checker.py` - Eligibility checker
- `ciris_engine/logic/services/tool/installer.py` - Tool installer
- `ciris_adapters/ciris_covenant_metrics/` - Covenant metrics adapter

### Mobile
- `mobile/shared/src/commonMain/kotlin/ai/ciris/mobile/shared/viewmodels/SetupViewModel.kt`
- `mobile/shared/src/commonMain/kotlin/ai/ciris/mobile/shared/ui/screens/SetupScreen.kt`
- `mobile/shared/src/commonMain/kotlin/ai/ciris/mobile/shared/models/Setup.kt`

### Tests
- `tests/adapters/api/test_adapter_availability.py`
- `tests/adapters/covenant_metrics/test_covenant_metrics_adapter.py`
- `tools/qa_runner/modules/setup_tests.py`

---

## Appendix C: Lessons Learned (for CIRISGUI-Standalone)

### C.1 Platform Detection Gotchas

**Issue:** Android reports `sys.platform` as `"linux"`, not `"android"`.

**Impact:** Platform requirements like `platforms=["darwin", "linux", "win32"]` will PASS on Android because "linux" matches.

**Solution:** For desktop-only tools, add a binary requirement that doesn't exist on Android:
```python
requirements=ToolRequirements(
    binaries=[BinaryRequirement(name="bash")],  # Filters out Android
    platforms=["darwin", "linux", "win32"],
)
```

**CIRISGUI Guidance:** When porting to standalone desktop app, don't rely solely on platform checks. Use binary requirements for tools that need shell access or desktop-specific binaries.

### C.2 BinaryRequirement Schema Strictness

**Issue:** `BinaryRequirement` uses `extra="forbid"` and only accepts these fields:
- `name` (required)
- `min_version` (optional)
- `verify_command` (optional)

Adding a `description` field causes a Pydantic validation error:
```python
# ❌ WRONG - causes silent failure
BinaryRequirement(name="slack", description="Slack CLI tool")

# ✅ CORRECT
BinaryRequirement(name="slack")
```

**Impact:** The eligibility check throws an exception, caught at DEBUG level, and the adapter silently disappears from both eligible and ineligible lists.

**CIRISGUI Guidance:** Always check schema definitions before adding fields. Test eligibility locally before deploying.

### C.3 Silent Eligibility Failures

**Issue:** When `_build_tool_info()` or `get_all_tool_info()` throws an exception during eligibility checking, the error is logged at DEBUG level and the adapter returns `(None, None)`:

```python
except Exception as e:
    logger.debug(f"Error checking eligibility for {adapter_name}: {e}")
    return None, None
```

This means the adapter doesn't appear in either eligible OR ineligible lists.

**Debugging Steps:**
1. Check if the adapter is initialized (look for `*ToolService initialized` in logs)
2. If initialized but no eligibility verdict, check for schema/validation errors
3. Run eligibility check manually in Python to see the actual error

**CIRISGUI Guidance:** Consider elevating this log to WARNING level for better observability. Add error tracking for adapters that initialize but have no eligibility verdict.

### C.4 Config Service Dependency

**Issue:** `ToolEligibilityChecker._check_config_keys()` skips validation if no `config_service` is provided:

```python
if not self.config_service:
    return True, []  # Skip config checks
```

**Impact:** Adapters with `config_keys` requirements load even when those config values don't exist.

**Solution:** Always pass `config_service` to eligibility checker:
```python
eligibility_checker = ToolEligibilityChecker(config_service=self.config_service)
```

**CIRISGUI Guidance:** Ensure config service is wired into eligibility checking from the start.

### C.5 CI Secret Masking

**Issue:** GitHub Actions automatically masks values that look like secrets/tokens, replacing them with `***` in logs AND in test assertions.

**Impact:** Tests like `assert "TESTJWT12345" in auth_header` fail because `auth_header` becomes `"***"`.

**Solution:** Accept both real value and masked value:
```python
is_bearer_auth = auth_header.startswith("Bearer ")
is_ci_masked = auth_header == "***"
assert is_bearer_auth or is_ci_masked
```

**CIRISGUI Guidance:** Use non-secret-looking test values (e.g., `"test_value_123"`) or skip token-value assertions in CI.

### C.6 Adapter Manifest Migration

**Issue:** Old-style manifest.json files with fields like `requires`, `provides`, `hooks`, `config_schema` cause validation errors against the current `ServiceManifest` schema.

**Correct Format:**
```json
{
  "module": {
    "name": "adapter_name",
    "version": "1.0.0",
    "description": "...",
    "author": "..."
  },
  "services": [
    {
      "type": "TOOL",
      "priority": "NORMAL",
      "class": "module.service.ClassName",
      "capabilities": ["..."]
    }
  ],
  "capabilities": ["..."],
  "dependencies": {...},
  "exports": {...},
  "configuration": {...}
}
```

**CIRISGUI Guidance:** Validate all adapter manifests against `ServiceManifest` schema before release.

### C.7 Test Flexibility with Dynamic Discovery

**Issue:** Tests that assert exact adapter counts break when new adapters are added:
```python
# ❌ Breaks when discovery adds adapters
assert len(adapters) == 4

# ✅ Flexible assertion
assert len(adapters) >= 4
assert "api" in adapter_ids  # Required adapter
```

**CIRISGUI Guidance:** Test for required adapters specifically, use minimum counts for totals, and don't hardcode expected adapter lists.

### C.8 Mobile Log Collection

**Best Practice:** Always use the QA runner to pull logs after testing:
```bash
python3 -m tools.qa_runner.modules.mobile pull-logs -o ./mobile_qa_reports/test_name
```

**Key Files to Check:**
1. `logs/incidents_latest.log` - Check first for errors
2. `logs/latest.log` - Search for `[AUTO-LOAD]` entries
3. `logcat_app.txt` - Kotlin/KMP logs

**Search Pattern for Adapter Issues:**
```bash
grep -i "not eligible\|AUTO-LOAD\|initialized" logs/latest.log
```

**CIRISGUI Guidance:** Build similar log collection tooling for desktop app debugging.
