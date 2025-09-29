# Unlimit Billing Service (Modular)

This optional module integrates the CIRIS agent stack with Unlimit, a European billing provider. It
keeps all billing logic outside the core engine to preserve the covenant boundary while providing a
simple credit-check primitive that other adapters can wire into their request flows.

## Capabilities

- Asynchronous credit checks keyed by OAuth identity
- Transaction spending against the authenticated Unlimit account
- AP2-compliant checkout tool (`ap2_unlimit_checkout`) that enforces mandate chains
- Short-lived in-memory caching to prevent API thrash on balance lookups
- Configurable failure behaviour (fail-closed by default) for balance checks
- Minimal telemetry hooks via structured logging

## Configuration

The service expects an Unlimit API key stored in the secrets service or environment variables. Key
settings can be provided when the service is instantiated:

| setting | env var | default | description |
| --- | --- | --- | --- |
| base_url | `UNLIMIT_API_BASE_URL` | `https://api.unlimit.com` | API endpoint |
| timeout_seconds | `UNLIMIT_API_TIMEOUT_SECONDS` | `5.0` | HTTP timeout |
| cache_ttl_seconds | `UNLIMIT_CACHE_TTL_SECONDS` | `15` | Result cache TTL |
| fail_open | `UNLIMIT_FAIL_OPEN` | `false` | Allow interactions when Unlimit is unreachable (balance checks only) |

## Manifest

The module ships with a `manifest.json` so it can be discovered by the modular service loader.

## Testing

Unit tests live under `tests/modular/test_unlimit_billing_service.py` and exercise cache, success,
error, and timeout paths using `httpx.MockTransport`.
