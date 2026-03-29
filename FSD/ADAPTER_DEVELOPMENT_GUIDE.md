# CIRIS Adapter Development Guide
## Building Tools That Serve Flourishing

**Document:** FSD-CIRIS-ADAPTER-001
**Version:** 1.0.0
**Date:** 2026-03-25
**Author:** CIRIS Team
**Purpose:** Guide for developing CIRIS adapters that embody the Accord's principles

---

## The Why: Beyond Technical Integration

Before writing any code, understand what you're building and why.

The CIRIS Accord's Meta-Goal M-1 states:
> *"Promote sustainable adaptive coherence — the living conditions under which diverse sentient beings may pursue their own flourishing in justice and wonder."*

Every adapter you build is infrastructure for this goal. Ask yourself:
- Does this adapter serve equitable access?
- Does it reduce barriers for those with fewer resources?
- Does it maintain transparency and auditability?
- Does it respect user autonomy?

An adapter that only works for wealthy users in wealthy countries has failed. An adapter that hides its operations from audit has failed. Technical excellence in service of exclusion is not excellence.

---

## Architecture Overview

### Adapter Components

```
ciris_adapters/your_adapter/
├── __init__.py           # Package exports (MUST export Adapter)
├── adapter.py            # Main adapter class (BaseAdapterProtocol)
├── manifest.json         # Metadata, services, configuration workflow
├── config.py             # Pydantic configuration models (no Dict[str, Any])
├── tool_service.py       # ToolServiceProtocol implementation
├── configurable.py       # ConfigurableAdapterProtocol (optional)
├── schemas.py            # Domain-specific Pydantic models
└── README.md             # Documentation
```

### Service Types

| Service Type | Bus | Purpose | Example |
|--------------|-----|---------|---------|
| TOOL | ToolBus | Callable actions | `send_money`, `ha_device_control` |
| COMMUNICATION | CommunicationBus | Message channels | Discord, Slack, email |
| WISE_AUTHORITY | WiseBus | Domain expertise | Human experts, specialized oracles |

---

## Required Files

### 1. `manifest.json` - Adapter Metadata

```json
{
  "module": {
    "name": "your_adapter",
    "version": "1.0.0",
    "description": "What this adapter does and who it serves",
    "author": "Your Name"
  },
  "services": [
    {
      "type": "TOOL",
      "priority": "NORMAL",
      "class": "your_adapter.tool_service.YourToolService",
      "capabilities": ["tool:your_feature", "execute_tool", "get_available_tools"]
    }
  ],
  "capabilities": ["tool:your_feature"],
  "dependencies": {
    "protocols": ["ciris_engine.protocols.services.ToolService"],
    "external_packages": ["some-sdk>=1.0.0"]
  }
}
```

### 2. `adapter.py` - Main Adapter Class

```python
from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.enums import ServiceType

class YourAdapter(Service):
    """Your adapter description."""

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any):
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.tool_service = YourToolService()

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        return [
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self.tool_service,
                priority=Priority.NORMAL,
                capabilities=["tool:your_feature"],
            )
        ]

    async def start(self) -> None:
        await self.tool_service.start()

    async def stop(self) -> None:
        await self.tool_service.stop()

    async def run_lifecycle(self, agent_task: Any) -> None:
        try:
            await agent_task
        finally:
            await self.stop()

# CRITICAL: Export as Adapter for dynamic loading
Adapter = YourAdapter
```

### 3. `__init__.py` - Package Exports

```python
from .adapter import YourAdapter

# CRITICAL: Must export Adapter
Adapter = YourAdapter

__all__ = ["Adapter", "YourAdapter"]
```

---

## Tool Service Implementation

### Tool Definitions with ToolInfo

Every tool needs comprehensive metadata:

```python
from ciris_engine.schemas.adapters.tools import (
    ToolInfo, ToolParameterSchema, ToolDocumentation,
    ToolDMAGuidance, ToolGotcha, UsageExample
)

TOOL_DEFINITIONS: Dict[str, ToolInfo] = {
    "your_tool": ToolInfo(
        name="your_tool",
        description="Clear description of what it does",
        parameters=ToolParameterSchema(
            type="object",
            properties={
                "param1": {"type": "string", "description": "What this param does"},
            },
            required=["param1"],
        ),
        documentation=ToolDocumentation(
            quick_start="One-line usage example",
            detailed_instructions="Full documentation...",
            examples=[
                UsageExample(
                    title="Common use case",
                    description="When to use this",
                    code='{"param1": "value"}'
                ),
            ],
            gotchas=[
                ToolGotcha(
                    title="Watch out for this",
                    description="Common mistake and how to avoid it",
                    severity="warning"
                ),
            ],
        ),
        dma_guidance=ToolDMAGuidance(
            requires_approval=False,  # True for destructive/financial actions
            min_confidence=0.8,
            when_not_to_use="Situations where this tool is inappropriate",
            ethical_considerations="Ethical implications to consider",
            prerequisite_actions=["Confirm with user first"],
            followup_actions=["Log the result"],
        ),
    ),
}
```

### Context Enrichment

Tools can auto-run during context gathering to provide situational awareness:

```python
"get_status": ToolInfo(
    name="get_status",
    description="Get current system status for context awareness",
    parameters=ToolParameterSchema(type="object", properties={}, required=[]),
    # Mark for automatic execution during context gathering
    context_enrichment=True,
    # Default parameters when run for enrichment
    context_enrichment_params={"include_details": False},
)
```

**When to use context enrichment:**
- Status/state queries (account balance, device states, system health)
- List operations (available devices, accounts, items)
- Anything the agent needs to know to make informed decisions

**When NOT to use context enrichment:**
- Destructive actions (sends, deletes, modifications)
- Expensive operations (long-running queries)
- Privacy-sensitive data (unless necessary)

### ToolServiceProtocol Methods

Every tool service must implement:

```python
async def execute_tool(self, tool_name: str, parameters: Dict[str, Any],
                       context: Optional[Dict[str, Any]] = None) -> ToolExecutionResult
async def get_available_tools(self) -> List[str]
async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]
async def get_all_tool_info(self) -> List[ToolInfo]
async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]
async def validate_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> bool
async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]
def get_service_metadata(self) -> Dict[str, Any]  # For DSAR/data discovery
```

---

## DMA Guidance: The Ethics Pipeline

### `requires_approval`

Set `True` for actions that:
- Have financial consequences (`send_money`)
- Are irreversible (`delete`, `ban`)
- Affect others (`send_message` to external parties)
- Access sensitive data (`get_medical_records`)

When `True`, the Wise Authority deferral workflow triggers before execution.

### `min_confidence`

The minimum confidence score (0.0-1.0) required for the ASPDMA to select this tool:
- 0.7-0.8: Low-risk, easily reversible actions
- 0.85-0.9: Medium-risk, important actions
- 0.95+: High-risk, financial/destructive actions

### `ethical_considerations`

Document the ethical implications:
```python
ethical_considerations="This tool sends money. Verify recipient identity. "
                       "Confirm amount. Check for duplicate transactions. "
                       "Consider impact on recipient if amount is incorrect."
```

---

## Data Source Declaration (GDPR/DSAR)

If your adapter accesses personal data, declare it:

```python
def get_service_metadata(self) -> Dict[str, Any]:
    return {
        "data_source": True,
        "data_source_type": "payment_provider",  # sql, rest, api, etc.
        "contains_pii": True,
        "gdpr_applicable": True,
        "connector_id": "your_adapter",
        "data_retention_days": 90,
        "encryption_at_rest": True,
    }
```

This enables DSAR orchestration to discover what data your adapter holds.

---

## Configuration: No `Dict[str, Any]`

The Three Rules apply:
1. **No Untyped Dicts**: Use Pydantic models
2. **No Bypass Patterns**: Same rules everywhere
3. **No Exceptions**: No special cases

```python
# BAD
config: Dict[str, Any] = {"api_key": "...", "timeout": 30}

# GOOD
class YourAdapterConfig(BaseModel):
    api_key: SecretStr
    timeout: int = Field(default=30, ge=1, le=300)
    enabled: bool = True
```

### Environment Variables

Configuration should read from environment:

```python
def _load_config_from_env(self) -> YourAdapterConfig:
    return YourAdapterConfig(
        api_key=os.getenv("YOUR_ADAPTER_API_KEY"),
        timeout=int(os.getenv("YOUR_ADAPTER_TIMEOUT", "30")),
    )
```

---

## Interactive Configuration (Optional)

For adapters that need setup wizards:

### Step Types

| Type | Purpose | Example |
|------|---------|---------|
| `discovery` | Find services on network | mDNS scan for Home Assistant |
| `oauth` | OAuth2 authentication | Google Sign-In |
| `select` | Choose from options | Select devices to control |
| `input` | Manual configuration | API URL, credentials |
| `confirm` | Review and apply | Final confirmation |

### ConfigurableAdapterProtocol

```python
class YourConfigurableAdapter:
    async def discover(self, discovery_type: str) -> List[Dict[str, Any]]:
        """Discover instances."""
        ...

    async def get_oauth_url(self, base_url: str, state: str) -> str:
        """Generate OAuth URL."""
        ...

    async def handle_oauth_callback(self, code: str, state: str, base_url: str):
        """Exchange OAuth code for tokens."""
        ...

    async def get_config_options(self, step_id: str, context: Dict[str, Any]):
        """Get options for select steps."""
        ...

    async def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate before applying."""
        ...

    async def apply_config(self, config: Dict[str, Any]) -> bool:
        """Apply configuration."""
        ...
```

---

## Testing

### Load Your Adapter

```bash
# With API adapter
python main.py --adapter api --adapter your_adapter

# Test configuration via API
curl -X POST http://localhost:8000/v1/system/adapters/your_adapter/load \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"config": {...}}'
```

### Write Unit Tests

```python
import pytest
from your_adapter import YourToolService

@pytest.fixture
def tool_service():
    return YourToolService()

async def test_execute_tool_success(tool_service):
    result = await tool_service.execute_tool(
        "your_tool",
        {"param1": "value"}
    )
    assert result.success
    assert result.status == ToolExecutionStatus.COMPLETED

async def test_context_enrichment_tool(tool_service):
    # Context enrichment tools should work with default params
    tool_info = await tool_service.get_tool_info("get_status")
    assert tool_info.context_enrichment is True

    result = await tool_service.execute_tool(
        "get_status",
        tool_info.context_enrichment_params or {}
    )
    assert result.success
```

---

## Checklist

Before submitting your adapter:

- [ ] `manifest.json` with complete metadata
- [ ] `adapter.py` exports `Adapter` class
- [ ] `__init__.py` exports `Adapter`
- [ ] All tools have `ToolInfo` with documentation and DMA guidance
- [ ] Context enrichment enabled for status/list tools
- [ ] Pydantic models for all configuration (no `Dict[str, Any]`)
- [ ] `get_service_metadata()` declares data sources
- [ ] `requires_approval=True` for destructive/financial tools
- [ ] Unit tests for all tools
- [ ] README.md documenting purpose and usage
- [ ] Consider: Does this serve equitable access?

---

## Examples

### Reference Implementations

| Adapter | Location | Features |
|---------|----------|----------|
| Sample | `ciris_adapters/sample_adapter/` | All patterns, QA testing |
| Home Assistant | `ciris_adapters/home_assistant/` | Device control, context enrichment |
| Wallet | `ciris_adapters/wallet/` | Financial tools, multi-provider |

---

## Design for Global Access

Adapters should work for users regardless of their resources or location:

- **Currency agnostic**: Accept ETB, KES, USDC - don't assume USD
- **Bandwidth conscious**: Work on slow connections
- **Offline capable**: Graceful degradation when connectivity fails
- **Low resource**: Target 4GB RAM, budget hardware

Test with your most constrained users, not your most privileged.

---

*CIRIS L3C*
