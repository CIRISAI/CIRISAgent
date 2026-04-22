# RuntimeControlBus

## Overview

The RuntimeControlBus is CIRIS's centralized message bus for all runtime control operations. It provides unified control over system lifecycle management, processor state transitions, adapter management, configuration operations, and emergency procedures. The bus acts as a critical safety layer, serializing control operations to prevent conflicts and maintaining system stability during all runtime modifications.

## Mission Alignment

The RuntimeControlBus directly supports Meta-Goal M-1: "Promote sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing" by:

- **Enabling Adaptive Behavior**: Manages cognitive state transitions (WAKEUP, WORK, PLAY, SOLITUDE, DREAM, SHUTDOWN) that allow the system to adapt its processing patterns to different contexts
- **Ensuring System Stability**: Provides ordered execution and conflict prevention for critical system operations, maintaining coherent system behavior
- **Supporting Safe Experimentation**: Offers single-step debugging and pause/resume capabilities for safe system exploration and development
- **Facilitating Graceful Adaptation**: Enables dynamic adapter loading/unloading and configuration changes without system disruption
- **Protecting System Integrity**: Implements operation serialization and validation to prevent unsafe system states

## Architecture

### Service Type Handled
- **Primary Service**: `RuntimeControlService` (ServiceType.RUNTIME_CONTROL)
- **Protocol**: `RuntimeControlServiceProtocol` - defines comprehensive runtime control interface
- **Provider Type**: Adapter-provided service (not a core service)

### Control Operations Supported
- **Processor Control**: Pause, resume, single-step, and shutdown operations
- **State Management**: Cognitive state transitions and processing schedule coordination
- **Adapter Lifecycle**: Dynamic loading, unloading, and status monitoring
- **Configuration Management**: Runtime config updates, validation, backup, and restore
- **Emergency Operations**: WA-authorized emergency shutdown procedures

### State Management Patterns
The bus enforces critical safety patterns:
- **Operation Serialization**: Uses `_operation_lock` to prevent concurrent configuration changes
- **Conflict Prevention**: Tracks active operations in `_active_operations` dictionary
- **Graceful Degradation**: Returns safe defaults when services are unavailable
- **Emergency Safety**: Cancels all active operations during shutdown sequences

### Cognitive State Coordination
The RuntimeControlBus coordinates the six cognitive states that enable CIRIS's adaptive behavior:

- **WAKEUP**: Identity confirmation and system initialization
- **WORK**: Normal task processing and problem-solving
- **PLAY**: Creative mode for exploration and innovation
- **SOLITUDE**: Reflection and self-observation periods
- **DREAM**: Deep introspection and memory consolidation
- **SHUTDOWN**: Graceful termination sequences

## Runtime Operations

### State Transitions
```python
# Enter specific cognitive state
await runtime_bus.enter_state("WORK")

# Force state transition with reason
await runtime_bus.force_state_transition("SOLITUDE", "High stress detected")

# Get current processing state
current_state = runtime_bus.get_current_state()
```

### Processing Control
```python
# Pause system processing
success = await runtime_bus.pause_processing()

# Resume from paused state
success = await runtime_bus.resume_processing()

# Execute single debugging step
response = await runtime_bus.single_step()
```

### Queue Management
```python
# Get detailed queue status
queue_status = await runtime_bus.get_processor_queue_status()
print(f"Queue size: {queue_status.queue_size}/{queue_status.max_size}")
print(f"Processing rate: {queue_status.processing_rate} msgs/sec")
```

### System Configuration
```python
# Get configuration snapshot
config = await runtime_bus.get_config(path="llm.default_provider")

# Update configuration with validation
response = await runtime_bus.update_config(
    path="processor.max_thoughts",
    value=100,
    reason="Performance optimization"
)
```

## Adapter Integration

Adapters provide RuntimeControlService implementations to enable:

### CLI Adapter Integration
- Interactive debugging commands (pause, resume, step)
- Configuration inspection and modification
- Real-time queue monitoring
- Emergency shutdown capabilities

### API Adapter Integration
- RESTful endpoints for all runtime control operations
- WebSocket support for real-time status updates
- Role-based access control for operations
- Comprehensive runtime metrics exposure

### Discord Adapter Integration
- Administrative commands for server management
- Status monitoring through Discord interfaces
- Emergency controls for community moderators

## Usage Examples

### Basic Status Monitoring
```python
# Check overall runtime health
status = await runtime_bus.get_runtime_status()
print(f"System running: {status['is_running']}")
print(f"Uptime: {status['uptime_seconds']} seconds")
print(f"Active operations: {status['bus_status']['active_operations']}")

# Get detailed queue metrics
queue_status = await runtime_bus.get_processor_queue_status()
if queue_status.queue_size > 0.8 * queue_status.max_size:
    logger.warning("Processing queue approaching capacity")
```

### Safe Configuration Changes
```python
# Backup current config before changes
backup_response = await runtime_bus.backup_config("pre_update_backup")

# Update configuration with validation
config_response = await runtime_bus.update_config(
    path="memory.max_nodes",
    value=50000,
    validation_level="full",
    reason="Increased memory requirements"
)

if not config_response.success:
    # Restore from backup on failure
    await runtime_bus.restore_config("pre_update_backup")
```

### Emergency Shutdown
```python
# Graceful shutdown with reason
response = await runtime_bus.shutdown_runtime(
    reason="Scheduled maintenance",
    handler_name="admin_console"
)

if response.success:
    logger.info("System shutdown initiated successfully")
else:
    logger.error(f"Shutdown failed: {response.error}")
```

### Dynamic Adapter Management
```python
# Load new adapter dynamically
adapter_info = await runtime_bus.load_adapter(
    adapter_type="webhook",
    adapter_id="github_webhook",
    config={"port": 9000, "secret": "webhook_secret"},
    auto_start=True
)

# Monitor adapter status
status = await runtime_bus.get_adapter_info("github_webhook")
print(f"Adapter status: {status.status}")
print(f"Messages processed: {status.messages_processed}")
```

## Quality Assurance

### Type Safety Measures
- **Comprehensive Pydantic Schemas**: All operations use typed request/response models
- **Enum-Based Constants**: `OperationPriority`, `ProcessorStatus`, `AdapterStatus` prevent magic strings
- **Protocol Compliance**: Strict adherence to `RuntimeControlServiceProtocol` interface
- **Generic Type Safety**: `BaseBus[RuntimeControlService]` ensures service type consistency

### State Consistency
- **Operation Serialization**: Critical operations protected by `_operation_lock`
- **Active Operation Tracking**: Prevents concurrent conflicting operations
- **Graceful Error Handling**: Safe defaults returned when services unavailable
- **Transaction Safety**: Config operations support backup/restore patterns

### Performance Considerations
- **Metrics Collection**: Tracks `_commands_sent`, `_state_broadcasts`, `_emergency_stops`
- **Efficient Service Selection**: Capability-based service routing
- **Queue Management**: Configurable queue sizes and processing rates
- **Resource Monitoring**: Built-in uptime and performance tracking

### Safety Mechanisms
- **Shutdown Protection**: Operations blocked during `_shutting_down` state
- **Capability Validation**: Services verified for required capabilities before use
- **Exception Isolation**: Individual operation failures don't affect bus stability
- **Emergency Procedures**: WA-signed emergency shutdown support

## Service Provider Requirements

Runtime control services must implement the `RuntimeControlServiceProtocol` with these capabilities:

### Required Methods
```python
# Processor control
async def pause_processing() -> ProcessorControlResponse
async def resume_processing() -> ProcessorControlResponse
async def single_step() -> ProcessorControlResponse
async def shutdown_runtime(reason: str) -> ProcessorControlResponse

# Status monitoring
async def get_processor_queue_status() -> ProcessorQueueStatus
async def get_runtime_status() -> RuntimeStatusResponse

# Configuration management
async def get_config(path: Optional[str], include_sensitive: bool) -> ConfigSnapshot
async def update_config(path: str, value: object, ...) -> ConfigOperationResponse

# Adapter management
async def load_adapter(adapter_type: str, ...) -> AdapterOperationResponse
async def unload_adapter(adapter_id: str, force: bool) -> AdapterOperationResponse
```

### Capability Declaration
Services must declare their capabilities through the `get_capabilities()` method, supporting operations like:
- `"pause_processing"`, `"resume_processing"`, `"single_step"`
- `"get_processor_queue_status"`, `"get_runtime_status"`
- `"load_adapter"`, `"unload_adapter"`, `"get_adapter_info"`
- `"get_config"`, `"update_config"`, `"backup_config"`
- `"shutdown_runtime"`, `"handle_emergency_shutdown"`

### Implementation Guidelines
- **Thread Safety**: Handle concurrent requests appropriately
- **State Validation**: Validate state transitions before execution
- **Resource Management**: Properly cleanup on adapter unload/shutdown
- **Error Reporting**: Provide detailed error information in responses
- **Metrics Collection**: Support performance monitoring and debugging
