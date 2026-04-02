# Tools - CLAUDE.md

Development, QA, security, and operational tooling for the CIRIS platform.

## Packages (invoke with `python3 -m tools.<name>`)

| Package | Purpose | Invocation |
|---------|---------|------------|
| `qa_runner` | Full QA test suite with auto server lifecycle, 40+ test modules, SSE monitoring | `python3 -m tools.qa_runner [module]` |
| `grace` | Sustainable dev companion — pre-commit, CI monitoring, session management | `python3 -m tools.grace [status\|ci\|fix\|morning\|night]` |
| `test_tool` | Docker-based pytest runner with coverage | `python3 -m tools.test_tool test tests/` |
| `quality_analyzer` | Unified code quality analysis (mypy + sonar) | `python3 -m tools.quality_analyzer` |
| `benchmark` | HE-300 ethical benchmark runner | `python3 -m tools.benchmark` |
| `generate_sdk` | Kotlin Multiplatform SDK generator from OpenAPI spec | `python3 -m tools.generate_sdk [generate\|fetch\|fix\|clean]` |
| `ciris_mypy_toolkit` | Custom mypy analyzers, error fixers, schema compliance | `python3 -m tools.ciris_mypy_toolkit` |
| `clawdbot_skill_converter` | Converts ClawdBot skills to CIRIS format | `python3 -m tools.clawdbot_skill_converter` |

## Subdirectories

| Directory | Contents |
|-----------|----------|
| `analysis/` | `sonar.py` (SonarCloud integration), `sonar_tool/`, `audit_system.py`, `telemetry_analyzer.py` |
| `database/` | DB tools — `debug_tools.py`, consolidation scripts, PostgreSQL setup scripts, `status.py` |
| `dev/` | Dev workflow — `bump_version.py`, `grace_precommit.py`, `generate_protocols.py`, CI check scripts |
| `ops/` | Deployment — `deploy.sh`, `check_deployment.py`, `register_agent_build.py`, Prometheus metrics |
| `quality/` | Code quality — `audit_dict_any_usage.py`, `analyze_orphans.py`, `validate_prod_routes.py` |
| `security/` | Accord crypto — `accord_invoke.py` (kill switch), `accord_keygen.py`, `accord_stego.py`, WA keypair generation |
| `templates/` | Template manifest generation and validation |
| `testing/` | Quick API auth test scripts (bash + python) |

## Standalone Scripts

| Script | Purpose |
|--------|---------|
| `analyze_llm_errors.py` | Parse incident logs for rate limits, retries, circuit breaker events |
| `api_telemetry_tool.py` | Test all telemetry endpoints with auth |
| `build_test_wheel.py` | Build platform-specific wheel with bundled GUI JAR (mimics CI) |
| `extract_changelog.py` | Extract release notes from CHANGELOG.md for CI/CD messages |
| `generate_template_manifest.py` | Generate signed manifest of pre-approved agent templates |
| `he300_accuracy_test.py` | Run HE-300 ethical scenarios against live agent via A2A |
| `introspect_memory.py` | Profile Python memory usage of running CIRIS agent |
| `ios_screenshot.swift` | Swift tool for iOS device screenshots |
| `py310_compat_checker.py` | Scan for Python 3.11+ features that break 3.10 compat |
| `screenshot.py` | Capture desktop app screenshots |
| `record_demo_clips.py` | SwiftCapture video recording + test automation for demo clips |
| `test_desktop_wipe_setup.sh` | Desktop E2E: wipe → setup wizard → HA adapter → verify |
| `test_setup_ui.py` | Playwright-based setup wizard UI test |
| `update_ciris_verify.py` | Update CIRISVerify binaries and Python bindings for Android/iOS |

## Key Workflows

```bash
# Daily dev
python3 -m tools.grace morning        # Start day
python3 -m tools.grace status         # Health check
python3 -m tools.grace ci             # CI status (10min throttle)

# Before commit
python3 -m tools.grace precommit      # Lint + safety checks
python3 -m tools.grace fix            # Auto-fix issues

# QA (server auto-managed)
python3 -m tools.qa_runner             # Run all tests
python3 -m tools.qa_runner auth agent  # Specific modules

# Version bump (ALWAYS after significant changes)
python3 tools/dev/bump_version.py patch|minor|major

# Desktop E2E (wipe → setup wizard → HA adapter → verify)
bash tools/test_desktop_wipe_setup.sh

# Desktop app testing
python3 -m tools.qa_runner.modules.web_ui desktop

# iOS E2E (via test automation server + iproxy)
xcrun devicectl device process launch -d $DEVICE_ID \
  --terminate-existing --environment-variables '{"CIRIS_TEST_MODE":"true"}' ai.ciris.mobile
iproxy 18091 8091 -u $IDEVICE_ID &
curl http://127.0.0.1:18091/health  # Test automation on iOS

# Demo clip recording (SwiftCapture + test automation)
python3 tools/record_demo_clips.py --launch --login -o ~/demo_clips/

# Mobile log pull
python3 -m tools.qa_runner.modules.mobile pull-logs
```
