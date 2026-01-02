# UI/UX Update Required: System and Error Message Handling

**Priority:** High
**Affects:** All UI clients (Web, Android, iOS, Desktop)
**Version:** v1.8.0+
**Date:** 2026-01-02

---

## Summary

The CIRIS API now emits **system** and **error** messages to the conversation history. All UI/UX clients must be updated to properly display these message types to users.

---

## API Changes

### 1. ConversationMessage Schema Update

The `GET /v1/agent/history` endpoint now returns messages with a `message_type` field:

```json
{
  "id": "msg_abc123",
  "author": "system",
  "content": "Rate limited by OpenRouter. Retrying in 5.0s...",
  "timestamp": "2026-01-02T10:15:30Z",
  "is_agent": true,
  "message_type": "error"
}
```

**`message_type` values:**
| Value | Description | Visual Treatment |
|-------|-------------|------------------|
| `"user"` | User-sent message | Default user bubble |
| `"agent"` | Agent response | Default agent bubble |
| `"system"` | System notification | Distinct info style |
| `"error"` | Error notification | Distinct error style |

### 2. System Channel

All users now receive messages from the `"system"` channel in addition to their personal channel. This is automatic - no client-side changes needed for fetching.

### 3. `is_agent` Flag Semantics

- `is_agent=true` now includes system/error messages (prevents agent self-observation)
- **Do NOT filter by `is_agent`** to show/hide messages
- **Use `message_type`** to determine visual styling

---

## Required UI Changes

### A. Message Rendering

Clients **must** handle all four message types:

```typescript
// Example React component
function MessageBubble({ message }: { message: ConversationMessage }) {
  switch (message.message_type) {
    case 'user':
      return <UserBubble>{message.content}</UserBubble>;
    case 'agent':
      return <AgentBubble>{message.content}</AgentBubble>;
    case 'system':
      return <SystemNotification>{message.content}</SystemNotification>;
    case 'error':
      return <ErrorNotification>{message.content}</ErrorNotification>;
    default:
      return <UserBubble>{message.content}</UserBubble>;
  }
}
```

### B. Visual Design Requirements

#### System Messages (`message_type: "system"`)
- **Background:** Light blue/gray (info color)
- **Icon:** Info icon (ℹ️)
- **Position:** Centered, not in left/right bubble flow
- **Text:** Regular weight, muted color

#### Error Messages (`message_type: "error"`)
- **Background:** Light red/orange (warning color)
- **Icon:** Warning icon (⚠️) or Error icon (❌)
- **Position:** Centered, not in left/right bubble flow
- **Text:** Regular weight, error color

#### Example Visual Layout
```
┌─────────────────────────────────────────┐
│  [You]: What is 2+2?                    │  <- user bubble (right)
├─────────────────────────────────────────┤
│     ⚠️ Rate limited. Retrying in 5s...  │  <- error (centered)
├─────────────────────────────────────────┤
│     ℹ️ Processing your request...       │  <- system (centered)
├─────────────────────────────────────────┤
│  [Scout]: The answer is 4.              │  <- agent bubble (left)
└─────────────────────────────────────────┘
```

### C. Error Message Categories

Clients may receive these error types (for potential special handling):

| Content Pattern | Category | Suggested UX |
|-----------------|----------|--------------|
| `"Rate limited by {provider}..."` | Rate limiting | Show countdown timer |
| `"LLM error ({n}/{max})..."` | LLM failure | Show retry indicator |
| `"LLM service '{name}' temporarily unavailable..."` | Circuit breaker | Show status indicator |
| `"Processing error in {dma}..."` | DMA failure | Show retry option |
| `"Message blocked: {reason}"` | Credit/Policy | Show upgrade/fix prompt |

---

## Migration Checklist

- [ ] **Parse `message_type` field** in history response
- [ ] **Add visual components** for system and error messages
- [ ] **Update message list rendering** to use message_type for styling
- [ ] **Remove any filtering by `is_agent`** that hides system/error messages
- [ ] **Test with mock data** including all four message types
- [ ] **Handle unknown message_type** gracefully (fallback to user style)

---

## Testing

### Test Payload
```json
{
  "messages": [
    {
      "id": "1", "author": "user123", "content": "Hello",
      "timestamp": "2026-01-02T10:00:00Z", "is_agent": false, "message_type": "user"
    },
    {
      "id": "2", "author": "system", "content": "Processing your request...",
      "timestamp": "2026-01-02T10:00:01Z", "is_agent": true, "message_type": "system"
    },
    {
      "id": "3", "author": "error", "content": "Rate limited. Retrying in 3s...",
      "timestamp": "2026-01-02T10:00:02Z", "is_agent": true, "message_type": "error"
    },
    {
      "id": "4", "author": "Scout", "content": "Hello! How can I help?",
      "timestamp": "2026-01-02T10:00:05Z", "is_agent": true, "message_type": "agent"
    }
  ],
  "total_count": 4,
  "has_more": false
}
```

---

## Questions?

Contact the backend team or refer to:
- `ciris_engine/logic/adapters/api/routes/agent.py` - API implementation
- `ciris_engine/logic/utils/error_emitter.py` - Error emission logic
- `FSD/system_messages.md` - Design specification
