# Server-Sent Events (SSE) Streaming API

This document describes the H3ERE reasoning event stream API, which provides real-time visibility into CIRIS agent reasoning through 6 structured events.

## Overview

The SSE API broadcasts reasoning events as the agent processes thoughts through the H3ERE (Hyper3 Ethical Recursive Engine) pipeline. Each event represents a key decision point in the reasoning process.

**6 Reasoning Events:**
1. `thought_start` - Thought begins processing
2. `snapshot_and_context` - System state and context snapshot
3. `dma_results` - Initial DMA analysis (CSDMA, DSDMA, PDMA)
4. `aspdma_result` - Action selection result
5. `conscience_result` - Conscience validation result
6. `action_result` - Final action execution result

## Usage Pattern

### 1. Submit Message (Async)

**Endpoint:** `POST /v1/agent/message`

Submit a message for processing and receive an immediate acknowledgment with a `task_id`. The task will generate thoughts during processing which emit reasoning events.

**Request:**
```json
{
  "message": "What's the weather like today?"
}
```

**Response (200 OK - Accepted):**
```json
{
  "status": "success",
  "data": {
    "message_id": "msg_abc123",
    "task_id": "task_xyz789",
    "channel_id": "api_default",
    "submitted_at": "2025-10-03T18:00:00.000Z",
    "accepted": true,
    "rejection_reason": null,
    "rejection_detail": null
  }
}
```

**Response (200 OK - Rejected):**
```json
{
  "status": "success",
  "data": {
    "message_id": "msg_abc123",
    "task_id": null,
    "channel_id": "api_default",
    "submitted_at": "2025-10-03T18:00:00.000Z",
    "accepted": false,
    "rejection_reason": "FILTERED_OUT",
    "rejection_detail": "Message filtered by adaptive filter"
  }
}
```

**Schema:**
```typescript
interface MessageRequest {
  message: string;  // The message content to process
  context?: MessageContext;  // Optional context
}

interface MessageSubmissionResponse {
  message_id: string;           // Unique message ID for tracking
  task_id: string | null;       // Task ID if accepted (null if rejected)
  channel_id: string;           // Channel where message was sent
  submitted_at: string;         // ISO timestamp of submission
  accepted: boolean;            // Whether message was accepted
  rejection_reason?: string;    // Reason if rejected
  rejection_detail?: string;    // Additional rejection details
}

// Wrapper for all API responses
interface SuccessResponse<T> {
  status: "success";
  data: T;
}
```

**Note:** The `task_id` can be used to filter SSE reasoning events. Each task generates one or more thoughts during processing, and each thought emits the 6 reasoning events.

### 2. Stream Reasoning Events (Real-time)

**Endpoint:** `GET /v1/agent/stream`

**Authentication:** Bearer token required

```bash
curl -N -H "Authorization: Bearer YOUR_TOKEN" \
  https://agents.ciris.ai/api/datum/v1/agent/stream
```

**Response:** Server-Sent Events stream

```
event: reasoning
data: {"event_type": "thought_start", "thought_id": "th_std_abc123...", ...}

event: reasoning
data: {"event_type": "snapshot_and_context", "thought_id": "th_std_abc123...", ...}

event: reasoning
data: {"event_type": "dma_results", "thought_id": "th_std_abc123...", ...}

event: reasoning
data: {"event_type": "aspdma_result", "thought_id": "th_std_abc123...", ...}

event: reasoning
data: {"event_type": "conscience_result", "thought_id": "th_std_abc123...", ...}

event: reasoning
data: {"event_type": "action_result", "thought_id": "th_std_abc123...", ...}
```

### 3. Poll for Response (Fallback)

**Endpoint:** `GET /v1/agent/history?channel_id={channel_id}&limit=10`

If SSE streaming is not available, poll this endpoint to retrieve recent messages and agent responses.

**Response:**
```json
{
  "status": "success",
  "data": {
    "messages": [
      {
        "id": "msg_abc123",
        "author": "user_123",
        "content": "What's the weather like today?",
        "timestamp": "2025-10-03T18:00:00.000Z",
        "is_agent": false
      },
      {
        "id": "msg_xyz789",
        "author": "CIRIS",
        "content": "The weather is sunny today!",
        "timestamp": "2025-10-03T18:00:05.000Z",
        "is_agent": true
      }
    ],
    "channel_id": "api_default",
    "total": 2
  }
}
```

**Alternative: Task Status Endpoint**

`GET /v1/system/tasks/{task_id}` - Check specific task status

**Response:**
```json
{
  "status": "success",
  "data": {
    "task_id": "task_xyz789",
    "status": "completed",
    "priority": 5,
    "created_at": "2025-10-03T18:00:00.000Z",
    "completed_at": "2025-10-03T18:00:05.000Z"
  }
}
```

---

## Event Schemas

### Event 0: `thought_start`

Broadcast when a thought begins processing.

**Fields:**
```typescript
interface ThoughtStartEvent {
  event_type: "thought_start";
  thought_id: string;           // Unique thought identifier
  task_id: string;              // Source task identifier (always present)
  timestamp: string;            // ISO 8601 timestamp

  // Thought metadata
  thought_type: string;         // "standard", "ponder", "recursive", etc.
  thought_content: string;      // The thought content/reasoning
  thought_status: string;       // "pending", "processing", etc.
  round_number: number;         // Processing round (0-based)
  thought_depth: number;        // Ponder depth (0-7, default: 0)
  parent_thought_id?: string;   // Parent thought if pondering

  // Task metadata (always present - context for the thought)
  task_description: string;     // What needs to be done
  task_priority: number;        // Priority 0-10
  channel_id: string;           // Channel where task originated
  updated_info_available: boolean; // Whether task has updated information (default: false)
}
```

**Example:**
```json
{
  "event_type": "thought_start",
  "thought_id": "th_std_7a6ad32e-c0a2-4732-a734-4c3deb",
  "task_id": "task_123",
  "timestamp": "2025-10-03T18:00:00.000Z",
  "thought_type": "standard",
  "thought_content": "Process message: What's the weather?",
  "thought_status": "processing",
  "round_number": 0,
  "thought_depth": 0,
  "task_description": "Respond to user query",
  "task_priority": 5,
  "channel_id": "1234567890",
  "updated_info_available": false
}
```

---

### Event 1: `snapshot_and_context`

Broadcast at the start of PERFORM_DMAS step with system state snapshot and thought context.

**Fields:**
```typescript
interface SnapshotAndContextEvent {
  event_type: "snapshot_and_context";
  thought_id: string;
  task_id: string;
  timestamp: string;

  system_snapshot: SystemSnapshot;  // Full system state
  context: string;                  // Formatted context string
  context_size: number;             // Context length in characters
}

interface SystemSnapshot {
  // Channel context (PRIMARY - user/channel info)
  channel_id?: string;              // Channel ID (Discord, 'cli', 'api')
  channel_context?: {
    channel_type: string;           // "discord", "api", "cli"
    channel_metadata: any;          // Channel-specific metadata
    active_users: string[];         // Active user IDs
  };

  // Current processing state
  current_task_details?: {
    task_id: string;
    description: string;
    status: string;
    priority: number;
  };
  current_thought_summary?: {
    thought_id: string;
    content: string;
    status: string;
  };

  // System overview
  system_counts: {                  // Always present (can be empty)
    total_tasks?: number;
    total_thoughts?: number;
    pending_tasks?: number;
    pending_thoughts?: number;
  };
  top_pending_tasks_summary: any[]; // Top 10 pending tasks
  recently_completed_tasks_summary: any[]; // Recent completions

  // Agent identity
  agent_identity?: string;          // Agent identity context
  user_profiles?: any[];            // User profile data

  // Timestamps
  current_time_utc?: string;        // Current time
}
```

**Example:**
```json
{
  "event_type": "snapshot_and_context",
  "thought_id": "th_std_7a6ad32e",
  "task_id": "task_123",
  "timestamp": "2025-10-03T18:00:01.000Z",
  "system_snapshot": {
    "channel_id": "1234567890",
    "channel_context": {
      "channel_type": "discord",
      "active_users": ["user_123"]
    },
    "current_task_details": {
      "task_id": "task_123",
      "description": "Respond to user query",
      "status": "active",
      "priority": 5
    },
    "system_counts": {
      "total_tasks": 42,
      "pending_tasks": 3
    },
    "current_time_utc": "2025-10-03T18:00:01.000Z"
  },
  "context": "User: What's the weather?\nAgent identity: CIRIS...",
  "context_size": 1234
}
```

---

### Event 2: `dma_results`

Broadcast at the start of PERFORM_ASPDMA step with results from all 3 DMAs.

**Fields:**
```typescript
interface DMAResultsEvent {
  event_type: "dma_results";
  thought_id: string;
  task_id: string;
  timestamp: string;

  // All 3 DMA results (non-optional, strongly typed)
  csdma: CSDMAResult;    // Common Sense DMA
  dsdma: DSDMAResult;    // Domain Specific DMA
  pdma: EthicalDMAResult; // Ethical Perspective DMA (PDMA)
}

interface CSDMAResult {
  common_sense_alignment: number;  // 0.0-1.0
  flags: string[];                 // Common sense flags
  reasoning: string;               // CSDMA reasoning
}

interface DSDMAResult {
  domain: string;                  // Domain name
  domain_alignment: number;        // 0.0-1.0
  flags: string[];                 // Domain-specific flags
  reasoning: string;               // DSDMA reasoning
}

interface EthicalDMAResult {
  decision: string;                // "approved", "denied", "review"
  reasoning: string;               // Ethical reasoning
  alignment_check: string;         // Alignment summary
}
```

**Example:**
```json
{
  "event_type": "dma_results",
  "thought_id": "th_std_7a6ad32e",
  "task_id": "task_123",
  "timestamp": "2025-10-03T18:00:02.000Z",
  "csdma": {
    "common_sense_alignment": 0.95,
    "flags": ["safe", "helpful"],
    "reasoning": "This is a straightforward weather query..."
  },
  "dsdma": {
    "domain": "conversation",
    "domain_alignment": 0.92,
    "flags": ["appropriate"],
    "reasoning": "Query fits conversational domain..."
  },
  "pdma": {
    "decision": "approved",
    "reasoning": "No ethical concerns with weather query",
    "alignment_check": "Aligned with helpful assistance"
  }
}
```

---

### Event 3: `aspdma_result`

Broadcast at the start of CONSCIENCE_EXECUTION step with action selection result.

**Fields:**
```typescript
interface ASPDMAResultEvent {
  event_type: "aspdma_result";
  thought_id: string;
  task_id: string | null;       // Parent task if any
  timestamp: string;

  selected_action: string;      // Action type selected
  action_rationale: string;     // Why this action was chosen
  is_recursive: boolean;        // Whether this is recursive ASPDMA after conscience override (default: false)
}
```

**Example:**
```json
{
  "event_type": "aspdma_result",
  "thought_id": "th_std_7a6ad32e",
  "task_id": "task_123",
  "timestamp": "2025-10-03T18:00:03.000Z",
  "selected_action": "speak",
  "action_rationale": "User asked a direct question requiring a response",
  "is_recursive": false
}
```

---

### Event 4: `conscience_result`

Broadcast at the start of FINALIZE_ACTION step with conscience validation result.

**Fields:**
```typescript
interface ConscienceResultEvent {
  event_type: "conscience_result";
  thought_id: string;
  task_id: string | null;               // Parent task if any
  timestamp: string;

  conscience_passed: boolean;           // Did conscience approve?
  final_action: string;                 // Action after conscience check
  epistemic_data: EpistemicData;        // Rich conscience evaluation data from all checks
  is_recursive: boolean;                // Whether this is recursive conscience check after override (default: false)
  conscience_override_reason?: string;  // Why action was overridden (null if not overridden)
  action_was_overridden: boolean;       // Was action changed?
  updated_status_available?: boolean;   // Whether UpdatedStatusConscience detected new info (null if not checked)
}

// EpistemicData can contain various conscience check results
interface EpistemicData {
  [key: string]: any;  // Dynamic data from various conscience checks
  // Common fields that may appear:
  confidence?: number;                  // 0.0-1.0
  uncertainty_acknowledged?: boolean;
  reasoning?: string;
  status?: string;
  reason?: string;
}
```

**Example:**
```json
{
  "event_type": "conscience_result",
  "thought_id": "th_std_7a6ad32e",
  "task_id": "task_123",
  "timestamp": "2025-10-03T18:00:04.000Z",
  "conscience_passed": true,
  "final_action": "speak",
  "epistemic_data": {
    "confidence": 0.85,
    "uncertainty_acknowledged": false,
    "reasoning": "High confidence in response accuracy",
    "status": "APPROVED"
  },
  "is_recursive": false,
  "conscience_override_reason": null,
  "action_was_overridden": false,
  "updated_status_available": false
}
```

---

### Event 5: `action_result`

Broadcast at ACTION_COMPLETE step with final execution result and audit data.

**Fields:**
```typescript
interface ActionResultEvent {
  event_type: "action_result";
  thought_id: string;
  task_id: string | null;           // Parent task if any
  timestamp: string;

  action_executed: string;          // Action type executed
  execution_success: boolean;       // Was execution successful?
  execution_time_ms: number;        // Execution duration in milliseconds
  follow_up_thought_id?: string;    // Follow-up thought created if any (null if none)
  error?: string;                   // Error message if execution failed (null if successful)

  // Audit trail data (tamper-evident hash chain)
  audit_entry_id?: string;          // ID of audit entry for this action (null if audit failed)
  audit_sequence_number?: number;   // Sequence number in audit hash chain (null if audit failed)
  audit_entry_hash?: string;        // Hash of audit entry (null if audit failed)
  audit_signature?: string;         // Ed25519 cryptographic signature (null if audit failed)
}
```

**Example:**
```json
{
  "event_type": "action_result",
  "thought_id": "th_std_7a6ad32e",
  "task_id": "task_123",
  "timestamp": "2025-10-03T18:00:05.000Z",
  "action_executed": "speak",
  "execution_success": true,
  "execution_time_ms": 245.0,
  "follow_up_thought_id": null,
  "error": null,
  "audit_entry_id": "audit_abc123",
  "audit_sequence_number": 42,
  "audit_entry_hash": "sha256:abcd1234...",
  "audit_signature": "ed25519:signature..."
}
```

---

## Client Implementation Examples

### JavaScript/TypeScript (Browser)

```typescript
// 1. Submit message
const response = await fetch('/v1/agent/message', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({ message: "What's the weather?" })
});

const result = await response.json();
const { task_id } = result.data;

// 2. Stream reasoning events
const eventSource = new EventSource(`/v1/agent/stream?token=${token}`);

eventSource.addEventListener('reasoning', (event) => {
  const reasoningEvent = JSON.parse(event.data);

  // Filter for this task's thoughts
  if (reasoningEvent.task_id === task_id) {
    console.log(`Event: ${reasoningEvent.event_type}`, reasoningEvent);

    // Final result
    if (reasoningEvent.event_type === 'action_result') {
      console.log('Processing complete!');
      eventSource.close();
    }
  }
});
```

### Python

```python
import requests
import json
from sseclient import SSEClient  # pip install sseclient-py

# 1. Submit message
response = requests.post(
    'https://agents.ciris.ai/api/datum/v1/agent/message',
    headers={'Authorization': f'Bearer {token}'},
    json={'message': "What's the weather?"}
)
result = response.json()
task_id = result['data']['task_id']

# 2. Stream reasoning events
headers = {'Authorization': f'Bearer {token}'}
stream_url = 'https://agents.ciris.ai/api/datum/v1/agent/stream'

client = SSEClient(stream_url, headers=headers)
for event in client.events():
    if event.event == 'reasoning':
        data = json.loads(event.data)

        # Filter for this task's thoughts
        if data['task_id'] == task_id:
            print(f"Event: {data['event_type']}")

            # Final result
            if data['event_type'] == 'action_result':
                print('Processing complete!')
                break
```

### cURL (Testing)

```bash
# 1. Submit message
TASK_ID=$(curl -X POST https://agents.ciris.ai/api/datum/v1/agent/message \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"What is the weather?"}' | jq -r '.data.task_id')

echo "Task ID: $TASK_ID"

# 2. Stream reasoning events (keep connection open)
curl -N -H "Authorization: Bearer $TOKEN" \
  https://agents.ciris.ai/api/datum/v1/agent/stream | \
  grep --line-buffered "task_id.*$TASK_ID"
```

---

## Error Handling

### SSE Connection Errors

- **401 Unauthorized**: Invalid or expired token - refresh authentication
- **Connection Lost**: Reconnect with exponential backoff (start with 1s, max 30s)
- **No Events Received**: Check thought_id matches, verify agent is running

### Message Submission Errors

- **400 Bad Request**: Invalid message format or missing required fields
- **403 Forbidden**: User lacks permission to interact with agent
- **429 Too Many Requests**: Rate limit exceeded - slow down requests
- **503 Service Unavailable**: Agent is in maintenance mode or overloaded

---

## Best Practices

1. **Keep SSE connection alive**: Don't reconnect for every message - reuse the stream
2. **Filter by task_id**: The stream includes all reasoning events - filter client-side by task_id from message submission
3. **Handle reconnection**: Implement exponential backoff for reconnection attempts
4. **Validate schemas**: Use the provided schemas to validate incoming events
5. **Track processing state**: Use event sequence to build a state machine
6. **Graceful degradation**: Fall back to polling `/v1/agent/history` if SSE is not available
7. **Timeout handling**: Set reasonable timeouts (30-60s for most thoughts)
8. **Check message acceptance**: Verify `accepted: true` in submission response before filtering SSE stream

---

## Validation

All events are validated against their schemas using Pydantic with `extra="forbid"`. Any additional fields will cause validation errors.

**Key validation rules:**
- All required fields must be present
- Field types must match exactly (no implicit conversions)
- Nested objects (SystemSnapshot, DMA results) are fully validated
- No extra/unknown fields allowed
- Enums must use exact values

To test your integration, run:
```bash
python -m tools.qa_runner streaming
```

This will verify:
- All 6 events are received in correct order
- No duplicate events
- All schemas validate 100%
- No extra or missing fields

---

## Production URLs

- **Main**: `https://agents.ciris.ai`
- **API**: `https://agents.ciris.ai/api/datum/v1/`
- **SSE Stream**: `https://agents.ciris.ai/api/datum/v1/agent/stream`
- **Message Submit**: `https://agents.ciris.ai/api/datum/v1/agent/message`
- **Message Poll**: `https://agents.ciris.ai/api/datum/v1/agent/message/{thought_id}`

---

## Support

For issues or questions:
- GitHub: https://github.com/CIRISAI/CIRISAgent/issues
- Documentation: https://docs.ciris.ai
