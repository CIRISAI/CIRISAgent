# MemoryBus

## Overview

The MemoryBus is CIRIS's central message bus for all graph storage and retrieval operations. It provides a unified interface for interacting with the memory graph, handling node memorization, recall operations, search queries, and time-series data management. The bus coordinates between handlers and memory service providers, ensuring type-safe memory operations across different backend implementations.

## Mission Alignment

The MemoryBus directly supports Meta-Goal M-1: "Promote sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing" by:

- **Preserving Conversational Context**: Maintains coherent dialogue history and relationship patterns, enabling meaningful interactions
- **Supporting Identity Continuity**: Stores and retrieves identity nodes, behavioral patterns, and ethical boundaries for consistent agent behavior  
- **Enabling Adaptive Learning**: Provides searchable memory of past interactions and decisions to improve future responses
- **Facilitating Consent Management**: Implements consent streams (TEMPORARY, PARTNERED, ANONYMOUS) for ethical data handling
- **Time-Aware Storage**: Maintains temporal context through time-series data and automatic expiration for privacy

## Architecture

### Service Type Handled
- **Primary Service**: `MemoryService` (ServiceType.MEMORY)
- **Protocol**: `MemoryServiceProtocol` - defines the three universal memory verbs

### Message Types Supported
- **MemorizeBusMessage**: Store graph nodes
- **RecallBusMessage**: Retrieve specific nodes  
- **ForgetBusMessage**: Remove nodes from memory
- **Direct Operations**: Most memory operations are synchronous for immediate results

### Graph Storage Backends Supported
- **SQLite** (LocalGraphMemoryService): Default persistence layer
- **Neo4j**: Graph database backend (via protocol)
- **ArangoDB**: Multi-model database backend (via protocol)
- **In-Memory**: Testing and development backend

## Graph Operations

### Core Memory Verbs

#### Memorize
```python
async def memorize(
    self, 
    node: GraphNode, 
    handler_name: Optional[str] = None, 
    metadata: Optional[dict] = None
) -> MemoryOpResult
```
Stores a graph node with automatic secret detection and processing. Returns operation status and metadata.

#### Recall  
```python
async def recall(
    self, 
    recall_query: MemoryQuery, 
    handler_name: Optional[str] = None, 
    metadata: Optional[dict] = None
) -> List[GraphNode]
```
Retrieves nodes based on structured queries. Supports wildcard queries (*) and specific node lookups.

#### Forget
```python
async def forget(
    self, 
    node: GraphNode, 
    handler_name: Optional[str] = None, 
    metadata: Optional[dict] = None
) -> MemoryOpResult  
```
Removes nodes from memory with audit trail preservation.

### Advanced Operations

#### Search Operations
```python
# Text-based memory search
async def search_memories(
    self, 
    query: str, 
    scope: str = "default", 
    limit: int = 10, 
    handler_name: Optional[str] = None
) -> List[MemorySearchResult]

# Flexible graph node search  
async def search(
    self, 
    query: str, 
    filters: Optional[MemorySearchFilter] = None, 
    handler_name: Optional[str] = None
) -> List[GraphNode]
```

#### Time-Series Operations
```python
# Store metrics in graph + TSDB correlation
async def memorize_metric(
    self, 
    metric_name: str, 
    value: float, 
    tags: Optional[Dict[str, str]] = None, 
    scope: str = "local", 
    handler_name: Optional[str] = None
) -> MemoryOpResult

# Store logs in graph + TSDB correlation  
async def memorize_log(
    self, 
    log_message: str, 
    log_level: str = "INFO", 
    tags: Optional[Dict[str, str]] = None, 
    scope: str = "local", 
    handler_name: Optional[str] = None
) -> MemoryOpResult

# Recall time-series data
async def recall_timeseries(
    self, 
    scope: str = "default", 
    hours: int = 24, 
    correlation_types: Optional[List[str]] = None, 
    handler_name: Optional[str] = None
) -> List[TimeSeriesDataPoint]
```

### Graph Traversal Patterns

The MemoryBus supports sophisticated graph traversal through:
- **Scoped Queries**: LOCAL, IDENTITY, ENVIRONMENT, COMMUNITY scopes
- **Type Filtering**: Filter by NodeType (AGENT, USER, CONCEPT, etc.)
- **Relationship Traversal**: Follow edges with configurable depth
- **Temporal Queries**: Time-based filtering and correlation

### Audit Trail Integration  

All memory operations are automatically audited:
- Operation tracking with handler identification
- Success/failure status logging
- Performance metrics collection
- Error reporting and debugging support

## Backend Support

### Multi-Provider Architecture

The MemoryBus uses CIRIS's service registry pattern to support multiple memory providers:

```python
# Service resolution
service = await self.get_service(
    handler_name=handler_name or "unknown", 
    required_capabilities=["memorize", "recall", "forget"]
)
```

### SQLite Backend (Default)
- **File**: `LocalGraphMemoryService` 
- **Features**: Full ACID compliance, SQL queries, automatic schema migration
- **Best For**: Development, single-node deployments, offline capability

### Neo4j Backend (Protocol)
- **Features**: Native graph queries, Cypher support, clustering
- **Best For**: Complex relationship queries, large-scale deployments

### ArangoDB Backend (Protocol)  
- **Features**: Multi-model (graph + document), JavaScript queries
- **Best For**: Mixed workloads, flexible schema requirements

### In-Memory Backend
- **Features**: Fast access, no persistence
- **Best For**: Testing, temporary data, development

### Backend Selection

Memory providers register with capabilities:
```python
capabilities = [
    "memorize", "recall", "forget",
    "search", "search_memories", 
    "memorize_metric", "memorize_log",
    "recall_timeseries", "export_identity_context"
]
```

## Usage Examples

### Basic Memory Operations

```python
from ciris_engine.schemas.services.graph_core import GraphNode, NodeType, GraphScope
from ciris_engine.schemas.services.operations import MemoryQuery

# Store a conversation memory  
conversation_node = GraphNode(
    id="conv_123",
    type=NodeType.CONCEPT, 
    scope=GraphScope.LOCAL,
    attributes=ConversationNodeAttributes(
        content="User asked about weather",
        participants=["user_456", "agent_789"],
        created_at=datetime.now(timezone.utc)
    )
)

result = await memory_bus.memorize(conversation_node, handler_name="chat_handler")
assert result.status == MemoryOpStatus.OK

# Recall specific conversation
query = MemoryQuery(
    node_id="conv_123",
    scope=GraphScope.LOCAL,
    include_edges=True
)
nodes = await memory_bus.recall(query, handler_name="chat_handler")
```

### Search Operations

```python
# Search conversations about weather
search_results = await memory_bus.search_memories(
    query="weather", 
    scope="local", 
    limit=10,
    handler_name="search_handler"
)

for result in search_results:
    print(f"Found: {result.content[:50]}... (relevance: {result.relevance_score})")

# Advanced graph search with filters
from ciris_engine.schemas.services.graph.memory import MemorySearchFilter

filter_config = MemorySearchFilter(
    scope=GraphScope.LOCAL,
    node_types=[NodeType.CONCEPT, NodeType.USER],
    limit=20
)

nodes = await memory_bus.search(
    query="type:concept AND scope:local", 
    filters=filter_config,
    handler_name="advanced_search_handler"
)
```

### Telemetry and Metrics

```python
# Store system metrics  
await memory_bus.memorize_metric(
    metric_name="response_time",
    value=0.234,
    tags={"handler": "chat", "model": "gpt-4"},
    scope="local",
    handler_name="telemetry_handler"
)

# Store audit logs
await memory_bus.memorize_log(
    log_message="User authentication successful",
    log_level="INFO", 
    tags={"user_id": "user_123", "ip": "192.168.1.1"},
    scope="local",
    handler_name="auth_handler" 
)

# Recall time-series data for analysis
data_points = await memory_bus.recall_timeseries(
    scope="local",
    hours=24,
    correlation_types=["response_time", "error_rate"],
    handler_name="analytics_handler"
)
```

### Identity Context Management

```python
# Export identity context for LLM consumption
identity_context = await memory_bus.export_identity_context(
    handler_name="llm_handler"
)

# Use in prompt context
prompt = f"""
Previous context: {identity_context}
Current question: {user_message}
"""
```

## Quality Assurance

### Type Safety Measures

- **Zero Dict[str, Any]**: All data uses Pydantic models
- **Strict Schemas**: GraphNode, MemoryQuery, MemoryOpResult with validation
- **Protocol Compliance**: All providers must implement MemoryServiceProtocol
- **Enum Usage**: NodeType, GraphScope, MemoryOpStatus prevent magic strings

### Data Consistency Features

- **Atomic Operations**: Each memory operation is atomic with clear success/failure
- **Schema Validation**: All nodes validated before storage
- **Consent Enforcement**: Automatic expiration for TEMPORARY consent streams
- **Audit Trails**: Complete operation logging for debugging and compliance

### Performance Considerations

- **Parallel Telemetry**: Multi-provider telemetry collection with timeout
- **Connection Pooling**: Database connection reuse and management
- **Query Optimization**: Indexed searches and efficient graph traversal
- **Caching**: Service-level caching for frequently accessed nodes

### Error Handling

```python
# Graceful degradation
try:
    result = await memory_bus.memorize(node)
    if result.status != MemoryOpStatus.OK:
        logger.warning(f"Memory operation failed: {result.reason}")
except Exception as e:
    logger.error(f"Memory bus error: {e}")
    # Continue with reduced functionality
```

### Monitoring and Metrics

The MemoryBus provides comprehensive telemetry:

```python
metrics = memory_bus.get_metrics()
# Returns:
# - memory_bus_operations: Total successful operations
# - memory_bus_broadcasts: Message queue usage  
# - memory_bus_errors: Operation failures
# - memory_bus_subscribers: Active provider count
```

## Service Provider Requirements

### Implementation Checklist

Memory service providers must implement:

1. **Core Operations**: memorize(), recall(), forget()
2. **Search Capabilities**: search(), search_memories()
3. **Time-Series Support**: memorize_metric(), memorize_log(), recall_timeseries()
4. **Health Monitoring**: is_healthy(), get_telemetry()
5. **Capability Declaration**: get_capabilities()

### Protocol Compliance

```python
class MyMemoryService(MemoryServiceProtocol):
    async def memorize(self, node: GraphNode) -> MemoryOpResult:
        # Validate node schema
        # Store with secrets processing  
        # Return typed result
        
    async def recall(self, query: MemoryQuery) -> List[GraphNode]:
        # Validate query parameters
        # Execute graph traversal
        # Return typed nodes
        
    # ... implement all protocol methods
```

### Registration Pattern

```python
# Register with service registry
capabilities = ServiceCapabilities(
    supports_operations=["memorize", "recall", "forget", "search"],
    provider_name="MyMemoryProvider",
    version="1.0.0"
)

registry.register_service(
    service_type=ServiceType.MEMORY,
    service_instance=my_memory_service,
    capabilities=capabilities
)
```

### Quality Standards

- **Response Times**: < 100ms for simple operations, < 1s for complex queries
- **Data Integrity**: ACID compliance where possible
- **Secret Handling**: Integration with SecretsService for sensitive data
- **Error Reporting**: Detailed error information in MemoryOpResult
- **Telemetry**: Real-time metrics for monitoring and debugging

---

The MemoryBus serves as the foundation for CIRIS's graph-centric memory architecture, enabling coherent, context-aware interactions while maintaining strict type safety and ethical data handling practices.