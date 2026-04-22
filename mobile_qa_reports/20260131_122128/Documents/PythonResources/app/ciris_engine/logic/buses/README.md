# CIRIS Message Bus Architecture

The message bus system is the communication backbone of CIRIS, enabling scalable, fault-tolerant service orchestration through typed message passing. Each bus specializes in a specific domain and supports multiple service providers.

## Architecture Overview

CIRIS uses **6 specialized message buses** managed by the `BusManager`:

| Bus | Purpose | Service Type | Key Features |
|-----|---------|-------------|--------------|
| **[CommunicationBus](./communication_bus.md)** | External interactions | Multi-adapter communication | Discord, API, CLI adapters |
| **[MemoryBus](./memory_bus.md)** | Graph storage/retrieval | Multiple graph backends | Neo4j, ArangoDB, in-memory |
| **[LLMBus](./llm_bus.md)** | Language model access | Multiple LLM providers | OpenAI, Anthropic, local models |
| **[ToolBus](./tool_bus.md)** | Tool execution | Multi-provider tools | Adapter-provided capabilities |
| **[RuntimeControlBus](./runtime_control_bus.md)** | System control | Runtime management | Processing control, state management |
| **[WiseBus](./wise_bus.md)** | Wisdom/guidance | Authority services | Ethical guidance, decision support |

## Mission Alignment

All buses serve **Meta-Goal M-1**: *Promote sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing*

**Bus-Specific Contributions:**
- **Communication**: Transparent, respectful multi-channel interaction
- **Memory**: Consistent, auditable knowledge preservation
- **LLM**: Responsible AI capability access with resource tracking
- **Tool**: Safe, traceable capability execution
- **RuntimeControl**: Adaptive system behavior for sustainability
- **Wise**: Ethical guidance integration in all operations

## Base Architecture

All buses extend `BaseBus[ServiceT]` providing:

### Core Functionality
```python
class BaseBus(ABC, Generic[ServiceT]):
    - Typed service handling (Generic[ServiceT])
    - Async message queuing (max 1000 messages)
    - Graceful error handling with metrics
    - Service discovery via ServiceRegistry
    - Automatic retry and failure recovery
```

### Lifecycle Management
- **Start/Stop**: Coordinated by BusManager
- **Processing Loop**: Async message consumption
- **Queue Management**: Overflow protection
- **Health Monitoring**: Queue size and processing metrics

### Message Flow
```
Handler Request → Bus Message → Service Selection → Processing → Response
```

## Bus Selection Strategy

**Multi-Provider Services** (use buses):
- Multiple implementations available
- Load balancing required
- Provider-specific capabilities
- Fallback/redundancy needed

**Single-Instance Services** (direct calls):
- One authoritative implementation
- No load balancing needed
- Consistent behavior required

## Service Registry Integration

Each bus uses the `ServiceRegistry` for:
- **Service Discovery**: Find available providers
- **Capability Matching**: Select services by required capabilities
- **Health Tracking**: Route around failed services
- **Load Balancing**: Distribute across healthy providers

## Quality Assurance

**Type Safety:**
- All buses are strongly typed with `Generic[ServiceT]`
- Service contracts enforced via protocols
- Message validation at bus boundaries

**Reliability:**
- Queue overflow protection (1000 message limit)
- Graceful degradation on service failures
- Comprehensive error logging and metrics

**Performance:**
- Async processing with 0.1s timeout loops
- Non-blocking message enqueuing
- Efficient service lookup caching

## Usage Patterns

### Handler Access
```python
# Access via BusManager
await bus_manager.communication.send_message(...)
await bus_manager.memory.memorize(...)
await bus_manager.llm.call_llm(...)
```

### Service Implementation
```python
# Implement service protocol
class MyMemoryService(MemoryServiceProtocol):
    async def memorize(self, node: GraphNode) -> bool:
        # Implementation
```

### Bus Extension
```python
# Extend BaseBus for new domains
class CustomBus(BaseBus[CustomServiceProtocol]):
    async def _process_message(self, message: BusMessage) -> None:
        # Custom processing logic
```

## Monitoring and Observability

**Bus Statistics:**
- Processed message count
- Failed message count
- Current queue size
- Running status

**Health Checks:**
- Bus running state
- Queue utilization (< 90% for healthy)
- Service availability
- Processing latency

**Telemetry Integration:**
All buses report metrics to the telemetry service for:
- Performance monitoring
- Capacity planning
- Error analysis
- Resource optimization

## Error Handling Philosophy

**Graceful Degradation:**
- Individual message failures don't stop processing
- Service failures trigger fallback selection
- Queue overflow drops messages with logging

**Observability:**
- All errors logged with full context
- Failed message handling customizable per bus
- Statistics tracked for analysis

**Recovery:**
- Automatic retry via service registry
- Circuit breaker patterns for failed services
- Queue drainage during shutdown

## Development Guidelines

**Adding New Buses:**
1. Extend `BaseBus[YourServiceProtocol]`
2. Implement `_process_message()` method
3. Add to BusManager initialization
4. Update this documentation

**Bus Testing:**
- Unit tests for message processing
- Integration tests with service registry
- Load testing for queue management
- Failure scenario testing

**Performance Considerations:**
- Keep message processing fast (< 100ms typical)
- Avoid blocking operations in buses
- Use capability-based service selection
- Monitor queue sizes regularly

---

*The bus architecture enables CIRIS's flexible, scalable service ecosystem while maintaining type safety, reliability, and ethical alignment with our mission of promoting flourishing for all sentient beings.*
