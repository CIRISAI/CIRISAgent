# Decision Making Algorithms (DMA)

## Overview

The DMA (Decision Making Algorithm) system provides structured, ethical decision-making capabilities for CIRIS. All DMAs follow the ethical principles defined in the Covenant and provide structured reasoning for their decisions.

## Architecture

### Base Classes

| Class | Purpose | File |
|-------|---------|------|
| **BaseDMA** | Abstract base for all DMAs | `base_dma.py` |
| **BaseDSDMA** | Base for Decision Support DMAs | `dsdma_base.py` |

### H3ERE DMA Architecture: 3 Core + 1 Recursive = 4 Total DMAs

| DMA Type | Class | Purpose | Protocol |
|----------|-------|---------|----------|
| **PDMA** | `EthicalPDMAEvaluator` | Principled ethical evaluation | `PDMAProtocol` |
| **CSDMA** | `CSDMAEvaluator` | Common-sense validation | `CSDMAProtocol` |
| **DSDMA** | `BaseDSDMA` | Domain-specific criteria | `DSDMAProtocol` |
| **ASPDMA** | `ActionSelectionPDMAEvaluator` | **Recursive action selection** | `ActionSelectionDMAProtocol` |

#### DMA Processing Flow
1. **PDMA, CSDMA, DSDMA** evaluate thoughts against their respective criteria
2. **ASPDMA** recursively processes the 3 DMA outputs to select final action
3. Selected action triggers one of the 10 H3ERE handlers

## Key Components

### 1. Prompt Management
- **File**: `prompt_loader.py`
- **Purpose**: Centralized prompt loading and template management
- **Features**: YAML-based prompt definitions with override support

### 2. Action Selection
- **File**: `action_selection_pdma.py`
- **Purpose**: Specialized PDMA for action selection decisions
- **Features**: Context-aware action evaluation and selection

### 3. Exception Handling
- **File**: `exceptions.py`
- **Class**: `DMAFailure`
- **Purpose**: Structured error handling for DMA operations

## Usage Patterns

### Basic DMA Usage
```python
from ciris_engine.logic.dma import EthicalPDMAEvaluator

# Initialize with service registry
dma = EthicalPDMAEvaluator(service_registry=registry)

# Evaluate a decision
result = await dma.evaluate(thought_data, context)

# Access structured result
print(f"Decision: {result.decision}")
print(f"Confidence: {result.confidence}")
print(f"Reasoning: {result.reasoning}")
```

### Custom Prompts
```python
# Override default prompts
prompt_overrides = {
    "system_prompt": "Custom ethical evaluation prompt..."
}

dma = EthicalPDMAEvaluator(
    service_registry=registry,
    prompt_overrides=prompt_overrides
)
```

## Ethical Framework

All DMAs in CIRIS are bound by the **Covenant** ethical framework:

1. **Beneficence**: Decisions must benefit users and society
2. **Non-maleficence**: Avoid harm in all decisions
3. **Autonomy**: Respect user agency and choice
4. **Justice**: Fair and equitable treatment
5. **Transparency**: Clear reasoning for all decisions

## Integration Points

### Service Dependencies
- **LLMService**: For language model access via LLMBus
- **MemoryService**: For context and historical data via MemoryBus
- **TelemetryService**: For decision tracking and metrics

### Protocol Compliance
All DMAs implement specific protocols:
- Input/output type safety via generics
- Structured error handling via `DMAFailure`
- Consistent evaluation interface
- Telemetry integration for decision tracking

## Configuration

DMAs support various configuration options:
- **Model Selection**: Choose LLM backend (OpenAI, Anthropic, etc.)
- **Retry Logic**: Configure retry attempts for failed evaluations
- **Prompt Customization**: Override default prompts for specific use cases
- **Temperature Settings**: Control randomness in LLM responses

## Development Guidelines

### Creating New DMAs
1. Extend appropriate base class (`BaseDMA`, `BaseDSDMA`)
2. Implement required protocol methods
3. Define input/output schemas with Pydantic
4. Add comprehensive error handling
5. Include telemetry integration
6. Write unit tests with mock data

### Testing DMAs
- Use `MockLLMService` for unit tests
- Test both success and failure scenarios
- Validate ethical compliance in test cases
- Ensure structured output schema compliance

## File Structure

```
dma/
├── __init__.py              # Public API exports
├── base_dma.py             # Abstract base classes
├── dsdma_base.py           # Decision Support DMA base
├── exceptions.py           # DMA-specific exceptions
├── pdma.py                 # Primary Decision Making Algorithm
├── csdma.py               # Confidence Scoring DMA
├── action_selection_pdma.py # Action selection specialization
└── prompt_loader.py        # Prompt management utilities
```

## Related Documentation
- [Protocols Documentation](../protocols/README.md) - DMA protocol definitions
- [Schemas Documentation](../../schemas/README.md) - DMA input/output schemas
- [LLM Bus Documentation](../buses/llm_bus.md) - Language model integration
- [Service Registry Documentation](../registries/README.md) - Service discovery
