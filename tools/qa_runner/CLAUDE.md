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

## Reporting

Test results are saved to `qa_reports/` with timestamps. Use `--json` for machine-readable output. The status tracker persists results across runs for the `--status` dashboard.
