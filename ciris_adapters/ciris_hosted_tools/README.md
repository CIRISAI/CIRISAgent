# CIRIS Hosted Tools Adapter

This adapter provides access to CIRIS-hosted tools via the CIRIS proxy infrastructure. These tools require platform-level security guarantees (device attestation) to prevent API abuse.

## Version

**1.0.0** - Production Ready

## Overview

| Feature | Details |
|---------|---------|
| **Tools Provided** | `web_search` |
| **Authentication** | Google ID Token via Play Integrity |
| **Billing Model** | Credits (free tier + paid) |
| **Supported Platforms** | Android (iOS/Web planned) |

## Tools

### web_search

Search the web using Brave Search API via the CIRIS proxy.

**Parameters:**
- `q` (required): Search query string
- `count` (optional): Number of results (default: 10, max: 20)

**Example:**
```json
{
  "name": "web_search",
  "arguments": {
    "q": "latest python 3.13 features",
    "count": 5
  }
}
```

## Platform Requirements

These tools require device attestation because:

1. The CIRIS proxy provides free/subsidized API access
2. Without proof of possession, tokens could be extracted and abused
3. Device attestation proves the request comes from a real device running the official app

### Current Support

- **Android**: Google Play Integrity API + Native Google Sign-In

### Future Support

- **iOS**: App Attest + Apple Sign-In
- **Web**: DPoP token binding (RFC 9449)

## Credit Model

| Tier | Amount |
|------|--------|
| Welcome Bonus | 10 free searches (one-time) |
| Daily Free | 3 searches per day (resets UTC midnight) |
| Paid | 1 credit per search after free tier |

Credits can be purchased via in-app billing on Android.

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CIRIS_BILLING_GOOGLE_ID_TOKEN` | Google ID token for auth | None (required) |
| `CIRIS_PROXY_URL` | Primary proxy URL | `https://proxy1.ciris-services-1.ai` |
| `CIRIS_PROXY_FALLBACK_URL` | Fallback proxy URL | `https://proxy1.ciris-services-2.ai` |
| `CIRIS_BILLING_API_URL` | Primary billing URL | `https://billing1.ciris-services-1.ai` |
| `CIRIS_BILLING_FALLBACK_URL` | Fallback billing URL | `https://billing1.ciris-services-2.ai` |

### Loading the Adapter

**Via API:**
```bash
curl -X POST http://localhost:8000/v1/system/adapters/ciris_hosted_tools \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"config": {"enabled": true}}'
```

**Via agent profile:**
```json
{
  "adapters": [
    {
      "adapter_type": "ciris_hosted_tools",
      "enabled": true
    }
  ]
}
```

## Testing Without Android

For Docker/CI testing, you need a test token that the billing backend recognizes:

```bash
# Set via environment variable
export CIRIS_BILLING_GOOGLE_ID_TOKEN="<test_token>"

# Or in docker-compose.yml
environment:
  - CIRIS_BILLING_GOOGLE_ID_TOKEN=${TEST_TOKEN}
```

See [Hosted Services Testing Guide](../../docs/testing/HOSTED_SERVICES_TESTING.md) for comprehensive testing instructions.

## QA Testing

Run the adapter tests via QA runner:

```bash
# Run hosted tools tests (some require token)
python -m tools.qa_runner hosted_tools

# Expected results without token:
# ✅ load_adapter - Works (no token needed)
# ✅ adapter_status - Works (no token needed)
# ✅ tool_discovery - Works (no token needed)
# ❌ balance_check - Needs token
# ❌ web_search - Needs token
```

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    CIRIS Agent                                │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │           CIRISHostedToolsAdapter                        │ │
│  │  ┌─────────────────┐    ┌─────────────────────────────┐ │ │
│  │  │ CIRISHostedTool │───►│   CIRIS Proxy               │ │ │
│  │  │    Service      │    │ proxy1.ciris-services-1.ai  │ │ │
│  │  └─────────────────┘    └─────────────────────────────┘ │ │
│  │           │                         │                    │ │
│  │           ▼                         ▼                    │ │
│  │  ┌─────────────────┐    ┌─────────────────────────────┐ │ │
│  │  │ Token Lookup    │    │   Brave Search API          │ │ │
│  │  │ (env/file)      │    │   (via proxy)               │ │ │
│  │  └─────────────────┘    └─────────────────────────────┘ │ │
│  └─────────────────────────────────────────────────────────┘ │
│                           │                                   │
│                           ▼                                   │
│            ┌─────────────────────────────────────┐            │
│            │        CIRIS Billing                 │            │
│            │  billing1.ciris-services-1.ai       │            │
│            │  - Credit checking                   │            │
│            │  - Usage tracking                    │            │
│            │  - Free tier management              │            │
│            └─────────────────────────────────────┘            │
└──────────────────────────────────────────────────────────────┘
```

## Error Handling

| Error | Meaning | Solution |
|-------|---------|----------|
| `Not authenticated` | Missing Google ID token | Set `CIRIS_BILLING_GOOGLE_ID_TOKEN` |
| `No web search credits` | Free tier exhausted | Wait for daily reset or purchase credits |
| `Token expired` | ID token has expired | Refresh token (Android auto-refreshes) |
| `TIMEOUT` | Network/service issue | Check connectivity, try fallback |

## Related Documentation

- [Hosted Services Testing](../../docs/testing/HOSTED_SERVICES_TESTING.md)
- [Billing API](../../docs/BILLING_API.md)
- [Adapter Developer Guide](../../docs/ADAPTER_DEVELOPERS_GUIDE.md)
