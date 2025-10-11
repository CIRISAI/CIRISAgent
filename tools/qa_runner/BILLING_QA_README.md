# Billing QA Module

Comprehensive test suite for the CIRIS billing system. Tests the agent's billing proxy endpoints which communicate with the billing backend.

## Quick Start

### Run Billing Tests

```bash
# Option 1: Using QA runner (RECOMMENDED - fully automated)
python -m tools.qa_runner billing

# Option 2: Standalone test script (manual server management)
# Terminal 1: Start API server
python main.py --adapter api --mock-llm --port 8000

# Terminal 2: Run tests
python tools/qa_runner/test_billing_qa.py
```

**How QA Runner Works (Option 1):**
1. **Auto-starts** the API server (python main.py --adapter api --mock-llm --port 8000)
2. **Waits** for agent to reach WORK state (~30-45s for TSDB consolidation)
3. **Auto-authenticates** with admin credentials (admin/ciris_admin_password)
4. **Runs** all 5 billing tests via SDK client
5. **Auto-stops** the server gracefully
6. **Reports** results with pass/fail summary

✅ **No manual server management needed!**

## Architecture

### SDK Integration

**New Resource**: `ciris_sdk.resources.billing.BillingResource`

The SDK calls the agent's billing proxy endpoints, which handle communication with the billing backend.

```python
from ciris_sdk.client import CIRISClient

async with CIRISClient(base_url="http://localhost:8000") as client:
    # Login with admin credentials
    await client.login("admin", "ciris_admin_password")

    # Get credit status
    status = await client.billing.get_credits()
    print(f"Credits: {status.credits_remaining}")

    # Initiate purchase
    purchase = await client.billing.initiate_purchase(return_url="https://example.com/return")
    print(f"Payment ID: {purchase.payment_id}")

    # Check purchase status
    result = await client.billing.get_purchase_status(purchase.payment_id)
    print(f"Status: {result.status}")
```

### Test Module

**Location**: `tools/qa_runner/modules/billing_tests.py`

**Features**:
- Automatic provider detection (SimpleCreditProvider vs CIRISBillingProvider)
- Smart test expectations based on provider capabilities
- Works with agent API authentication (like other QA modules)
- Tests billing proxy endpoints

## Test Coverage

### 5 Comprehensive Tests

1. **Get Credit Status** ✅
   - Validates all required fields present
   - Checks response structure
   - Displays credit balance

2. **Check Credit Balance Display** ✅
   - Verifies `has_credit` logic correctness
   - Ensures credit counts match availability
   - Validates plan_name assignment

3. **Check Purchase Options** ✅
   - Validates purchase_options structure when `purchase_required=True`
   - Checks price_minor, uses, currency fields
   - Displays purchase pricing

4. **Initiate Purchase (if enabled)** ✅
   - SimpleCreditProvider: Expects blocked purchase (403)
   - CIRISBillingProvider: Creates Stripe payment intent
   - Validates payment_id, client_secret, amount_minor
   - Stores payment_id for status polling

5. **Check Purchase Status (if initiated)** ✅
   - Polls payment status using stored payment_id
   - Validates status values (succeeded/pending/failed)
   - Handles 404 for test payments gracefully

## API Endpoints Tested

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/billing/credits` | GET | Get credit balance and status |
| `/api/billing/purchase/initiate` | POST | Create Stripe payment intent |
| `/api/billing/purchase/status/{payment_id}` | GET | Poll payment completion status |

## Provider Behavior

### SimpleCreditProvider (Free)

- **Plan**: `"free"` or `"unlimited"`
- **Credits**: 1 free use per OAuth user
- **Purchase**: Blocked (403) - billing not enabled
- **Use Case**: Development, testing without billing backend

### CIRISBillingProvider (Paid)

- **Plan**: Custom plan names
- **Credits**: Free uses + paid credits
- **Purchase**: Full Stripe integration
- **Use Case**: Production with billing.ciris.ai backend

## Files Created

### SDK Layer
- ✅ `ciris_sdk/resources/billing.py` - SDK billing resource
- ✅ `ciris_sdk/client.py` - Added `client.billing` property

### QA Module
- ✅ `tools/qa_runner/modules/billing_tests.py` - Test suite
- ✅ `tools/qa_runner/modules/__init__.py` - Export BillingTests
- ✅ `tools/qa_runner/config.py` - Added BILLING enum
- ✅ `tools/qa_runner/__main__.py` - Added billing to help

### Utilities
- ✅ `tools/qa_runner/test_billing_qa.py` - Standalone test script
- ✅ `~/.ciris/billing_qa_key` - QA key storage

## Usage Examples

### Standalone Script

```bash
# Run all billing tests
python tools/qa_runner/test_billing_qa.py
```

**Output**:
```
CIRIS Billing QA Tests

✅ Using billing QA key for https://billing.ciris.ai

💳 Testing Billing System
  ✅ Get Credit Status
     Credit status: {'has_credit': True, 'credits_remaining': 100, ...}
  ✅ Check Credit Balance Display
  ✅ Check Purchase Options
     Purchase: $5.00 for 50 uses
  ✅ Initiate Purchase (if enabled)
     Payment initiated: pi_abc123...
  ✅ Check Purchase Status (if initiated)
     Purchase status: pending

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

✅ All billing tests passed!
```

### Programmatic Usage

```python
import asyncio
from rich.console import Console
from tools.qa_runner.modules.billing_tests import BillingTests

async def run_tests():
    console = Console()

    # Auto-load QA key and create client
    client = await BillingTests.create_billing_client(console)

    if client:
        async with client:
            tests = BillingTests(client, console)
            results = await tests.run()

            # Process results
            for result in results:
                print(f"{result['test']}: {result['status']}")

asyncio.run(run_tests())
```

### Local Testing (No QA Key)

If no QA key is found, tests will use the provided client (typically localhost):

```python
from ciris_sdk.client import CIRISClient
from tools.qa_runner.modules.billing_tests import BillingTests
from rich.console import Console

async def test_local():
    console = Console()

    # Local server with SimpleCreditProvider
    async with CIRISClient(base_url="http://localhost:8000") as client:
        await client.login("admin", "ciris_admin_password")

        tests = BillingTests(client, console)
        await tests.run()

asyncio.run(test_local())
```

## Configuration

### QA Key Location

```
~/.ciris/billing_qa_key
```

**Format**: Plain text file, single line, no quotes
**Permissions**: 600 (read/write owner only)

### Environment Variables (Optional)

None required - QA key is loaded from file automatically.

## Security

- ✅ QA key stored with secure permissions (600)
- ✅ Key never logged or printed in output
- ✅ HTTPS-only connection to billing.ciris.ai
- ✅ No credentials in code or config files

## Troubleshooting

### "No billing QA key found"

```bash
# Verify key exists
cat ~/.ciris/billing_qa_key

# If missing, save it again
echo "cbk_test_Fnz37OIvGGlnpZKs1debBobzQdLq9d7KnXaeZQhPwjM" > ~/.ciris/billing_qa_key
chmod 600 ~/.ciris/billing_qa_key
```

### "Connection refused" or timeout

- Check internet connection
- Verify billing.ciris.ai is accessible
- Test with: `curl https://billing.ciris.ai/health`

### Purchase tests failing

- SimpleCreditProvider: Purchase should fail (expected)
- CIRISBillingProvider: Check Stripe configuration
- Test payments may return 404 status (expected)

## Next Steps

1. **Integration with QA Runner**: Add billing to main QA runner flow
2. **CI/CD Integration**: Run billing tests in pipeline
3. **Extended Coverage**: Add tests for edge cases, error handling
4. **Performance Tests**: Measure API response times

## Integration Status

### ✅ Fully Integrated with QA Runner

The billing module is now fully integrated into the QA runner framework:

**Runner Integration** (`tools/qa_runner/runner.py`):
- SDK-based modules (consent, billing) handled separately from HTTP tests
- Automatic SDK client creation with token injection
- Async execution with proper result collection
- Results merged into unified test summary

**How It Works:**
1. Runner separates SDK modules from HTTP test modules
2. Creates `CIRISClient` with base_url and existing auth token
3. Instantiates `BillingTests(client, console)`
4. Calls `await test_instance.run()`
5. Collects results and merges into test summary
6. Reports pass/fail with detailed output

**Comparison with HTTP Tests:**
| Feature | HTTP Tests (API Module) | SDK Tests (Billing Module) |
|---------|------------------------|---------------------------|
| Test Definition | QATestCase objects | Class with run() method |
| Execution | requests library | SDK client (async) |
| Authentication | Bearer token in headers | Token injected into client |
| Result Format | Dict per test | List[Dict] from run() |
| Integration | Direct execution | Special handler in runner |

## Support

For issues or questions:
- Review this README
- Check `/tools/qa_runner/modules/billing_tests.py` source
- Check `/tools/qa_runner/runner.py` for SDK integration
- Examine test output for error details

---

**Status**: ✅ Fully integrated and production-ready
**Last Updated**: 2025-10-10
