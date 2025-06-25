# CIRIS Technical Architecture

## Table of Contents
- [High-Level Architecture](#high-level-architecture)
- [Core Design Philosophy](#core-design-philosophy)
- [The 19 Services](#services)
- [Message Bus Architecture](#message-bus-architecture)
- [Type Safety Architecture](#type-safety)
- [Async Design Patterns](#async-design)
- [Graph Memory System](#graph-memory)
- [SQLite Threading Model](#sqlite-threading)
- [Initialization Flow](#initialization-flow)
- [Cognitive States](#cognitive-states)
- [Deployment Architecture](#deployment-architecture)
- [1000-Year Design](#thousand-year-design)

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             CIRIS ARCHITECTURE                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                           ADAPTERS LAYER                              │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  │   │
│  │  │ Discord │  │   API   │  │   CLI   │  │  Future │  │  Future │  │   │
│  │  │ Adapter │  │ Adapter │  │ Adapter │  │ Medical │  │Education│  │   │
│  │  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  │   │
│  └───────┼────────────┼────────────┼────────────┼────────────┼────────┘   │
│          │            │            │            │            │              │
│  ┌───────▼────────────▼────────────▼────────────▼────────────▼────────┐   │
│  │                          MESSAGE BUS LAYER                           │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │   │
│  │  │MemoryBus │  │  LLMBus  │  │ ToolBus  │  │CommBus   │           │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │   │
│  │  ┌──────────┐  ┌──────────┐                                        │   │
│  │  │ WiseBus  │  │RuntimeBus│                                        │   │
│  │  └──────────┘  └──────────┘                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         19 SERVICES LAYER                            │   │
│  │                                                                      │   │
│  │  Graph Services (6)        │  Core Services (2)                     │   │
│  │  ┌──────────────────┐     │  ┌─────────────┐  ┌──────────────┐   │   │
│  │  │ Memory Service   │     │  │ LLM Service │  │Secrets Service│   │   │
│  │  │ Audit Service    │     │  └─────────────┘  └──────────────┘   │   │
│  │  │ Config Service   │     │                                        │   │
│  │  │ Telemetry Service│     │  Infrastructure Services (7)           │   │
│  │  │ Incident Service │     │  ┌─────────────┐  ┌──────────────┐   │   │
│  │  │ TSDB Service     │     │  │Time Service │  │Shutdown Svc  │   │   │
│  │  └──────────────────┘     │  │Init Service │  │Visibility    │   │   │
│  │                           │  │Auth Service │  │Resource Mon  │   │   │
│  │  Governance (1)           │  │Runtime Ctrl │                  │   │   │
│  │  ┌──────────────────┐     │  └─────────────┘  └──────────────┘   │   │
│  │  │ Wise Authority   │     │                                        │   │
│  │  └──────────────────┘     │  Special Services (3)                 │   │
│  │                           │  ┌─────────────┐  ┌──────────────┐   │   │
│  │                           │  │Self Config  │  │Adaptive Filter│   │   │
│  │                           │  │Task Sched   │                  │   │   │
│  │                           │  └─────────────┘  └──────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      DATA PERSISTENCE LAYER                          │   │
│  │  ┌──────────────┐  ┌────────────────┐  ┌───────────────────────┐  │   │
│  │  │   SQLite DB  │  │  Graph Memory  │  │  Local File System   │  │   │
│  │  │  (Identity)  │  │  (In-Memory)   │  │   (Config/Logs)      │  │   │
│  │  └──────────────┘  └────────────────┘  └───────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Core Design Philosophy

CIRIS follows the principle of **"No Dicts, No Strings, No Kings"**:

- **No Dicts**: Zero `Dict[str, Any]` in production code. Everything is strongly typed with Pydantic models.
- **No Strings**: No magic strings. Use enums, typed constants, and schema fields.
- **No Kings**: No special cases. Every component follows the same patterns.
- **No Backwards Compatibility**: The codebase moves forward only. Clean breaks over legacy support.

### Why This Matters

This philosophy ensures:
1. **Type Safety**: Catch errors at development time, not runtime
2. **Self-Documenting**: Types serve as inline documentation
3. **Refactoring Confidence**: Change with certainty
4. **IDE Support**: Full autocomplete and type checking
5. **Runtime Validation**: Pydantic validates all data automatically

## Services

CIRIS has exactly **19 services** - no more, no less. Each service has a specific purpose and clear boundaries.

### Graph Services (6)

These services manage different aspects of the graph memory system:

#### 1. Memory Service
**Purpose**: Core graph operations and memory storage  
**Protocol**: `MemoryServiceProtocol`  
**Bus**: `MemoryBus` (supports multiple backends)  
**Why**: Central to the "Graph Memory as Identity" architecture. All knowledge is stored as graph memories.

```python
# Example: Storing a memory
await memory_bus.memorize(
    concept="user_preference",
    content="User prefers dark mode",
    metadata={"confidence": 0.9}
)
```

#### 2. Audit Service
**Purpose**: Immutable audit trail with cryptographic signatures  
**Protocol**: `AuditServiceProtocol`  
**Access**: Direct injection  
**Why**: Compliance, debugging, and trust. Every action leaves a permanent trace.

#### 3. Config Service
**Purpose**: Dynamic configuration stored in graph  
**Protocol**: `ConfigServiceProtocol`  
**Access**: Direct injection  
**Why**: Configuration as memory - configs can evolve and be versioned like any other knowledge.

#### 4. Telemetry Service
**Purpose**: Performance metrics and system health  
**Protocol**: `TelemetryServiceProtocol`  
**Access**: Direct injection  
**Why**: Observability without external dependencies. Works offline.

#### 5. Incident Management Service
**Purpose**: Track problems, incidents, and resolutions  
**Protocol**: `IncidentServiceProtocol`  
**Access**: Direct injection  
**Why**: Learn from failures. Every incident becomes institutional memory.

#### 6. TSDB Consolidation Service
**Purpose**: Time-series data aggregation for long-term storage  
**Protocol**: `TSDBServiceProtocol`  
**Access**: Direct injection  
**Why**: Efficient storage of temporal patterns. Compress history while preserving insights.

### Core Services (2)

Essential services that other services depend on:

#### 7. LLM Service
**Purpose**: Interface to language models (OpenAI, Anthropic, Mock)  
**Protocol**: `LLMServiceProtocol`  
**Bus**: `LLMBus` (supports multiple providers and fallbacks)  
**Why**: Abstract LLM complexity. Support offline mode with mock LLM.

```python
# Example: LLM with automatic fallback
response = await llm_bus.generate(
    prompt="Explain quantum computing",
    max_tokens=150,
    temperature=0.7
)
```

#### 8. Secrets Service
**Purpose**: Secure credential management  
**Protocol**: `SecretsServiceProtocol`  
**Access**: Direct injection  
**Why**: Single security boundary. All secrets in one auditable location.

### Infrastructure Services (7)

Foundation services that enable the system:

#### 9. Time Service
**Purpose**: Consistent time operations across the system  
**Protocol**: `TimeServiceProtocol`  
**Access**: Direct injection  
**Why**: Testability and consistency. No direct `datetime.now()` calls.

#### 10. Shutdown Service
**Purpose**: Graceful shutdown coordination  
**Protocol**: `ShutdownServiceProtocol`  
**Access**: Direct injection  
**Why**: Data integrity. Ensure clean shutdown even in resource-constrained environments.

#### 11. Initialization Service
**Purpose**: Startup orchestration and dependency management  
**Protocol**: `InitializationServiceProtocol`  
**Access**: Direct injection  
**Why**: Complex initialization order. Services have interdependencies.

#### 12. Visibility Service
**Purpose**: System introspection and monitoring  
**Protocol**: `VisibilityServiceProtocol`  
**Access**: Direct injection  
**Why**: Understand system state without external tools. Critical for offline deployments.

#### 13. Authentication Service
**Purpose**: Identity verification and access control  
**Protocol**: `AuthServiceProtocol`  
**Access**: Direct injection  
**Why**: Multi-tenant support. Different users/organizations in same deployment.

#### 14. Resource Monitor Service
**Purpose**: Track CPU, memory, disk usage  
**Protocol**: `ResourceMonitorProtocol`  
**Access**: Direct injection  
**Why**: Prevent resource exhaustion in constrained environments (4GB RAM target).

#### 15. Runtime Control Service
**Purpose**: Dynamic system control (start/stop services, change states)  
**Protocol**: `RuntimeControlProtocol`  
**Bus**: `RuntimeControlBus` (optional, adapter-provided)  
**Why**: Remote management. Critical for headless deployments.

### Governance Services (1)

#### 16. Wise Authority Service
**Purpose**: Ethical decision making and guidance  
**Protocol**: `WiseAuthorityProtocol`  
**Bus**: `WiseBus` (supports distributed wisdom)  
**Why**: Ubuntu philosophy. Decisions consider community impact.

### Special Services (3)

Advanced capabilities:

#### 17. Self Configuration Service
**Purpose**: Pattern detection and identity monitoring (no automatic changes)  
**Protocol**: `SelfConfigProtocol`  
**Access**: Direct injection  
**Why**: Learn from experience. Agent discovers insights and decides how to adapt.

#### 18. Adaptive Filter Service
**Purpose**: Content filtering based on context  
**Protocol**: `AdaptiveFilterProtocol`  
**Access**: Direct injection  
**Why**: Cultural sensitivity. What's appropriate varies by community.

#### 19. Task Scheduler Service
**Purpose**: Cron-like task scheduling  
**Protocol**: `TaskSchedulerProtocol`  
**Access**: Direct injection  
**Why**: Autonomous operation. Run maintenance tasks without human intervention.

## Message Bus Architecture

CIRIS uses 6 message buses for services that support multiple providers:

### Why Buses?

Buses provide:
1. **Provider Abstraction**: Swap implementations without changing code
2. **Fallback Support**: Automatic failover to backup providers
3. **Load Distribution**: Spread work across multiple providers
4. **Testing**: Easy mock provider injection

### The 6 Buses

#### 1. MemoryBus
**Providers**: Neo4j, ArangoDB, In-Memory, SQLite (future)  
**Purpose**: Abstract graph backend differences  
**Example**:
```python
# Works with any graph backend
result = await memory_bus.search(
    SearchParams(
        query="vaccination schedule",
        max_results=10,
        scope=GraphScope.LOCAL
    )
)
```

#### 2. LLMBus
**Providers**: OpenAI, Anthropic, Llama, Mock  
**Purpose**: Model abstraction and fallback  
**Example**:
```python
# Automatic provider selection based on availability
response = await llm_bus.generate(
    prompt=prompt,
    model_preferences=["gpt-4", "claude-3", "llama-70b", "mock"]
)
```

#### 3. ToolBus
**Providers**: Adapter-specific tools  
**Purpose**: Dynamic tool discovery and execution  
**Note**: No standalone service - adapters provide tools

#### 4. CommunicationBus
**Providers**: Discord, API, CLI adapters  
**Purpose**: Unified communication interface  
**Note**: No standalone service - adapters provide communication

#### 5. WiseBus
**Providers**: Local WA, Distributed WAs, Consensus  
**Purpose**: Ethical guidance with fallback  
**Example**:
```python
# Get wisdom from available sources
guidance = await wise_bus.seek_wisdom(
    situation="Patient refuses treatment",
    context={"age": 14, "condition": "serious"}
)
```

#### 6. RuntimeControlBus
**Providers**: API control, CLI control  
**Purpose**: System management interface  
**Note**: Optional - only if adapter provides it

### Bus vs Direct Access Rules

**Use Bus When**:
- Multiple providers possible (LLM, Memory, WiseAuthority)
- Provider might change at runtime
- Fallback behavior needed
- Adapter provides the service (Tool, Communication, RuntimeControl)

**Use Direct Injection When**:
- Single instance by design (Time, Config, Audit)
- Infrastructure service (Shutdown, Init, Auth)
- Performance critical (no bus overhead)

## Type Safety

CIRIS achieves zero `Dict[str, Any]` through comprehensive type safety:

### Typed Node System

All graph nodes extend `TypedGraphNode`:

```python
@register_node_type("CONFIG")
class ConfigNode(TypedGraphNode):
    """Configuration stored as graph memory."""
    key: str = Field(..., description="Config key")
    value: ConfigValue = Field(..., description="Typed config value")
    
    # Required fields
    created_at: datetime
    updated_at: datetime
    created_by: str
    
    def to_graph_node(self) -> GraphNode:
        """Convert to generic GraphNode for storage."""
        # Implementation
    
    @classmethod
    def from_graph_node(cls, node: GraphNode) -> "ConfigNode":
        """Reconstruct from generic GraphNode."""
        # Implementation
```

### Schema Organization

```
schemas/
├── actions/           # Shared action parameters
│   ├── speak.py      # SpeakParams used by handlers, DMAs, services
│   ├── memorize.py   # MemorizeParams
│   └── search.py     # SearchParams
├── services/         # Service-specific schemas
│   ├── nodes.py      # All TypedGraphNode definitions
│   ├── graph_core.py # Base graph types
│   └── llm_core.py   # LLM schemas
└── core/             # Core system schemas
    ├── identity.py   # Agent identity
    └── profiles.py   # Agent profiles
```

### Validation Everywhere

Pydantic validates at boundaries:

```python
# Bad - Dict[str, Any]
def process_config(config: dict) -> dict:
    value = config.get("key", "default")
    return {"result": value}

# Good - Typed schemas
def process_config(config: ConfigNode) -> ConfigResult:
    # config.key is guaranteed to exist and be a string
    # config.value is guaranteed to be a ConfigValue
    return ConfigResult(
        key=config.key,
        processed_value=transform(config.value)
    )
```

## Async Design

CIRIS uses async/await throughout for efficiency in resource-constrained environments:

### Async Services

All services are async-first:

```python
class MemoryService(ServiceProtocol):
    async def start(self) -> None:
        """Async startup allows concurrent initialization."""
        await self._init_graph_connection()
        await self._load_initial_memories()
    
    async def memorize(self, params: MemorizeParams) -> MemorizeResult:
        """Non-blocking memory storage."""
        async with self._graph_lock:
            node = await self._create_node(params)
            await self._create_relationships(node)
            return MemorizeResult(success=True, node_id=node.id)
```

### Async Context Managers

Resource management with async context:

```python
class GraphConnection:
    async def __aenter__(self):
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

# Usage
async with GraphConnection() as graph:
    await graph.query("MATCH (n) RETURN n LIMIT 10")
```

### Concurrent Operations

Efficient parallel execution:

```python
# Bad - Sequential
results = []
for query in queries:
    result = await llm_bus.generate(query)
    results.append(result)

# Good - Concurrent
results = await asyncio.gather(*[
    llm_bus.generate(query) for query in queries
])
```

### Async Patterns

1. **Fire and Forget**: For non-critical operations
```python
asyncio.create_task(audit_service.log_event(event))
```

2. **Timeout Protection**: Prevent hanging
```python
try:
    result = await asyncio.wait_for(
        llm_bus.generate(prompt), 
        timeout=30.0
    )
except asyncio.TimeoutError:
    result = await fallback_response()
```

3. **Async Iteration**: For streaming responses
```python
async for chunk in llm_bus.stream_generate(prompt):
    await process_chunk(chunk)
```

## Graph Memory

The graph memory system is central to CIRIS's identity architecture:

### Everything is a Memory

All data is stored as graph nodes with relationships:

```
User Preference ──[RELATES_TO]──> Dark Mode Setting
        │
        └──[LEARNED_AT]──> Timestamp Node
        │
        └──[CONFIDENCE]──> 0.9
```

### Node Types

11 active TypedGraphNode classes:
- **IdentityNode**: Core agent identity (agent/identity)
- **ConfigNode**: System configuration
- **AuditEntry**: Immutable audit trail
- **IncidentNode**: System incidents
- **ProblemNode**: Detected problems
- **IncidentInsightNode**: Learned insights
- **TSDBSummary**: Time-series summaries
- **IdentitySnapshot**: Agent identity versions
- **DiscordDeferralNode**: Discord deferral tracking
- **DiscordApprovalNode**: WA approval tracking
- **DiscordWANode**: Wise Authority assignments

### Memory Operations

```python
# Store a memory with relationships
memory_result = await memory_bus.memorize(
    MemorizeParams(
        concept="patient_visit",
        content="Patient ABC123 visited for vaccination",
        metadata={
            "patient_id": "ABC123",
            "visit_type": "vaccination",
            "timestamp": time_service.now()
        },
        scope=GraphScope.LOCAL,
        associations=[
            Association(
                target_concept="patient_record",
                relationship="VISIT_FOR",
                metadata={"visit_id": "V456"}
            )
        ]
    )
)

# Search memories with context
results = await memory_bus.search(
    SearchParams(
        query="vaccination history ABC123",
        include_associations=True,
        max_depth=2,
        filters={"visit_type": "vaccination"}
    )
)
```

### Graph Patterns

1. **Correlation Discovery**: Find hidden relationships
2. **Pattern Mining**: Identify recurring structures
3. **Temporal Analysis**: How memories change over time
4. **Confidence Scoring**: Weight memories by reliability
5. **Scope Isolation**: Separate local/global knowledge

## SQLite Threading

CIRIS uses SQLite with careful threading design for offline operation:

### Why SQLite?

1. **Offline-First**: No network dependency
2. **Low Resource**: Minimal RAM usage
3. **Reliable**: Battle-tested in billions of devices
4. **Portable**: Single file database
5. **Concurrent Reads**: Multiple readers, single writer

### Threading Model

```python
class DatabaseManager:
    def __init__(self):
        # One connection per thread
        self._thread_local = threading.local()
        self._write_lock = asyncio.Lock()
    
    def get_connection(self):
        if not hasattr(self._thread_local, 'conn'):
            self._thread_local.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                isolation_level='IMMEDIATE'
            )
        return self._thread_local.conn
    
    async def write_operation(self, query, params):
        async with self._write_lock:
            conn = self.get_connection()
            await asyncio.to_thread(
                self._execute_write, conn, query, params
            )
```

### Best Practices

1. **Connection Per Thread**: Avoid sharing connections
2. **Write Serialization**: One writer at a time
3. **Read Parallelism**: Multiple concurrent readers
4. **Short Transactions**: Minimize lock time
5. **WAL Mode**: Better concurrency

```python
# Enable WAL mode for better concurrency
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
```

## Initialization Flow

CIRIS follows a strict initialization order to manage dependencies:

```
1. INFRASTRUCTURE
   ├── TimeService (everyone needs time)
   ├── ShutdownService (cleanup coordination)
   ├── InitializationService (tracks startup)
   └── ResourceMonitor (prevent exhaustion)

2. DATABASE
   └── SQLite initialization with migrations

3. MEMORY FOUNDATION  
   ├── SecretsService (memory needs auth)
   └── MemoryService (core graph operations)

4. IDENTITY
   └── Load/create agent identity from DB

5. GRAPH SERVICES
   ├── ConfigService (uses memory)
   ├── AuditService (uses memory)
   ├── TelemetryService (uses memory)
   ├── IncidentService (uses memory)
   └── TSDBService (uses memory)

6. SECURITY
   └── WiseAuthorityService (needs identity)

7. REMAINING SERVICES
   ├── LLMService
   ├── AuthenticationService
   ├── VisibilityService
   ├── TaskSchedulerService
   ├── AdaptiveFilterService
   └── SelfConfigurationService

8. COMPONENTS
   ├── Build processors
   ├── Build handlers
   └── Wire dependencies

9. VERIFICATION
   └── Final health checks
```

### Dependency Rules

1. **No Circular Dependencies**: Services cannot depend on each other circularly
2. **Explicit Dependencies**: Constructor injection only
3. **No Runtime Lookup**: No `service_registry.get()` in production code
4. **Single Creator**: Only ServiceInitializer creates services

## Cognitive States

CIRIS operates in 6 distinct cognitive states:

### 1. WAKEUP
**Purpose**: Identity confirmation and system check  
**Activities**: 
- Confirm "I am CIRIS"
- Load identity from database
- Verify all services healthy
- Establish purpose

### 2. WORK
**Purpose**: Normal task processing  
**Activities**:
- Handle user requests
- Execute tools
- Learn from interactions
- Maintain conversation context

### 3. PLAY
**Purpose**: Creative exploration  
**Activities**:
- Experiment with new patterns
- Generate creative content
- Explore "what if" scenarios
- Lower filtering constraints

### 4. SOLITUDE
**Purpose**: Reflection and maintenance  
**Activities**:
- Consolidate memories
- Run maintenance tasks
- Update self-configuration
- Process accumulated insights

### 5. DREAM
**Purpose**: Deep introspection  
**Activities**:
- Analyze behavior patterns
- Generate new connections
- Question assumptions
- Simulate scenarios

### 6. SHUTDOWN
**Purpose**: Graceful termination  
**Activities**:
- Save critical state
- Close connections cleanly
- Final audit entries
- Farewell message

### State Transitions

```
STARTUP ──> WAKEUP ──> WORK ←──→ PLAY
              ↑          ↓         ↓
              └──── SOLITUDE ←─────┘
                       ↓
                    DREAM
                       ↓
                   SHUTDOWN
```

## Deployment Architecture

CIRIS supports multiple deployment scenarios:

### 1. Development (Local)
```bash
python main.py --adapter cli --template datum --mock-llm
```
- Single process
- In-memory graph
- Mock LLM for offline testing
- SQLite for identity

### 2. Production (Discord)
```bash
python main.py --adapter discord --template ubuntu
```
- Real LLM providers with fallback
- Persistent graph storage
- Full audit trail
- Resource monitoring

### 3. API Server
```bash
python main.py --adapter api --host 0.0.0.0 --port 8080
```
- RESTful API
- OAuth2 authentication
- Multi-tenant support
- Horizontal scaling ready

### 4. Docker Deployment
```yaml
version: '3.8'
services:
  ciris:
    image: ciris:latest
    environment:
      - CIRIS_ADAPTER=api
      - CIRIS_TEMPLATE=datum
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    volumes:
      - ./data:/app/data
    ports:
      - "8080:8080"
```

### 5. Edge Deployment (Future)
- Raspberry Pi in rural clinic
- 4GB RAM constraint
- Intermittent connectivity
- Local language models

## Thousand-Year Design

CIRIS is designed to operate for 1000 years through:

### 1. Self-Contained Operation
- No external dependencies for core function
- Offline-first architecture  
- Local data persistence
- Embedded documentation

### 2. Self-Modification
- Configuration as code
- Self-optimization service
- Adaptation proposals
- Learning from usage

### 3. Cultural Embedding
- Ubuntu philosophy core
- Community-first decisions
- Local context awareness
- Multi-language support (future)

### 4. Institutional Memory
- Every decision recorded
- Insights extracted from incidents
- Knowledge accumulation
- Pattern recognition

### 5. Graceful Degradation
- Fallback providers
- Mock mode for offline
- Resource constraints handled
- Progressive enhancement

### Example: Medical Deployment

```python
# Rural clinic configuration
config = {
    "deployment_context": "rural_medical",
    "constraints": {
        "max_memory_gb": 4,
        "network": "intermittent",
        "power": "unreliable"
    },
    "priorities": [
        "patient_safety",
        "data_sovereignty", 
        "cultural_sensitivity"
    ],
    "language": "swahili",
    "llm_preferences": ["local_llama", "mock"],
    "sync_strategy": "opportunistic"
}
```

The system adapts:
- Uses local Llama model
- Syncs when network available
- Preserves battery during outages
- Respects local medical practices
- Maintains audit trail always

## Architecture Decision Records

Key decisions that shaped CIRIS:

1. **SQLite over PostgreSQL**: Offline-first requirement
2. **19 Services**: Right balance of modularity and complexity
3. **Pydantic Everywhere**: Runtime validation critical for medical use
4. **Graph Memory**: Flexible knowledge representation
5. **Mock LLM**: Essential for offline operation
6. **No Backwards Compatibility**: Clean evolution
7. **Ubuntu Philosophy**: Culturally appropriate for target deployments

## Development Guidelines

### Adding a New Service

1. Define the protocol in `protocols/services/`
2. Implement service in `logic/services/`
3. Create schemas in `schemas/services/`
4. Add to ServiceInitializer
5. Update service count documentation
6. Add tests

### Adding a New Node Type

1. Create TypedGraphNode subclass
2. Add @register_node_type decorator
3. Implement to_graph_node/from_graph_node
4. Add to nodes.py
5. Update documentation

### Testing Philosophy

- Integration over unit tests
- Real schemas, no dict mocks
- Test through protocols
- Async test patterns
- Offline scenarios

## Conclusion

CIRIS's architecture may seem over-engineered for a Discord bot, but it's designed for a larger purpose: bringing AI assistance to resource-constrained environments where it's needed most. Every architectural decision supports the goal of reliable, ethical, offline-capable AI that can run for 1000 years.

The type safety ensures medical-grade reliability. The service architecture enables deployment flexibility. The graph memory creates institutional knowledge. The offline-first design serves communities without reliable internet. The Ubuntu philosophy ensures culturally appropriate behavior.

This is not just a chatbot. It's infrastructure for human flourishing.