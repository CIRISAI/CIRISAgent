# Handler Protocols

This directory contains protocol definitions for all 10 CIRIS action handlers. Each handler orchestrates service calls through the BusManager to implement specific agent actions.

## Handler Categories

Note: Handler protocols are defined in the base protocol files, not in separate category files.

### External Actions
Handlers that interact with the outside world:
  - `SpeakHandlerProtocol` - Sends messages to users
  - `ToolHandlerProtocol` - Executes external tools
  - `ObserveHandlerProtocol` - Monitors channels/environment

### Control Actions
Handlers that control agent decision flow:
  - `RejectHandlerProtocol` - Refuses to perform actions
  - `PonderHandlerProtocol` - Deep thinking and reflection
  - `DeferHandlerProtocol` - Defers decisions to Wise Authority

### Memory Actions
Handlers that manage the agent's memory:
  - `MemorizeHandlerProtocol` - Stores information in graph
  - `RecallHandlerProtocol` - Retrieves information from graph
  - `ForgetHandlerProtocol` - Removes information from graph

### Terminal Action
Handler that completes tasks:
  - `TaskCompleteHandlerProtocol` - Marks tasks as complete

## Handler Rules

1. **Bus Manager Only**: Handlers MUST use BusManager for all service calls
2. **No Direct Service Access**: Never import or call services directly
3. **Typed Parameters**: All handler methods must use typed schemas
4. **Audit Everything**: All actions must be logged to audit trail
5. **Error Recovery**: Handlers must gracefully handle service failures

## Handler Lifecycle

1. **Receive**: Handler receives `ActionSelectionResult` from DMA
2. **Validate**: Handler validates action parameters
3. **Execute**: Handler orchestrates service calls via BusManager
4. **Audit**: Handler logs action to audit trail
5. **Update**: Handler updates thought/task status
6. **Return**: Handler returns `HandlerResult`

## Adding a New Handler

1. Determine the handler category (external/control/memory/terminal)
2. Add the protocol to the appropriate file
3. Implement the handler following the protocol exactly
4. Register handler in the runtime
5. Add handler-specific tests

## Common Handler Patterns

### Service Access Pattern
```python
# CORRECT - via BusManager
result = await self.bus_manager.memory.recall(query)

# WRONG - direct service access
result = await self.memory_service.recall(query)
```

### Error Handling Pattern
```python
try:
    result = await self.bus_manager.tool.execute(tool_name, params)
except ServiceError as e:
    await self.bus_manager.audit.log_error(e)
    return HandlerResult(success=False, error=str(e))
```

### Audit Pattern
```python
await self.bus_manager.audit.log_action(
    action="SPEAK",
    context=dispatch_context,
    outcome="success",
    metadata={"message_id": msg_id}
)
