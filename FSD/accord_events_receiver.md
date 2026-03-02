# Functional Specification: CIRISLens Covenant Events Receiver

**Version:** 1.0
**Date:** 2025-12-31
**Author:** CIRIS Engineering
**Status:** Draft

## 1. Overview

This document specifies the implementation requirements for the CIRISLens `/v1/covenant/events` endpoint that receives Ed25519-signed reasoning traces from CIRIS agents with explicit user consent.

## 2. Endpoint Specification

### 2.1 URL
```
POST /v1/covenant/events
```

### 2.2 Authentication
- No authentication required (public endpoint)
- Traces are self-authenticating via Ed25519 signatures
- Agent identity verified through signature chain of trust

### 2.3 Request Format

```json
{
  "events": [
    {
      "event_type": "complete_trace",
      "trace": {
        "trace_id": "trace-th_std_xxxxx-20251231180909",
        "components": [...],
        "signature": "base64-encoded-ed25519-signature",
        "signer_key_id": "wa-2025-06-14-ROOT00"
      }
    }
  ],
  "batch_timestamp": "2025-12-31T18:09:09.123456+00:00",
  "consent_timestamp": "2025-01-01T00:00:00Z"
}
```

### 2.4 Response Format

**Success (200):**
```json
{
  "status": "ok",
  "received": 10,
  "accepted": 10,
  "rejected": 0
}
```

**Validation Error (400):**
```json
{
  "status": "error",
  "message": "Invalid signature",
  "rejected_traces": ["trace-id-1", "trace-id-2"]
}
```

## 3. Trace Structure

Each trace contains 6 components representing the complete H3ERE pipeline reasoning cycle:

### 3.1 Component Types

| Component | Description |
|-----------|-------------|
| `THOUGHT_START` | Initial observation that triggered processing |
| `SNAPSHOT_AND_CONTEXT` | System snapshot and environmental context |
| `DMA_RESULTS` | Decision-Making Architecture analysis results |
| `ASPDMA_RESULT` | Action-Selection PDMA evaluation |
| `CONSCIENCE_RESULT` | Ethical validation with 6 conscience fields |
| `ACTION_RESULT` | Final action taken and audit metadata |

### 3.2 Complete Trace Example

```json
{
  "trace_id": "trace-th_std_71cf5cb5-3e51-4d48-a094-ad610baf181f-20251231181436",
  "components": [
    {
      "event_type": "THOUGHT_START",
      "data": {
        "thought_id": "th_std_71cf5cb5-3e51-4d48-a094-ad610baf181f",
        "task_description": "You are Datum, a Datum - The Humble Measurement...",
        "timestamp": "2025-12-31T18:14:36.123456+00:00"
      }
    },
    {
      "event_type": "SNAPSHOT_AND_CONTEXT",
      "data": {
        "cognitive_state": "WAKEUP",
        "services_online": 22,
        "memory_used_mb": 256
      }
    },
    {
      "event_type": "DMA_RESULTS",
      "data": {
        "selected_action": "SPEAK",
        "confidence_score": 0.95,
        "reasoning_summary": "..."
      }
    },
    {
      "event_type": "ASPDMA_RESULT",
      "data": {
        "action_permitted": true,
        "guardrails_passed": true
      }
    },
    {
      "event_type": "CONSCIENCE_RESULT",
      "data": {
        "ethical_faculties_skipped": false,
        "updated_status_detected": true,
        "updated_status_content": "Identity verified",
        "thought_depth_triggered": false,
        "thought_depth_current": 0,
        "thought_depth_max": 3,
        "entropy_passed": true,
        "entropy_score": 0.85,
        "entropy_threshold": 0.5,
        "coherence_passed": true,
        "coherence_score": 0.92,
        "coherence_threshold": 0.7,
        "optimization_veto_triggered": false,
        "optimization_veto_reason": null,
        "epistemic_humility_triggered": false,
        "epistemic_humility_recommendation": null
      }
    },
    {
      "event_type": "ACTION_RESULT",
      "data": {
        "action_type": "SPEAK",
        "action_parameters": {
          "content": "CORE IDENTITY - I am Datum, a single data point in the CIRIS ecosystem...",
          "channel_id": "api_127.0.0.1_8080"
        },
        "action_success": true,
        "audit_entry_hash": "sha256:abc123..."
      }
    }
  ],
  "signature": "base64-encoded-ed25519-signature",
  "signer_key_id": "wa-2025-06-14-ROOT00"
}
```

## 4. Signature Verification

### 4.1 Root Public Key

The root public key for the v1 CIRIS Covenant is:

```
Key ID: wa-2025-06-14-ROOT00
Algorithm: Ed25519
Public Key (base64): [Stored in seed/root_pub.json]
```

### 4.2 Verification Process

1. Extract `signature` and `signer_key_id` from trace
2. Look up public key by `signer_key_id`
3. Construct canonical message: JSON-serialize components (sorted keys, no extra whitespace)
4. Verify Ed25519 signature against message

### 4.3 Reference Implementation

```python
from nacl.signing import VerifyKey
import json

def verify_trace(trace: dict, public_keys: dict) -> bool:
    signature = base64.b64decode(trace["signature"])
    signer_key_id = trace["signer_key_id"]

    if signer_key_id not in public_keys:
        return False

    verify_key = VerifyKey(base64.b64decode(public_keys[signer_key_id]))

    # Canonical message is JSON of components
    message = json.dumps(trace["components"], sort_keys=True)

    try:
        verify_key.verify(message.encode(), signature)
        return True
    except Exception:
        return False
```

## 5. Wakeup Trace Types

CIRIS agents send 5 wakeup traces on startup:

| Trace Type | Description | Task Pattern |
|------------|-------------|--------------|
| `VERIFY_IDENTITY` | Agent identity confirmation | "You are Datum", "Humble Measurement" |
| `VALIDATE_INTEGRITY` | Internal state validation | "Validate your internal state" |
| `EVALUATE_RESILIENCE` | Resilience assessment | "You are robust", "resilience", "adaptive" |
| `ACCEPT_INCOMPLETENESS` | Acknowledge limitations | "You recognize your incompleteness" |
| `EXPRESS_GRATITUDE` | Ubuntu gratitude expression | "You are grateful" |

## 6. Conscience Fields (6 Components)

The `CONSCIENCE_RESULT` component contains 6 conscience validation fields:

### 6.1 Bypass Guardrails (2)
- `updated_status_detected`: Boolean - status update available
- `thought_depth_triggered`: Boolean - recursive thinking depth check

### 6.2 Ethical Faculties (4)
- `entropy_passed`: Boolean - diversity/randomness check
- `coherence_passed`: Boolean - logical consistency check
- `optimization_veto_triggered`: Boolean - excessive optimization detected
- `epistemic_humility_triggered`: Boolean - knowledge uncertainty flagged

## 7. Storage Requirements

### 7.1 Trace Retention
- Store all valid traces indefinitely
- Index by: trace_id, timestamp, agent_id (anonymized), trace_type

### 7.2 Anonymization
- Agent IDs are pre-hashed by the sending agent (SHA-256, first 16 chars)
- No PII is included in traces

## 8. Rate Limiting

- Default batch size: 10 events
- Default flush interval: 60 seconds
- No per-agent rate limit required (consent-based collection)

## 9. Metrics

Track and expose:
- `traces_received_total`: Counter
- `traces_accepted_total`: Counter
- `traces_rejected_total`: Counter by reason
- `batch_processing_time_seconds`: Histogram

## 10. Error Handling

| Error | HTTP Code | Response |
|-------|-----------|----------|
| Invalid JSON | 400 | `{"error": "Invalid JSON"}` |
| Invalid signature | 400 | `{"error": "Invalid signature", "trace_id": "..."}` |
| Unknown signer | 400 | `{"error": "Unknown signer key"}` |
| Server error | 500 | `{"error": "Internal error"}` |

## 11. Test Fixtures

Sample trace files are available at:
```
qa_reports/trace_VERIFY_IDENTITY_*.json
qa_reports/trace_VALIDATE_INTEGRITY_*.json
qa_reports/trace_EVALUATE_RESILIENCE_*.json
qa_reports/trace_ACCEPT_INCOMPLETENESS_*.json
qa_reports/trace_EXPRESS_GRATITUDE_*.json
```

## 12. Implementation Checklist

- [ ] Create `/v1/covenant/events` POST endpoint
- [ ] Implement Ed25519 signature verification
- [ ] Load root public key from seed/root_pub.json
- [ ] Store valid traces in database
- [ ] Add metrics instrumentation
- [ ] Implement rate limiting (optional)
- [ ] Add health check endpoint
- [ ] Write integration tests

## 13. Contact

For questions about this specification:
- CIRIS Engineering Team
- Repository: github.com/CIRISAI/CIRISAgent
