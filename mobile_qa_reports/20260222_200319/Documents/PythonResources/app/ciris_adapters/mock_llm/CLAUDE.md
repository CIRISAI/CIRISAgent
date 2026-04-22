# Mock LLM Adapter - CLAUDE.md

## Overview

The Mock LLM provides deterministic responses for offline testing of CIRIS. It simulates a real LLM by parsing commands and generating appropriate handler actions.

## Core Principle: Handler Flow

**Critical**: The mock LLM must follow the correct handler completion flow:

```
Non-terminal handlers → SPEAK result → TASK_COMPLETE
Terminal handlers → Done (no follow-up needed)

Terminal:     DEFER, REJECT, TASK_COMPLETE
Non-terminal: SPEAK, MEMORIZE, RECALL, FORGET, TOOL, OBSERVE, PONDER
```

### Correct Flow Examples

```
SPEAK → follow-up → TASK_COMPLETE
MEMORIZE → follow-up → SPEAK result → follow-up → TASK_COMPLETE
RECALL → follow-up → SPEAK result → follow-up → TASK_COMPLETE
PONDER → follow-up → SPEAK conclusion → follow-up → TASK_COMPLETE
TOOL → follow-up → SPEAK result → follow-up → TASK_COMPLETE
OBSERVE → follow-up → SPEAK result → follow-up → TASK_COMPLETE
FORGET → follow-up → SPEAK result → follow-up → TASK_COMPLETE
```

**Why SPEAK before TASK_COMPLETE?**
- Handler results must be communicated to the user
- TASK_COMPLETE without SPEAK causes validation errors
- Tests expect handler output in the response

## Key Files

### `responses.py` - Context Extraction

Extracts context from LLM messages and detects follow-up thoughts:

```python
# Handler completion patterns (deterministic prefixes)
handler_completion_patterns = [
    ("MEMORIZE COMPLETE", "memorize"),
    ("MEMORIZE action", "memorize"),
    ("FORGET COMPLETE", "forget"),
    ("RECALL COMPLETE", "recall"),
    ("Memory query", "recall"),
    ("=== PONDER ROUND", "ponder"),      # From PonderHandler
    ("=== PREVIOUS CONTEXT", "ponder"),  # Accumulated ponder context
]
```

Context items passed to action selection:
- `is_followup:true` - This is a follow-up thought
- `followup_type:speak|memorize|recall|...` - What handler created this
- `should_task_complete:true` - Only for SPEAK follow-ups
- `followup_content:...` - The follow-up thought content

### `responses_action_selection.py` - Action Selection

Determines which action to return based on context:

**Early Follow-up Handling** (lines ~310-330):
```python
if is_followup_from_context:
    if followup_type == "speak":
        # SPEAK follow-up → TASK_COMPLETE
        return TASK_COMPLETE
    else:
        # Other handlers → SPEAK the result
        return SPEAK with handler result
```

**Late Follow-up Handling** (lines ~880-990):
Pattern detection for when early handling doesn't trigger:
- `is_speak_followup` → TASK_COMPLETE
- `is_ponder_followup` → SPEAK conclusion
- `is_memorize_followup|is_recall_followup|...` → SPEAK result
- Unknown → SPEAK summary (creates SPEAK follow-up → TASK_COMPLETE)

## Deterministic Patterns

Each handler creates follow-up thoughts with deterministic content:

| Handler | Follow-up Content Pattern |
|---------|--------------------------|
| SPEAK | `SPEAK SUCCESSFUL! Message delivered...` |
| MEMORIZE | `MEMORIZE COMPLETE - stored observation...` |
| RECALL | `Memory query...returned:...` or `RECALL COMPLETE...` |
| FORGET | `FORGET COMPLETE...` or `successfully forgot key...` |
| TOOL | `TOOL action {name} executed for thought...` |
| OBSERVE | `OBSERVE action completed. Info: Fetched...` |
| PONDER | `=== PONDER ROUND {n} ===` with `Conscience feedback:` |

## Command Syntax

The mock LLM recognizes `$command` syntax:

```
$speak <message>           - Send message
$memorize <id> [type] [scope] - Store to memory
$recall <query>            - Query memory
$forget <id> <reason>      - Remove from memory
$ponder <q1>; <q2>        - Think about questions
$tool <name> [params]      - Execute tool
$observe [channel]         - Observe channel
$defer <reason>            - Defer to authority
$reject <reason>           - Reject request
$task_complete             - Complete task
$help                      - Show help
```

## Schema Compliance

**Critical**: Use correct field names for schemas:

```python
# TaskCompleteParams uses completion_reason, NOT summary
TaskCompleteParams(completion_reason="...")  # Correct
TaskCompleteParams(summary="...")            # WRONG - validation error!
```

## Debugging

Add logging to trace follow-up detection:

```python
logger.info(f"[MOCK_LLM] FOLLOW-UP CONTENT: {content[:100]}...")
logger.info(f"[MOCK_LLM] followup_type={followup_type}")
logger.info(f"[MOCK_LLM] is_ponder_followup={is_ponder_followup}")
```

Check logs for:
- `DETECTED FOLLOW-UP THOUGHT` - Follow-up was recognized
- `FOLLOW-UP CONTENT:` - What content was extracted
- `→ SPEAK result` or `→ TASK_COMPLETE` - What action was chosen

## Common Issues

### Infinite loops (SPEAK → SPEAK → ... → DEFER)
- Follow-up detection not matching patterns
- Add pattern to `handler_completion_patterns`
- Check early follow-up handling in `responses_action_selection.py`

### "validation error for TaskCompleteParams"
- Using wrong field name (e.g., `summary` instead of `completion_reason`)
- Check schema in `ciris_engine/schemas/actions/parameters.py`

### Handler not detected as follow-up
- Pattern not in `handler_completion_patterns` list
- Content doesn't start with expected prefix
- Add new pattern for the handler's deterministic output
