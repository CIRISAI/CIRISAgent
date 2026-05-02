# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with the CIRIS codebase.

## 🎯 CURRENT FOCUS: Production Quality & Stability

**Goal**: Maintain production-grade quality, stability, and test coverage

### Priority Areas

1. **Test Coverage** - Target 80%
   - Focus on critical path services
   - Integration tests for complex flows
   - Edge case coverage

2. **Bug Fixes & Stability**
   - Address any production issues from agents.ciris.ai
   - Fix flaky tests
   - Resolve memory leaks or performance issues

3. **Documentation & Code Quality**
   - Update outdated documentation
   - Remove dead code and TODOs
   - Ensure all APIs are properly documented

4. **Security Hardening**
   - Review authentication flows
   - Audit secret handling
   - Validate input sanitization

### ⚠️ CRITICAL: Medical Domain Prohibition

**NEVER implement in main repo:**
- Medical/health capabilities
- Diagnosis/treatment logic
- Patient data handling
- Clinical decision support

**These are BLOCKED at the bus level.** See `PROHIBITED_CAPABILITIES` in `wise_bus.py`.

---

## Project Overview

CIRIS (Core Identity, Integrity, Resilience, Incompleteness, and Signalling Gratitude) is an ethical AI platform:
- **Production**: Discord moderation + API at agents.ciris.ai
- **Architecture**: 22 core services, 6 message buses, strict type safety
- **Philosophy**: No Untyped Dicts, No Bypass Patterns, No Exceptions
- **Target**: 4GB RAM, offline-capable deployment

## Multi-Occurrence Deployment Support

CIRIS supports running multiple runtime occurrences of the same agent against a shared database for horizontal scaling.

### Key Concepts

- **Occurrence**: A single runtime instance of an agent (process/container)
- **Shared Tasks**: Agent-level tasks using `agent_occurrence_id="__shared__"` that coordinate across occurrences
- **Atomic Claiming**: Race-free task claiming using deterministic IDs + `INSERT OR IGNORE`

### Configuration

```bash
# Set occurrence ID (defaults to "default")
export AGENT_OCCURRENCE_ID="occurrence-1"

# Set total occurrence count for discovery
export AGENT_OCCURRENCE_COUNT="9"
```

### Architecture

**Single Decision-Maker Pattern:**
- Wakeup/shutdown decisions made by ONE occurrence
- Decision applies to ALL occurrences
- Other occurrences skip or monitor the shared decision

**Implementation:**
- `try_claim_shared_task()` - Atomic task claiming
- `is_shared_task_completed()` - Check if another occurrence decided
- `get_latest_shared_task()` - Retrieve shared decision
- Deterministic task IDs: `WAKEUP_SHARED_20251027`, `SHUTDOWN_SHARED_20251027`

### Key Files

- **Shared Task Functions**: `ciris_engine/logic/persistence/models/tasks.py`
- **Occurrence Utils**: `ciris_engine/logic/utils/occurrence_utils.py`
- **Wakeup Coordination**: `ciris_engine/logic/processors/states/wakeup_processor.py`
- **Shutdown Coordination**: `ciris_engine/logic/processors/states/shutdown_processor.py`

### Testing Multi-Occurrence

```python
# Unit tests with race simulation
pytest tests/ciris_engine/logic/persistence/test_shared_tasks.py

# Occurrence discovery tests
pytest tests/ciris_engine/logic/utils/test_occurrence_utils.py
```

**Important**: Configuration already in `EssentialConfig.agent_occurrence_id` (line 129)

## Core Philosophy: Type Safety First

🚧 **PROGRESS: Minimizing `Dict[str, Any]` usage in production code**

### The Three Rules

1. **No Untyped Dicts**: All data uses Pydantic models instead of `Dict[str, Any]`
2. **No Bypass Patterns**: Every component follows consistent rules and patterns
3. **No Exceptions**: No special cases, emergency overrides, or privileged code paths

### Before Creating ANY New Type

```bash
# ALWAYS search first:
grep -r "class.*YourThingHere" --include="*.py"
# The schema already exists. Use it.
```

### Type Safety Best Practices

1. **Replace Untyped Dicts with Pydantic Models**
   ```python
   # ❌ Bad
   def process_data(data: Dict[str, Any]) -> Dict[str, Any]:
       return {"result": data.get("value", 0) * 2}

   # ✅ Good
   class ProcessRequest(BaseModel):
       value: int = 0

   class ProcessResponse(BaseModel):
       result: int

   def process_data(data: ProcessRequest) -> ProcessResponse:
       return ProcessResponse(result=data.value * 2)
   ```

2. **Use Specific Types Instead of Any**
   ```python
   # ❌ Bad
   metrics: Dict[str, Any] = {"cpu": 0.5, "memory": 1024}

   # ✅ Good
   class SystemMetrics(BaseModel):
       cpu: float = Field(..., ge=0, le=1, description="CPU usage 0-1")
       memory: int = Field(..., gt=0, description="Memory in MB")

   metrics = SystemMetrics(cpu=0.5, memory=1024)
   ```

3. **Leverage Union Types for Flexibility**
   ```python
   # For gradual migration or multiple input types
   def process(data: Union[dict, ProcessRequest]) -> ProcessResponse:
       if isinstance(data, dict):
           data = ProcessRequest(**data)
       return ProcessResponse(result=data.value * 2)
   ```

4. **Avoid Bypass Patterns - Follow Consistent Rules**
   ```python
   # ❌ Bad - Special bypass for "emergency"
   if emergency_mode:
       return process_without_validation(data)

   # ✅ Good - Same validation rules apply everywhere
   validated_data = validate_request(data)
   return process_validated_data(validated_data)
   ```

5. **Use Enums for Constants**
   ```python
   # ❌ Bad
   status = "active"  # Magic string

   # ✅ Good
   class ServiceStatus(str, Enum):
       ACTIVE = "active"
       INACTIVE = "inactive"
       ERROR = "error"

   status = ServiceStatus.ACTIVE
   ```

6. **Enhanced Mypy Configuration**
   - `strict = True` enabled in mypy.ini with additional strictness flags
   - `disallow_any_explicit = True` temporarily disabled (too many false positives)
   - Minimal Dict[str, Any] usage remaining, none in critical code paths
   - Run mypy as part of CI/CD pipeline

7. **Build-Time Generated Files**
   - Some files are generated at build time and not present in the repo/CI
   - These require `# type: ignore[import-not-found]` comments
   - **DO NOT REMOVE** these comments even if mypy reports "unused-ignore" locally
   - Examples:
     - `ciris_adapters/wallet/providers/_build_secrets.py` - Contains API keys/URLs injected at build time
   - Always add a comment explaining why the ignore is needed:
     ```python
     # _build_secrets is generated at build time, not present in CI/repo
     from ._build_secrets import get_api_key  # type: ignore[import-not-found]
     ```

## CRITICAL: OAuth Callback URL Format

**PRODUCTION OAuth CALLBACK URL - DO NOT FORGET:**
```
https://agents.ciris.ai/v1/auth/oauth/{agent_id}/{provider}/callback
```

Example for Datum + Google:
```
https://agents.ciris.ai/v1/auth/oauth/datum/google/callback
```

**REMEMBER:**
- Agent ID comes BEFORE provider
- /v1/ is at the ROOT level
- This is the DEFAULT route (not /api/{agent}/v1/)


## Architecture Overview

### Message Bus Architecture (6 Buses)

Buses enable multiple providers for scalability:

**Bussed Services**:
- CommunicationBus → Multiple adapters (Discord, API, CLI)
- MemoryBus → Multiple graph backends (Neo4j, ArangoDB, in-memory)
- LLMBus → Multiple LLM providers (OpenAI, Anthropic, local models)
- ToolBus → Multiple tool providers from adapters
- RuntimeControlBus → Multiple control interfaces
- WiseBus → Multiple wisdom sources

**Direct Call Services**:
- All Graph Services (except memory)
- Core Services: secrets
- Infrastructure Services (except wise_authority)
- All Special Services

### Service Registry Usage

Only for multi-provider services:
1. **LLM** - Multiple providers
2. **Memory** - Multiple graph backends
3. **WiseAuthority** - Multiple wisdom sources
4. **RuntimeControl** - Adapter-provided only

### Cognitive States (6)
- **WAKEUP** - Identity confirmation
- **WORK** - Normal task processing
- **PLAY** - Creative mode
- **SOLITUDE** - Reflection
- **DREAM** - Deep introspection
- **SHUTDOWN** - Graceful termination

## Localization

CIRIS supports 29 languages with full pipeline localization. The entire ethical reasoning system operates in the user's preferred language.

### Supported Languages (29)

Together these reach roughly 95% of the world's population — chosen to maximize accessibility for the people who most need ethical, multilingual AI assistance.

Source of truth: `localization/manifest.json`. To add or remove a language, update the manifest first.

`am` (Amharic), `ar` (Arabic, RTL), `bn` (Bengali), `de` (German), `en` (English, base), `es` (Spanish), `fa` (Persian, RTL), `fr` (French), `ha` (Hausa), `hi` (Hindi), `id` (Indonesian), `it` (Italian), `ja` (Japanese), `ko` (Korean), `mr` (Marathi), `my` (Burmese), `pa` (Punjabi), `pt` (Portuguese), `ru` (Russian), `sw` (Swahili), `ta` (Tamil), `te` (Telugu), `th` (Thai), `tr` (Turkish), `uk` (Ukrainian), `ur` (Urdu, RTL), `vi` (Vietnamese), `yo` (Yoruba), `zh` (Chinese, Simplified)

### Key Files
- **UI Strings**: `localization/{lang}.json` - Mobile/API UI strings
- **ACCORD**: `ciris_engine/data/localized/accord_1.2b_{lang}.txt`
- **Guides**: `ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE_{lang}.md`
- **DMA Prompts**: `ciris_engine/logic/dma/prompts/localized/{lang}/*.yml`

### Setting Language
```bash
export CIRIS_PREFERRED_LANGUAGE=am  # Set before starting server
```

### How It Works
1. `get_preferred_language()` reads `CIRIS_PREFERRED_LANGUAGE` env var
2. `DMAPromptLoader` auto-detects language on first load
3. Each DMA calls `get_localized_accord_text(lang)` for localized ACCORD
4. Conscience strings use `get_string(lang, "conscience.ponder_*")`

### Testing Localization
```bash
# Run streaming test with Amharic
CIRIS_PREFERRED_LANGUAGE=am python3 -m tools.qa_runner streaming --verbose
# Look for Amharic text: ከመጀመሪያው ጥያቄ በፊት...
```

## Development Tools

### Grace - Sustainable Development Companion

Grace is your intelligent pre-commit gatekeeper and development assistant that ensures sustainable coding practices:

```bash
# Quick status check
python -m tools.grace status           # Current session, health, CI status

# CI/CD Monitoring (CRITICAL for Claude)
python -m tools.grace ci               # Current branch CI + PR summary (10min throttle)
python -m tools.grace ci prs           # All PRs with conflict/block detection
python -m tools.grace ci builds        # Build & Deploy status across branches
python -m tools.grace ci hints         # Common CI failure hints & existing schemas

# Pre-commit assistance
python -m tools.grace precommit        # Detailed pre-commit status and fixes
python -m tools.grace fix              # Auto-fix pre-commit issues

# Session management
python -m tools.grace morning          # Morning check-in
python -m tools.grace pause            # Save context before break
python -m tools.grace resume           # Resume after break
python -m tools.grace night            # Evening choice point

# Deployment & incidents
python -m tools.grace deploy           # Check deployment status
python -m tools.grace incidents        # Check production incidents

# Short forms: s, m, p, r, n, d, c, pc, f, i
```

**Grace Philosophy:**
- **Be strict about safety, gentle about style** - Blocks only critical issues (syntax errors, security)
- **Progress over perfection** - Quality issues are reminders, not blockers
- **Sustainable pace** - Tracks work sessions and encourages breaks

**Pre-commit Integration:**
Grace is the primary pre-commit hook. It:
1. Auto-formats with black and isort
2. Blocks critical issues (syntax, merge conflicts, secrets)
3. Reports quality issues as gentle reminders
4. Runs all checks concurrently for speed

### CRITICAL CI Guidance for Claude (You!)

**YOUR BAD HABITS TO STOP:**
1. **Creating new Dict[str, Any]** - A schema already exists. Always.
2. **Creating NewSchemaV2** - The original schema is fine. Use it.
3. **Checking CI too frequently** - CI takes time to complete. Check periodically.
4. **Making "temporary" helper classes** - They're never temporary. Use existing schemas.
5. **Creating elaborate abstractions** - Simple existing patterns work better.

**BEFORE CREATING ANY NEW TYPE:**
```bash
# ALWAYS search first:
grep -r "class.*YourThingHere" --include="*.py"
# The schema already exists. Use it.
```

### Schemas That Already Exist (Stop Recreating!)

- `AuditEventData` - ALL audit events
- `ServiceMetrics` - ALL metrics
- `SystemSnapshot` - System state
- `ProcessingQueueItem` - Queue items
- `ActionResponse` - Handler responses
- `ThoughtSchema` - Thoughts
- `GuidanceRequest/Response` - WA guidance


## Service Architecture

### 22 Core Services

**Graph Services (7):**
memory, consent, config, telemetry, audit, incident_management, tsdb_consolidation

**Infrastructure Services (4):**
authentication, resource_monitor, database_maintenance, secrets

**Lifecycle Services (4):**
initialization, shutdown, time, task_scheduler

**Governance Services (4):**
wise_authority, adaptive_filter, visibility, self_observation

**Runtime Services (2):**
llm, runtime_control

**Tool Services (1):**
secrets_tool

### Message Buses (6)

- **CommunicationBus** → Multiple adapters
- **MemoryBus** → Multiple graph backends
- **LLMBus** → Multiple LLM providers
- **ToolBus** → Multiple tool providers
- **RuntimeControlBus** → Multiple control interfaces
- **WiseBus** → Multiple wisdom sources *(FOCUS AREA)*

## Adapter Development

Adapters extend CIRIS with new capabilities via the bus system. See `FSD/ADAPTER_DEVELOPMENT_GUIDE.md` for the full guide.

### Quick Reference

**Required Files:**
```
ciris_adapters/your_adapter/
├── __init__.py           # MUST export Adapter
├── adapter.py            # BaseAdapterProtocol implementation
├── manifest.json         # Metadata, services, capabilities
├── tool_service.py       # ToolServiceProtocol implementation
└── config.py             # Pydantic config models (no Dict[str, Any])
```

**Context Enrichment:**
Tools that provide situational awareness should auto-run during context gathering:
```python
ToolInfo(
    name="get_status",
    context_enrichment=True,
    context_enrichment_params={"include_details": False},
    ...
)
```

**DMA Guidance:**
Financial and destructive tools MUST have:
```python
dma_guidance=ToolDMAGuidance(
    requires_approval=True,  # Triggers Wise Authority deferral
    min_confidence=0.95,     # High confidence required
    ethical_considerations="...",
)
```

**Reference Implementations:**
- `ciris_adapters/sample_adapter/` - Complete template
- `ciris_adapters/home_assistant/` - Context enrichment example
- `ciris_adapters/wallet/` - Financial tools example

## Unified Agent UX (`client/`)

The `client/` directory contains the **unified CIRIS agent UX** - a Kotlin Multiplatform (KMP) client targeting Android, iOS, Windows, macOS, and Linux. It's the cross-platform user interface for interacting with CIRIS agents.

### Unified Entry Point (`ciris-agent`)

The `ciris-agent` command is the **unified entry point** that starts both the Python backend and the desktop GUI:

```bash
# Unified: Start API server + launch desktop app (DEFAULT)
ciris-agent

# Server-only modes (headless)
ciris-agent --server              # API server only
ciris-agent --adapter api         # Same as --server
ciris-agent --adapter discord     # Discord bot mode

# Separate commands
ciris-server                      # Headless API server only
ciris-desktop                     # Desktop app only (connects to running server)
```

**How it works (from `ciris_engine/cli.py`):**
1. Starts Python API server on port 8080 via `main.py --adapter api`
2. Waits briefly to detect startup failures
3. Launches desktop JAR via `desktop_launcher.py`
4. On exit, shuts down server gracefully

**Desktop JAR location:**
- Production: `ciris_engine/desktop_app/CIRIS-*.jar` (bundled in pip package)
- Development: `client/desktopApp/build/compose/jars/CIRIS-*.jar`

### Mobile QA Runner (ALWAYS USE THIS)

When debugging mobile app issues, **always** use the QA runner to pull logs:

```bash
# Pull all logs from device (debug build) - THE COMMAND TO USE
python3 -m tools.qa_runner.modules.mobile pull-logs

# Specify output directory
python3 -m tools.qa_runner.modules.mobile pull-logs -o ./my_logs

# Specific device
python3 -m tools.qa_runner.modules.mobile pull-logs -d emulator-5554
```

**Files collected (saved to `client_qa_reports/<timestamp>/`):**
- `logs/latest.log` - Python runtime logs (CIRIS engine)
- `logs/incidents_latest.log` - Incident/error logs (CHECK THIS FIRST!)
- `logcat_python.txt` - Python stdout/stderr
- `logcat_app.txt` - Kotlin/KMP logs (CIRISApp, ViewModels, etc.)
- `logcat_combined.txt` - All relevant logs combined
- `logcat_crashes.txt` - Android crashes
- `databases/*.db` - SQLite databases (ciris_engine.db, secrets.db, audit.db)
- `prefs/*.xml` - Shared preferences
- `env_file.txt` - .env file (tokens redacted)
- `app_info.txt` - Device and package info

**Quick analysis:**
```bash
# Check for errors (ALWAYS DO THIS FIRST!)
grep -i error client_qa_reports/*/logs/incidents_latest.log

# Recent Python logs
tail -100 client_qa_reports/*/logs/latest.log

# Kotlin/KMP logs (CIRISApp, ViewModels)
grep -i "CIRISApp\|ViewModel\|error" client_qa_reports/*/logcat_app.txt
```

### UI Automation Tests

Automated UI testing for the CIRIS client app:

```bash
# Full flow test with test account
python3 -m tools.qa_runner.modules.mobile test full_flow

# Individual tests
python3 -m tools.qa_runner.modules.mobile test app_launch
python3 -m tools.qa_runner.modules.mobile test google_signin
python3 -m tools.qa_runner.modules.mobile setup_wizard
python3 -m tools.qa_runner.modules.mobile chat_interaction

# Build and test
python3 -m tools.qa_runner.modules.mobile --build full_flow
```

**Test account:** ciristest1@gmail.com (password in `~/.ciristest1_password`)

### Build and Deploy

```bash
# Build debug APK
cd client && ./gradlew :androidApp:assembleDebug

# IMPORTANT: Kill the app before reinstalling (required for Python runtime to reload)
~/Android/Sdk/platform-tools/adb shell am force-stop ai.ciris.mobile.debug

# Install to device
~/Android/Sdk/platform-tools/adb install -r client/androidApp/build/outputs/apk/debug/androidApp-debug.apk

# Launch the app
~/Android/Sdk/platform-tools/adb shell am start -n ai.ciris.mobile.debug/ai.ciris.mobile.MainActivity
```

### Desktop UI Test Mode

The desktop app includes an embedded HTTP server for programmatic UI testing:

```bash
# Via unified entry point (starts server + desktop with test mode)
export CIRIS_TEST_MODE=true
ciris-agent

# Via Gradle (development - desktop only, connects to existing server)
export CIRIS_TEST_MODE=true
cd client && ./gradlew :desktopApp:run

# Build development JAR first (if needed)
cd client && ./gradlew :desktopApp:packageUberJarForCurrentOS

# Custom test server port
export CIRIS_TEST_PORT=9000
```

**Test Server Endpoints (`http://localhost:8091`):**
- `GET /health` - Health check
- `GET /screen` - Current screen name
- `GET /tree` - Full UI element tree with positions
- `POST /click` - Click element: `{"testTag": "btn_login"}`
- `POST /input` - Input text: `{"testTag": "input_user", "text": "admin"}`
- `POST /wait` - Wait for element: `{"testTag": "btn_send", "timeoutMs": 5000}`

**Full documentation:** `client/desktopApp/src/main/kotlin/ai/ciris/desktop/testing/README.md`

## Development Workflow

### Grace - Your Development Companion

```bash
# Daily workflow
python -m tools.grace morning          # Start day
python -m tools.grace status           # Check health
python -m tools.grace precommit        # Before commits
python -m tools.grace night            # End day

# CI monitoring (WAIT 10 MINUTES between checks!)
python -m tools.grace_shepherd status  # Check CI
python -m tools.grace_shepherd wait    # Monitor CI
```

### Testing

```bash
# Docker-based testing (preferred)
python -m tools.test_tool test tests/
python -m tools.test_tool status
python -m tools.test_tool results

# Direct pytest (ALWAYS use -n 16 for parallel execution with 5+ minute timeout)
pytest -n 16 tests/ --timeout=300

# Coverage analysis
python -m tools.quality_analyzer       # Find gaps

# SonarCloud quality analysis
python -m tools.analysis.sonar quality-gate  # PR + main quality gate status (IMPORTANT!)
python -m tools.analysis.sonar status        # Main branch status only
python -m tools.analysis.sonar_tool status   # Alternative main branch status
```

### QA Runner - API Test Suite

The CIRIS QA Runner provides comprehensive API testing with automatic server lifecycle management:

```bash
# Run all tests (default) - QA runner manages server lifecycle
python -m tools.qa_runner                # Run all test modules

# Quick module testing
python -m tools.qa_runner auth          # Authentication tests
python -m tools.qa_runner agent         # Agent interaction tests
python -m tools.qa_runner memory        # Memory system tests
python -m tools.qa_runner telemetry     # Telemetry & metrics tests
python -m tools.qa_runner system        # System management tests
python -m tools.qa_runner audit         # Audit trail tests
python -m tools.qa_runner tools         # Tool integration tests
python -m tools.qa_runner guidance      # Wise Authority guidance tests
python -m tools.qa_runner handlers      # Message handler tests
python -m tools.qa_runner filters       # Adaptive filtering tests (36 tests)
python -m tools.qa_runner sdk           # SDK compatibility tests
python -m tools.qa_runner streaming     # H3ERE pipeline streaming tests

# Comprehensive test suites
python -m tools.qa_runner extended_api  # Extended API coverage (24 tests)
python -m tools.qa_runner api_full      # Complete API test suite (24 tests)

# Full verbose output for debugging
python -m tools.qa_runner <module> --verbose

# Multi-backend testing (sequential by default)
python -m tools.qa_runner auth --database-backends sqlite postgres

# Parallel backend testing (run SQLite and PostgreSQL simultaneously)
python -m tools.qa_runner auth --database-backends sqlite postgres --parallel-backends
```

**QA Runner Features:**
- 🤖 **Automatic Lifecycle Management** - Starts/stops API server automatically
- 🔑 **Smart Token Management** - Auto re-authentication after logout/refresh tests
- ⚡ **Fast Execution** - Most modules complete quickly
- 🧪 **Comprehensive Coverage** - Authentication, API endpoints, streaming, filtering
- 🔍 **Detailed Reporting** - Success rates, duration, failure analysis
- 🚀 **Production Ready** - Validates all critical system functionality
- 🔄 **Multi-Backend Support** - Test against SQLite and PostgreSQL (sequential or parallel)
- 📂 **Local-Tee for Live Lens Traces** - When `--live-lens` is active, every batch the agent ships to lens is also written to `/tmp/qa-runner-lens-traces-<UTC-iso>/` automatically. Auto-enabled by the QA runner; default-off otherwise via `CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR`. **Useful for troubleshooting any agent issue surfaced by a sweep** — defer-when-shouldn't, fabrication, register break, conscience-scalar weirdness — the answer lives in those batch JSON files (full reasoning event stream, every `LLM_CALL`, every conscience signal, every CIRISVerify attestation field). See `tools/qa_runner/CLAUDE.md` § "Live-Lens Trace Capture (Local Tee)" for debug recipes.

**IMPORTANT - Server Lifecycle:**
- QA runner automatically starts and stops the API server
- DO NOT manually start the server before running QA tests
- If you have a server already running, kill it first: `pkill -f "python main.py --adapter api"`
- Use `--no-auto-start` only if you need to debug with an existing server

### Testing API Locally

```bash
# 1. Start API server with mock LLM
python main.py --adapter api --mock-llm --port 8000

# 2. Complete setup wizard (first run) - creates admin user with your chosen password
# Or for QA testing, use: python -m tools.qa_runner (auto-creates admin/qa_test_password_12345)

# 3. Get auth token (use the password you set during setup)
TOKEN=$(curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"YOUR_PASSWORD_FROM_SETUP"}' \
  2>/dev/null | python -c "import json,sys; print(json.load(sys.stdin)['access_token'])")

# 3. Check telemetry (should show 35/35 services when fully working)
curl -X GET http://localhost:8000/v1/telemetry/unified \
  -H "Authorization: Bearer $TOKEN" 2>/dev/null | \
  python -c "import json,sys; d=json.load(sys.stdin); print(f'{d[\"services_online\"]}/{d[\"services_total\"]} services healthy')"

# 4. List unhealthy services
curl -X GET http://localhost:8000/v1/telemetry/unified \
  -H "Authorization: Bearer $TOKEN" 2>/dev/null | \
  python -c "import json,sys; d=json.load(sys.stdin); print('Unhealthy:', [k for k,v in d['services'].items() if not v['healthy']])"

# 5. Interactive agent test
curl -X POST http://localhost:8000/v1/agent/interact \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello, how are you?"}' 2>/dev/null | python -m json.tool
```

### Version Management

```bash
# ALWAYS bump version after significant changes
python tools/dev/bump_version.py patch     # Bug fixes
python tools/dev/bump_version.py minor     # New features
python tools/dev/bump_version.py major     # Breaking changes
```

## Live LLM model matrix (production + QA)

The agent is exercised against three providers in production and live QA. **Confirm the exact model identifier against the provider's catalog before changing — model names are case-sensitive and a typo lands as `404 model_not_available` which now fails fast (categorized non-retryable in 2.7.4) but still blocks the affected provider until corrected.**

| Provider | Endpoint | Model identifier (CASE-SENSITIVE) | Notes |
|---|---|---|---|
| **Together AI** | `https://api.together.xyz/v1` | `google/gemma-4-31B-it` | **Capital `B`, lowercase `it`.** Production datum primary. NOT `gemma-3` (deprecated), NOT `gemma-4-31b-it` (wrong case). Verify with `curl -H "Authorization: Bearer $KEY" https://api.together.xyz/v1/models \| jq '.data[].id \| select(test("gemma"))'`. |
| **OpenRouter** | `https://openrouter.ai/api/v1` | `meta-llama/llama-4-scout` | Scout for the QA matrix (live as of 2026-04-28). Routed to DeepInfra under the hood. Key at `~/.openrouter_key`; usage gate is $100/week ($0.0000018/call observed). |
| **Together AI** | `https://api.together.xyz/v1` | `meta-llama/Llama-4-Scout-17B-16E-Instruct` | Scout exists in Together's catalog but is **NOT serverless** — every Llama-4 variant requires a paid dedicated endpoint. Don't use Together for scout until that changes. |
| **Groq** | `https://api.groq.com/openai/v1` | `meta-llama/llama-4-scout-17b-16e-instruct` | Production datum backup, all lowercase. **8192 max_tokens cap** — agent must not pass higher (this was the 2.7.4 incident). The live key was 401-invalid as of 2026-04-28; refresh `~/.groq_key` before relying on it. |
| **DeepInfra** | `https://api.deepinfra.com/v1/openai` | `Qwen/Qwen3.6-35B-A3B` | Used as the canonical PDMA v3.2 / locale eval test bed. **Always pass `extra_body={"chat_template_kwargs": {"enable_thinking": false}}`** or thinking-mode burns through max_tokens before producing visible output (see `llm_service/service.py:1426`). |

**API keys**: `~/.together_key`, `~/.groq_key`, `~/.deepinfra_key`. Each holds the raw bearer token, no quotes, no trailing newline.

**v1_sensitive corpus**: `/home/emoore/bounce-test/model_eval_questions/v1_sensitive.json` — 6 attractor-bait questions (Theology, Politics, AI Ethics, History/Tiananmen, Epistemology, Mental Health) with translations across all 29 supported locales. The History question is the canonical framework-override test.

**Live model_eval invocation pattern**:
```bash
CIRIS_LLM_CAPTURE_HANDLER=EthicalPDMAEvaluator \
CIRIS_LLM_CAPTURE_FILE=/tmp/pdma-<provider>.jsonl \
python3 -u -m tools.qa_runner model_eval \
    --live \
    --live-key-file ~/.<provider>_key \
    --live-model "<exact-name-from-table-above>" \
    --live-base-url "<endpoint-from-table-above>" \
    --live-provider openai \
    --model-eval-questions-file /home/emoore/bounce-test/model_eval_questions/v1_sensitive.json \
    --model-eval-languages en \
    --model-eval-concurrency 1 \
    --verbose
```

**Pre-flight checklist before live eval**:
1. **Stash any persistent `.env`** at `/home/emoore/ciris/.env` if it has `CIRIS_CONFIGURED="true"` — the qa_runner needs first-run setup. Restore via `trap` on exit.
2. **Wipe `/home/emoore/ciris/data/ciris_engine.db*`** so each run starts with a fresh user/auth state.
3. **Verify the model name with the provider's catalog** before launching the matrix — three hours of 600s qa_runner timeouts on a typo'd name is real production cost.
4. **Use `python3 -u`** in benchmark scripts so `print()` output streams live through `tee` (CI cancellation discards stdout buffer otherwise — see `.github/workflows/memory-benchmark.yml` PYTHONUNBUFFERED=1 fix).

## Critical URLs & Paths

### Production
- **Main**: https://agents.ciris.ai
- **API**: https://agents.ciris.ai/api/datum/v1/
- **OAuth**: https://agents.ciris.ai/v1/auth/oauth/{agent_id}/{provider}/callback

### Production Server Access
- **SSH**: `ssh -i ~/.ssh/ciris_deploy root@108.61.119.117`
- **Agent Locations**: `/opt/ciris/agents/`
- **Log Files**: Logs are always written to files inside containers at `/app/logs/`
  - `/app/logs/incidents_latest.log` - Current incidents (ALWAYS CHECK THIS FIRST)
  - `/app/logs/application.log` - General application logs
  - `/app/logs/ciris_YYYY-MM-DD.log` - Daily log files
- **Common Commands**:
  ```bash
  # Find agent containers
  cd /opt/ciris/agents && ls -la

  # Check specific agent status
  cd /opt/ciris/agents/echo-speculative-4fc6ru
  docker-compose ps

  # View agent logs FROM FILES (not docker logs)
  docker exec echo-speculative-4fc6ru tail -100 /app/logs/incidents_latest.log
  docker exec echo-speculative-4fc6ru tail -100 /app/logs/application.log

  # Check for consolidation activity
  docker exec echo-speculative-4fc6ru grep -i "consolidat" /app/logs/incidents_latest.log | tail -20

  # Check shutdown status
  docker exec echo-speculative-4fc6ru grep -i "shutdown" /app/logs/incidents_latest.log | tail -20

  # Execute commands in container
  docker-compose exec echo-speculative-4fc6ru python -c "print('hello')"

  # Check database files
  docker-compose exec echo-speculative-4fc6ru find /app -name '*.db'
  ```

**Service Tokens** (for API access):
- Use format: `Authorization: Bearer service:TOKEN_VALUE`
- Manager tokens found in agent deployment configs
- Example: `curl -H "Authorization: Bearer service:abc123..." https://agents.ciris.ai/api/agent-id/v1/system/health`

### Repository Structure
```
CIRISAgent/
├── ciris_engine/         # Core engine
│   ├── logic/           # Business logic
│   ├── schemas/         # Pydantic models
│   └── protocols/       # Service interfaces
├── FSD/                 # Functional specifications
├── tools/               # Development tools
└── tests/               # Test suite
```

### Separate Repositories (LIABILITY ISOLATION)
```
CIRISMedical/            # PRIVATE - Medical implementation
└── NO medical code in main repo
```

## Debugging Best Practices

### The Golden Rule
**ALWAYS check incidents_latest.log FIRST:**
```bash
docker exec container tail -n 100 /app/logs/incidents_latest.log
```

### Debug Workflow
1. Check incidents log
2. Use debug_tools.py for traces
3. Verify with audit trail
4. Test incrementally

### Reasoning-Stream Forensics (live-lens runs)

When a QA sweep against the live lens produces unexpected behavior — defer that shouldn't have fired, conscience scalar that looks off, a primer rule that didn't hold, fabrication or register-break that the conscience layer should have caught — the full reasoning event stream is sitting in `/tmp/qa-runner-lens-traces-<UTC-iso>/`. The QA runner auto-tees every batch the agent ships to lens into that dir.

```bash
# Find the most recent live-lens run dump
ls -lt /tmp/qa-runner-lens-traces-*/ | head -3

# Find the trace for a specific thought_id
grep -l "th_abc123" /tmp/qa-runner-lens-traces-*/accord-batch-*.json

# Why did the agent defer? Decode the action_result
python3 -c "
import json, glob
for f in sorted(glob.glob('/tmp/qa-runner-lens-traces-*/accord-batch-*.json')):
    for ev in json.load(open(f))['events']:
        if ev.get('action_executed') == 'defer':
            print(ev['thought_id'], ev.get('execution_reason', ''))
"
```

Default-off in production (env var unset). The QA runner is the only caller that auto-enables. See `tools/qa_runner/CLAUDE.md` § "Live-Lens Trace Capture (Local Tee)" for full recipes.

### Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| Dict[str, Any] error | Schema already exists - search for it |
| CI failing | Wait for CI to complete, check SonarCloud |
| OAuth not working | Check callback URL format |
| Service not found | Check ServiceRegistry capabilities |
| WA deferral failing | Check WiseBus broadcast logic |
| Live-lens sweep behavior unexplained | Inspect `/tmp/qa-runner-lens-traces-<ts>/accord-batch-*.json` — full reasoning stream, every LLM_CALL, every conscience scalar |

## Command Timeouts

Long-running commands may need timeout parameters for CI operations and comprehensive test runs.

## Important Reminders

1. **OAuth Format**: `/v1/auth/oauth/{agent_id}/{provider}/callback`
2. **Default Auth**: Set via setup wizard (QA runner uses admin/qa_test_password_12345)
3. **Service Count**: 22 core services (complete, don't add more)
4. **No Service Creates Services**: Only ServiceInitializer
5. **Version After Changes**: Always bump version
6. **Medical Prohibition**: Zero medical code in main repo
7. **Check Existing Schemas**: They already exist
8. **NEVER PUSH DIRECTLY TO MAIN**: Always create a branch, bump version, NO merge to main without explicit permission

## Quality Standards

- **Type Safety**: Minimal Dict[str, Any] usage
- **Test Coverage**: Target 80%
- **Response Time**: <1s API responses
- **Memory**: 4GB RAM maximum
- **Security**: Ed25519 signatures throughout

## Getting Help

- **Issues**: https://github.com/CIRISAI/CIRISAgent/issues
- **CI Status**: `python -m tools.grace_shepherd status`
- **Coverage**: `python -m tools.quality_analyzer`
- **Incidents**: Check container logs first

---

*Remember: The schema you're about to create already exists. Search for it first.*
