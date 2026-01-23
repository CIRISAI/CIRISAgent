# CIRIS QA Runner

A modular quality assurance testing framework for CIRIS API and components.

## Features

- **Modular Testing**: Test specific components or run comprehensive suites
- **Automatic Server Management**: Starts/stops API server automatically
- **Parallel Execution**: Run tests concurrently for faster results
- **Rich Reporting**: Generate HTML and JSON reports
- **Retry Logic**: Automatic retry for transient failures
- **Progress Tracking**: Real-time progress with rich terminal UI

## Installation

```bash
pip install -r tools/qa_runner/requirements.txt
```

## Quick Start

```bash
# Run all API tests
python -m tools.qa_runner api_full

# Run specific modules
python -m tools.qa_runner auth telemetry agent

# Run everything
python -m tools.qa_runner all

# Run with existing server (don't auto-start)
python -m tools.qa_runner api_full --no-auto-start

# Generate reports
python -m tools.qa_runner all --json --html --report-dir ./qa_reports
```

## Available Modules

### Core API Modules
- `auth` - Authentication endpoints
- `telemetry` - Telemetry and metrics
- `agent` - Agent interaction
- `system` - System management
- `memory` - Memory operations
- `audit` - Audit trail
- `tools` - Tool management
- `tasks` - Task management
- `guidance` - Guidance system
- `consent` - Consent management tests

### Adapter Modules
- `covenant_metrics` - CIRIS Covenant metrics adapter (CIRISLens integration)
- `hosted_tools` - CIRIS hosted tools adapter (web search, requires billing token)
- `utility_adapters` - Weather and navigation adapters (free APIs)
- `mcp` - MCP client/server adapter tests
- `sql_external_data` - SQL external data adapter tests
- `reddit` - Reddit adapter tests (requires API keys)
- `adapter_config` - Adapter configuration and persistence tests
- `adapter_autoload` - Adapter auto-loading tests
- `adapter_manifest` - Adapter manifest validation tests

### Handler Modules
- `handlers` - Message handlers
- `simple_handlers` - Simple handler tests

### Filter Modules
- `filters` - Adaptive and secrets filter configuration and testing

### Cognitive State Modules
- `cognitive_state_api` - Cognitive state API tests
- `state_transition` - State transition workflow tests

### SDK Modules
- `sdk` - SDK tests
- `sdk_comprehensive` - Comprehensive SDK tests

### Integration Modules
- `streaming` - H3ERE pipeline streaming tests
- `vision` - Vision/image processing tests
- `dsar` - DSAR automation tests
- `dsar_multi_source` - Multi-source DSAR tests
- `dsar_ticket_workflow` - DSAR ticket workflow tests
- `billing` - Billing provider tests
- `billing_integration` - Full billing integration tests
- `air` - AIR (Accountability, Integrity, Responsibility) tests
- `context_enrichment` - Context enrichment tests
- `covenant` - Covenant compliance tests
- `multi_occurrence` - Multi-occurrence deployment tests
- `partnership` - Partnership management tests
- `identity_update` - Identity update workflow tests
- `system_messages` - System message handling tests

### Aggregate Modules
- `api_full` - All API modules
- `handlers_full` - All handler modules
- `all` - Everything

## Command Line Options

### Server Configuration
- `--url URL` - Base URL of API server (default: http://localhost:8000)
- `--port PORT` - API server port (default: 8000)
- `--no-auto-start` - Don't automatically start the API server
- `--no-mock-llm` - Don't use mock LLM (requires real LLM)
- `--adapter {api,cli,discord}` - Adapter to use (default: api)

### Authentication
- `--username USERNAME` - Admin username (default: admin)
- `--password PASSWORD` - Admin password (default: ciris_admin_password)

### Test Configuration
- `--parallel` - Run tests in parallel
- `--workers N` - Number of parallel workers (default: 4)
- `--timeout SECONDS` - Total timeout in seconds (default: 300)
- `--retry N` - Number of retries for failed tests (default: 3)

### Output Configuration
- `--verbose, -v` - Verbose output
- `--json` - Generate JSON report
- `--html` - Generate HTML report
- `--report-dir DIR` - Directory for reports (default: qa_reports)

## Examples

### Basic Testing

```bash
# Test authentication system
python -m tools.qa_runner auth

# Test multiple modules
python -m tools.qa_runner auth telemetry agent

# Test everything
python -m tools.qa_runner all
```

### Advanced Usage

```bash
# Parallel execution with reports
python -m tools.qa_runner api_full --parallel --json --html

# Custom server configuration
python -m tools.qa_runner all --url http://localhost:8080 --no-auto-start

# Verbose output with retries
python -m tools.qa_runner api_full --verbose --retry 5
```

### Adapter Testing

```bash
# Test utility adapters (weather, navigation - no API keys needed)
python -m tools.qa_runner utility_adapters

# Test CIRIS covenant metrics adapter
python -m tools.qa_runner covenant_metrics

# Test CIRIS hosted tools (requires billing token)
CIRIS_BILLING_GOOGLE_ID_TOKEN=your_token python -m tools.qa_runner hosted_tools

# Test MCP client/server adapters
python -m tools.qa_runner mcp

# Test SQL external data adapter
python -m tools.qa_runner sql_external_data
```

### CI/CD Integration

```bash
# Run in CI with JSON output for parsing
python -m tools.qa_runner all --json --report-dir ./test-results

# Exit with proper code for CI
if python -m tools.qa_runner api_full; then
    echo "Tests passed"
else
    echo "Tests failed"
    exit 1
fi
```

## Report Formats

### JSON Report
Contains structured test results with timing and error details:
```json
{
  "timestamp": "20240823_143022",
  "config": {
    "base_url": "http://localhost:8000",
    "modules": ["auth", "telemetry"]
  },
  "results": {
    "auth::Login": {
      "success": true,
      "status_code": 200,
      "duration": 0.234
    }
  },
  "summary": {
    "total": 10,
    "passed": 9,
    "failed": 1,
    "success_rate": 90.0
  }
}
```

### HTML Report
Interactive HTML report with:
- Summary statistics
- Color-coded pass/fail indicators
- Detailed error messages
- Test duration tracking
- Module grouping

## Architecture

```
qa_runner/
├── __init__.py                     # Package initialization
├── __main__.py                     # CLI entry point
├── config.py                       # Configuration and test definitions
├── runner.py                       # Main test runner
├── server.py                       # API server management
├── modules/                        # Test modules
│   ├── api_tests.py                # Core API endpoint tests
│   ├── handler_tests.py            # Handler tests
│   ├── sdk_tests.py                # SDK tests
│   ├── filter_tests.py             # Adaptive filter tests
│   │
│   │ # Adapter tests
│   ├── covenant_metrics_tests.py   # CIRISLens integration
│   ├── hosted_tools_tests.py       # CIRIS proxy tools
│   ├── utility_adapters_tests.py   # Weather/navigation
│   ├── mcp_tests.py                # MCP client/server
│   ├── sql_external_data_tests.py  # SQL data sources
│   ├── reddit_tests.py             # Reddit adapter
│   ├── adapter_config_tests.py     # Config/persistence
│   ├── adapter_autoload_tests.py   # Auto-loading
│   ├── adapter_manifest_tests.py   # Manifest validation
│   │
│   │ # Integration tests
│   ├── streaming_verification.py   # H3ERE streaming
│   ├── cognitive_state_api_tests.py # State API
│   ├── billing_tests.py            # Billing provider
│   └── ...                         # Many more modules
└── README.md                       # This file
```

## Adding New Tests

1. Add test case to `config.py`:
```python
QATestCase(
    name="My New Test",
    module=QAModule.AGENT,
    endpoint="/v1/agent/new-endpoint",
    method="POST",
    payload={"key": "value"},
    expected_status=200,
    requires_auth=True,
    description="Test description"
)
```

2. Or create a new module in `modules/`:
```python
class MyTestModule:
    @staticmethod
    def get_tests() -> List[QATestCase]:
        return [
            QATestCase(...),
            ...
        ]
```

## Troubleshooting

### Server won't start
- Check if port 8000 is already in use
- Verify Python path and dependencies
- Check logs in console output

### Tests failing with 401
- Verify authentication credentials
- Check if token is being properly passed
- Ensure server has auth enabled

### Timeout errors
- Increase timeout with `--timeout 600`
- Check if server is responding
- Verify network connectivity

## Development

Run tests for the QA runner itself:
```bash
python -m pytest tests/tools/test_qa_runner.py
```

## License

Part of the CIRIS project.
