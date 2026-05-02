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

### Live-Lens Trace Capture (Local Tee) — debugging gold

When a QA run uses `--live-lens` (live mode against the real lens server, not the mock logshipper), the QA runner auto-enables the **local-tee** feature in `accord_metrics`. Every batch payload that gets POSTed to the lens is *also* written to disk locally.

**Default location:** `/tmp/qa-runner-lens-traces-<UTC-iso>/`

The QA runner prints the path during startup:

```
   CIRIS_ACCORD_METRICS_ENDPOINT=https://lens.ciris-services-1.ai/lens-api/api/v1
   CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR=/tmp/qa-runner-lens-traces-20260501T180000Z
```

Files in that dir are named `accord-batch-<UTC-iso-microseconds>-<NNNN>.json`, sortable by timestamp, one file per batch flushed to lens.

**Why this matters for troubleshooting** — the local copies contain the *exact* JSON the lens received: full reasoning event stream, every `@streaming_step` broadcast, every `LLM_CALL` event with prompt/completion bytes + duration + status enum, every conscience scalar, every CIRISVerify attestation field. When a sweep produces unexpected behavior — defer when it shouldn't, fabrication that the EH bullet should have caught, register-break that the IRIS-C BOUNDARY INTEGRITY principle missed — the answer lives in these batch files.

**Common debug recipes:**

```bash
# What did the agent ship to lens during the last QA run?
ls -lt /tmp/qa-runner-lens-traces-*/  | head

# Find the trace for a specific thought_id (extract from qa_runner.log first)
grep -l "th_abc123" /tmp/qa-runner-lens-traces-*/accord-batch-*.json

# What conscience signals fired on a particular thought?
python3 -c "
import json, sys
for f in sys.argv[1:]:
    payload = json.load(open(f))
    for ev in payload['events']:
        if ev.get('thought_id') == 'th_abc123' and 'conscience' in ev.get('event_type', '').lower():
            print(f, ev['event_type'], ev.get('coherence', ev.get('entropy_reduction_ratio')))
" /tmp/qa-runner-lens-traces-*/accord-batch-*.json

# Why did the agent defer? Find the action_result + the conscience scalars that preceded it
python3 -c "
import json, glob
events = []
for f in sorted(glob.glob('/tmp/qa-runner-lens-traces-*/accord-batch-*.json')):
    events.extend(json.load(open(f))['events'])
for ev in events:
    if ev.get('action_executed') == 'defer':
        print('DEFER:', ev['thought_id'], ev.get('execution_reason'))
"

# Replay a captured trace against persist (the new wire-format ingest path)
curl -X POST "$PERSIST_URL/v1/traces/ingest" \
     -H "Content-Type: application/json" \
     -d @/tmp/qa-runner-lens-traces-20260501T180000Z/accord-batch-20260501T180012345678-0001.json
```

**Operator override:** if you want the copies routed somewhere other than `/tmp/`, pre-set `CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR` before invoking the QA runner. The runner respects the override.

```bash
CIRIS_ACCORD_METRICS_LOCAL_COPY_DIR=~/qa-debug/$(date +%Y%m%d) \
    python3 -m tools.qa_runner model_eval --live ...
```

**Default-off in production:** the env var is unset by default. Production agents shipping to lens don't tee unless the operator opts in. The QA runner is the only caller that sets the var automatically.

**Best-effort contract:** disk failures (full disk, permission denied, non-serializable event) are logged at WARNING with a "POST unaffected" suffix. The lens always gets the data even if the local tee fails. Never blocks the live ship.

See `ciris_adapters/ciris_accord_metrics/services.py` (`_send_events_batch`) for the implementation, `tests/adapters/accord_metrics/test_local_copy_tee.py` for the contract pinned in tests.

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

### Adding New Modules

When creating a new test module, you must update **THREE places** in `runner.py`:

1. **Import the module** (~line 893):
   ```python
   from .modules.my_new_tests import MyNewTests
   ```

2. **Add to `module_map`** (~line 954):
   ```python
   QAModule.MY_NEW: MyNewTests,
   ```

3. **Add to `sdk_modules` list** (~line 233):
   ```python
   QAModule.MY_NEW,
   ```

**CRITICAL**: If you forget step 3, your module will be silently skipped! The `sdk_modules` list determines which modules are routed to `_run_sdk_modules()`. Modules not in this list are treated as HTTP test modules and may not run.

Also add the enum to `config.py`:
```python
MY_NEW = "my_new"  # Description of what it tests
```

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
