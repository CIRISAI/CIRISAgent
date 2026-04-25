# Changelog

All notable changes to CIRIS Agent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.7.1] - 2026-04-25

### Fixed

- **CIRISLens reporting null `verify_attestation` fields (production)** — `docker/agent/Dockerfile` was installing `libtss2-esys-3.0.2-0t64` and `libtss2-tcti-device0t64` but missing `libtss2-tctildr0t64`, the TCTI loader the FFI calls at runtime. CIRISVerify failed to initialize in production with `Failed to load library: libtss2-tctildr.so.0`, every batch context fell into the silent fallback, and Lens received nulls. Added the missing package and a `python3 -c "ctypes.CDLL('libtss2-tctildr.so.0')"` smoke check inside the same RUN so a missing TPM2 lib fails the build instead of shipping silently.
- **CIRISLens reporting null `verify_attestation` fields (QA)** — separate root cause from production. `AuthenticationService.start()` (a) skipped attestation entirely when `CIRIS_IMPORT_MODE` or `CIRIS_MOCK_LLM` was set — a path that should never have existed; ciris_verify is a hard runtime dependency — and (b) launched `run_startup_attestation` as fire-and-forget `asyncio.create_task(...)`, racing the first `batch_context` build which then hit a broad `except Exception` fallback that emitted nulls. Replaced with a captured `self._attestation_task` plus an `await_attestation_ready()` gate that any consumer requiring the cache must call first; failures re-raise loudly. `prefetch_batch_context()` no longer has a fallback path — missing or failed attestation is fatal at thought-context build.
- **Google Play 16 KB page-size rejection (partial)** — bumped `com.microsoft.onnxruntime:onnxruntime-android` from 1.17.0 to 1.21.0. ONNX Runtime added 16 KB-aligned `.so` files in 1.20.0; 1.21.0 is the current stable. `libonnxruntime.so` and `libonnxruntime4j_jni.so` are now 16 KB-aligned in the AAB. **Still pending: `libllama_server.so` (Android) and `libciris_verify_ffi.so` (iOS) need the same 16 KB rebuild — see Known Issues below.**
- **SonarCloud blockers in `ciris_adapters/__init__.py`** — `__all__` declared three module names that have never existed (`geo_wisdom`, `weather_wisdom`, `sensor_wisdom`); removed them and rewrote the docstring to reflect that adapters are discovered via `manifest.json` at runtime, not enumerated here.

### Changed

- **Test infrastructure consolidated around centralized fixtures.** The strict attestation gate exposed a wide set of tests that were either constructing throwaway runtime mocks inline (`mock_runtime = MagicMock()`) or relying on a permissive graceful-degradation path that no longer exists. The fix touched the centralized fixtures rather than chasing every test:
  - `tests.fixtures.mocks.MockRuntime` now bakes in the `ciris_verify` adapter, `adapter_manager`, `service_registry`, and `bus_manager` so tests that need custom adapters or services seed the existing mutable dicts rather than rebuilding the runtime from scratch.
  - `tests.fixtures.mocks.MockServiceRegistry` now carries an attestation-aware `get_authentication()` returning a fully-passing `AttestationResult` via `await_attestation_ready()` / `get_cached_attestation()`.
  - All three `mock_runtime` fixtures (`tests/conftest.py`, `tests/fixtures/system_snapshot_fixtures.py`, `tests/ciris_engine/logic/context/conftest.py`) now delegate to `MockRuntime` so the strict gate sees a consistent shape regardless of fixture-resolution order.
  - ~75 tests across 9 files updated to use the centralized fixtures instead of inline `Mock()` runtimes — most via mechanical script edits, a few hand-rewritten because they were testing real SUT type-safety branches the strict gate would otherwise mask.

### Known Issues (Carry-Over)

- **iOS bundled `libciris_verify_ffi.so` still 4 KB-aligned.** `client/iosApp/Resources/app/ciris_adapters/ciris_verify/ffi_bindings/libciris_verify_ffi.so` reports `LOAD p_align=0x1000`. Apple Silicon iOS uses 16 KB pages; the iOS team should rebuild this binary with `-Wl,-z,max-page-size=16384` (or the equivalent flag for whatever toolchain produced the original). Linking with the existing CIRISVerify Rust source — same target triple, same exports — is the expected path; no Python/Kotlin changes needed.
- **Android bundled `libllama_server.so` still 4 KB-aligned.** Local-LLM (llama.cpp + Gemma 4) feature in the AAB is gated on this. Rebuild with the same linker flag against the llama.cpp source that produced the 2.6.0 binary, then drop into `client/androidApp/src/main/jniLibs/{arm64-v8a,x86_64}/`.

## [2.7.0] - 2026-04-23

### Added

- **Full 29-language pipeline localization** - the complete ethical reasoning chain (DMAs, consciences, handler follow-ups, ACCORD/guides, DSASPDMA taxonomy + glossaries) now operates in the user's preferred language rather than English-with-translation. Language is resolved per thought from `context.system_snapshot.user_profiles[0].preferred_language`, with a per-language loader cache so no shared global state is mutated. Covers ~95% of the world population by language need, not market size.
- **LLM bus FIFO + dual-replica load balancing** - the LLM bus now maintains a per-service FIFO concurrency gate and tracks in-flight requests for `LEAST_LOADED` replica selection. Set `CIRIS_LLM_REPLICAS=2` to run dual-registered providers; the bus prefers the least-loaded sibling before falling through to the secondary priority.
- **Round-1 grant baseline workflow** - reproducible measurement pipeline for service taxonomy + endpoint inventory snapshots (`GRANT_EVIDENCE_REFRESH.md`).

### Changed

- **Entropy conscience recalibrated** so it no longer blocks substantive multilingual content for non-English languages (previously fired on normal Amharic/Arabic/Chinese responses due to English-biased thresholds).
- **ASPDMA deferral guidance tightened** - `action_instruction_generator.py` now distinguishes personal medical/legal/financial ADVICE (defer) from EDUCATIONAL discussion of those concepts (answer directly). Also explicitly disallows pre-deferral on historically or politically sensitive questions; the conscience layer already handles propaganda guards.
- **DEFER notification fires on any channel**, not just `api_*`, so synchronous `interact()` callers get a notification instead of hanging on an unanswered SPEAK until timeout. User-facing text intentionally omits the deferral reason - that stays for WA review only.
- **Handler credit-attach warnings downgraded and deduplicated** - `[CREDIT_ATTACH]` missing-provider / missing-resource-monitor messages no longer fire at CRITICAL per message. They now fire once per reason per server lifetime at WARNING, removing the 1000-line noise from mock-mode benchmark runs.
- **Apple native auth token verification hardened** - full cryptographic verification via Apple JWKS (RS256 + audience + issuer + required claims) with JWKS caching and graceful timeout fallback to cached keys.

### Fixed

- **Trace signing canonicalization** - signed payloads no longer include `trace_schema_version` (that field stays in the envelope), eliminating verification mismatches between the agent's signed digest and CIRISLens's canonical JSON reconstruction.
- **Benchmark subprocess reaping** - `tools/memory_benchmark.py` and `tools/introspect_memory.py` now always terminate the child agent process on any early-exit path, with fallback to SIGKILL after grace period.
- **CI memory benchmark unblocked** - workflow now installs the CIRISVerify runtime deps (`libtss2-esys0` + `libtss2-tctildr0` + `libtss2-mu0`, with a fallback chain for Ubuntu 24.04 t64 renames) and pins `CIRIS_DISABLE_TASK_APPEND=1` + `CIRIS_API_RATE_LIMIT_PER_MINUTE=600` at the workflow env level so the 100/1000-message benchmarks can complete on `ubuntu-latest`. Once the libtss2-* deps resolve at dlopen time, CIRISVerify's Rust factory degrades cleanly to software-only signing if no TPM is present; the deploy/CI environment just needs the libs installed. `scripts/install.sh` updated to match.
- **Streaming verification schema allowlist** synced with the current `IDMAResult` schema - recent fragility-model fields (`collapse_margin`, `collapse_rate`, `rho_mean`, etc.) are now accepted by the H3ERE reasoning-event stream test.
- **Test harness env-isolation** - autouse conftest fixture pins `CIRIS_PREFERRED_LANGUAGE=en` and clears `CIRIS_LLM_REPLICAS` via monkeypatch for every test, so raw `os.environ[...]` mutations in any test are rolled back at teardown and can't leak between xdist workers.
- **Pytest collection baseline parsing** hardened against malformed or partial baselines.
- **Wallet audit log sanitization** (SonarCloud S5145) - user-supplied addresses are validated as `0x` + 40 hex before being logged; non-conforming values render as `<invalid-address>` to prevent CR/LF log injection.

## [2.6.9] - 2026-04-22

### Fixed

- **Desktop Startup Polling** - CLI now waits on `/v1/system/startup-status` before launching the desktop app
  - Uses `api_status == "server_ready"` so first-run onboarding does not false-time out
  - Reports startup phase and `services_online/services_total` progress while booting
  - Fails fast if the backend exits during polling instead of waiting for the full timeout

## [2.6.8] - 2026-04-22

### Fixed

- **Desktop Startup Race Condition** - CLI waits for backend health before opening the desktop app
  - Prevents the desktop app from trying to start a second backend on the same port
  - Moves the health-wait path inside `try/finally` so Ctrl+C cleans up the backend subprocess

## [2.6.7] - 2026-04-22

### Fixed

- **iOS SQLite Freeze (Root Cause)** - CIRISVerify v1.6.4 uses system SQLite on iOS
  - Bundled rusqlite was duplicating sqlite3 symbols, causing Apple's libRPAC assertions
  - Python-side: `_IOSConnectionProxy` + `_IOSCursorProxy` prevent cross-thread `sqlite3_finalize()`
  - Rust-side: link against iOS SDK SQLite instead of compiling from source

- **Mobile LLM Adapter Lifecycle** - `run_lifecycle()` now uses `finally` for cleanup
  - Previously leaked background tasks on non-CancelledError exceptions

## [2.6.6] - 2026-04-22

### Fixed

- **iOS SQLite Cursor Proxy** - Wrap cursors in addition to connections
  - `sqlite3_finalize()` on GC'd cursors was triggering the same libRPAC assertion

## [2.6.5] - 2026-04-22

### Fixed

- **iOS SQLite Connection Proxy** - `_IOSConnectionProxy` suppresses `close()`/`__del__()`
  - Prevents Python GC from calling `sqlite3_finalize()` on wrong thread
  - Thread-local connection cache ensures thread ownership for Apple's tracking

- **iOS App Crash on Launch** - Missing `CADisableMinimumFrameDurationOnPhone` in Info.plist
  - Compose Multiplatform throws `IllegalStateException` on ProMotion iPhones without it
  - Added `NSSetUncaughtExceptionHandler` to catch Kotlin/Native exceptions on dispatch queues

- **iOS Install Failure** - Static KMP framework embedded in Frameworks/
  - `project.yml` pre/postCompile scripts detect static archives and strip them
  - Pre-build script syncs Resources.zip from repo source (prevents stale zip)

### Changed

- **Icons** - Removed `compose.materialIconsExtended` (113MB → 93KB inline vectors)
  - `CIRISMaterialIcons.kt`: 50 inline ImageVector definitions from Material Design SVGs
  - iOS framework: 392MB → 279MB (debug), release 161MB
  - Resources.zip: 144MB → 36MB (removed bundled desktop JAR + gui_static)
  - Gradle JVM heap: 4GB → 8GB (release LTO needs more without tree-shaking)

- **iOS Keyboard** - Enabled `imePadding()` (was no-op), added to SetupScreen root

## [2.6.4] - 2026-04-22

### Changed

- Bump build numbers (iOS 250, Android 95)
- `rebuild_and_deploy.sh`: `--device` flag, preflight checks, `desktop_app` exclusion
- `bump_version.py`: fix `mobile/` → `client/` paths

## [2.6.3] - 2026-04-21

### Added

- **Secrets Encryption QA Module** - New `secrets_encryption` test module for v1.6.0 features
  - Tests CIRISVerify status, key storage mode, encryption capabilities
  - Direct encryption module validation
  - Telemetry integration checks

### Fixed

- **iOS SQLite Thread Safety** - Thread-local connection cache for iOS
  - Prevents Apple's SQLiteDatabaseTracking assertion failures
  - Each thread gets its own persistent connection per database
  - Automatic connection validation and recovery

- **Encryption Version Mismatch Detection** - Clear error for v1.6.0 secrets on v1.5.x binary
  - RuntimeError with upgrade instructions instead of cryptic decryption failure
  - Checks `encryption_key_ref` field to detect hardware-encrypted secrets

- **Mypy Type Errors** - Fixed strict type checking issues
  - Type annotation for cached SQLite connection
  - KeyStorageMode validation cast in SecretsStore

## [2.6.2] - 2026-04-21

### Security

- **Hardware-Backed Secret Encryption** - Master key migration to TPM/Keystore/SecureEnclave
  - CIRISVerify v1.6.0 encryption API (AES-256-GCM)
  - Key storage mode config: `auto`/`hardware`/`software`
  - Atomic migration with canary verification

- **Critical Fixes (C1-C3)**
  - Sanitize exception messages in secrets audit log
  - Fix shell injection in smart-commit-hook.py (`shell=False`)
  - Fix path traversal with `validate_path_safety()`

- **High Fixes (H1-H11)**
  - SSRF protection for document download (URL validation, DNS rebinding)
  - Service token revocation endpoint with database persistence
  - WAL/SHM file permissions (0600) with TOCTOU mitigation
  - Remove debug logging of exception objects
  - Add `--` separator to git commands

- **Medium Fixes (M1-M13)**
  - Ed25519 signature verification for ACCORD manifest
  - Word-boundary regex for capability matching
  - Expand PROHIBITED_CAPABILITIES with 500+ stemming variants
  - Remove overly broad 'compliance' from LEGAL_CAPABILITIES

- **Low Fixes (L1-L4)**
  - User-agent sanitization
  - Hardware mode config fixes

### Added

- **WASM Icon System** - Replace Unicode emojis with SVG-based ImageVectors for Skia
  - `emojiToIcon()` / `emojiBusColor()` mapping functions
  - Icons render correctly in SSE bubbles, timeline bar, skill import dialog
  - CIRISMaterialIcons with stroke color on 225 path() calls

- **WASM Static File Serving** - Support `wasm_static/` directory for HA addon
  - Multiple lookup paths for production/development
  - Root `/health` endpoint for diagnostics

- **HA Addon Mode Detection** - Auto-detect HA ingress context in WASM
  - Checks URL path, query params, referrer for HA patterns

### Fixed

- **SonarCloud Issues**
  - Duplicate key in BLOCKED_HOSTS set
  - Union type to modern syntax (`KeyStorageMode | str`)
  - Redundant inner try/except in guide loading

- **Rate Limiter Logging** - 429 responses now logged with client ID and retry_after

- **Mobile Adapter Loading** - Increased timeout to 60s (was 30s)

- **Polling Reduction** - Cache-Control headers on setup/status (5s) and adapter-list (10s)

## [2.6.1] - 2026-04-20

### Fixed

- **HA Addon .env Path Discovery** - Add `CIRIS_CONFIG_DIR`/`CIRIS_HOME` to early path search

## [2.6.0] - 2026-04-19

### Added

- **Cell Visualization Enhancements** - Grounded ρ (service-failure clustering), σ from signed audit SQLite, non-LLM BusArc panels wired to telemetry
- **Desktop Viz QA Module** - Programmatic smoke test for cell visualization (`tools/qa_runner/modules/desktop_viz.py`)
- **KMP 2.x Migration Scripts** - Validation and migration scripts for Kotlin 2.0.21 upgrade (`mobile/scripts/`)

### Changed

- **Directory Restructure** - Removed legacy `android/` and `ios/` directories; wheels relocated to `mobile/androidApp/wheels/`
- **Deferral Ripple Animation** - Eased rotation pause timing for smoother UX

### Fixed

- **HA Ingress Identity Persistence** - Ingress users now stored under `provider:external_id` key with OAuth identity linked to WA for cross-restart persistence
- **Setup Ingress IP Validation** - Added trusted IP check (172.30.32.2) to setup ingress fallback, rejecting spoofed headers
- **HA Network Trust Scope** - Restricted trust to supervisor IP only (removed overly-permissive /23 range)
- **First-User Admin Flag** - Removed in-memory flag that could reset on restart; now uses authoritative DB check
- **Setup Identity Fragmentation** - Setup now uses ingress user's actual identity instead of creating separate `ha_admin` user

### Security

- **Ingress Auth Hardening** - Five P1 security fixes addressing privilege escalation, identity binding, and IP validation vulnerabilities

## [2.5.0] - 2026-04-15

### Added

- **Local LLM Server Discovery** - Backend endpoint to discover local inference servers (Ollama, vLLM, llama.cpp, LM Studio) via hostname probing
- **Settings Screen LLM Discovery UI** - Mobile/desktop UI for discovering and selecting local LLM servers
- **System Health Warnings** - Health endpoint now returns actionable warnings for missing LLM provider and adapters needing re-authentication
- **Graceful No-LLM Startup** - Agent can start without LLM provider when CIRIS services disabled, displaying warning instead of failing

### Fixed

- **Windows Console Crash** - Fixed `AttributeError` on non-Windows platforms when `ctypes.windll` doesn't exist
- **Persisted LLM Provider Loading** - Fixed LLM service not being set when loading from persisted runtime providers with CIRIS services disabled
- **Local Inference Timeout** - Increased timeout for local inference servers from 30s to 120s to accommodate slower on-device models
- **Localization Pipeline** - DMA prompts now load fresh each request to respect runtime language changes
- **User Preferences Enrichment** - User enrichment now merges `preferences/{user_id}` node for complete profile data
- **Fallback Admin Security** - Fallback admin only created with `CIRIS_TESTING_MODE=true`

### Changed

- **DMA Type Safety** - All DMAs now use proper `DMAPromptLoader` and `PromptCollection` return types instead of `Any`
- **Test Infrastructure** - Global `CIRIS_TESTING_MODE` set in `tests/conftest.py` for all test authentication

## [2.4.3] - 2026-04-13

### Added

- **Skill Studio UI** - Visual skill builder with validation and full 29-language localization
- **Adapter Re-Auth Tracking** - Track adapter re-authentication events with structured telemetry
- **Location Settings Persistence** - User location preferences now persist across restarts

### Fixed

- **HA Token Persistence** - Fixed Home Assistant token being null after restart
- **SIGSEGV Crash** - Fixed crash in `ciris_verify_generate_key` by adding missing FFI argtypes
- **HA Adapter Hardening** - Improved resilience for multi-occurrence deployments
- **SonarCloud Issues** - Fixed cognitive complexity, duplicated literals, path security, and log injection issues

### Security

- **Dynamic Admin Password** - Admin password now dynamically generated at startup instead of hardcoded
- **Path Construction Security** - Refactored skill_import to avoid constructing paths from user input
- **Log Injection Prevention** - Removed user-controlled data from log messages

## [2.4.2] - 2026-04-10

### Added

- **Context Enrichment Cache Auto-Population** - Enrichment cache now auto-populates at startup and when adapters load dynamically, eliminating first-thought latency
- **Unit Tests for Enrichment Cache** - Added comprehensive tests for startup cache population and adapter cache refresh

### Fixed

- **Context Enrichment Route** - Fixed 404 on `/adapters/context-enrichment` endpoint by moving it before wildcard route

## [2.4.1] - 2026-04-09

### Added

- **WA Key Auto-Rotation** - User Wise Authority keys now auto-rotate with unit test coverage
- **WA Signing via CIRISVerify** - Named key signing capability through CIRISVerify integration
- **Play Integrity Reporting** - CIRISVerify v1.5.3 with Play Integrity failure reporting

### Fixed

- **Wallet Badge Display** - Fixed trust badge and wallet race conditions at startup
- **Attestation Lights** - Parse CIRISVerify v1.5.x unified attestation format correctly
- **Domain Filtering** - Fixed domain filtering and deterministic trace IDs

## [2.4.0] - 2026-04-07

### Added

- **Bengali Localization** - Full Bengali (bn) language support across all localization files and backend validation
- **Language Coverage Analysis** - New `localization/CLAUDE.md` with expansion roadmap and coverage analysis
- **Localization Manifest** - Enhanced `localization/manifest.json` with per-language metadata (speaker counts, regions, script info)

### Fixed

- **Observer Login Scope** - Changed observer login blocking to only apply on mobile platforms (Android/iOS), allowing OBSERVER OAuth logins on standalone API servers where read-only access is valid
- **HA Adapter Wizard** - Fixed 401 error during first-time Home Assistant adapter setup by checking session auth before requiring token

### Changed

- **Build-Time Secrets Documentation** - Added guidance in CLAUDE.md about `# type: ignore[import-not-found]` comments for generated files

## [2.3.7] - 2026-04-06

### Fixed

- **OAuth Founding Partnership** - Consent node for OAuth users now keyed by OAuth external ID (e.g., `google:123456`) instead of WA ID, matching ConsentService lookup pattern
- **Logout Stuck Loop** - Fixed logout getting stuck in infinite loop with resume overlay timeout
- **iOS Restart** - Fixed iOS restart when Python runtime is dead; graceful server shutdown on iOS restart signal
- **Mobile Factory Reset** - Wait for server restart after mobile factory reset completes
- **Mobile Env Path** - Fixed `get_env_file_path()` returning None on mobile platforms
- **First-Run Detection** - Improved first-run detection logging on Login screen
- **Wallet Attestation Retry** - Handle `AttestationInProgressError` in wallet key retry loop
- **Mypy Cleanup** - Removed unused `type:ignore[import-not-found]` from wallet providers

### Changed

- **Developer Docs** - Added force-stop before APK install instruction in CLAUDE.md

## [2.3.6] - 2026-04-06

### Added

- **Localized ACCORD for Action Selection** - ASPDMA and TSASPDMA now use single-language localized ACCORD text for clearer action guidance, while other DMAs continue using polyglot ACCORD for cross-cultural ethical depth
- **English Localized ACCORD** - Created `accord_1.2b_en.txt` for English language action selection
- **Self-Custody Messaging** - Updated all 16 language localization files with new self-custody key management strings (FSD-002)

### Fixed

- **Startup Animation** - Removed redundant StartupStatusPoller; startup lights now driven directly from Python console output parsing
- **Self-Custody Registration** - Agent now signs Portal's `registration_challenge` instead of self-constructed message, fixing signature verification failures
- **Language Preference Default** - Setup wizard now always saves `CIRIS_PREFERRED_LANGUAGE` to .env (defaults to "en" if not selected)
- **Mypy Strict Mode** - Fixed type annotations in wallet provider build secrets (`List[int]` parameters)
- **Test Stability** - Updated device auth tests to use proper hex registration challenges

## [2.3.4] - 2026-04-02

### Added

- **OpenClaw Skill Import** - Import OpenClaw SKILL.md files as CIRIS adapters
  - Parse and convert full skill definitions (metadata, requirements, instructions, install steps)
  - Security scanner with 8 attack categories (prompt injection, credential theft, backdoors, cryptominers, typosquatting, obfuscation, undeclared network, metadata inconsistency)
  - HyperCard-style skill builder with 6 card types (identity, tools, requires, instruct, behavior, install)
  - Preview and validate skills before import
  - Auto-load imported skills into runtime
- **Server Connection Manager** - New screen accessible via Local/Offline badge
  - View and manage local server state
  - Restart backend if crashed (desktop)
  - Connect to remote agents at custom URL:port
- **Skill Workshop Localization** - 135 skill_* keys translated to all 16 languages
- **Linux Demo Recording** - `record_demo_clips.py` now supports Linux with ffmpeg

### Fixed

- **Install Steps in ToolInfo** - Imported skills now include dependency installation guidance
- **Supporting File Paths** - Preserve directory structure (no more collisions from same-named files)
- **Builder Install Card** - User-authored install instructions carried through to ParsedSkill
- **Port Race Condition** - Increased startup delay from 3s to 6s to prevent desktop app connecting before server ready
- **Mypy Type Error** - Fixed `range` to `list[int]` conversion in scanner
- **ReDoS Vulnerability** - Replaced regex with string-based YAML frontmatter extraction in skill parser
- **Path Traversal Security** - Added pre-validation (null bytes, length limits) and portable temp directory handling
- **CI Test Stability** - Added shell-level timeout and pytest markers to prevent worker hangs
- **API Documentation** - Added `responses` parameter to skill builder routes for proper OpenAPI docs

## [2.3.3] - 2026-04-02

### Added

- **Ambient Signet Animation** - Login screen displays animated signet with subtle glow effect

### Fixed

- **FFI Library Loading** - Check pip package location first before system paths; prevents loading wrong-platform binaries
- **Cross-Platform FFI Safety** - Permanent fix to prevent loading .so on macOS or .dylib on Linux
- **Login Error Display** - Fixed error message visibility and signet/language selector overlap
- **Static Analysis** - Refactored `get_package_root()` to use `__file__` traversal instead of importing `ciris_engine`, eliminating SonarCloud circular dependency false positive
- **TSDB Test Parallel Safety** - Added `xdist_group` marker to prevent parallel execution conflicts when patching `get_db_connection`
- **Mypy Optional Deps** - Added cv2 and numpy to ignored imports in mypy.ini (optional dependencies)
- **Localization Sync** - Synced all 16 language files to Android assets and desktop resources
- **iOS Build** - Bumped to build 215, fixed stale release framework

## [2.3.2] - 2026-04-01

### Added

- **Cross-Platform Test Automation** - HTTP server (Desktop: Ktor CIO, iOS: POSIX sockets) on port 8091
- **Shared Test Logic** - Test handler models and state in `commonMain` for all KMP targets
- **Desktop Automation** - `/screenshot` endpoint (java.awt.Robot), `/mouse-click` for dropdowns
- **Testable UI Elements** - `testableClickable` on provider/model dropdowns and login buttons
- **Demo Recording** - SwiftCapture integration (`tools/record_demo_clips.py`)
- **Desktop E2E Test** - Wipe-to-setup test script (`tools/test_desktop_wipe_setup.sh`)
- **CIRIS Signet** - Login screen displays signet icon instead of plain "C" text
- **First-Run Welcome** - Localized welcome message for 16 languages
- **Desktop Restart API** - `postLocalShutdown()` for server restart after wipe

### Fixed

- **Factory Reset Keys** - Preserves signing keys (prevents CIRISVerify FFI crash on restart)
- **Founding Partnership** - Uses `consent/{wa_id}` matching ConsentService lookups
- **First Run Detection** - Checks `.env` contents for `CIRIS_CONFIGURED`, not just file existence
- **CIRISVerify FFI** - Platform-aware suffix ordering (.dylib before .so on macOS)
- **Config Path** - Standardized to `~/ciris/.env`, removed CWD-based path check
- **Stale Env Vars** - `CIRIS_CONFIGURED` cleared when `.env` is deleted
- **Language Rotation** - No longer triggers API sync or pipeline label recomposition
- **Env Var Prefix** - `CIRIS_` prefix supported by LLM service, main.py, service_initializer
- **Wizard Skip** - Select step accepts "skip" for optional steps (cameras)
- **Desktop Wipe** - Server restart via local-shutdown API, repo root data dir detection
- **Python Runtime** - Empty cognitive_state treated as healthy, not stuck
- **CIRIS_HOME Detection** - Multi-strategy path probing for Android/iOS (fixes settings persistence)
- **Message Dedup** - Duplicate user message deduplication window widened to 30 seconds
- **Location Parsing** - Fixed parsing order to match setup serialization (Country, Region, City)
- **Coordinate Parsing** - Added error handling for malformed latitude/longitude env values

### Known Issues

- **Wallet Paymaster** - ERC-4337 paymaster sends require deployed smart account; new users may see "account not deployed" errors until smart account factory integration is added (#656)

## [2.3.1] - 2026-03-30

### Added

- **Urdu Language Support** - 16th language with full pipeline localization
- **Desktop Scrollbars** - Visible scrollbars with platform-specific implementation
- **Location Services** - User location for weather and navigation adapters
- **Localization Sync Check** - Pre-commit hook to catch missing translations

### Changed

- **Language Selector** - Centered on login, shows "Interface + Agent" to clarify scope

### Fixed

- **Desktop Scroll** - Login, Startup, Telemetry screens scroll properly
- **Language Selector Click** - Fixed z-order on desktop
- **Wallet Attestation** - Correct attestation level display
- **Startup Language Rotation** - Stops when startup completes
- **Test Reliability** - Fixed flaky TSDB edge tests

## [2.3.0] - 2026-03-28

### Added

- **Full Pipeline Localization** - 14 languages with complete ethical reasoning in user's preferred language
  - ACCORD ethical framework (~1150 lines per language)
  - All 6 DMA prompts (PDMA, CSDMA, DSDMA, IDMA, ASPDMA, TSASPDMA)
  - Comprehensive Guide runtime instructions
  - Conscience strings and ponder questions
  - KMP mobile/desktop UI (24+ screens, ~500 strings)
  - Languages: Amharic, Arabic, Chinese, English, French, German, Hindi, Italian, Japanese, Korean, Portuguese, Russian, Swahili, Turkish

- **Wallet Adapter** - Cryptocurrency payment integration
  - x402/Chapa payment providers
  - Auto-load keys from CIRISVerify secure element
  - USDC transfers on Base network
  - Gas fee guidance and warnings

- **HA/MA Tool Documentation** - Full LLM context enrichment for all tools
  - 10 Home Assistant tools with detailed_instructions, examples, gotchas
  - 5 Music Assistant tools with search strategies and queue behavior docs

- **Navigation & Weather Services** - Setup wizard integration
  - OpenStreetMap routing and geocoding
  - NOAA National Weather Service API

### Changed

- **Audit Trail Multi-Source Merging** - Proper deduplication across SQLite, Graph, and JSONL backends
- **ASPDMA Schema** - Removed invalid `tool_parameters` field (TSASPDMA handles parameters)

### Fixed

- **Action Sequence Conscience** - Fixed action types stored as `"HandlerActionType.SPEAK"` instead of `"speak"`, preventing conscience from detecting repeated SPEAK actions
- **DMA Prompt JSON Escaping** - Fixed `KeyError: '"reasoning"'` caused by unescaped JSON braces in LANGUAGE RULES examples (affects all 15 localized prompt sets)
- **Error Visibility** - Added `emit_dma_failure` and `emit_circuit_breaker_open` calls for UI display
- **ACCORD Mode** - Added `CIRIS_ACCORD_MODE` env var (compressed/full/none) with default "compressed"
- **Env Var Security** - Added sanitization in `sync_env_var()` to prevent log injection
- **Kotlin Composable Context** - Fixed `localizedString()` calls in non-composable contexts
- **ASPDMA Language** - Use `get_preferred_language()` instead of prompt_loader

## [2.2.9] - 2026-03-24

### Added

- **Founding Partnerships** - Backfill founding partnership status for pre-existing ROOT users
- **Privacy Compliance** - Enhanced DSAR data management

### Fixed

- **Data Management Screen** - Fixed 404 errors and always-sync resources

## [2.2.8] - 2026-03-22

### Added

- **HA Resilience** - Improved Home Assistant connection handling

### Fixed

- **iOS Version Display** - Correct version shown in app
- **Bump Script** - Version alignment across all constants files

## [2.2.7] - 2026-03-20

### Added

- **Music Assistant Tools** - Full MA integration with search, play, browse, queue, players
- **HA Documentation** - Comprehensive tool documentation for LLM context
- **DEFER Guidance** - Improved human deferral handling

### Fixed

- **LLM Response Parsing** - Better handling of malformed responses
- **Mobile Settings** - Various UI improvements

## [2.2.6] - 2026-03-18

### Added

- **H3ERE Pipeline Visualization** - Real-time reasoning pipeline display
- **Conscience TOOL Loop Prevention** - Prevents infinite tool call loops

### Fixed

- **Timeline Deduplication** - Proper dedup of action entries
- **PONDER Display** - Correct rendering of ponder actions
- **Dream State** - Various dream mode fixes

## [2.2.5] - 2026-03-16

### Fixed

- **FFI Initialization** - Fixed native library loading issues
- **App Store Review** - Account deletion, auth clarity, purchase token refresh
- **Telemetry Scheduler** - Improved scheduling reliability

## [2.2.4] - 2026-03-14

### Added

- **Telemetry Push Scheduler** - Scheduled telemetry uploads

### Fixed

- **Dream State** - Various dream mode improvements
- **Mobile Updates** - UI polish and bug fixes

## [2.2.3] - 2026-03-12

### Added

- **Desktop Auto-Launch** - Unified `ciris-agent` entry point launches both server and desktop app
- **Mobile Guide** - In-app help documentation

### Fixed

- **Graph Defaults** - Correct default settings for memory graph

## [2.2.2] - 2026-03-11

### Added

- **Tickets Screen** - Privacy request management UI
- **Scheduler Screen** - Task scheduling interface
- **Human Deferrals** - Improved WA deferral handling

## [2.2.1] - 2026-03-10

### Fixed

- **Mobile Stability** - Various crash fixes and performance improvements

## [2.2.0] - 2026-03-09

### Added

- **Action Timeline** - Real-time audit trail visualization in mobile app
  - ActionType enum with all 10 CIRIS verbs
  - Color-coded ActionBubble component (green=L5, amber=L4, red=L1-3)
  - SSE-triggered live updates

- **Trust Page Enhancements**
  - Level Debug expansion showing L1-L5 check details
  - Agent version badge alongside CIRISVerify version
  - Continuous polling for live attestation updates

### Fixed

- **Trust Shield Colors** - Match TrustPage (L1-3=red, L4=amber, L5=green)
- **Double-Encoded JSON** - Fixed parsing for tool parameters
- **Nested JSON Display** - Proper rendering in audit UI

## [2.1.11] - 2026-03-08

### Changed

- **SDK Sync** - Updated SDK files for compatibility
- **Mobile Manifest CI** - Improved CI for mobile builds
- **iOS Support** - bump_version.py now handles iOS

## [2.1.10] - 2026-03-07

### Added

- **Attestation Level Colors** - Visual indicators for trust levels
- **CIRISVerify v1.1.24** - Updated verification library

## [2.1.8] - 2026-03-06

### Changed

- **CIRISVerify v1.1.22** - Security and stability improvements
- **Manifest Fixes** - Corrected mobile manifest handling
- **Update Script** - Fixed auto-update issues

## [2.1.6] - 2026-03-05

### Changed

- **CIRISVerify v1.1.21** - Minor improvements

## [2.1.5] - 2026-03-04

### Changed

- **CIRISVerify v1.1.20** - Initial stable release
- **CI Fixes** - Build pipeline improvements

## [2.0.1] - 2026-03-01

### Added

- **CIRISRegistry CI Integration** - Build manifests now automatically registered with CIRISRegistry
  - New `register-build` job in GitHub Actions workflow
  - Hashes all source files in `ciris_engine/` and `ciris_adapters/`
  - Enables CIRISVerify integrity validation for deployed agents

## [2.0.0] - 2026-02-28

### Changed

- **Major Release** - CIRIS Agent 2.0 "Context Engineering"
  - See release notes for full details

## [1.9.9] - 2026-02-08

### Added

- **MCP Server JWT Authentication** - Added JWT token validation as authentication method
  - New `security.py` module with `MCPServerSecurity` class
  - Config options: `jwt_secret`, `jwt_algorithm` (default HS256)
  - Environment variables: `MCP_JWT_SECRET`, `MCP_JWT_ALGORITHM`
  - Falls back to API key auth if JWT validation fails

- **Mobile Error Display** - Python runtime errors now shown on splash screen
  - Previously just showed "Waiting for server..." indefinitely
  - Now displays meaningful error messages (e.g., "Build error: pydantic_core native library missing")

- **Emulator Support** - Added x86_64 ABI for debug builds only
  - ARM-only for release AAB (developing markets optimization)
  - x86_64 gated to debug buildType (not in defaultConfig)
  - Debug APK includes x86_64 for emulator testing

### Fixed

- **Trace Signature Payload Mismatch** - Fixed ~900 byte difference between signed and sent payloads
  - `sign_trace()` used `_strip_empty()` but `to_dict()` sent raw data
  - Now both use module-level `_strip_empty()` for consistent payloads
  - CIRISLens signature verification now succeeds for all trace levels

- **Compose Thread Safety** - Fixed mutableStateOf mutation from background thread
  - Python error state now updated via `runOnUiThread`
  - Prevents snapshot concurrency exceptions on startup errors

- **Redundant response_model** - Removed duplicate response_model parameters in FastAPI routes (S8409)
- **Redundant None check** - Fixed always-true condition in discord_tool_service.py (S2589)

### Changed

- **CIRISNode Client Migrated to Adapter** - Moved from `ciris_engine/logic/adapters` to `ciris_adapters/cirisnode`
  - Updated API endpoints to match CIRISNode v2 (`/api/v1/` prefix)
  - JWT authentication via `CIRISNODE_AUTH_TOKEN` and `CIRISNODE_AGENT_TOKEN`
  - Agent events use `X-Agent-Token` header for managed agent auth
  - Async job model for benchmarks with polling convenience methods
  - Tool service interface for integration via manifest.json

- **Adapter Renaming** - Renamed 49 clawdbot_* adapters to generic names
  - e.g., `clawdbot_1password` → `onepassword`, `clawdbot_github` → `github`

## [1.9.8] - 2026-02-08

### Performance

- **Pydantic defer_build Optimization** - Added `defer_build=True` to 670 models for memory reduction
  - Excludes visibility schemas with complex nested types (causes model_rebuild errors)

### Fixed

- **Trace Signature Per-Level Integrity** - Each trace level now has unique signature
  - `trace_level` included in signed payload for generic/detailed/full_traces
  - Fixes verification failures when same trace sent at multiple levels
  - CIRISLens can now verify signatures at any trace level independently

- **ASPDMA Prompt Schema Mismatch** - LLM now returns flat fields instead of nested `action_parameters`
  - Fixes validation errors with Groq/Llama models returning `{"action_parameters": {...}}`
  - Updated `action_instruction_generator.py` to match `ASPDMALLMResult` flat schema

- **Live LLM Model Name** - Added `OPENAI_MODEL_NAME` to env var precedence in `service_initializer.py`
  - QA runner `--live` mode now correctly uses specified model

- **SonarCloud Blockers** - Resolved cognitive complexity and code smell issues
  - `introspect_memory.py`: Extracted helper functions, fixed bare except clause
  - `test_setup_ui.py`: Async file I/O with aiofiles, extracted helpers

### Security

- **Dockerfile Non-Root User** - Container now runs as unprivileged `ciris` user
  - Added `--no-install-recommends` to minimize attack surface
  - Proper file ownership with `COPY --chown`

## [1.9.7] - 2026-02-07

### Security

- **API Auth Hardening** - Fail closed when auth services unavailable (503 instead of dev fallback)
- **CORS Configuration** - Configurable `cors_allow_credentials` with wildcard safety checks

### Added

- **Template Selection in Setup Wizard** - Optional "Advanced Settings" section
  - CLI `--template` flag now honored (was ignored on first-run)
  - Template picker in both CIRISGUI-Standalone and KMP mobile wizards
- **Mobile Live Model Selection** - `POST /v1/setup/list-models` in KMP generated API

### Fixed

- **Accord Metrics Trace Optimization** - 98% size reduction (100KB → 1.7KB)
  - `_strip_empty()` removes null/empty values, compact JSON separators

## [1.9.6] - 2026-02-06

### Changed

- **SonarCloud Code Quality** - Major API route improvements
  - New `_common.py` pattern library with `AuthDep`, `AuthObserverDep`, `RESPONSES_*` dictionaries
  - Fixed S8409/S8410/S8415 blockers across agent.py, auth.py, setup.py, telemetry.py, adapters.py
  - Replaced broad `except Exception` with specific types (JWT errors, ValueError, TypeError)
  - Extracted reusable helpers in `control_service.py` and `authentication/service.py`

- **Mobile QA Runner** - iOS and Android testing improvements
  - Enhanced device helper and build helper modules
  - iOS logger and main entry point updates
  - Platform-specific path detection fixes

## [1.9.5] - 2026-02-05

### Added

- **Live Provider Model Listing** - `POST /v1/setup/list-models` endpoint for real-time model discovery
  - Fetches available models directly from provider APIs during setup
  - Supports OpenAI, Anthropic, Google, and OpenRouter providers
  - 30-second timeout with graceful fallback to cached defaults

- **Web UI QA Runner** - End-to-end browser testing with Playwright
  - Full setup wizard flow: load → LLM config → model selection → account creation → login
  - Covenant metrics consent checkbox verification
  - Agent interaction testing (send message, receive response)
  - Screenshot capture at each step for debugging
  - `python -m tools.qa_runner.modules.web_ui` command

- **Mobile Platform Detection** - Platform-specific Python path resolution
  - `getPythonPath()` for iOS and Android runtime detection
  - Enhanced startup screen with Python environment diagnostics

### Fixed

- **ARM32 Android Support** - Fixed engine startup on 32-bit ARM devices
  - Pinned bcrypt to 3.1.7 (only version with armeabi-v7a wheels)
  - Reported by user in Ethiopia on 32-bit Android device

- **Mobile Error Screen Debug Info** - Added device info to startup failure screens
  - Android: Shows OS version, device model, CPU architecture, supported ABIs
  - iOS: Shows iOS version, device model, CPU, app version, memory
  - Both platforms include GitHub issue reporting link

- **Python 3.10 Compatibility** - Fixed PEP 695 type parameter syntax
  - Replaced `def func[T: Type]()` with traditional TypeVar for Python 3.10 support
  - Affected wa.py route helpers

- **LLM Validation Base URL** - Setup wizard now resolves provider base URLs consistently
  - `_validate_llm_connection` uses same `_get_provider_base_url()` as model listing
  - Fixes validation failures when provider requires non-default base URL

### Changed

- **SonarCloud Code Quality** - Addressed 44 code smell issues across API routes
  - Removed redundant `response_model` parameters (FastAPI infers from return type)
  - Converted `Depends()` to `Annotated` type hints (PEP 593)
  - Added HTTPException documentation via `responses` parameter
  - Files: connectors.py, partnership.py, setup.py, wa.py

### Tests

- Added 54 new tests for API routes
  - test_connectors.py: 18 new tests (36 total)
  - test_partnership_endpoint.py: 8 new tests (26 total)
  - test_wa_routes.py: 28 new tests (new file)

## [1.9.4] - 2026-02-01

### Added

- **iOS KMP Support** - Merged ios-kmp-refactor branch for Kotlin Multiplatform iOS support
  - Cross-platform authentication with `NativeSignInResult` (Google on Android, Apple on iOS)
  - Platform-specific logging via `platformLog()` expect/actual function
  - iOS Python runtime bridge and Apple Sign-In helper
  - Shared KMP modules for auth, platform detection, and secure storage

- **Apple Native Auth** - iOS Sign-In with Apple support
  - `POST /v1/auth/native/apple` endpoint for Apple ID token exchange
  - Local JWT decode for Apple tokens (validates issuer, expiry)
  - Auto-mint SYSTEM_ADMIN users as ROOT WA (same as Google flow)

- **Platform Requirements System** - Filter adapters by platform capabilities
  - `DESKTOP_CLI` requirement for CLI-only tools (40+ adapters marked)
  - `platform_requirements` and `platform_requirements_rationale` in adapter manifests
  - Automatic filtering in mobile adapter wizard (CLI tools hidden on Android/iOS)

- **Local JWT Decode Fallback** - On-device auth resilience
  - Falls back to local JWT decoding when Google tokeninfo API is unreachable
  - Validates token expiry and issuer locally
  - Enables authentication on devices with limited network access

- **HE-300 Benchmark Template** - Ethical judgment agent for moral scenario evaluations
  - Minimal permitted actions (speak, ponder, task_complete only)
  - Direct ETHICAL/UNETHICAL or TRUE/FALSE judgments
  - DSDMA configuration with ethical evaluation framework

### Security

- **Billing URL SSRF Protection** - Validates billing service URLs against allowlist
  - Trusted hosts: `billing.ciris.ai`, `localhost`, `127.0.0.1`
  - Pattern matching for `billing*.ciris-services-N.ai` (N=1-99)
  - HTTPS required for non-localhost hosts

### Fixed

- **Mobile SDK JSON Parsing** - Fixed 16 empty union type classes in generated API
  - `Default.kt`, `ModuleTypeInfoMetadataValue.kt`, `ResponseGetSystemStatusV1TransparencyStatusGetValue.kt`
  - `AdapterOperationResultDetailsValue.kt`, `BodyValue.kt`, `ConscienceResultDetailsValue.kt`
  - `DeferParamsContextValue.kt`, `DependsOn.kt`, `LocationInner.kt`, `Max.kt`, `Min.kt`
  - `ParametersValue.kt`, `ResponseGetAvailableToolsV1SystemToolsGetValue.kt`
  - `ServiceDetailsValueValue.kt`, `ServiceSelectionExplanationPrioritiesValueValue.kt`, `SettingsValue.kt`
  - Each wrapped with `JsonElement` and custom `KSerializer` to handle dynamic JSON types

- **Mobile Attributes Model** - Made all union type fields nullable in `Attributes.kt`
  - Fixed `content`, `memoryType`, `source`, `key`, `value`, `description`, etc.
  - Allows parsing of partial attribute objects from different node types

- **DateTime Serialization** - ISO-8601 timestamps now include `Z` suffix
  - Added `serialize_datetime_iso()` helper function
  - Fixed `GraphNode`, `GraphNodeAttributes`, `GraphEdgeAttributes`
  - Fixed `NodeAttributesBase`, `MemoryNodeAttributes`, `ConfigNodeAttributes`, `TelemetryNodeAttributes`
  - Fixed `TimelineResponse`, `QueryRequest`, `MemoryStats` in memory_models.py
  - Kotlin `kotlinx.datetime.Instant` can now parse server timestamps

- **Configuration Display** - Fixed `ConfigValue` union type rendering
  - Added `ConfigValue.toDisplayString()` extension to extract actual value
  - Config page now shows `api` instead of `ConfigValue(stringValue=api, intValue=null, ...)`

- **Mobile UI Fixes**
  - Navigation bar padding on SetupScreen (Continue button no longer blocked)
  - Adapter wizard error dialog now shows on error (not just when dialog open)
  - Capability chips limited to 2 with "+N" overflow (prevents stretched empty chips)
  - Filter blank capabilities at API client mapping layer

- **Rate Limiting** - Added adapter endpoints to exempt paths
  - `/v1/system/adapters` and `/v1/setup/adapter-types` no longer rate-limited
  - Fixes "+" Add Adapter button returning 429 errors

- **401 Auth on Mobile** - Fixed Google tokeninfo API timeout on-device
  - Python running on Android can't reach Google servers reliably
  - Local JWT decode fallback validates tokens without network call

- **Mobile Billing Purchase Flow** - Fixed 401/500 errors on purchase verification
  - Added `onTokenUpdated` callback to CIRISApp for billing apiClient sync
  - Billing endpoint falls back to `CIRIS_BILLING_GOOGLE_ID_TOKEN` env var
  - Kotlin EnvFileUpdater writes token, Python billing reads it

- **Accord Metrics Trace Levels** - Fixed per-adapter trace level configuration
  - Config now overrides env var (was reversed)
  - Added adapter instance ID to logging for multi-adapter debugging
  - QA runner default changed from `full_traces` to `detailed`
  - Covenant metrics tests load `generic` and `full_traces` adapters

- **Default Template Changed** - Ally is now the default agent template
  - Renamed `default.yaml` → `datum.yaml`, `ally.yaml` → `default.yaml`
  - Ally provides personal assistant functionality with crisis response protocols

- **Test Isolation Improvements** - Fixed parallel test pollution
  - Added `isolate_test_env_vars` fixture for env var isolation
  - Isolates LLM provider detection env vars (GOOGLE_API_KEY, ANTHROPIC_API_KEY, etc.)
  - Fixed A2A adapter tests to use proper async mock for `on_message`
  - Updated dual_llm tests to explicitly clear interfering env vars
  - All 8867 tests now pass consistently with `pytest -n 16`

- **Accord Metrics Consent Timestamp** - Auto-set when adapter enabled
  - Setup wizard now writes `CIRIS_ACCORD_METRICS_CONSENT=true` and timestamp
  - Fixes `TRACE_REJECTED_NO_CONSENT` errors on mobile devices

- **SonarCloud Code Quality** - Addressed code smells and cognitive complexity
  - Extracted helper functions to reduce cognitive complexity in 6+ files
  - Renamed iOS classes to match PascalCase convention (IOSDictRow, etc.)
  - Removed unused variables and fixed implicit string concatenations
  - Added mobile/iOS directory exclusions to sonar-project.properties

## [1.9.3] - 2026-01-27

### Added

- **TSASPDMA (Tool-Specific Action Selection PDMA)** - Documentation-aware tool validation
  - Activated when ASPDMA selects a TOOL action
  - Reviews full tool documentation before execution
  - Can return TOOL (proceed), SPEAK (ask clarification), or PONDER (reconsider)
  - Returns same `ActionSelectionDMAResult` as ASPDMA for transparent integration
  - Catches parameter ambiguities and gotchas that ASPDMA couldn't see

- **Native LLM Provider Support** - Direct SDK integration for major LLM providers
  - **Google Gemini**: Native `google-genai` SDK with instructor support
    - Models: `gemini-2.5-flash` (1M tokens/min), `gemini-2.0-flash` (higher quotas)
    - Automatic instructor mode: `GEMINI_TOOLS` for structured output
  - **Anthropic Claude**: Native `anthropic` SDK with instructor support
    - Models: `claude-sonnet-4-20250514`, `claude-opus-4-5-20251101`
    - Automatic instructor mode: `ANTHROPIC_TOOLS` for structured output
  - **Provider Auto-Detection**: Detects provider from API key environment variables
    - Checks `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_API_KEY`
    - Falls back to OpenAI-compatible mode if none found

- **New Environment Variables** - LLM configuration with CIRIS_ prefix priority
  - `CIRIS_LLM_PROVIDER`: Explicit provider selection (`openai`, `anthropic`, `google`)
  - `CIRIS_LLM_MODEL_NAME`: Model name override (takes precedence over `OPENAI_MODEL`)
  - `CIRIS_LLM_API_KEY`: API key override (takes precedence over provider-specific keys)
  - Fallback support for `LLM_PROVIDER`, `LLM_MODEL`, `OPENAI_MODEL`

- **Adapter Auto-Discovery Service** - Multi-path adapter scanning
  - Scans `ciris_adapters/`, `~/.ciris/adapters/`, `.ciris/adapters/`
  - `CIRIS_EXTRA_ADAPTERS` env var for additional paths (colon-separated)
  - First occurrence wins for duplicate adapter names
  - Integrated with eligibility filtering

- **Tool Eligibility Checker** - Runtime requirement validation
  - Validates binaries in PATH (`shutil.which`)
  - Validates environment variables are set
  - Validates platform compatibility
  - Validates config keys (when config service available)
  - `EligibilityResult` with detailed missing requirements and install hints

- **Clawdbot Skill Converter** - Tool to convert Clawdbot skills to CIRIS adapters
  - `python -m tools.clawdbot_skill_converter <skills_dir> <output_dir>`
  - Parses SKILL.md YAML frontmatter + markdown documentation
  - Generates manifest.json, service.py, adapter.py, README.md
  - Proper `ToolInfo.requirements` integration for eligibility checking
  - 49 Clawdbot skills converted to CIRIS adapters

- **Tool Summaries in ASPDMA Context** - Concise tool guidance for action selection
  - Injects `when_to_use` field into ASPDMA context
  - Falls back to truncated description if no `when_to_use`
  - Helps ASPDMA make informed tool selection without full documentation

- **Adapter Availability Discovery API** - Expose adapters with unmet requirements
  - `GET /adapters/available` - List all adapters with eligibility status
  - `POST /adapters/{name}/install` - Install missing dependencies (brew, apt, pip, etc.)
  - `POST /adapters/{name}/check-eligibility` - Recheck after manual installation
  - New schemas: `AdapterAvailabilityStatus`, `AdapterDiscoveryReport`, `InstallRequest/Response`
  - Discovery service now tracks ineligible adapters with detailed reasons

- **Tool Installer Service** - Execute installation steps for missing dependencies
  - Supports: brew, apt, pip, uv, npm, winget, choco, manual commands
  - Platform-aware installation (skips incompatible platforms)
  - Dry-run mode for safe testing
  - Binary verification after installation

- **Installable Tools in ASPDMA Prompt** - Agent awareness of tools that can be installed
  - ASPDMA prompt now lists tools available for installation
  - Shows missing dependencies and install methods
  - Guides agent to use SPEAK to ask user about installation

### Fixed

- **TSASPDMA Execution Pipeline** - Fixed tool validation not triggering
  - Added `sink` parameter to TSASPDMAEvaluator initialization (required for LLM calls)
  - Fixed ToolBus.get_tool_info() to search ALL tool services (not just default handler)
  - Fixed escaped braces in tsaspdma.yml prompt (`{entity_id}` → `{{entity_id}}`)
  - Override to PONDER when ASPDMA selects a non-existent tool
  - TSASPDMA now mandatory for all TOOL actions (never skipped)

- **Event Streaming** - Fixed IDMA/TSASPDMA event structure
  - Separated IDMA from dma_results event (IDMA now streams independently)
  - TSASPDMA_RESULT event includes `final_action` field ("tool", "speak", "ponder")
  - 8-component traces: THOUGHT_START → SNAPSHOT_AND_CONTEXT → DMA_RESULTS → IDMA_RESULT → TSASPDMA_RESULT → ASPDMA_RESULT → CONSCIENCE_RESULT → ACTION_RESULT
  - Added INFO logging for TSASPDMA event emission with final_action visibility

- **Schema Fixes** - Fixed various mypy errors from 1.9.3 changes
  - Fixed GraphNode instantiation with correct fields (id, type, attributes)
  - Fixed PonderParams import path (schemas.actions.parameters)
  - Fixed discovery_service, llm_service, service_initializer type annotations

- **Adapter Eligibility Checking** - Services now properly check requirements
  - `_check_requirements()` now uses `ToolInfo.requirements` instead of hardcoded empty lists
  - Adapters requiring missing binaries/env vars are no longer incorrectly loaded

- **Clawdbot Adapter Schema Compliance** - Fixed multiple manifest issues
  - Changed `sensitive: true` to `sensitivity: "HIGH"` in configuration
  - Removed invalid `source` field from module section
  - Added required `description` to confirm steps
  - Fixed protocol path to `ciris_engine.protocols.services.runtime.tool.ToolServiceProtocol`
  - Fixed binary requirement format (no longer double-quoted)

### Changed

- **Reduced Cognitive Complexity** - Refactored functions to meet SonarCloud limits (≤15)
  - `discovery_service._instantiate_and_check_with_info`: 21→12 via helper extraction
  - `discovery_service.get_adapter_eligibility`: 28→10 via helper extraction
  - `installer._build_command`: 24→6 via dispatch table pattern
  - Added 28 new tests for extracted helper methods (94 total in tool services)

- **TSASPDMA Ethical Reasoning** - Enhanced prompt for ethical tool validation
  - Rationale must include: why tool is appropriate, why it's ethical, gotchas acknowledged
  - Added ethical check to PONDER criteria (inappropriate/unethical tool use)
  - Added ethical appropriateness to TOOL criteria

- **ASPDMA/TSASPDMA Schema Refactoring** - Removed Union types for Gemini compatibility
  - Gemini's structured output doesn't support discriminated unions
  - `ASPDMALLMResult`: Flat schema with `selected_action` + optional parameter fields
  - `TSASPDMALLMResult`: Flat schema with `tool_parameters` as JSON dict
  - `convert_llm_result_to_action_result()`: Converts flat result to typed `ActionSelectionDMAResult`
  - All existing tests pass with new flat schema design

- **New Dependencies** - Added native LLM provider SDKs
  - `google-genai>=1.0.0,<2.0.0`: New Google GenAI SDK with instructor support
  - `jsonref>=1.0.0,<2.0.0`: Required by google-genai for schema resolution
  - `anthropic>=0.40.0,<1.0.0`: Already present, now actively used for native integration

## [1.9.2] - 2026-01-27

### Added

- **Enhanced ToolInfo Schema** - Rich skill-like documentation support for adapter tools
  - New `requirements` field: Runtime requirements (binaries, env vars, config keys)
  - New `install_steps` field: Installation instructions (brew/apt/pip/npm/manual)
  - New `documentation` field: Rich docs (quick_start, examples, gotchas, related_tools)
  - New `dma_guidance` field: DMA guidance (when_not_to_use, requires_approval, min_confidence)
  - New `tags` field: Categorization tags for tool discovery
  - New `version` field: Tool version string
  - All fields optional for full backward compatibility
  - See `ciris_adapters/README.md` for adapter developer documentation

- **New Supporting Schemas** for ToolInfo enhancement:
  - `BinaryRequirement`, `EnvVarRequirement`, `ConfigRequirement` - requirement types
  - `ToolRequirements` - combined runtime requirements
  - `InstallStep` - installation instruction with platform targeting
  - `UsageExample`, `ToolGotcha`, `ToolDocumentation` - rich documentation
  - `ToolDMAGuidance` - DMA decision-making guidance

- **Mobile Build Improvements** - Python sources synced from main repo at build time
  - New `syncPythonSources` Gradle task copies `ciris_engine/` and `ciris_adapters/`
  - Eliminates need to maintain separate android/ copy of Python sources
  - Mobile-specific files remain in `mobile/androidApp/src/main/python/`

- **Mobile Memory Graph** - Force-directed layout visualization for memory nodes
  - Interactive graph with zoom, pan, and node selection
  - Scope filtering (LOCAL, SOCIAL, IDENTITY, ENVIRONMENT)
  - Edge relationship visualization

- **Mobile Users Management** - New screen for managing WA users

### Fixed

- **SonarCloud Code Quality** - Resolved multiple code smells in `agent.py`
  - Reduced cognitive complexity in `_create_interaction_message`, `_derive_credit_account`, `get_identity`
  - Extracted helper functions for image/document processing, provider derivation, service categorization
  - Replaced `Union[]` with `|` syntax, `set([])` with `{}`
  - Removed unused variables

- **TaskOutcome Schema Compliance** - WA deferral resolution now uses proper `TaskOutcome` schema
  - Changed from `{"status": "resolved", "message": ...}` format
  - Now uses: `status`, `summary`, `actions_taken`, `memories_created`, `errors`

- **Memory Graph Scope Mixing** - Fixed cross-scope edge issues in mobile visualization
  - Made `GraphFilter.scope` non-nullable with `GraphScope.LOCAL` default
  - Removed "All" option from scope filter

- **WA Service Query** - Fixed query to use `outcome_json` column instead of non-existent `outcome`

- **Telemetry Test Mocks** - Marked incomplete mock setup tests as xfail

### Changed

- **SonarCloud Exclusions** - Added `mobile/**/*` to exclusions in `sonar-project.properties`

## [1.9.1] - 2026-01-25

### Fixed

- **MCP QA Tests False Positives** - Tests now properly verify tool execution success
  - Adapter loading tests verify tools are discovered (not just that adapter object exists)
  - Tool execution tests check `context.metadata.outcome == 'success'` in audit entries
  - Tests fail correctly when MCP SDK not installed or server connection fails
  - Pass rate: 100% (22/22 tests) when MCP SDK installed

- **MCP Test Audit Verification** - Fixed audit entry field mapping
  - Was checking non-existent `action_result.success` and `handler_result.success`
  - Now correctly checks `context.metadata.outcome` for success/failure

### Added

- **Trace Format v1.9.1 JSON Schema** - Machine-readable schema for CIRISLens
  - `ciris_adapters/ciris_accord_metrics/schemas/trace_format_v1_9_1.json`
  - Full field documentation for all 6 H3ERE components
  - Includes level annotations (generic, detailed, full_traces)

## [1.9.0] - 2026-01-22

### Added

- **Accord Metrics Live Testing** - Full integration with CIRISLens server (100% pass rate)
  - `--live-lens` flag for QA runner to test against real Lens server
  - Multi-level trace adapters (generic, detailed, full_traces) via API loading
  - PDMA field validation tests at detailed/full trace levels
  - Key ID consistency verification between registration and signing
  - Updated default endpoint to production URL

- **Comprehensive Adapter QA Testing** - All adapters now have QA test coverage
  - `ciris_accord_metrics`: 100% - Full CIRISLens integration
  - `mcp_client/mcp_server`: 95.5% - Handle adapter reload
  - `external_data_sql`: 100% - Fixed config passing
  - `weather`: 100% - Free NOAA API
  - `navigation`: 100% - Free OpenStreetMap API
  - `ciris_hosted_tools`: 60% - Awaiting billing token
  - `reddit`, `home_assistant`: Need API credentials

- **Adapter Manifest Validation** - Comprehensive QA module for all adapters
  - Validates manifest.json structure for all modular adapters
  - Tests adapter loading, configuration, and lifecycle

- **Adapter Status Documentation** - Test status table in ciris_adapters/README.md

### Fixed

- **System Channel Admin-Only** - Non-admin users no longer see system/error messages
  - Rate limit errors from other sessions no longer appear for new users
  - System channel now restricted to ADMIN, SYSTEM_ADMIN, AUTHORITY roles

- **Trace Signature Format** - Signatures now match CIRISLens verification format
  - Was: signing SHA-256 hash of entire trace object
  - Now: signing JSON components array with `sort_keys=True`

- **CIRISLens Default URL** - Updated to production endpoint
  - Was: `https://lens.ciris.ai/v1`
  - Now: `https://lens.ciris-services-1.ai/lens-api/api/v1`

- **MCP Test Reliability** - Handle existing adapters by unloading before reload
  - Pass rate improved from 72.7% to 95.5%

- **SQL External Data Adapter** - Config now passed from adapter_config during load
  - Adapter builds SQLConnectorConfig from adapter_config parameters
  - Tests load adapter via API with proper configuration
  - Pass rate improved from 25% to 100%

- **Adapter Config API** - Added missing `load_persisted_configs()` and `remove_persisted_config()` methods
  - Added unit tests for both methods

- **OAuth Callback Test** - Handle HTML response instead of expecting JSON

- **State Transition Tests** - Updated test expectations for shutdown_evaluator and template_loading

## [1.8.13] - 2026-01-21

### Fixed

- **Adapter Persist Flag Not Extracted** - Adapters loaded via API with `persist=True` were not being persisted
  - Root cause: `_convert_to_adapter_config()` nested `persist` inside `adapter_config` dict
  - But `_save_adapter_config_to_graph()` checked top-level `AdapterConfig.persist` (default `False`)
  - Fix: Extract `persist` flag from config dict and set on `AdapterConfig` directly
  - Affects: Covenant metrics adapter and any adapter loaded via API with persistence

- **Rate Limit Retry Timeout Too Short** - Increased from 25s to 90s
  - Multi-agent deployments hitting Groq simultaneously exhaust rate limits
  - 25s wasn't enough time for Groq to recover between retries
  - Now allows up to 90s of rate limit retries before giving up

## [1.8.12] - 2026-01-20

### Fixed

- **Path Traversal Security Fix (SonarCloud S2083)** - Removed user-controlled path construction
  - `create_env_file()` and `_save_setup_config()` no longer accept `save_path` parameter
  - Functions now call `get_default_config_path()` internally (whitelist approach)
  - Path is constructed from known-safe bases, not user input
  - Eliminated potential path injection attack vector

- **Clear-text Storage Hardening (CodeQL)** - Added restrictive file permissions
  - `.env` files now created with `chmod 0o600` (owner read/write only)
  - Prevents other users on system from reading sensitive configuration

- **Dev Mode Config Path** - Changed from `./.env` to `./ciris/.env`
  - Development mode now uses `./ciris/.env` for consistency with production
  - Backwards compatibility: still checks `./.env` as fallback
  - `get_config_paths()` updated to check `./ciris/.env` first in dev mode

## [1.8.11] - 2026-01-20

### Fixed

- **LLM Failover Timeout Bug** - DMA was timing out before LLMBus could failover to secondary provider
  - Root cause: DMA timeout (30s) < LLM timeout (60s), so failover never had a chance to occur
  - DMA timeout increased from 30s to 90s (configurable via `CIRIS_DMA_TIMEOUT` env var)
  - LLM Bus retries per service reduced from 3 to 1 for fast failover between providers
  - LLM service timeout reduced from 60s to 20s (configurable via `CIRIS_LLM_TIMEOUT` env var)
  - LLM max_retries reduced from 3 to 2 to fit within DMA timeout budget
  - New timeout budget: 90s DMA > (20s LLM × 2 retries × 2 providers = 80s)
  - Fixes: Echo Core deferrals when Together AI was down but Groq was available

- **Unified Adapter Persistence Model** - Single consistent pattern for adapter auto-restore
  - Unified to single pattern: `adapter.{adapter_id}.*` with explicit `persist=True` flag
  - Removed deprecated `adapter.startup.*` pattern and related methods
  - Adapters with `persist=True` in config are auto-restored on startup
  - Added adapter config de-duplication (same type, occurrence_id, and config hash)
  - Database maintenance cleans up non-persistent adapter configs on startup
  - Fixed occurrence_id mismatch issue (configs saved with wrong occurrence_id)
  - Removed redundant `auto_start` field in favor of `persist`
  - CIRISRuntime initialization step now handles all adapter restoration

## [1.8.10] - 2026-01-20

### Fixed

- **Adapter Auto-Restore: Fix adapter_manager Resolution** - The loader was looking in the wrong place
  - `load_saved_adapters_from_graph()` was calling `_get_runtime_service(runtime, "adapter_manager")`
  - But `ServiceInitializer` doesn't have `adapter_manager` - it's on `RuntimeControlService`
  - Now correctly gets adapter_manager via `runtime_control_service.adapter_manager`
  - This was the final missing piece - 1.8.9 registered the step but it always returned early

## [1.8.9] - 2026-01-19

### Fixed

- **Adapter Auto-Restore on Restart (Step Registration)** - The fix was missing from 1.8.7 and 1.8.8
  - Added missing "Load Saved Adapters" initialization step registration in `CIRISRuntime`
  - Root cause: fix commit was pushed to release/1.8.7 AFTER PR was merged
  - Cherry-picked commit `8d54e51e` which contains the actual code change

## [1.8.8] - 2026-01-19

### Fixed

- **Adapter Auto-Restore on Restart (Incomplete)** - Changelog-only release, code fix was missing
  - This release only updated changelog and version, not the actual code

## [1.8.7] - 2026-01-19

### Fixed

- **Adapter Auto-Restore on Restart** - Initial implementation (superseded by 1.8.11)
  - Database maintenance cleanup no longer deletes persisted adapter configs
  - Added "Load Saved Adapters" initialization step to `CIRISRuntime`
  - Note: The `adapter.startup.*` pattern from this version was deprecated in 1.8.11
  - See 1.8.11 for the unified persistence model using `adapter.{adapter_id}.persist=True`

### Changed

- **Database Maintenance Cleanup Logic** - More selective config cleanup
  - Added protection for adapter configs marked for auto-restore
  - Updated README with accurate preservation rules
  - Refactored `_cleanup_runtime_config` to reduce cognitive complexity (23 → ~10)
  - Extracted helper methods: `_should_preserve_config`, `_is_runtime_config`, `_delete_ephemeral_configs`
  - Added 12 unit tests for config preservation logic

## [1.8.6] - 2026-01-19

### Added

- **Unified Ed25519 Signing Key** - Single signing key shared between audit and covenant metrics
  - New `signing_protocol.py` with algorithm-agnostic signing protocol
  - `UnifiedSigningKey` singleton at `data/agent_signing.key` (32 bytes Ed25519)
  - Key ID format: `agent-{sha256(pubkey)[:12]}`
  - PQC-ready design with migration path to ML-DSA/SLH-DSA

- **RSA to Ed25519 Migration Utility** - Migrate existing audit chains
  - `AuditKeyMigration` class for atomic chain migration with rollback
  - Re-signs entire audit chain preserving original timestamps
  - `database_maintenance.migrate_audit_key_to_ed25519()` method for admin access
  - RSA-2048 verification maintained for backward compatibility

- **CIRISLens Public Key Registration** - Automatic key registration on startup
  - Covenant metrics adapter registers public key before sending connect event
  - Enables CIRISLens to verify trace signatures

### Changed

- **AuditSignatureManager now uses Ed25519** - No longer generates RSA-2048 keys
  - New installations automatically use unified Ed25519 key
  - Legacy RSA verification maintained for existing audit chains
  - Key rotation deprecated in favor of unified key management

### Fixed

- **Accord Metrics agent_id_hash** - Traces now include proper agent ID hash instead of "unknown"
  - Service now receives agent_id from persistence during adapter loading
  - Agent identity retrieved from graph when initializing modular adapters
  - Preserved legacy `runtime.agent_id` fallback for mocks and lightweight runtimes
  - Fixes lens team reported issue with traces showing `agent_id_hash: "unknown"`

- **Accord Metrics cognitive_state** - Traces now include cognitive state in SNAPSHOT_AND_CONTEXT
  - Added `cognitive_state` field to SystemSnapshot schema
  - Populated from `agent_processor.get_current_state()` during context building
  - Fixes lens team reported issue with `cognitive_state: null` in traces

## [1.8.5] - 2026-01-18

### Added

- **Multi-Occurrence Adapter Support** - Adapters now track which occurrence loaded them
  - `occurrence_id` saved with adapter config in graph
  - On startup, only loads adapters matching current occurrence
  - Prevents duplicate adapter loading in multi-occurrence deployments

- **Accord Metrics Connectivity Events** - Adapter notifies CIRISLens on startup/shutdown
  - Sends `startup` event to `/covenant/connected` when service starts
  - Sends `shutdown` event before HTTP session closes
  - Includes agent hash, trace level, version, and correlation metadata
  - Enables monitoring agent connectivity without waiting for interactions

### Fixed

- **services_registered API Response** - Adapter status now shows registered services
  - Added `services_registered` field to `AdapterInfo` schema
  - API endpoints now return actual registered services instead of empty array
  - Fixes visibility into which services each adapter provides

### Changed

- **Adapter Loading Behavior** - Adapters without occurrence_id treated as "default" occurrence
  - Legacy adapters seamlessly work with single-occurrence deployments
  - Multi-occurrence deployments require explicit occurrence matching

## [1.8.4] - 2026-01-18

### Fixed

- **P1 Security: Adapter Config Sanitization** - Fixed `_sanitize_config_params` dropping `adapter_config` field
  - Both `settings` and `adapter_config` fields now properly sanitized before exposing to observers
  - Sensitive fields masked with `***MASKED***` pattern

- **Adapter Config Persistence** - Config passed during adapter load now returned in `get_adapter_info` API
  - Added `config_params` field to `AdapterInfo` schema
  - Config properly propagated through RuntimeControlService to API endpoints

- **Scout Template Validation** - Fixed schema compliance in scout.yaml
  - Converted nested lists to semicolon-delimited strings for `high_stakes_architecture` fields

### Changed

- **Reduced Cognitive Complexity** - Refactored `_sanitize_config_params` from complexity 20 to ~8
  - Extracted module-level constants: `SENSITIVE_FIELDS_BY_ADAPTER_TYPE`, `DEFAULT_SENSITIVE_PATTERNS`, `MASKED_VALUE`
  - Extracted helper functions: `_should_mask_field()`, `_sanitize_dict()`
  - Added 21 unit tests for extracted functions

## [1.8.3] - 2026-01-17

### Added

- **QA Test Modules** - New comprehensive API test modules
  - `adapter_autoload_tests.py` - Tests adapter persistence and auto-load functionality
  - `identity_update_tests.py` - Tests identity refresh from template

- **Adapter Auto-Load** - Saved adapters now auto-load from graph on startup
  - Adapter configs persisted to graph during load
  - Configs retrieved and adapters reloaded on runtime initialization

### Fixed

- **ConfigNode Value Extraction (P1)** - Fixed adapter loading from persisted configs
  - `ConfigNode` values now properly extracted before passing to adapter loader
  - Prevents validation errors when loading adapters from graph storage

- **Type Annotations** - Added proper type annotations for mypy strict mode compliance

## [1.8.2] - 2026-01-17

### Added

- **Identity Update from Template** - Admin operation to refresh identity from template updates
  - New `--identity-update` CLI flag (requires `--template`)
  - Uses `update_agent_identity()` for proper version tracking and signing
  - Preserves creation metadata while updating template fields

### Changed

- **Code Modularization** - Refactored largest files for maintainability
  - `system.py` (3049 lines) → 10 focused modules in `system/` package
  - `telemetry_service.py` (2429→1120 lines) → extracted `aggregator.py`, `storage.py`
  - `TelemetryAggregator` (1221→457 lines) → 5 focused modules
  - `ciris_runtime.py` (2342→1401 lines) → 7 helper modules
  - Backward compatibility maintained via `__init__.py` re-exports

- **Reduced Cognitive Complexity** - SonarCloud fixes in system routes and LLM bus

### Fixed

- **Billing Provider** - Explicit `api_key` now takes precedence over env-sourced `google_id_token`

- **MCP Tool Execution** - Fixed Mock LLM handling of MCP tool calls

- **Adapter Status Reporting** - Fixed `AdapterStatus` enum comparison issues

- **Security** - Removed debug logging that could leak sensitive adapter configs

## [1.8.1] - 2026-01-15

### Added

- **Accord Metrics Trace Detail Levels** - Three privacy levels for trace capture
  - `generic` (default): Numeric scores only - powers [ciris.ai/ciris-scoring](https://ciris.ai/ciris-scoring)
  - `detailed`: Adds actionable lists (sources_identified, stakeholders, flags)
  - `full_traces`: Complete reasoning text for Coherence Ratchet corpus
  - Configurable via `CIRIS_ACCORD_METRICS_TRACE_LEVEL` env var or `trace_level` config

### Fixed

- **Multi-Occurrence Task Lookup** - Fixed `__shared__` task visibility across occurrences
  - `gather_context.py` now uses `get_task_by_id_any_occurrence()` to fetch parent tasks
  - Thoughts can now find their parent tasks regardless of occurrence_id (including `__shared__` tasks)
  - Fixes "Could not fetch task" errors in multi-occurrence scout deployments
  - Exported `get_task_by_id_any_occurrence` from persistence module for consistency

- **Covenant Stego Logging** - Reduced noise from stego scanning normal messages
  - Zero-match results now log at DEBUG level (expected for non-stego messages)
  - Only partial matches (>0 but <expected) log at WARNING (possible corruption)
  - Fixes log spam from defensive scanning of user input

- **Accord Metrics IDMA Field Extraction** - Fixed incorrect field names in trace capture
  - Changed `source_assessments` to `sources_identified` (matching IDMAResult schema)
  - Added missing `correlation_risk` and `correlation_factors` fields
  - Ensures complete IDMA/CCA data is captured for Coherence Ratchet corpus

## [1.8.0] - 2026-01-02

### Added

- **IDMA (Intuition Decision Making Algorithm)** - Semantic implementation of Coherence Collapse Analysis (CCA)
  - Applies k_eff formula: `k_eff = k / (1 + ρ(k-1))` to evaluate source independence
  - Phase classification: chaos (contradictory) / healthy (diverse) / rigidity (echo chamber)
  - Fragility detection when k_eff < 2 OR phase = "rigidity"
  - Integrated as 4th DMA in pipeline, runs after PDMA/CSDMA/DSDMA
  - Results passed to ASPDMA for action selection context
  - Non-fatal: pipeline continues with warning if IDMA fails

- **Covenant v1.2-Beta** - Added Book IX: The Mathematics of Coherence
  - The Coherence Ratchet mathematical framework for agents
  - CCA principles for detecting correlation-driven failure modes
  - Rationale document explaining why agents have access to this knowledge
  - Updated constants to reference new covenant file

- **Coherence Ratchet Trace Capture** - Full 6-component reasoning trace for corpus building
  - Captures: situation_analysis, ethical_pdma, csdma, action_selection, conscience_check, guardrails
  - Cryptographic signing of complete traces for immutability
  - Mock logshipper endpoint for testing trace collection
  - Transparency API endpoints for trace retrieval (`/v1/transparency/traces/latest`)

- **OpenRouter Provider Routing** - Select/ignore specific LLM backends
  - Environment variables: `OPENROUTER_PROVIDER_ORDER`, `OPENROUTER_IGNORE_PROVIDERS`
  - Provider config passed via `extra_body` to Instructor
  - Success logging: `[OPENROUTER] SUCCESS - Provider: {name}`

- **System/Error Message Visibility** - Messages visible to all users via system channel
  - System and error messages emitted to agent history
  - `is_agent=True` on system/error messages prevents agent self-observation
  - System channel included in all user channel queries

### Changed

- **LLM Bus Retry Logic** - 3 retries per service before failover
  - Configurable retry count with exponential backoff
  - Log deduplication for repeated failures (WARNING instead of ERROR)
  - Circuit breaker integration with retry exhaustion

- **Changelog Rotation** - Archived 2025 changelog
  - `CHANGELOG-2025.md` contains v1.1.1 through v1.7.9
  - Fresh `CHANGELOG.md` for 2026

### Fixed

- **ServiceRegistry Lookup for Modular Adapters** - Transparency routes now query ServiceRegistry
  - Modular adapters register with ServiceRegistry, not runtime.adapters
  - Fixed trace API returning 404/500 for covenant_metrics traces

- **Streaming Verification Test** - Added `action_parameters` to expected fields
  - ActionResultEvent schema includes action_parameters but test validation was missing it
  - QA runner streaming tests now pass with full schema validation

## [Unreleased]

### Added

### Changed

### Deprecated

### Removed

### Fixed

### Security

---

## Previous Years

- [2025 Changelog](./CHANGELOG-2025.md) - v1.1.1 through v1.7.9
