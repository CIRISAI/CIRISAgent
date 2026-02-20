# QA Runner - CLAUDE.md

## Overview

The QA Runner is a comprehensive test framework for validating CIRIS API functionality. It manages server lifecycle, authentication, and provides SSE-based task completion monitoring.

## Key Architecture

### SSE-Based Task Completion Monitoring

**Critical**: Tests must wait for `TASK_COMPLETE` action via SSE before proceeding to the next test. This prevents the `updated_info_available` flag from being set, which triggers bypass conscience retries.

```
Flow:
1. submit_message() → returns immediately with task_id
2. Monitor SSE stream for action_result events
3. Wait specifically for action_executed="task_complete"
4. Get response from history (filter by submission time)
5. Proceed to next test
```

### FilterTestHelper (`modules/filter_test_helper.py`)

Monitors SSE stream at `/v1/system/runtime/reasoning-stream` for task completion:

```python
class FilterTestHelper:
    def __init__(self, base_url: str, token: str, verbose: bool = False):
        self.task_complete_seen = False  # Set when TASK_COMPLETE action seen

    def start_monitoring(self) -> None:
        # Connects to SSE stream, watches for action_result events

    def wait_for_task_complete(self, task_id=None, timeout=30.0) -> bool:
        # Waits for task_complete_seen flag
```

Key SSE event structure:
```json
{
  "events": [{
    "event_type": "action_result",
    "action_executed": "task_complete",  // or speak, memorize, etc.
    "execution_success": true,
    "task_id": "...",
    "thought_id": "..."
  }]
}
```

### Handler Tests (`modules/handler_tests.py`)

Tests all 10 handler verbs:
1. SPEAK - Communicate to user
2. MEMORIZE - Store to memory graph
3. RECALL - Query memory graph
4. FORGET - Remove from memory graph
5. TOOL - Execute external tool
6. OBSERVE - Fetch channel messages
7. DEFER - Defer to Wise Authority
8. REJECT - Reject request
9. PONDER - Think deeper
10. TASK_COMPLETE - Mark task done

**Test Flow**:
```python
async def _interact(self, message: str, timeout: float = 30.0) -> str:
    # 1. Reset task_complete_seen flag
    self.sse_helper.task_complete_seen = False

    # 2. Submit message (returns immediately)
    submission = await self.client.agent.submit_message(message)

    # 3. Wait for TASK_COMPLETE via SSE
    completed = self._wait_for_task_complete_action(timeout=timeout)

    # 4. Get response from history (after submission time)
    history = await self.client.agent.get_history(limit=10)
    for msg in history.messages:
        if msg.is_agent and msg.timestamp > submission_time:
            return msg.content
```

## Why SSE Monitoring Matters

Without proper SSE monitoring:
1. Test N+1 starts before Test N's task completes
2. New observation arrives in same channel as active task
3. `updated_info_available` flag gets set on the task
4. `UpdatedStatusConscience` triggers, forcing PONDER override
5. Task cycles through retries until DEFER at depth limit
6. Test fails with "Still processing" or wrong response

With SSE monitoring:
1. Each test waits for TASK_COMPLETE before proceeding
2. No overlapping tasks in the same channel
3. `updated_info_available` flag never set
4. Clean task completion every time

## Token Retrieval

The SSE helper needs the auth token from the client:

```python
transport = getattr(self.client, "_transport", None)
token = getattr(transport, "api_key", None) if transport else None
```

## Running Handler Tests

```bash
# Run all handler tests
python3 -m tools.qa_runner handlers

# With verbose output
python3 -m tools.qa_runner handlers --verbose
```

## Common Issues

### "TASK_COMPLETE not seen in 30.0s"
- SSE connection issue or mock LLM not returning TASK_COMPLETE
- Check that token is being passed correctly
- Check mock LLM follow-up handling

### "Still processing" response
- Test ran before previous task completed
- SSE monitoring not working
- Check FilterTestHelper connection

### Tests getting "defer" responses
- Follow-up thoughts not completing to TASK_COMPLETE
- Mock LLM follow-up detection needs adjustment
- Check `responses.py` handler_completion_patterns
