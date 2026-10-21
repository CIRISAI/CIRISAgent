# SDK Module Integration for QA Runner

**Date**: 2025-10-10
**Status**: ✅ Complete and functional

## Overview

Integrated SDK-based test modules (Billing, Consent) into the QA runner framework, enabling unified test execution with automated server lifecycle management.

## Architecture

### Two Test Module Patterns

#### Pattern 1: HTTP Test Modules
**Examples**: `APITestModule`, `HandlerTestModule`, `FilterTestModule`

**Structure**:
```python
class APITestModule:
    @staticmethod
    def get_auth_tests() -> List[QATestCase]:
        return [
            QATestCase(
                name="Login with valid credentials",
                module=QAModule.AUTH,
                endpoint="/v1/auth/login",
                method="POST",
                payload={"username": "admin", "password": "qa_test_password_12345"},
                expected_status=200,
                requires_auth=False,
            ),
            # ... more test cases
        ]
```

**Execution**: Runner makes HTTP requests using `requests` library

#### Pattern 2: SDK Test Modules (NEW)
**Examples**: `BillingTests`, `ConsentTests`

**Structure**:
```python
class BillingTests:
    def __init__(self, client: CIRISClient, console: Console):
        self.client = client
        self.console = console
        self.results = []

    async def run(self) -> List[Dict]:
        """Run all tests and return results."""
        # Execute tests using SDK client
        # Return list of dicts with test results
```

**Execution**: Runner creates SDK client, injects auth token, calls `run()` method

## Implementation

### Files Modified

#### 1. `tools/qa_runner/runner.py`

**Added SDK module handling** (lines 83-106):
```python
# Separate SDK-based modules from HTTP test modules
sdk_modules = [QAModule.CONSENT, QAModule.BILLING]
http_modules = [m for m in modules if m not in sdk_modules]
sdk_test_modules = [m for m in modules if m in sdk_modules]

# Run HTTP tests
if all_tests:
    self.console.print(f"\n📋 Running {len(all_tests)} HTTP test cases...")
    if self.config.parallel_tests:
        success = self._run_parallel(all_tests)
    else:
        success = self._run_sequential(all_tests)

# Run SDK-based tests
if sdk_test_modules:
    sdk_success = self._run_sdk_modules(sdk_test_modules)
    success = success and sdk_success
```

**Added `_run_sdk_modules()` method** (lines 361-419):
```python
def _run_sdk_modules(self, modules: List[QAModule]) -> bool:
    """Run SDK-based test modules (consent, billing, etc.)."""
    from ciris_sdk.client import CIRISClient
    from .modules import ConsentTests, BillingTests

    all_passed = True

    # Map modules to test classes
    module_map = {
        QAModule.CONSENT: ConsentTests,
        QAModule.BILLING: BillingTests,
    }

    async def run_module(module: QAModule):
        """Run a single SDK module."""
        test_class = module_map.get(module)
        if not test_class:
            self.console.print(f"[red]❌ Unknown SDK module: {module.value}[/red]")
            return False

        # Create SDK client with authentication
        async with CIRISClient(base_url=self.config.base_url) as client:
            # Manually set the token (skip login since we already have it)
            client._transport._session.headers["Authorization"] = f"Bearer {self.token}"

            # Instantiate and run test module
            test_instance = test_class(client, self.console)
            results = await test_instance.run()

            # Store results in runner's results dict
            for result in results:
                test_name = result["test"]
                passed = "PASS" in result["status"]

                self.results[f"{module.value}::{test_name}"] = {
                    "success": passed,
                    "status": result["status"],
                    "error": result.get("error"),
                    "duration": 0.0,  # SDK tests don't track individual durations
                }

            # Check if all tests passed
            return all(r["status"] == "✅ PASS" for r in results)

    # Run all SDK modules sequentially (they use async internally)
    for module in modules:
        self.console.print(f"\n📋 Running {module.value} SDK tests...")
        try:
            module_passed = asyncio.run(run_module(module))
            if not module_passed:
                all_passed = False
        except Exception as e:
            self.console.print(f"[red]❌ Error running {module.value}: {e}[/red]")
            import traceback
            if self.config.verbose:
                self.console.print(f"[dim]{traceback.format_exc()}[/dim]")
            all_passed = False

    return all_passed
```

#### 2. `tools/qa_runner/BILLING_QA_README.md`

Updated with:
- Corrected quick start instructions explaining QA runner automation
- Full integration status section
- Comparison table between HTTP and SDK test patterns
- Architecture details

### Files Already Present

These files were previously created and are now fully integrated:

- ✅ `ciris_sdk/resources/billing.py` - SDK billing resource
- ✅ `tools/qa_runner/modules/billing_tests.py` - Billing test module
- ✅ `tools/qa_runner/modules/consent_tests.py` - Consent test module
- ✅ `tools/qa_runner/config.py` - Already had BILLING and CONSENT enums

## Usage

### Running Billing Tests

```bash
# Fully automated - no server management needed
python -m tools.qa_runner billing

# Runs both consent and billing together
python -m tools.qa_runner consent billing

# Include in full test suite
python -m tools.qa_runner api_full billing
```

### What Happens

1. **Server Startup** (30-45s)
   - Starts `python main.py --adapter api --mock-llm --port 8000`
   - Waits for WORK state
   - Records incidents log position

2. **Authentication**
   - Logs in with admin/qa_test_password_12345
   - Stores JWT token

3. **HTTP Tests** (if any)
   - Executes standard API endpoint tests
   - Uses `requests` library

4. **SDK Tests**
   - Creates `CIRISClient(base_url="http://localhost:8000")`
   - Injects auth token into client
   - Instantiates test class (e.g., `BillingTests(client, console)`)
   - Calls `await test_instance.run()`
   - Collects and merges results

5. **Reporting**
   - Shows test summary
   - Reports incidents
   - Generates JSON/HTML reports (if enabled)

6. **Server Shutdown**
   - Graceful termination (15s timeout)
   - Force kill if needed

## Example Output

```
🧪 Starting QA Tests
Modules: billing

📋 INCIDENTS LOG STATUS (STARTUP):
   📁 Log: /home/emoore/CIRISAgent/logs/incidents_latest.log
   📊 Size: 12,345 bytes
   ⚠️  Warnings: 0
   🚫 Errors: 0
   💥 Critical: 0
✅ No critical issues found

🚀 Starting API server...
✅ API server started successfully
✅ Authentication successful

📋 Running billing SDK tests...

💳 Testing Billing System
  ✅ Get Credit Status
     Credit status: {'has_credit': True, 'credits_remaining': 100, ...}
  ✅ Check Credit Balance Display
  ✅ Check Purchase Options
     Purchase: $5.00 for 50 uses
  ✅ Initiate Purchase (if enabled)
     Purchase unavailable: Billing not enabled
  ✅ Check Purchase Status (if initiated)
     Skipping: No payment to check

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Test                           ┃ Status ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━┩
│ Get Credit Status              │ ✅ PASS│
│ Check Credit Balance Display   │ ✅ PASS│
│ Check Purchase Options         │ ✅ PASS│
│ Initiate Purchase (if enabled) │ ✅ PASS│
│ Check Purchase Status          │ ✅ PASS│
└────────────────────────────────┴────────┘

Passed: 5/5

📋 INCIDENTS LOG STATUS (POST-TEST):
   📁 Log: /home/emoore/CIRISAgent/logs/incidents_latest.log
   📊 Size: 12,456 bytes
   ⚠️  Warnings: 0
   🚫 Errors: 0
   💥 Critical: 0
✅ No critical issues found

🛑 Stopping API server...
✅ Server stopped gracefully

┏━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Metric       ┃ Value ┃
┡━━━━━━━━━━━━━━╇━━━━━━━┩
│ Total Tests  │ 5     │
│ Passed       │ 5     │
│ Failed       │ 0     │
│ Success Rate │ 100%  │
│ Duration     │ 52.3s │
└──────────────┴───────┘

✅ All tests passed!

✅ No critical incidents - tests completed cleanly!
```

## Benefits

### For Developers

- **Single command** to run all tests
- **No manual server management**
- **Unified reporting** across HTTP and SDK tests
- **Consistent authentication** handling
- **Incident tracking** throughout test execution

### For CI/CD

- **Exit code 0 on success**, 1 on failure
- **JSON reports** for parsing
- **HTML reports** for human review
- **Incident detection** prevents false passes
- **Parallel execution** support (for HTTP tests)

## Adding New SDK Modules

To add a new SDK-based test module:

1. **Create test module** in `tools/qa_runner/modules/your_module.py`:
```python
class YourModuleTests:
    def __init__(self, client: CIRISClient, console: Console):
        self.client = client
        self.console = console
        self.results = []

    async def run(self) -> List[Dict]:
        """Run all tests."""
        tests = [
            ("Test Name", self.test_something),
        ]

        for name, test_func in tests:
            try:
                await test_func()
                self.results.append({"test": name, "status": "✅ PASS", "error": None})
                self.console.print(f"  ✅ {name}")
            except Exception as e:
                self.results.append({"test": name, "status": "❌ FAIL", "error": str(e)})
                self.console.print(f"  ❌ {name}: {str(e)[:100]}")

        return self.results

    async def test_something(self):
        """Test implementation."""
        result = await self.client.your_resource.some_method()
        if not result:
            raise ValueError("Test failed")
```

2. **Register in config** (`tools/qa_runner/config.py`):
```python
class QAModule(Enum):
    YOUR_MODULE = "your_module"

# In get_module_tests():
elif module == QAModule.YOUR_MODULE:
    return []  # Will be handled separately by runner
```

3. **Add to runner** (`tools/qa_runner/runner.py`):
```python
# In run() method:
sdk_modules = [QAModule.CONSENT, QAModule.BILLING, QAModule.YOUR_MODULE]

# In _run_sdk_modules():
module_map = {
    QAModule.CONSENT: ConsentTests,
    QAModule.BILLING: BillingTests,
    QAModule.YOUR_MODULE: YourModuleTests,
}
```

4. **Export from modules** (`tools/qa_runner/modules/__init__.py`):
```python
from .your_module import YourModuleTests

__all__ = [..., "YourModuleTests"]
```

Done! Run with `python -m tools.qa_runner your_module`

## Technical Details

### Token Injection

The SDK client is created with the runner's existing auth token:

```python
async with CIRISClient(base_url=self.config.base_url) as client:
    # Manually set the token (skip login since we already have it)
    client._transport._session.headers["Authorization"] = f"Bearer {self.token}"
```

This avoids double-authentication and reuses the same session.

### Result Collection

SDK test results are normalized into the runner's result format:

```python
self.results[f"{module.value}::{test_name}"] = {
    "success": passed,
    "status": result["status"],
    "error": result.get("error"),
    "duration": 0.0,  # SDK tests don't track individual durations
}
```

This ensures consistent reporting across all test types.

### Async Execution

SDK tests use `asyncio.run()` to execute async test methods:

```python
module_passed = asyncio.run(run_module(module))
```

This isolates each module's async context while maintaining synchronous runner flow.

## Testing the Integration

To verify the integration works:

```bash
# Test billing module alone
python -m tools.qa_runner billing

# Test consent module alone
python -m tools.qa_runner consent

# Test both together
python -m tools.qa_runner consent billing

# Test with verbose output
python -m tools.qa_runner billing --verbose

# Test with reports
python -m tools.qa_runner billing --json --html --report-dir ./test_reports
```

## Known Limitations

1. **No parallel execution for SDK tests** - SDK tests run sequentially due to async nature
2. **No individual duration tracking** - SDK tests report 0.0s duration (overall duration tracked)
3. **Token injection required** - SDK client doesn't support external token injection API

## Future Enhancements

1. **Add duration tracking** to SDK test modules
2. **Support parallel SDK execution** if tests are independent
3. **Add SDK client token injection API** for cleaner integration
4. **Create base class** for SDK test modules to reduce boilerplate
5. **Add retry logic** for flaky SDK tests

---

**Status**: ✅ Complete and functional
**Tested**: Billing and Consent modules working correctly
**Documentation**: Complete with usage examples
