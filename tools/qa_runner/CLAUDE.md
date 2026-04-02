# QA Runner - CLAUDE.md

Comprehensive test framework for validating CIRIS API functionality. Manages server lifecycle, authentication, SSE-based task monitoring, and 40+ modular test suites.

## Quick Start

```bash
# Run everything (server auto-managed)
python3 -m tools.qa_runner

# Specific modules
python3 -m tools.qa_runner auth agent handlers

# Status dashboard
python3 -m tools.qa_runner --status
python3 -m tools.qa_runner --failing
python3 -m tools.qa_runner --not-run

# Multi-backend (SQLite + PostgreSQL)
python3 -m tools.qa_runner auth --database-backends sqlite postgres --parallel-backends

# Verbose debugging
python3 -m tools.qa_runner handlers --verbose
```

## Server Lifecycle (Automatic)

The QA runner **automatically starts and stops** the CIRIS API server. Do NOT manually start a server before running tests.

### How It Works (`server.py` → `APIServerManager`)

1. **Kill existing**: Finds and kills any process on the configured port
2. **Data wipe**: Optionally cleans databases for a fresh slate
3. **Start server**: Spawns `python3 main.py --adapter api --mock-llm --port <port>`
4. **Health poll**: Waits for `/v1/system/health` to return 200
5. **Authenticate**: Logs in with admin credentials, stores token
6. **Run tests**: Executes selected modules
7. **Teardown**: Kills server process

### Mock Logshipper

`server.py` also starts a mock logshipper (`MockLogshipperHandler`) that receives Accord traces from the agent during testing. Traces are stored and can be validated by `accord_metrics_tests.py`.

### If Server Won't Start

```bash
# Kill orphaned servers
pkill -f "python3 main.py --adapter api"
# or
lsof -ti:8080 | xargs kill -9

# Manual start for debugging
python3 main.py --adapter api --mock-llm --port 8080
```

## Architecture

```
__main__.py          CLI entry point — parses args, selects modules
    ↓
runner.py            QARunner — orchestrates server + modules + reporting
    ↓
server.py            APIServerManager — process lifecycle, auth, health
    ↓
modules/             40+ test modules (each inherits BaseTestModule)
    ├── *_tests.py   Individual test suites
    ├── mobile/      Android/iOS device testing
    └── web_ui/      Desktop app + browser testing
```

### Key Files

| File | Purpose |
|------|---------|
| `__main__.py` | CLI argument parsing, module selection, status dashboard |
| `runner.py` | `QARunner` class — runs modules, auto-configures adapters per module needs |
| `server.py` | `APIServerManager` — start/stop server, auth, mock logshipper |
| `config.py` | `QAConfig` (urls, ports, timeouts), `QAModule` enum (all module names) |
| `status_tracker.py` | Tracks pass/fail per module across runs |
| `qa_api_test.py` | Legacy API test client |
| `qa_test_sdk.py` | SDK-based test client |
| `mcp_test_server.py` | Mock MCP server for MCP adapter tests |

### Auto-Adapter Configuration

The runner automatically configures adapters based on which modules are selected:
- `reddit` module → adapter set to `api,reddit`
- `sql_external_data` / `dsar_multi_source` → adapter set to `api,external_data_sql`

## SSE-Based Task Completion Monitoring

**Critical**: Tests must wait for `TASK_COMPLETE` action via SSE before proceeding to the next test.

### Why This Matters

Without SSE monitoring:
1. Test N+1 starts before Test N's task completes
2. New observation arrives in same channel as active task
3. `updated_info_available` flag gets set on the task
4. `UpdatedStatusConscience` triggers, forcing PONDER override
5. Task cycles through retries until DEFER at depth limit
6. Test fails with "Still processing" or wrong response

### FilterTestHelper (`modules/filter_test_helper.py`)

Monitors SSE stream at `/v1/system/runtime/reasoning-stream`:

```python
helper = FilterTestHelper(base_url, token, verbose=True)
helper.start_monitoring()

# Submit message...
submission = await client.agent.submit_message(message)

# Wait for completion
completed = helper.wait_for_task_complete(timeout=30.0)

# Get response from history
history = await client.agent.get_history(limit=10)
```

SSE event structure:
```json
{
  "events": [{
    "event_type": "action_result",
    "action_executed": "task_complete",
    "execution_success": true,
    "task_id": "...",
    "thought_id": "..."
  }]
}
```

### Token Retrieval for SSE

```python
transport = getattr(self.client, "_transport", None)
token = getattr(transport, "api_key", None) if transport else None
```

## Module Groups

```bash
python3 -m tools.qa_runner api_full         # All API modules
python3 -m tools.qa_runner handlers_full    # All handler modules
python3 -m tools.qa_runner all              # Everything
```

See `modules/CLAUDE.md` for the full module inventory.

## Common Issues

| Problem | Fix |
|---------|-----|
| "TASK_COMPLETE not seen in 30.0s" | SSE connection issue — check token, check mock LLM follow-up handling |
| "Still processing" response | Previous test didn't complete — SSE monitoring not working |
| Tests getting "defer" responses | Follow-up thoughts not reaching TASK_COMPLETE — check `responses.py` |
| Server won't start | Kill orphaned process: `pkill -f "python3 main.py"` |
| "Address already in use" | `lsof -ti:8080 \| xargs kill -9` |
| Auth token expired | Runner auto-re-authenticates after logout/refresh tests |

## Desktop UI E2E Testing

In addition to API-level tests, CIRIS supports end-to-end desktop UI testing
via the test automation HTTP server (port 8091). This is separate from the QA
runner's API tests.

**E2E test script:**
```bash
# Full wipe → setup wizard → verify consent/partnership/lens-identifier
bash tools/test_desktop_wipe_setup.sh
```

**What the E2E test validates:**
1. Clean launch (Login screen)
2. Login with default admin
3. Factory reset (wipe data, preserve signing keys)
4. Server restart and first-run detection
5. Setup wizard: location, LLM (OpenRouter), traces opt-in, account creation
6. Founding partnership consent (PARTNERED stream)
7. Lens-identifier endpoint (signing key based)
8. .env configuration (no mock LLM, correct provider)

**Home Assistant adapter setup (manual + scripted):**
1. Navigate to Adapters → click + → select home_assistant
2. mDNS discovery finds HA instances automatically
3. OAuth via browser (emoore/ciristest1 for test HA)
4. Feature selection (device control, automations, sensors, notifications)
5. Camera selection (optional)
6. Confirm → adapter loaded and running

**Key tools:**
- `tools/test_desktop_wipe_setup.sh` — Full desktop E2E test script
- `tools/record_demo_clips.py` — SwiftCapture video recording + automation
- Test automation API at `:8091` (all platforms when `CIRIS_TEST_MODE=true`)

**Platform-specific automation:**

| Platform | Test Server | Screenshots | Mouse Events | Notes |
|----------|------------|-------------|--------------|-------|
| Desktop | Ktor CIO `:8091` | java.awt.Robot | java.awt.Robot | Full automation |
| iOS | POSIX sockets `:8091` | pymobiledevice3 | N/A | Via iproxy; 2s delay between inputs |
| Android | TODO (Ktor CIO) | adb screencap | N/A | Currently use Espresso |

**iOS E2E automation:**
```bash
# Launch with test mode
xcrun devicectl device process launch -d $DEVICE_ID \
  --terminate-existing \
  --environment-variables '{"CIRIS_TEST_MODE":"true"}' ai.ciris.mobile

# Port forward
iproxy 18091 8091 -u $IDEVICE_ID &
iproxy 18080 8080 -u $IDEVICE_ID &

# Drive UI (same HTTP endpoints as desktop)
curl http://127.0.0.1:18091/screen
curl -X POST http://127.0.0.1:18091/click -d '{"testTag":"btn_local_login"}'

# HA adapter: API-driven with OAuth callback forwarding
# See mobile/CLAUDE.md for full iOS E2E workflow
```

**iOS-specific gotchas:**
- `--terminate-existing` required to kill previous app instance
- Text input needs 2s delay between fields (StateFlow propagation)
- OAuth callbacks go to `127.0.0.1:8080` — forward via `iproxy 18080`
- API adapter config uses nested `{"step_data":{...}}` format
- `.env` must contain `CIRIS_CONFIGURED="true"` to not be first-run
- `pymobiledevice3 tunneld` must be running for screenshots

## Reporting

Test results are saved to `qa_reports/` with timestamps. Use `--json` for machine-readable output. The status tracker persists results across runs for the `--status` dashboard.
