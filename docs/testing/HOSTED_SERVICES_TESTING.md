# CIRIS Hosted Services Testing Guide

This document covers testing CIRIS hosted services (billing, proxy, hosted tools) in Docker containers and CI/CD environments.

## Overview

CIRIS provides several hosted services that normally require Android device attestation:

| Service | URL | Purpose |
|---------|-----|---------|
| **Billing** | `billing1.ciris-services-1.ai` | Credit checking, spending, purchases |
| **Proxy** | `proxy1.ciris-services-1.ai` | Web search, LLM proxy |
| **Fallback Billing** | `billing1.ciris-services-2.ai` | EU region failover |
| **Fallback Proxy** | `proxy1.ciris-services-2.ai` | EU region failover |

## Authentication Architecture

### Normal Flow (Android)

```
┌──────────────────────┐
│    Android Device    │
│  ┌────────────────┐  │
│  │ Google Sign-In │──┼──> Google ID Token
│  └────────────────┘  │
│  ┌────────────────┐  │
│  │ Play Integrity │──┼──> Device Attestation
│  └────────────────┘  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│   CIRIS Services     │
│  - Validates token   │
│  - Checks credits    │
│  - Allows API calls  │
└──────────────────────┘
```

1. User signs in with Google on Android
2. Google Play Integrity API provides device attestation
3. App receives Google ID Token
4. Token stored as `CIRIS_BILLING_GOOGLE_ID_TOKEN`
5. All API calls include this token in `Authorization: Bearer <token>`

### Testing Without Android

For Docker/CI testing, you need a **test token** that the billing backend recognizes:

```bash
# Set via environment variable
export CIRIS_BILLING_GOOGLE_ID_TOKEN="<test_token>"

# Or in .env file
CIRIS_BILLING_GOOGLE_ID_TOKEN="<test_token>"

# Or in docker-compose.yml
environment:
  - CIRIS_BILLING_GOOGLE_ID_TOKEN=<test_token>
```

## Token Lookup Priority

The code checks for tokens in this order:

1. `CIRIS_BILLING_GOOGLE_ID_TOKEN` environment variable
2. `GOOGLE_ID_TOKEN` environment variable
3. `.env` file at:
   - `/data/data/ai.ciris.mobile/files/ciris/.env` (Android)
   - `$CIRIS_HOME/.env`
   - `~/.env`
   - `./.env`

## Getting a Test Token

### Option 1: Test Account Token (Recommended)

Contact the billing team to:
1. Create a test Google account
2. Pre-provision test credits
3. Generate a long-lived ID token

### Option 2: Billing Test Mode

The billing backend may support a test mode:
```bash
# Special test token format (if supported)
CIRIS_BILLING_GOOGLE_ID_TOKEN="test:qa_user_12345"
```

### Option 3: Local Mock Billing

For unit tests, mock the billing provider:
```python
from unittest.mock import AsyncMock

mock_billing = AsyncMock()
mock_billing.check_credit.return_value = CreditCheckResult(
    has_credit=True,
    credits_remaining=100,
    free_uses_remaining=10
)
```

## Testing the Hosted Tools Adapter

### QA Runner Tests

```bash
# Run hosted tools tests (will show which need token)
python -m tools.qa_runner hosted_tools

# Expected results without token:
# ✅ load_adapter - Works (no token needed)
# ✅ adapter_status - Works (no token needed)
# ✅ tool_discovery - Works (no token needed)
# ❌ balance_check - Needs token
# ❌ web_search - Needs token
```

### With Test Token

```bash
# Set token and run
export CIRIS_BILLING_GOOGLE_ID_TOKEN="<your_test_token>"
python -m tools.qa_runner hosted_tools

# All tests should pass
# ✅ load_adapter
# ✅ adapter_status
# ✅ tool_discovery
# ✅ balance_check
# ✅ web_search
```

### Docker Testing

```yaml
# docker-compose.test.yml
version: '3.8'
services:
  ciris-test:
    image: ghcr.io/cirisai/ciris-agent:latest
    environment:
      - CIRIS_BILLING_GOOGLE_ID_TOKEN=${TEST_TOKEN}
      - CIRIS_PROXY_URL=https://proxy1.ciris-services-1.ai
      - CIRIS_BILLING_API_URL=https://billing1.ciris-services-1.ai
    command: python -m tools.qa_runner hosted_tools
```

```bash
# Run with token from environment
TEST_TOKEN=your_token docker-compose -f docker-compose.test.yml up
```

## Testing the CIRIS Billing Provider

### Direct API Testing

```python
import asyncio
from ciris_engine.logic.services.infrastructure.resource_monitor.ciris_billing_provider import (
    CIRISBillingProvider
)
from ciris_engine.schemas.services.credit_gate import CreditAccount, CreditContext

async def test_billing():
    provider = CIRISBillingProvider(
        google_id_token="<your_test_token>",
        base_url="https://billing1.ciris-services-1.ai"
    )
    await provider.start()

    account = CreditAccount(
        provider="google",
        account_id="test_user_12345"
    )

    # Check credits
    result = await provider.check_credit(account)
    print(f"Has credit: {result.has_credit}")
    print(f"Credits remaining: {result.credits_remaining}")
    print(f"Free uses: {result.free_uses_remaining}")

    await provider.stop()

asyncio.run(test_billing())
```

### QA Runner Billing Tests

```bash
# Run billing tests
python -m tools.qa_runner billing

# With OAuth integration tests
python -m tools.qa_runner billing_integration
```

## Testing the CIRIS LLM Proxy

### Prerequisites

The CIRIS LLM proxy requires:
1. Valid Google ID token
2. Available credits (free or paid)
3. Network access to `proxy1.ciris-services-1.ai`

### Testing LLM Proxy

```python
import httpx

async def test_llm_proxy():
    token = "<your_test_token>"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://proxy1.ciris-services-1.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 50
            }
        )

        if response.status_code == 200:
            print("LLM proxy working!")
            print(response.json())
        elif response.status_code == 401:
            print("Token invalid or expired")
        elif response.status_code == 402:
            print("No credits available")
        else:
            print(f"Error: {response.status_code}")
            print(response.text)
```

## Environment Variables Reference

### Required for Testing

| Variable | Description | Default |
|----------|-------------|---------|
| `CIRIS_BILLING_GOOGLE_ID_TOKEN` | Google ID token for auth | None |

### Optional Overrides

| Variable | Description | Default |
|----------|-------------|---------|
| `CIRIS_PROXY_URL` | Primary proxy URL | `https://proxy1.ciris-services-1.ai` |
| `CIRIS_BILLING_API_URL` | Primary billing URL | `https://billing1.ciris-services-1.ai` |
| `CIRIS_BILLING_TIMEOUT_SECONDS` | Request timeout | `5.0` |
| `CIRIS_BILLING_CACHE_TTL_SECONDS` | Credit cache TTL | `15` |
| `CIRIS_BILLING_FAIL_OPEN` | Allow on billing failure | `false` |

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Hosted Services Tests

on: [push, pull_request]

jobs:
  test-hosted-services:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run hosted tools tests (no token)
        run: python -m tools.qa_runner hosted_tools
        # Will show 3/5 pass without token

      - name: Run hosted tools tests (with token)
        if: ${{ secrets.CIRIS_TEST_TOKEN != '' }}
        env:
          CIRIS_BILLING_GOOGLE_ID_TOKEN: ${{ secrets.CIRIS_TEST_TOKEN }}
        run: python -m tools.qa_runner hosted_tools
        # Will show 5/5 pass with token
```

### GitLab CI Example

```yaml
test-hosted-services:
  stage: test
  script:
    - pip install -r requirements.txt
    - python -m tools.qa_runner hosted_tools
  variables:
    CIRIS_BILLING_GOOGLE_ID_TOKEN: $CIRIS_TEST_TOKEN
```

## Troubleshooting

### "Not authenticated" Error

```
Tool returned: Not authenticated. Web search requires Google Sign-In...
```

**Solution**: Set `CIRIS_BILLING_GOOGLE_ID_TOKEN` environment variable.

### "No web search credits available" Error

```
Tool returned: No web search credits available...
```

**Solution**:
- Request more test credits from billing team
- Wait for daily free credits to reset (UTC midnight)
- Purchase credits via test Stripe flow

### Connection Timeout

```
TIMEOUT: All regions timed out (US-primary, EU-fallback)
```

**Solution**:
- Check network connectivity to CIRIS services
- Verify firewall allows outbound HTTPS
- Check service status at status.ciris.ai

### Token Expired (401)

```
AUTH_EXPIRED: Token expired or invalid
```

**Solution**:
- Request a new test token
- Tokens expire - get a fresh one from billing team
- For long-running tests, implement token refresh

## Related Documentation

- [Billing API](../BILLING_API.md) - Agent billing proxy endpoints
- [Adapter Guide](../ADAPTER_DEVELOPERS_GUIDE.md) - Creating custom adapters
- [QA Runner](../../tools/qa_runner/README.md) - Test framework documentation
