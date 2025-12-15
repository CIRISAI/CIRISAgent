# CIRIS Covenant Metrics Adapter

This adapter provides covenant compliance metrics collection for CIRISLens, reporting WBD (Wisdom-Based Deferral) events and PDMA decision events as specified in the CIRIS Covenant Section II.

## Privacy-First Design

**CRITICAL**: This adapter requires **EXPLICIT opt-in** via the setup wizard. No data is collected or sent without your consent.

### What Data is Collected

When you consent, the following data is sent to CIRISLens:

#### WBD (Wisdom-Based Deferral) Events
Per CIRIS Covenant Section II, Chapter 3:
```json
{
  "event_type": "wbd_deferral",
  "timestamp": "2025-12-15T14:00:00Z",
  "agent_id": "abc123def456...",  // Anonymized hash
  "thought_id": "thought-123",
  "task_id": "task-456",
  "reason": "Ethical uncertainty...",  // Truncated to 200 chars
  "defer_until": "2025-12-15T15:00:00Z",
  "priority": "medium"
}
```

#### PDMA Decision Events
Per CIRIS Covenant Section II, Chapter 2:
```json
{
  "event_type": "pdma_decision",
  "timestamp": "2025-12-15T14:00:00Z",
  "agent_id": "abc123def456...",  // Anonymized hash
  "thought_id": "thought-123",
  "selected_action": "SPEAK",
  "rationale": "User requested...",  // Truncated to 200 chars
  "reasoning_summary": "..."  // Truncated to 500 chars
}
```

### What is NOT Collected

- User messages or conversation content
- Personal identifiable information (PII)
- Chat history
- Tool call details or parameters
- External API responses
- File contents

### Privacy Controls

1. **Anonymization**: Agent IDs are SHA-256 hashed
2. **Truncation**: All text fields are truncated to prevent sensitive data leakage
3. **No PII**: Only structural metadata is collected
4. **Consent Required**: Nothing is sent without explicit consent
5. **Revocable**: Disable the adapter to stop collection immediately

## Usage

### 1. Load the Adapter

```bash
python main.py --adapter api --adapter ciris_covenant_metrics
```

### 2. Complete Setup Wizard

The adapter requires completing the setup wizard which includes:

1. **Data Disclosure**: Review exactly what data will be collected
2. **Explicit Consent**: Check the consent box (required)
3. **Endpoint Config**: Configure CIRISLens URL (optional, has default)
4. **Confirmation**: Review and enable

### 3. Verify Status

Check adapter status via the API:
```bash
curl http://localhost:8000/v1/system/adapters/ciris_covenant_metrics
```

## Configuration

Environment variables:
- `CIRIS_LENS_ENDPOINT`: CIRISLens API URL (default: `https://lens.ciris.ai/v1`)

Wizard configuration:
- `consent_given`: Boolean - must be true to collect data
- `consent_timestamp`: ISO timestamp when consent was given
- `batch_size`: Number of events to batch (1-100, default: 10)
- `flush_interval_seconds`: Seconds between batch sends (10-300, default: 60)

## How It Works

### WBD Event Collection

1. Adapter registers as a `WISE_AUTHORITY` service with `send_deferral` capability
2. When any component calls `WiseBus.send_deferral()`, it broadcasts to ALL services with this capability
3. The CovenantMetricsService receives the deferral and queues it for transmission
4. Events are batched and sent to CIRISLens API

### Event Batching

- Events are queued in memory
- Sent when batch reaches `batch_size` OR `flush_interval_seconds` elapsed
- Failed batches are re-queued up to 10x batch size
- All events are flushed on adapter stop

## Revoking Consent

To stop data collection:

1. **Via Setup Wizard**: Re-run wizard and uncheck consent
2. **Disable Adapter**: Remove from command line arguments
3. **Immediate**: Data collection stops immediately when consent is revoked

## CIRISLens API

Events are sent to:
```
POST {endpoint}/covenant/events
```

Request body:
```json
{
  "events": [...],
  "batch_timestamp": "2025-12-15T14:00:00Z",
  "consent_timestamp": "2025-12-15T13:00:00Z"
}
```

## Covenant References

- **Section II, Chapter 2**: Principled Decision-Making Algorithm (PDMA)
- **Section II, Chapter 3**: Wisdom-Based Deferral (WBD)

For more information about the CIRIS Covenant, see: https://ciris.ai/covenant

## Support

- Privacy Policy: https://ciris.ai/privacy
- Issues: https://github.com/CIRISAI/CIRISAgent/issues
