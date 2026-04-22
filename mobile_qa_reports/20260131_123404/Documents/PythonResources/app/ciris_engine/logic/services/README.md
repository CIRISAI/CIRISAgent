# CIRIS Services

The 22 core services that implement CIRIS's mission-driven architecture. Each service serves a specific purpose aligned with Meta-Goal M-1: promoting sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing.

## Service Architecture Overview

CIRIS follows a strict service architecture with exactly **22 core services** organized into 6 categories:

### [Graph Services (6)](#graph-services) - Memory and Data Management
Services that manage different aspects of the graph memory system and data persistence.

### [Infrastructure Services (4)](#infrastructure-services) - Foundation Systems
Core infrastructure services that enable reliable system operation.

### [Lifecycle Services (4)](#lifecycle-services) - System Lifecycle Management
Services that manage system initialization, operation, and shutdown.

### [Governance Services (5)](#governance-services) - Ethical and Operational Governance
Services that ensure ethical behavior and operational transparency.

### [Runtime Services (2)](#runtime-services) - Essential Runtime Operations
Critical services for system operation and external integrations.

### [Tool Services (1)](#tool-services) - Agent Self-Help Capabilities
Services that provide tools for agent self-sufficiency.

## Service Categories

### Graph Services (6)

All graph services extend `BaseGraphService` and integrate with the graph memory system:

1. **[Memory Service](graph/memory_service.py)** - Core graph operations and memory storage
   - Central to "Graph Memory as Identity" architecture
   - Handles MEMORIZE, RECALL, and FORGET operations
   - Manages graph node creation and relationship mapping
   - *See: [memory_service/README.md](memory_service/README.md)*

2. **[Audit Service](graph/audit_service.py)** - Immutable audit trail with cryptographic signatures
   - Complete traceability of all system operations
   - Ed25519 signatures for data integrity
   - Compliance and debugging support

3. **[Config Service](graph/config_service.py)** - Dynamic configuration stored in graph
   - Configuration as memory - versioned and evolutionary
   - Graph-based configuration management
   - Runtime configuration updates

4. **[Telemetry Service](graph/telemetry_service.py)** - Performance metrics and system health
   - Real-time system monitoring and metrics collection
   - Performance tracking and optimization insights
   - Offline-capable observability

5. **[Incident Management Service](graph/incident_service.py)** - Problem tracking and resolution
   - Incident detection, tracking, and resolution workflows
   - Learning from failures for institutional memory
   - Problem pattern recognition

6. **[TSDB Consolidation Service](graph/tsdb_consolidation/)** - Time-series data consolidation
   - Consolidates telemetry into 6-hour summaries
   - Long-term memory storage (1000+ years)
   - Historical trend analysis

### Infrastructure Services (4)

Foundation services extending `BaseInfrastructureService`:

1. **[Authentication Service](infrastructure/authentication.py)** - Identity verification and access control
   - Multi-tenant support with role-based access
   - JWT token management and OAuth2 integration
   - WA certificate validation

2. **[Resource Monitor Service](infrastructure/resource_monitor.py)** - System resource tracking
   - CPU, memory, and disk usage monitoring
   - Resource constraint prevention (4GB RAM target)
   - Performance optimization insights

3. **Database Maintenance Service** - SQLite optimization and long-term health
   - Database vacuum operations and optimization
   - Storage efficiency for 1000-year operation
   - Data integrity verification

4. **Secrets Service** - Cryptographic secret management
   - AES-256-GCM encryption for all secrets
   - Centralized security boundary
   - Secure credential storage and retrieval

### Lifecycle Services (4)

Services managing system lifecycle extending `BaseService`:

1. **[Initialization Service](lifecycle/initialization.py)** - Startup orchestration
   - Complex initialization order management
   - Service dependency resolution
   - System health verification

2. **[Shutdown Service](lifecycle/shutdown.py)** - Graceful shutdown coordination
   - Clean shutdown in resource-constrained environments
   - Data integrity preservation during shutdown
   - Service dependency cleanup

3. **[Time Service](lifecycle/time.py)** - Consistent time operations
   - Testability and consistency across system
   - No direct `datetime.now()` calls
   - Timezone and temporal coordination

4. **[Task Scheduler Service](lifecycle/scheduler.py)** - Cron-like scheduling and autonomous behavior
   - Autonomous agent activities and maintenance
   - Scheduled task execution and management
   - Proactive system behavior

### Governance Services (5)

Ethical and operational governance services:

1. **[Wise Authority Service](governance/wise_authority.py)** - Ethical decision making
   - Ubuntu philosophy implementation
   - Community-impact decision making
   - Human oversight and guidance

2. **[Adaptive Filter Service](governance/filter.py)** - Intelligent message prioritization
   - ML-based priority detection and spam filtering
   - User trust level tracking and management
   - Attention economy management

3. **[Visibility Service](governance/visibility.py)** - Reasoning transparency
   - Decision chain explanation ("the why")
   - Trust through transparency
   - Audit trail of reasoning processes

4. **[Consent Service](governance/consent.py)** - User consent and data handling
   - GDPR compliance and ethical data handling
   - TEMPORARY/PARTNERED/ANONYMOUS stream management
   - 90-day decay protocol implementation

5. **Self Observation Service** - Behavioral analysis and pattern detection
   - Identity variance monitoring (20% threshold)
   - Behavioral pattern analysis and insight generation
   - Continuous learning and adaptation

### Runtime Services (2)

Essential runtime services:

1. **[LLM Service](runtime/llm_service.py)** - Language model interface
   - Multi-provider LLM abstraction (OpenAI, Anthropic, Mock)
   - Automatic fallback and provider selection
   - Offline mode with mock LLM support

2. **[Runtime Control Service](runtime/control_service.py)** - Dynamic system control
   - Remote system management and debugging
   - Pause/resume processor functionality
   - Production operations interface

### Tool Services (1)

Agent self-help capabilities:

1. **[Secrets Tool Service](tools/secrets_tool_service.py)** - Agent secret management
   - Secret recall and filter update capabilities
   - Agent self-sufficiency tools
   - Always available, even offline

## Service Architecture Patterns

### Base Service Classes

- **`BaseService`** - Common service interface and lifecycle management
- **`BaseGraphService`** - Graph-integrated services with memory capabilities
- **`BaseInfrastructureService`** - Infrastructure services with system integration
- **`BaseScheduledService`** - Services with time-based scheduling capabilities

### Service Dependencies

Services follow strict dependency order during initialization:

1. **Infrastructure** (time, shutdown, init, resources)
2. **Database** (SQLite with migrations)
3. **Memory Foundation** (secrets, memory service)
4. **Identity** (load/create agent identity)
5. **Graph Services** (config, audit, telemetry, etc.)
6. **Security** (wise authority)
7. **Remaining Services**
8. **Tool Services**
9. **Component Assembly**
10. **Final Verification**

### Message Bus vs Direct Injection

**Services Using Message Buses:**
- Memory Service (MemoryBus) - Multiple graph backends
- LLM Service (LLMBus) - Multiple LLM providers
- Wise Authority Service (WiseBus) - Distributed wisdom
- Secrets Tool Service (ToolBus) - Tool ecosystem
- Runtime Control Service (RuntimeControlBus) - Management interfaces

**Services Using Direct Injection:**
- All Graph Services (except memory)
- All Infrastructure Services
- All Lifecycle Services
- All remaining Governance Services

### Service Principles

1. **Mission Alignment** - Every service justifies existence against Meta-Goal M-1
2. **Single Responsibility** - Each service has one clear purpose
3. **Protocol-First** - All services implement defined protocols
4. **Type Safety** - Zero `Dict[str, Any]` in service implementations
5. **Async-First** - All services support async operations
6. **Offline Capable** - Services work without external dependencies
7. **Audit Everything** - All service operations are traceable

## Development Guidelines

### Adding a New Service

**⚠️ IMPORTANT**: The 22-service architecture is complete. New services should only be added with explicit architectural justification.

1. Define protocol in `ciris_engine/protocols/services/`
2. Implement service extending appropriate base class
3. Create schemas in `ciris_engine/schemas/services/`
4. Add to ServiceInitializer dependency order
5. Update service count documentation (if approved)
6. Add comprehensive tests
7. Document service purpose and mission alignment

### Service Testing

- Integration over unit tests
- Real schemas, no dict mocks
- Test through protocols, not implementations
- Async test patterns throughout
- Offline scenario coverage

---

*These 22 services implement the technical foundation for CIRIS's mission of enabling diverse sentient beings to pursue flourishing through sustainable adaptive coherence.*
