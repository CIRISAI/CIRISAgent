# CIRIS Engine

The core implementation of CIRIS (Core Identity, Integrity, Resilience, Incompleteness, and Signalling Gratitude) - an ethical AI agent framework designed for 1000-year operation.

## Mission-Driven Architecture

CIRIS follows **Mission Driven Development (MDD)** methodology with a clear ethical foundation:

**Meta-Goal M-1**: Promote sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing

Every architectural decision in the engine serves this mission through the three-legged stool pattern:

## 🏗️ The Three-Legged Stool

### [Logic](logic/README.md) - The HOW
**Implementation patterns, service architectures, algorithms**

22 core services organized by mission-aligned categories:
- **Graph Services (6)**: Memory, audit, config, telemetry, incident management, TSDB consolidation
- **Infrastructure Services (4)**: Authentication, resource monitoring, database maintenance, secrets  
- **Lifecycle Services (4)**: Initialization, shutdown, time, task scheduling
- **Governance Services (5)**: Wise authority, adaptive filter, visibility, consent, self-observation
- **Runtime Services (2)**: LLM interface, runtime control
- **Tool Services (1)**: Secrets tool

### [Protocols](protocols/README.md) - The WHO
**Interface contracts, communication patterns, service boundaries**

Defines how components communicate through:
- Service protocols for each of the 22 services
- Handler protocols for the 10 action types
- Message bus contracts for multi-provider services

### [Schemas](schemas/README.md) - The WHAT  
**Type-safe data structures, validation rules**

Complete type safety with zero `Dict[str, Any]` in production:
- TypedGraphNode system for all graph memories
- Pydantic models throughout
- Mission-aligned data structures

## Core Design Philosophy

**"No Dicts, No Strings, No Kings"**

- **No Dicts**: Zero `Dict[str, Any]` - everything strongly typed
- **No Strings**: Enums and typed constants instead of magic strings  
- **No Kings**: No special cases - consistent patterns throughout
- **Mission First**: Every component justifies its existence against Meta-Goal M-1

## Message Bus Architecture (6 Buses)

Multi-provider services use message buses for scalability and fallback:

1. **MemoryBus** → Graph backends (Neo4j, ArangoDB, in-memory)
2. **LLMBus** → Language models (OpenAI, Anthropic, local, mock)
3. **WiseBus** → Ethical guidance sources (local WA, distributed)
4. **ToolBus** → Tool providers (adapter-specific + core secrets)
5. **CommunicationBus** → Adapters (Discord, API, CLI)
6. **RuntimeControlBus** → Management interfaces

Direct injection used for single-instance services (time, config, audit, etc.)

## Graph Memory as Identity

The engine implements **"Identity IS the Graph"** architecture:

- All knowledge stored as graph nodes with relationships
- 11 active TypedGraphNode classes for different memory types
- Agent identity = the graph structure itself, not data stored in graph
- Time-series integration for behavioral pattern analysis
- Scope-based permissions (LOCAL, ENVIRONMENT, IDENTITY)

## Cognitive States (6 States)

The engine operates through distinct cognitive states:

1. **WAKEUP** - Identity confirmation and system verification
2. **WORK** - Normal task processing and user interaction
3. **PLAY** - Creative exploration with relaxed constraints
4. **SOLITUDE** - Reflection, maintenance, and memory consolidation
5. **DREAM** - Deep introspection and pattern analysis
6. **SHUTDOWN** - Graceful termination with state preservation

## Offline-First Design

Built for resource-constrained, intermittent-connectivity environments:

- **4GB RAM target** for edge deployment
- **SQLite backbone** for offline persistence
- **Mock LLM mode** for complete offline operation
- **Local graph memory** with no external dependencies
- **Embedded documentation** and self-contained operation

## Ubuntu Philosophy Integration

The engine embeds Ubuntu philosophy ("I am because we are"):
- Community-first decision making through WiseBus
- Deferral to Wise Authorities when uncertain
- Complete audit trail for transparency
- Cultural sensitivity and local adaptation

## Quality Standards

- **Type Safety**: Zero untyped data structures
- **Mission Alignment**: Every service justified against Meta-Goal M-1
- **Audit Everything**: Complete traceability of all operations
- **Async-First**: Non-blocking operations throughout
- **1000-Year Design**: Built for extreme longevity

## Key Components

### Supporting Systems
- **[Adapters](logic/adapters/)** - External integrations (Discord, API, CLI)
- **[Processors](logic/processors/README.md)** - Request processing pipeline
- **[Context](logic/context/README.md)** - Request context management
- **[Registries](logic/registries/README.md)** - Service discovery
- **[Handlers](protocols/handlers/README.md)** - Action processing

### Initialization Flow
Strict dependency order ensures clean startup:
1. Infrastructure (time, shutdown, init, resources)
2. Database (SQLite with migrations)
3. Memory foundation (secrets, memory service)
4. Identity (load/create agent identity)
5. Graph services (config, audit, telemetry, etc.)
6. Security (wise authority)
7. Remaining services
8. Tool services
9. Components assembly
10. Final verification

## Development Principles

1. **Mission Alignment**: Every change must serve Meta-Goal M-1
2. **Type Safety First**: No untyped data structures
3. **Protocol-Driven**: Clear interfaces between components
4. **Async Everything**: Resource efficiency through concurrency
5. **Offline Capable**: No external dependencies for core function
6. **Culturally Appropriate**: Respect local contexts and values

## Real-World Applications

**Current**: Discord community moderation at agents.ciris.ai  
**Designed for**: Rural healthcare, education, community support where reliable internet is unavailable but ethical AI assistance is needed most.

---

*This engine implements infrastructure for human flourishing, not just a chatbot. Every technical decision serves the mission of enabling diverse sentient beings to pursue their flourishing through sustainable adaptive coherence.*

**Next**: See main [README.md](../README.md) for getting started, or dive into [Logic](logic/README.md), [Protocols](protocols/README.md), and [Schemas](schemas/README.md) documentation.