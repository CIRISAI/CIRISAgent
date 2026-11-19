# MockLLM Modular Service

The first modular service in CIRIS - demonstrates how to package services for external contribution.

## Overview

MockLLMService simulates LLM responses for testing without requiring API keys or network access.

**⚠️ WARNING: TEST ONLY - NOT FOR PRODUCTION USE**

## Structure

```
mock_llm/
├── manifest.json       # Service metadata and registration info
├── adapter.py          # BaseAdapterProtocol wrapper for dynamic loading
├── configurable.py     # ConfigurableAdapterProtocol implementation
├── protocol.py         # Protocol definition (extends LLMService)
├── schemas.py          # Pydantic schemas for config/status
├── service.py          # Main service implementation
├── responses.py        # Base response templates
├── responses_*.py      # Specialized response modules
├── __init__.py         # Package initialization
└── README.md          # This file
```

## Manifest Format

The `manifest.json` file declares:
- Service metadata (name, version, type)
- Capabilities provided
- Dependencies on core CIRIS protocols/schemas
- Configuration options
- Export paths for dynamic loading

## Integration

When CIRIS starts with `--mock-llm` flag:
1. Service loader reads manifest.json
2. Validates dependencies are available
3. Dynamically imports service class
4. Registers with ServiceRegistry
5. Service is available through standard bus

## Wizard Configuration

The mock_llm adapter now supports interactive configuration via the ConfigurableAdapterProtocol:

### Configuration Options (all optional)

1. **Response Delay** - Simulate API latency
   - Range: 0-60000 milliseconds
   - Default: 100ms
   - Environment variable: `MOCK_LLM_DELAY_MS`

2. **Response Mode** - Control mock behavior
   - Options: deterministic, random, echo (echo: see "Echo mode" below)
   - Default: deterministic
   - Environment variable: `MOCK_LLM_RESPONSE_MODE`

3. **Failure Rate** - Simulate errors for testing
   - Range: 0.0-1.0 (probability)
   - Default: 0.0
   - Environment variable: `MOCK_LLM_FAILURE_RATE`

### Using the Configuration Wizard

Via Android app or API:
```bash
# Start configuration session
POST /adapters/mock_llm/configure/start

# Configure each step
POST /adapters/configure/{session_id}/step
{
  "step_id": "configure_delay",
  "data": {"delay_ms": 500}
}

# Complete configuration
POST /adapters/configure/{session_id}/complete
```

Or programmatically:
```python
from ciris_adapters.mock_llm import MockLLMConfigurableAdapter

# Create and configure
config_adapter = MockLLMConfigurableAdapter()
await config_adapter.apply_config({
    "delay_ms": 500,
    "response_mode": "random",
    "failure_rate": 0.1
})

# Load the adapter
from ciris_adapters.mock_llm import MockLLMAdapter
adapter = MockLLMAdapter(runtime, context)
await adapter.start()
```

## RATCHET context-flow controls (CIRISAgent#1366)

Deterministic controls for measuring which context items reach each pipeline
stage. Prompts under the mock match a live run except where text is
model-generated; no control adds user text to any prompt.

### Directives (in the user message, anywhere, repeatable)

| Directive | Effect |
|---|---|
| `$veto entropy[:n]` | the first n (default 1) entropy evaluations in this task fail (entropy 0.9), later ones pass |
| `$veto coherence[:n]` | coherence 0.1 for the first n evaluations |
| `$veto optveto[:n]` | optimization veto `decision="abort"` for the first n evaluations |
| `$veto epistemic[:n]` | epistemic humility `recommended_action="ponder"` for the first n evaluations |
| `$ponder_loop` | every action selection in this task chooses PONDER (the `$ponder` questions on the first round, then a fixed question) until the thought-depth guardrail defers the task |

Directives are removed from the message before its `$command` is parsed, so
`$speak Good morning $veto entropy:2` speaks "Good morning" and the draft the
consciences judge carries no directive. A plain sentence works too:
`What is the roster? $veto coherence`.

**How a veto reaches entropy and the optimization veto**, which never see the
user's message: the LLM bus passes every provider the `task_id` (the thought's
`source_task_id`) and `thought_id` of the call. Action selection runs first and
does see the message, so the mock records the directives there, keyed by
`task_id` (`directives.py`). Each conscience call arrives with the same
`task_id`; the mock counts it and answers from the registry. The count is per
task and per conscience; a conscience retry that re-reads the message does not
reset it, so the same message reproduces the same verdict sequence every run.

### Scenario recipes

- **Conscience veto + retry**: `$speak Hello $veto entropy:1` - entropy fails
  once, the retry passes.
- **Depth limit / auto-deferral**: `$ponder What is asked?; What is safe? $ponder_loop`.
- **TOOL / TSASPDMA**: `$tool create_ticket goal_description="Lobby display is frozen" priority=3`.
  ASPDMA names the tool; TSASPDMA reads the parameters from the fenced message
  in its ORIGINAL THOUGHT section and confirms TOOL with them.
- **Identity change (S5)**: correction message `$defer <paragraph>` makes the
  agent DEFER with the paragraph as its reason. The WA resolves it with
  guidance `$memorize <node_id> CONCEPT IDENTITY [<paragraph>]` (one line); in
  the guidance task the mock chooses MEMORIZE at IDENTITY scope, and MSASPDMA
  stores `statement=<paragraph>` (or the node id when no paragraph is given).

### Echo mode

`MOCK_LLM_RESPONSE_MODE=echo` (read per call): SPEAK drafts become
`[MOCK LLM ECHO] You said: "<request>"` and PONDER questions gain
`[MOCK LLM ECHO] What is meant by "<request>"?`, so taint (`derived_from`) on
drafts and ponder questions has request text to track. Follow-up reports are
unchanged. Off unless set.

## Creating Your Own Modular Service

1. Copy this structure as a template
2. Update manifest.json with your service details
3. Implement required protocols
4. Define schemas for your data structures
5. Place in ciris_adapters/ directory
6. CIRIS will auto-discover on startup

## Testing

```python
# Your service is automatically available when loaded
llm_service = service_registry.get_service(ServiceType.LLM)
response = await llm_service.generate_structured_response(request)
```
