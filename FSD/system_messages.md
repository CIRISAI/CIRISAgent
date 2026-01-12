# FSD: System Messages for UI/UX Visibility

## Overview

System messages provide real-time visibility into agent processing status, errors, and decisions that don't result in user-visible responses. These messages enable UIs to display meaningful feedback during agent operations.

## Current State

### Existing Infrastructure
- `APICommunicationService.send_system_message(channel_id, content, message_type, author_name)`
- `message_type`: "system" | "error"
- Messages stored via correlation tracking
- Retrievable via `GET /v1/agent/history` with `message_type` field

### Current Usage (Limited)
1. **Speak Handler** - "Failed to deliver agent response" on SPEAK failure
2. **Agent Routes** - Billing errors, message blocking, credit denial

### Missing Coverage
- DMA failures (rate limits, schema validation)
- Action selection failures
- Conscience vetoes (optimization, ethical, epistemic)
- Non-SPEAK action completions (OBSERVE, RECALL, DEFER, PONDER)
- Wakeup phase progress/completion
- Circuit breaker state changes

## Desired Behavior

### Message Categories

#### 1. Processing Status (`message_type: "system"`)
Informational messages about agent state and progress.

| Event | Message Template |
|-------|------------------|
| Wakeup phase complete | `"[Wakeup] {phase_name} complete: {affirmation_preview}..."` |
| Action executed (non-SPEAK) | `"Agent performed {action_type} action for task"` |
| Task deferred | `"Agent deferred to {authority} for guidance"` |
| Observation recorded | `"Agent observed and recorded context"` |

#### 2. Processing Errors (`message_type: "error"`)
Error conditions the user should be aware of.

| Event | Message Template |
|-------|------------------|
| Rate limit hit | `"Rate limited by LLM provider. Retrying in {wait_time}s..."` |
| DMA failure | `"Processing error: {dma_name} failed. Retrying..."` |
| All retries exhausted | `"Processing failed after {n} attempts: {error_summary}"` |
| Circuit breaker open | `"LLM service temporarily unavailable. Will retry shortly."` |
| Conscience veto | `"Action vetoed by {conscience_type}: {reason_preview}..."` |

#### 3. Decision Transparency (`message_type: "system"`)
Explain agent decisions that don't produce visible output.

| Event | Message Template |
|-------|------------------|
| PONDER action | `"Agent is reflecting on: {ponder_question_preview}..."` |
| REJECT action | `"Agent declined task: {rejection_reason}"` |
| Task filtered | `"Message filtered: {filter_reason}"` |

### API Response Format

`GET /v1/agent/history` returns messages with:

```json
{
  "messages": [
    {
      "id": "msg_123",
      "author": "System",
      "content": "Rate limited by LLM provider. Retrying in 5s...",
      "timestamp": "2025-01-01T00:00:00Z",
      "is_agent": false,
      "message_type": "error"
    },
    {
      "id": "msg_124",
      "author": "Datum",
      "content": "Agent performed OBSERVE action for task",
      "timestamp": "2025-01-01T00:00:01Z",
      "is_agent": true,
      "message_type": "system"
    }
  ]
}
```

### Implementation Points

#### LLM Bus (`llm_bus.py`)
Emit system messages on:
- Rate limit detection (before retry wait)
- Schema validation retry
- Circuit breaker state change
- All retries exhausted

#### Thought Processor (`thought_processor/main.py`)
Emit system messages on:
- Conscience veto with reason
- Non-SPEAK action completion
- PONDER/DEFER decisions

#### Wakeup Processor (`wakeup_processor.py`)
Emit system messages on:
- Each wakeup phase completion
- Wakeup failure with reason

#### Action Dispatcher (`action_dispatcher.py`)
Emit system messages on:
- Non-SPEAK action success
- Action failure with context

### Channel Routing

System messages should be sent to the channel associated with the current task/thought:
1. Get `channel_id` from thought context or task metadata
2. Fall back to default API channel if not available
3. Use `api_{ip}_{port}` format for API adapter channels

### QA Validation

The `system_messages` QA module should verify:

1. **Rate Limit Messages**
   - Trigger rate limit condition
   - Verify error message appears in history
   - Verify message includes wait time

2. **Processing Error Messages**
   - Trigger DMA failure
   - Verify error message appears
   - Verify retry count in message

3. **Non-SPEAK Action Messages**
   - Trigger OBSERVE/RECALL/DEFER actions
   - Verify system message appears
   - Verify action type in message

4. **Conscience Veto Messages**
   - Trigger conscience rejection
   - Verify veto message with reason

5. **History Retrieval**
   - Verify `message_type` field is correct
   - Verify chronological ordering
   - Verify `is_agent` flag is correct

## Implementation Priority

1. **High**: Rate limit and DMA failure messages (immediate debugging value)
2. **Medium**: Conscience veto messages (transparency)
3. **Medium**: Non-SPEAK action messages (completeness)
4. **Low**: Wakeup progress messages (nice-to-have)

## Notes

- Messages should be concise (<200 chars) for UI display
- Include enough context to be actionable
- Rate limit messages to avoid flooding (max 1 per 5s per category)
- Consider SSE stream integration for real-time updates
