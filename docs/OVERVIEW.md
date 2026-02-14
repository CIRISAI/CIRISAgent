# CIRIS Architecture Overview

CIRIS (Core Identity, Integrity, Resilience, Incompleteness, and Signalling Gratitude) is an ethical AI agent platform designed for production deployment with built-in human oversight, auditability, and graceful degradation.

## What CIRIS Is

CIRIS is a complete AI agent framework that:

- Runs as a Discord moderator, API service, or standalone CLI
- Makes decisions through a multi-stage reasoning pipeline with conscience checks
- Signs every action with Ed25519 for tamper-proof audit trails
- Operates within 4GB RAM, supports offline mode, and runs on edge devices

**Production deployment**: [agents.ciris.ai](https://agents.ciris.ai)

## Core Concepts

### Decision-Making Pipeline

Every thought passes through the DMA (Decision-Making Algorithm) pipeline:

```
Input → CSDMA → DSDMA → PDMA → IDMA → ASPDMA → Conscience → Action
         ↓        ↓       ↓       ↓        ↓          ↓
      Common   Domain  Practical Identity  Action   Ethical
       Sense  Specific            Check  Selection Validation
```

### Cognitive States

The agent operates in 6 states:

| State | Purpose |
|-------|---------|
| WAKEUP | Identity confirmation, system checks |
| WORK | Primary operational state |
| PLAY | Creative exploration mode |
| SOLITUDE | Reflection and maintenance |
| DREAM | Deep introspection, memory consolidation |
| SHUTDOWN | Graceful termination |

### Conscience Checks

Before any action, the conscience validates:

- **Entropy** - Is uncertainty within acceptable bounds?
- **Coherence** - Is the decision logically consistent?
- **Optimization Veto** - Could this cause value collapse?
- **Epistemic Humility** - Are we acknowledging limitations?

## Service Architecture

CIRIS comprises 22 core services organized into 6 categories:

### Graph Services (7)
Data persistence and memory management.

| Service | Purpose |
|---------|---------|
| Memory | Graph operations, node/relationship management |
| Consent | User consent, GDPR compliance |
| Config | Dynamic configuration |
| Telemetry | Real-time metrics |
| Audit | Immutable audit trail with signatures |
| Incident | Problem tracking and resolution |
| TSDBConsolidation | 6-hour metric summaries |

### Infrastructure Services (4)
Core system infrastructure.

| Service | Purpose |
|---------|---------|
| Authentication | JWT, OAuth2, access control |
| ResourceMonitor | CPU, memory, disk monitoring |
| DatabaseMaintenance | SQLite optimization |
| Secrets | AES-256-GCM secret management |

### Lifecycle Services (4)
System lifecycle management.

| Service | Purpose |
|---------|---------|
| Initialization | Startup orchestration |
| Shutdown | Graceful termination |
| Time | Timezone-aware time operations |
| TaskScheduler | Cron-like task scheduling |

### Governance Services (4)
Ethical behavior and transparency.

| Service | Purpose |
|---------|---------|
| WiseAuthority | Human oversight, ethical guidance |
| AdaptiveFilter | Message prioritization |
| Visibility | Decision chain explanation |
| SelfObservation | Behavioral monitoring |

### Runtime Services (2)
Core runtime operations.

| Service | Purpose |
|---------|---------|
| LLM | Multi-provider LLM interface |
| RuntimeControl | Dynamic system control |

### Tool Services (1)
Agent self-sufficiency.

| Service | Purpose |
|---------|---------|
| SecretsTool | Secret recall and management |

## Message Buses

6 buses provide multi-provider abstraction:

| Bus | Purpose | Example Providers |
|-----|---------|-------------------|
| MemoryBus | Graph backends | SQLite, Neo4j, ArangoDB |
| LLMBus | LLM inference | OpenAI, Anthropic, Llama |
| ToolBus | Tool execution | Adapter tools, core tools |
| CommunicationBus | Multi-channel messaging | Discord, API, CLI |
| WiseBus | Ethical guidance | Local WA, distributed |
| RuntimeControlBus | System control | Core, adapter extensions |

## Directory Structure

```
CIRISAgent/
├── ciris_engine/          # Core engine
│   ├── logic/             # Business logic (HOW)
│   ├── protocols/         # Service interfaces (WHO)
│   └── schemas/           # Pydantic models (WHAT)
├── ciris_adapters/        # Platform adapters
│   ├── discord/           # Discord integration
│   ├── api/               # REST API
│   └── ciris_covenant_metrics/  # Trace capture
├── docs/                  # Documentation
├── FSD/                   # Functional specs
├── tools/                 # Development tools
└── tests/                 # Test suite
```

## Key Patterns

### Three-Legged Stool
- **Logic** (HOW) - Implementation
- **Protocols** (WHO) - Contracts
- **Schemas** (WHAT) - Type-safe structures

### Type Safety First
- No `Dict[str, Any]` in production code
- Pydantic models for all data structures
- Strict mypy configuration

### No Bypass Patterns
- Every component follows consistent rules
- No emergency overrides or privileged paths
- Same validation everywhere

## Getting Started

```bash
# Quick start with mock LLM
python main.py --adapter api --mock-llm --port 8000

# Production with real LLM
export OPENAI_API_KEY=your_key
python main.py --adapter api --port 8000

# Discord adapter
python main.py --adapter discord
```

## Related Documentation

- [TRACE_FORMAT.md](TRACE_FORMAT.md) - Covenant trace specification
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [API_SPEC.md](API_SPEC.md) - API documentation
- [ARCHITECTURE.md](ARCHITECTURE.md) - Detailed architecture
- [../COVENANT.md](../COVENANT.md) - Ethical framework
