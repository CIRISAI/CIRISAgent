# H3ERE Action Handlers

## Overview

CIRIS implements the **H3ERE (Hyper3 Ethical Recursive Engine)** architecture with exactly 10 action handlers organized in a 3×3×3×3 structure. These handlers execute ethically-approved actions determined by the 3 Decision-Making Algorithms (PDMA, CSDMA, DSDMA) operating across 3 Contextual Knowledge Graphs.

## H3ERE Architecture: 3×3×3×3 Ethical Recursive Engine

### 4 Decision-Making Algorithms (DMAs): 3 Core + 1 Recursive
- **PDMA** (Principled DMA): Foundational ethical principles
- **CSDMA** (Common-Sense DMA): Universal common-sense contexts  
- **DSDMA** (Domain-Specific DMA): Specialized task-relevant criteria
- **ASPDMA** (Action Selection PDMA): Recursive final action selection from 3 DMA outputs

### 3 Contextual Knowledge Graphs
- **Core Identity Graph**: Ethical identity and system imperatives
- **Environmental Graph**: Common-sense understanding of the world
- **Task-Specific Graph**: Mission-relevant operational context

### 3 Core Handlers × 3 Options Each + 1 Terminal = 10 Total Handlers

## The 10 H3ERE Handlers

### Action Handler (3 Options)
| Handler | Action | Purpose | Ethical Function |
|---------|--------|---------|------------------|
| **SpeakHandler** | SPEAK | External communication | Ethically express thoughts and responses |
| **ToolHandler** | ACT | Tool execution | Perform ethically-approved external actions |
| **ObserveHandler** | LISTEN | Environmental awareness | Gather context while respecting boundaries |

### Memory Handler (3 Options)  
| Handler | Action | Purpose | Ethical Function |
|---------|--------|---------|------------------|
| **MemorizeHandler** | MEMORIZE | Store information | Ethically preserve knowledge with consent |
| **RecallHandler** | REMEMBER | Retrieve information | Access memories while respecting privacy |
| **ForgetHandler** | FORGET | Remove information | Ethically delete information when appropriate |

### Deferral Handler (3 Options)
| Handler | Action | Purpose | Ethical Function |
|---------|--------|---------|------------------|
| **RejectHandler** | REJECT | Refuse unsafe actions | Ethically refuse inappropriate or harmful requests |
| **PonderHandler** | PONDER | Deep reflection | Consider complex ethical implications |
| **DeferHandler** | DEFER | Escalate to authority | Delegate complex decisions to Wise Authority |

### Terminal Handler (1 Option)
| Handler | Action | Purpose | Ethical Function |
|---------|--------|---------|------------------|
| **TaskCompleteHandler** | TASK_COMPLETE | Finalize tasks | Complete ethically-approved objectives |

## Conscience Evaluation Coverage

Before handlers execute, the **Conscience System** evaluates actions for ethical safety:

**Actions Subject to Conscience (5)**:
- **SPEAK** - External communication requires ethical validation
- **TOOL** (ACT) - External actions require safety checks
- **PONDER** - Internal reflection can be overridden for better alignment
- **MEMORIZE** - Writing to memory requires validation
- **FORGET** - Deleting from memory requires validation

**Exempt Actions (5)**:
- **RECALL** (REMEMBER) - Passive memory retrieval, no ethical implications
- **TASK_COMPLETE** - Terminal action, already fully vetted
- **OBSERVE** (LISTEN) - Passive observation, no external output
- **DEFER** - Explicit decision to decline action
- **REJECT** - Explicit refusal to engage

Exempt actions bypass conscience checks as they are passive input operations or explicit non-engagement.

## Ethical Recursive Processing

The H3ERE engine operates through ethical recursive loops:

1. **Thought Generation**: Initial ethical thoughts trigger DMA evaluation
2. **DMA Evaluation**: All 3 DMAs (PDMA, CSDMA, DSDMA) assess against 3 knowledge graphs
3. **Handler Selection**: One of the 10 handlers is selected based on ethical assessment
4. **Action Execution**: Handler executes ethically-approved action
5. **Recursive Generation**: Actions may generate new ethical thoughts, continuing the cycle

## Handler Interface

### Base Handler Implementation
```python
class BaseActionHandler:
    """Base class for all H3ERE action handlers."""
    
    async def handle(
        self,
        result: ActionSelectionDMAResult,
        thought: Thought,
        dispatch_context: DispatchContext
    ) -> ActionResponse:
        """Execute the ethically-approved handler action."""
        pass
```

### Common Patterns

#### Error Handling
```python
try:
    # Execute action logic
    result = await self._execute_action(params)
    return ActionResponse(
        action_type=HandlerActionType.SUCCESS,
        content=result
    )
except HandlerError as e:
    logger.error(f"Handler failed: {e}")
    return ActionResponse(
        action_type=HandlerActionType.ERROR,
        content=f"Action failed: {str(e)}"
    )
```

#### Follow-up Creation
```python
# Create follow-up thought for continued processing
follow_up = create_follow_up_thought(
    original_thought=thought,
    content="Follow-up action needed",
    context=dispatch_context
)
await self._enqueue_thought(follow_up)
```

## Dependencies

### Service Integration
Handlers integrate with CIRIS services via:
- **Bus Manager**: Access to all message buses
- **Service Registry**: Discovery of required services
- **Persistence Layer**: Database operations and state management

### Required Services
- **MemoryService**: For all memory-related operations
- **CommunicationService**: For external interactions
- **ConsentService**: For privacy and permission validation
- **TelemetryService**: For metrics and monitoring

## Error Handling

### Handler-Specific Exceptions
- **FollowUpCreationError**: Failed to create follow-up thoughts
- **HandlerError**: General handler execution failure
- **ConsentNotFoundError**: Missing required permissions

### Error Response Types
```python
class HandlerActionType(Enum):
    SUCCESS = "success"
    ERROR = "error"
    DEFER = "defer"
    FOLLOW_UP = "follow_up"
    TERMINAL = "terminal"
```

## Configuration

### Handler Registration
Handlers are automatically discovered and registered based on their action type:
```python
# Handler mapping in base infrastructure
HANDLER_REGISTRY = {
    ActionType.MEMORIZE: MemorizeHandler,
    ActionType.SPEAK: SpeakHandler,
    ActionType.DEFER: DeferHandler,
    # ... etc
}
```

### Execution Context
Handlers receive execution context including:
- **Original thought**: The triggering thought
- **DMA result**: Decision-making algorithm output  
- **Dispatch context**: Runtime execution environment
- **Service dependencies**: Available services and buses

## Development Guidelines

### Creating New Handlers
1. **Extend BaseActionHandler**: Inherit common functionality
2. **Define Action Type**: Create corresponding enum value
3. **Implement handle()**: Core execution logic
4. **Add Error Handling**: Comprehensive error coverage
5. **Include Tests**: Unit and integration test coverage
6. **Document Behavior**: Clear documentation of handler purpose

### Testing Handlers
```python
class TestMemorizeHandler:
    async def test_successful_memorize(self):
        handler = MemorizeHandler(dependencies)
        result = await handler.handle(dma_result, thought, context)
        assert result.action_type == HandlerActionType.SUCCESS
```

### Handler Best Practices
- **Idempotent Operations**: Handle duplicate executions gracefully
- **Resource Cleanup**: Properly clean up resources on failure
- **Audit Trail**: Log all significant actions for debugging
- **Performance**: Minimize execution time for synchronous operations

## Integration Points

### Message Bus Integration
Handlers interact with buses for:
- **Communication**: External message delivery
- **Memory**: Graph storage and retrieval
- **Tools**: External tool execution
- **Runtime Control**: Process management

### Thought Processing Pipeline
```
Thought → DMA Evaluation → Action Selection → Handler Execution → Response
```

## File Structure

```
handlers/
├── memory/
│   ├── memorize_handler.py    # Store information
│   ├── recall_handler.py      # Retrieve information  
│   └── forget_handler.py      # Remove information
├── control/
│   ├── defer_handler.py       # Delegate to authority
│   ├── reject_handler.py      # Refuse unsafe actions
│   └── ponder_handler.py      # Deep reflection
├── external/
│   ├── speak_handler.py       # Send messages
│   ├── observe_handler.py     # Gather data
│   └── tool_handler.py        # Execute tools
└── terminal/
    └── task_complete_handler.py # Finalize tasks
```

## Related Documentation
- [Base Handler Infrastructure](../infrastructure/handlers/README.md) - Core handler framework
- [Action Schemas](../../schemas/actions/README.md) - Handler parameter definitions  
- [DMA Documentation](../dma/README.md) - Decision-making integration
- [Bus Documentation](../buses/README.md) - Service integration patterns