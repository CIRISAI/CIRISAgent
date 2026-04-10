# CIRISNode Changes Needed for Domain-Aware Deferral Routing

**Date**: 2026-04-08
**Related PR**: Domain-aware deferral routing in CIRISAgent

## Summary

CIRISAgent now filters deferrals by `domain_hint` to ensure only nodes licensed for specific domains (MEDICAL, FINANCIAL, LEGAL, etc.) receive those deferrals. This requires corresponding changes in CIRISNode and CIRISPortal/Registry.

## Changes Required in CIRISNode

### 1. Registration Response Should Include Supported Domains

When an agent registers its public key with CIRISNode, the response should include the `supported_domains` that this node is licensed to handle.

```json
// POST /api/v1/accord/public-keys response
{
  "status": "registered",
  "key_id": "agent-abc123...",
  "supported_domains": ["MEDICAL", "FINANCIAL"]  // NEW FIELD
}
```

### 2. Node Configuration for Domain Licensing

CIRISNode should have a configuration that declares which domains it can handle:

```yaml
# CIRISNode config
domains:
  supported:
    - MEDICAL
    - FINANCIAL
  # Empty = general-purpose only (no specialized domains)
```

### 3. WBD Submit Should Validate Domain

When receiving a deferral via `POST /api/v1/wbd/submit`, CIRISNode should:
- Check if the `domain_hint` is in its supported domains
- Reject deferrals for domains it's not licensed to handle
- Return appropriate error: `{"error": "domain_not_supported", "domain": "MEDICAL"}`

### 4. Registry Integration

CIRISPortal/CIRISRegistry should:
- Track which domains each node is licensed for
- Provide domain licensing info via `GetPublicKeys` gRPC
- Allow admins to configure domain licensing per node

## Changes Made in CIRISAgent

1. **SimpleCapabilities.supported_domains** - New field declaring which DomainCategory values a service handles

2. **WiseBus.send_deferral()** - Now filters services by `domain_hint`:
   - If `context.domain_hint` is set, only services with that domain in `supported_domains` receive the deferral
   - Services with empty `supported_domains` only receive general (no domain_hint) deferrals

3. **CIRISNodeService.get_capabilities()** - Returns `supported_domains` from config instead of all domains

## Domain Categories (from agent_credits.py)

```python
class DomainCategory(str, Enum):
    GENERAL = "GENERAL"
    MEDICAL = "MEDICAL"
    FINANCIAL = "FINANCIAL"
    LEGAL = "LEGAL"
    TECHNICAL = "TECHNICAL"
    EDUCATIONAL = "EDUCATIONAL"
    CREATIVE = "CREATIVE"
    RESEARCH = "RESEARCH"
```

## Testing

The agent-side tests are in `tests/test_agent_credits.py`:
- `test_filters_services_by_domain` - Verifies MEDICAL deferrals only go to MEDICAL-capable services
- `test_no_domain_hint_broadcasts_to_all` - Verifies general deferrals go to all services

CIRISNode should add corresponding tests for:
- Rejecting deferrals for unsupported domains
- Accepting deferrals for supported domains
- General deferrals (no domain_hint) being accepted
