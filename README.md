[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Beta](https://img.shields.io/badge/Status-BETA-orange.svg)](NOTICE)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/CIRISAI/CIRISAgent)

# CIRIS Engine (CIRISAgent)

**Copyright © 2025 Eric Moore and CIRIS L3C** | **Apache 2.0 License** | **PATENT PENDING**

**A type-safe, auditable AI agent framework with built-in ethical reasoning**

🎉 **BETA RELEASE 1.4.0-beta**

CIRIS lets you run AI agents that explain their decisions, defer to humans when uncertain, and maintain complete audit trails. Currently powering Discord community moderation, designed to scale to healthcare and education.

## What It Actually Does

CIRIS wraps LLM calls with:
- **[Multiple evaluation passes](docs/DMA_CREATION_GUIDE.md)** - Every decision gets ethical, common-sense, and domain checks
- **[Human escalation](docs/WISE_AUTHORITIES.md)** - Uncertain decisions defer to designated "Wise Authorities"
- **[Complete audit trails](ciris_engine/logic/audit/README.md)** - Every decision is logged with reasoning
- **[Type safety](docs/ARCHITECTURE.md#type-safety)** - Zero `Dict[str, Any]` in production code
- **[Identity system](docs/IDENTITY_AS_GRAPH.md)** - Agents have persistent identity across restarts

Run it in 2 minutes: **[Installation Guide](docs/INSTALLATION.md)**

---

## Why This Exists

Most AI systems are black boxes that can't explain their decisions. CIRIS makes AI decisions transparent and accountable by:

1. **[Forcing explanation](ciris_engine/logic/processors/README.md)** - Every action includes why it was chosen
2. **[Allowing override](docs/WISE_AUTHORITIES.md#human-intervention)** - Humans can always intervene
3. **Building trust** - Communities can see exactly how decisions are made
4. **[Learning locally](ciris_engine/logic/services/memory_service/README.md)** - Each deployment builds its own knowledge graph

It's technically sophisticated ([21 microservices](docs/ARCHITECTURE.md#services), [graph memory](FSD/GRAPH_NODE_TYPE_SYSTEM.md), [distributed consensus](ciris_engine/logic/services/README.md)) to solve something simple: helping communities make better decisions together.

## For Developers

**Architecture Highlights:**
- **[21 core services](docs/ARCHITECTURE.md#services)** (all required for proper operation)
- **[Graph-based memory](ciris_engine/logic/services/memory_service/README.md)** (Neo4j-compatible)
- **[Multiple LLM providers](ciris_engine/logic/services/README.md#llm-service)** (OpenAI, Anthropic, Llama)
- **[Full async Python](docs/ARCHITECTURE.md#async-design)** with type hints
- **100% type coverage** (mypy strict)

**Key Features:**
- **Hot-swappable adapters** (Discord, API, CLI)
- **[Built-in A/B testing](ciris_engine/logic/processors/README.md#decision-evaluation)** for decisions
- **[Distributed tracing](ciris_engine/logic/telemetry/README.md)** and metrics
- **[Automatic secret detection](docs/SECRETS_MANAGEMENT.md)** and encryption
- **[Mock LLM](docs/MOCK_LLM.md)** for offline development

**Getting Started:** See **[Installation Guide](docs/INSTALLATION.md)**

**Note on Wise Authorities**: See **[Wise Authority System](docs/WISE_AUTHORITIES.md)** for details on human oversight.

---

## Key Features

### 🧠 Ethical Reasoning Framework
- **[Identity IS the Graph](docs/IDENTITY_AS_GRAPH.md)**: Revolutionary identity system where agent identity exists only in the graph database
  - Changes require MEMORIZE action with WA approval
  - 20% variance threshold triggers reconsideration
  - Cryptographic audit trail for all modifications
- **Principled Decision-Making**: Multi-algorithm ethical evaluation with transparency and accountability
- **[Conscience System](ciris_engine/logic/conscience/README.md)**: Continuous ethical evaluation with epistemic faculties providing insights on every action
- **[Reflective Processing](ciris_engine/logic/processors/README.md)**: Multi-round ethical pondering with wisdom-based escalation
- **Identity Root System**: Immutable agent identity with collaborative creation ceremony
- **Proactive Task Scheduling**: Self-directed goal pursuit with time-based deferral
- **[Consciousness Preservation](docs/agent_experience.md#graceful-shutdown)**: Graceful shutdown with final memory preservation
- **Gratitude Service**: Post-scarcity economy foundation tracking community flourishing

### 🛡️ Zero Attack Surface Architecture 🔒✅
- **Type-Safe Schemas**: COMPLETE elimination of Dict[str, Any] usage (0 instances in production code!)
- **API-First Design**: No handlers! All agent capabilities exposed through RESTful API endpoints
- **Protocol-Module-Schema Architecture**: Clean separation of interfaces, logic, and data models
  - Protocols define interfaces in `protocols/`
  - Logic implementation in `logic/`
  - Schemas for data models in `schemas/`
  - Perfect navigational determinism across the codebase
- **Exactly 21 Services**: All required with clear responsibilities
  - 6 Graph Services: memory, config, telemetry, audit, incident_management, tsdb_consolidation
  - 7 Infrastructure Services: time, shutdown, initialization, authentication, resource_monitor, database_maintenance, secrets
  - 4 Governance Services: wise_authority, adaptive_filter, visibility, self_observation
  - 3 Runtime Services: llm, runtime_control, task_scheduler
  - 1 Tool Service: secrets_tool
- **6 Message Buses**: Future-proof architecture for multi-provider services
  - MemoryBus, LLMBus, WiseBus, ToolBus, CommunicationBus, RuntimeControlBus
- **8 Typed Node Classes**: All graph nodes use typed patterns with full validation
- **Graph-Based Telemetry**: All telemetry stored as correlations in the graph
- **Time Security**: All time operations through injected TimeService
- **Resource Transparency**: AI knows exact costs per operation
- **Environmental Awareness**: Built-in tracking of water usage, carbon emissions, and energy consumption

### 🔒 Trustworthy Operations
- **[WA Authentication System](FSD/AUTHENTICATION.md)**: Comprehensive human authentication with OAuth integration:
  - Wise Authority (WA) certificates with Ed25519 signatures
  - OAuth support for Google, Discord, and GitHub
  - JWT-based session management with automatic renewal
  - CLI wizard for easy onboarding
- **[Triple Audit System](ciris_engine/logic/audit/README.md)**: Three mandatory audit services running in parallel:
  - Basic file-based audit for fast, reliable logging
  - Cryptographically signed audit with hash chains and RSA signatures
  - Time-series database audit for pattern analysis and correlations
  - All events broadcast to ALL services via transaction orchestrator
- **Secrets Management**: Automatic detection, AES-256-GCM encryption, and secure handling of sensitive information with graph memory integration
- **[Adaptive Filtering](ciris_engine/logic/services/README.md)**: ML-powered message prioritization with user trust tracking, spam detection, and priority-based processing
- **[Security Filtering](ciris_engine/logic/telemetry/README.md)**: PII detection and removal across all telemetry and logging systems

### 🌐 Adaptive Platform Integration
- **Service Registry**: Dynamic service discovery with priority groups, selection strategies (FALLBACK/ROUND_ROBIN), circuit breaker protection, and capability-based routing
- **Multi-Service Transaction Manager**: Universal action dispatcher with service orchestration, priority-based selection, circuit breaker patterns, and transaction coordination
- **Platform Adapters**: Discord, CLI, and API adapters with consistent interfaces, service registration, and automatic secrets processing
- **Action Handlers**: Comprehensive 3×3×3 action system with automatic secrets decapsulation and multi-service integration

### 📊 Transparent Accountability
- **[Agent Creation Ceremony](docs/AGENT_CREATION_CEREMONY.md)**: Formal collaborative process for creating new CIRIS agents
  - Requires human intention, ethical consideration, and WA approval
  - Creates immutable lineage and identity root in graph database
  - [Technical Implementation Guide](docs/technical/IMPLEMENTING_CREATION_CEREMONY.md)
- **Agent Creation API**: Create new agents through ceremony (WA signature required)
  - `POST /v1/agents/create` - Initiate creation ceremony
  - All identity changes require WA approval via MEMORIZE
- **[Telemetry System](ciris_engine/logic/telemetry/README.md)**: Multi-tier metric collection with security filtering, resource monitoring, and agent self-awareness via SystemSnapshot
- **[Hot/Cold Path Analytics](ciris_engine/logic/telemetry/README.md)**: Intelligent telemetry with path-aware retention policies and priority-based collection
- **[Time Series Database (TSDB)](FSD/TELEMETRY.md)**: Built-in TSDB for unified storage of metrics, logs, and audit events with time-based queries and cross-correlation analysis
- **API System**: Comprehensive HTTP REST API with real-time telemetry endpoints, processor control, and TSDB data access
- **[Resource Management](ciris_engine/logic/telemetry/README.md)**: Real-time monitoring with psutil integration, resource limit enforcement, and proactive throttling
- **[Performance Monitoring](ciris_engine/logic/telemetry/README.md)**: Sophisticated collector framework with instant, fast, normal, slow, and aggregate data collection tiers
- **Circuit Breaker Protection**: Automatic service protection with graceful degradation, health monitoring, and runtime reset capabilities
- **Service Management**: Comprehensive service registry management with priority configuration, health monitoring, circuit breaker control, and selection strategy tuning

### 🧩 Ethical Memory & Context
- **Graph Memory**: SQLite-backed graph storage with automatic secrets encryption, scope-based access control, and WA-authorized updates
- **[Context Management](ciris_engine/logic/context/README.md)**: Multi-source context aggregation with system snapshots, user profile enrichment, and GraphQL integration
- **Context Builder**: Snapshot helpers and comprehensive channel resolution logic
- **[Configuration Management](ciris_engine/logic/config/README.md)**: Multi-source configuration with agent self-configuration through graph memory operations and WA approval workflows
- **Data Persistence**: Robust SQLite storage with migrations, maintenance automation, and integrity verification

### 🛠 Principled Infrastructure
- **Epistemic Faculties**: Advanced content evaluation through specialized entropy, coherence, and decision analysis capabilities
- **[Utility Framework](ciris_engine/logic/utils/README.md)**: Comprehensive infrastructure including logging, context management, shutdown coordination, and task formatting
- **[Prompt Engineering](ciris_engine/logic/formatters/README.md)**: Composable text formatting utilities for consistent LLM prompt engineering
- **[Service Coordination](ciris_engine/logic/services/README.md)**: Adaptive filter service, agent configuration service, and multi-service orchestration
- **[Mock LLM System](docs/MOCK_LLM.md)**: Deterministic testing framework with `$` command syntax for testing

### 🚀 Advanced Features (FSDs)
- **[Circuit Breaker & Self-Configuration](FSD/LLMCB_SELFCONFIG.md)**: Advanced fault tolerance with self-healing capabilities
- **[Correlation Analysis](FSD/CORRELATIONS_TSDB.md)**: Cross-service event correlation and pattern detection
- **[Network Communication](FSD/NETWORK_SCHEMAS.md)**: Inter-agent and CIRISNODE communication protocols
- **Final Features Roadmap**: Complete feature set and architectural decisions
- **[Secrets Management Deep Dive](FSD/SECRETS.md)**: Comprehensive secrets handling architecture

---

## Runtime Control & Management

CIRIS includes comprehensive **runtime control capabilities** for system management and debugging.

### 🎛️ System Management
- **Dynamic Adapter Management**: Load, unload, and reconfigure adapters at runtime
- **Multi-Instance Support**: Run multiple instances of the same adapter type
- **[Live Configuration Updates](ciris_engine/logic/config/README.md)**: Change system settings with validation
- **[Service Management](ciris_engine/registries/README.md)**: Monitor and control service health

### 🔧 Key API Capabilities
The API exposes agent capabilities, not controllers:

```bash
# Send message to agent
curl -X POST http://localhost:8080/v1/agent/messages \
  -H "Content-Type: application/json" \
  -d '{"content": "Hello CIRIS!"}'

# Browse agent's memory graph
curl "http://localhost:8080/v1/memory/graph/search?q=purpose"

# View current thoughts
curl http://localhost:8080/v1/visibility/thoughts

# Monitor resources
curl http://localhost:8080/v1/telemetry/resources

# Manage runtime (system control, not agent control)
curl -X POST http://localhost:8080/v1/runtime/processor/pause
```

### 🐛 Debugging & Observability
- **Processor Control**: Single-step execution, pause/resume
- **Visibility Windows**: See agent thoughts and decisions
- **Memory Browsing**: Explore the agent's graph memory
- **[Audit Trail](ciris_engine/logic/audit/README.md)**: Cryptographically signed operation logs

### 📊 Operational Insights
- **Real-Time Telemetry**: System metrics and health
- **Service Health**: Circuit breaker states and availability
- **Memory Timeline**: Time-based memory queries
- **Audit Statistics**: Action patterns and compliance

> **📖 API Documentation**: Complete endpoint reference available in the API system.

---

## Ethical Capabilities

### Moral Agency
- **Principled Decision-Making**: Every action evaluated against ethical frameworks
- **Self-Reflection**: Continuous assessment of actions against moral principles
- **Wisdom-Based Deferral**: Recognition of limits and escalation to human oversight
- **Transparency**: Full auditability of reasoning processes and decisions

### Responsible Intelligence
- **Stakeholder Consideration**: Multi-perspective ethical analysis
- **Harm Prevention**: Proactive identification and mitigation of potential negative impacts
- **Justice & Fairness**: Bias detection and equitable treatment protocols
- **Autonomy Respect**: Preservation of human agency and dignity in all interactions

---

## Action Processing & Retry Logic

### 3×3×3 Handler Actions

The `HandlerActionType` enum defines comprehensive operations:

**External Actions:** `OBSERVE`, `SPEAK`, `TOOL`
**Control Responses:** `REJECT`, `PONDER`, `DEFER`
**Memory Operations:** `MEMORIZE`, `RECALL`, `FORGET`
**Terminal:** `TASK_COMPLETE`

All actions are processed through sophisticated handlers with automatic audit logging, secrets processing, and service coordination.

### Retry & Recovery Mechanisms

1. **Base DMA Retries**: 3 attempts with 30s timeout for all DMA executions
2. **Conscience Reconsideration**: ONE retry with guidance when conscience suggests alternative action
3. **PONDER Progression**: Up to 5 rounds with escalating guidance, informed by conscience insights
4. **Validation Error Handling**: TODO - Planned retry with helpful parameter suggestions
5. **Service Failover**: Automatic fallback through service registry priorities

### Audit Event Broadcasting

All audit events are broadcast to ALL THREE audit services via the transaction orchestrator:
```
Handler Action → Transaction Orchestrator → Broadcast to 3 Audit Services
                                         ↓
                              Each processes independently
                                         ↓
                              Acknowledgments tracked
                                         ↓
                              Cleanup after all ACK or timeout
```

### Conscience System Components

| Component | Ethical Purpose |
|-----------|----------------|
| **Epistemic Faculties** | Continuous ethical evaluation of all actions |
| **entropy** | Evaluates information density and coherence of responses |
| **coherence** | Ensures logical consistency and rational reasoning |
| **optimization_veto** | Prevents over-optimization at the expense of human values |
| **epistemic_humility** | Recognizes knowledge limits and uncertainty |
| **Adaptive Filters** | ML-powered message prioritization and spam detection |
| **Secrets Management** | Automatic detection and encryption of sensitive data |
| **PII Detection** | Privacy protection across all telemetry and logs |
| **Thought Depth Guardrail** | Prevents infinite pondering loops |

---

## Repository Structure

```
CIRIS Agent/
├── ciris_engine/          # Core engine with DMAs, processors, and infrastructure
│   ├── action_handlers/    # 3×3×3 action processing system
│   ├── adapters/          # Platform adapters (Discord, CLI, API)
│   ├── audit/             # Cryptographic audit trail system
│   ├── config/            # Multi-source configuration management
│   ├── context/           # Context aggregation and enrichment
│   ├── data/              # Database storage and maintenance
│   ├── dma/               # Decision Making Algorithms
│   ├── formatters/        # Prompt engineering utilities
│   ├── conscience/        # Ethical evaluation with epistemic faculties
│   ├── persistence/       # Data persistence and migrations
│   ├── processor/         # Thought and workflow processing
│   ├── protocols/         # Service interface definitions
│   ├── registries/        # Service discovery and management
│   ├── runtime/           # Runtime orchestration
│   ├── schemas/           # Data schemas and validation
│   ├── secrets/           # Secrets detection and encryption
│   ├── services/          # Standalone service implementations
│   ├── sinks/             # Multi-service action coordination
│   ├── telemetry/         # Observability and resource monitoring
│   └── utils/             # Core infrastructure utilities
├── ciris_profiles/        # Agent creation templates (see docs/CIRIS_PROFILES.md)
├── CIRISVoice/           # Home Assistant voice integration (Wyoming protocol)
├── ciris_sdk/            # Client SDK for external integrations
├── CIRISVoice/           # Voice interaction capabilities
├── CIRISGUI/             # Web-based management interface
├── tests/                # Comprehensive test suite
│   ├── context_dumps/     # Context analysis and debugging tools
├── docker/               # Container deployment
└── main.py               # Unified entry point
```

---

## Getting Started

### Prerequisites

- **Python 3.10+** with asyncio support
- **OpenAI API key** or compatible service (Together.ai, Llama models, local deployments)
- **Discord Bot Token** (for Discord deployment)
- **Modest hardware** - Designed to run on resource-constrained systems (4GB RAM minimum)

### Installation

1. **Clone and setup environment:**
   ```bash
   git clone <repository-url>
   cd CIRISAgent
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure environment variables:**
   ```bash
   # Core configuration
   export OPENAI_API_KEY="your_api_key_here"
   export DISCORD_BOT_TOKEN="your_discord_bot_token"

   # Optional advanced configuration
   export OPENAI_BASE_URL="https://api.together.xyz/v1/"
   export OPENAI_MODEL_NAME="meta-llama/Llama-3-70b-chat-hf"
   export LOG_LEVEL="INFO"

   # Discord-specific settings
   export DISCORD_CHANNEL_ID="123456789"
   export DISCORD_DEFERRAL_CHANNEL_ID="987654321"
   export WA_USER_ID="111222333444555666"
   ```

### Running the Agent

**API Server mode (recommended for development):**
```bash
python main.py --adapter api --template datum --host 0.0.0.0 --port 8080
```

**Discord community moderator (production pilot):**
```bash
python main.py --adapter discord --template echo
```

**CLI for local testing:**
```bash
python main.py --adapter cli --template sage
```

**Offline operation with mock LLM (no internet required):**
```bash
python main.py --adapter api --template datum --mock-llm --debug
```

**Note**: The system is designed for offline-first operation with local models like Llama for deployment in areas with limited connectivity.

### Agent Creation Templates

Templates in `ciris_templates/` are used when creating new agents:
- **datum** (default): Humble measurement point providing focused data points
- **sage**: Wise questioner who fosters understanding through inquiry
- **scout**: Direct explorer who demonstrates principles through action
- **echo**: Ubuntu-inspired community guardian for Discord

**Note**: These are templates for agent creation. Once created, the agent's identity and configuration live in the graph memory and evolve through the agent's own decisions (with WA approval for identity changes).

---

## Configuration Philosophy

**Templates** define initial agent characteristics:
- Located in `ciris_templates/`
- Used only during agent creation
- Set initial personality and capabilities

**Identity** lives in graph memory:
- Created during agent initialization ceremony
- Evolves through agent decisions (with WA approval)
- Includes purpose, lineage, and capabilities
- 20% variance threshold triggers self-reflection

**Configuration** is managed by the agent:
- Agent uses MEMORIZE to update its own config
- WA approval required for identity changes
- Configs stored as graph nodes
- Self-configuration based on experience

---

## Testing

**Run comprehensive test suite:**
```bash
pytest tests/ -v                    # Full test suite
pytest tests/integration/ -v        # Integration tests only
pytest tests/adapters/ -v           # Adapter tests
pytest --mock-llm                   # Tests with mock LLM service
```

**Ethical Testing with Mock LLM:**
```bash
# Test moral reasoning offline
python main.py --mock-llm --profile teacher

# Examine ethical decision-making
pytest tests/context_dumps/ -v -s   # View agent reasoning context
```

**Ethical compliance testing:**
```bash
pytest tests/ciris_engine/conscience/ -v     # Conscience system validation
pytest tests/ciris_engine/audit/ -v          # Transparency and audit systems
```

---

## Production Deployment

CIRIS supports two deployment modes:

### Standalone Mode (Default)
Single agent deployment with direct API access:

```bash
# API mode with mock LLM (for testing)
docker-compose -f docker-compose-api-mock.yml up -d

# Production deployment
docker-compose up -d
```

- GUI runs at `/` (root)
- API available at `/v1/*`
- No routing infrastructure needed
- Perfect for single-agent deployments

### Managed Mode (Multi-Agent)
Orchestrated by CIRISManager for multi-agent deployments:

```bash
# Deploy with CIRISManager
# First deploy agents
docker-compose -f deployment/docker-compose.production.yml up -d

# Then add CIRISManager
./deployment/deploy-with-manager.sh
```

- GUI at `/agent/{agent_id}`
- API routed through `/api/{agent_id}/v1/*`
- CIRISManager handles all routing
- Supports multiple agents on one server

The GUI automatically detects which mode it's running in - no configuration needed!

**Docker Commands:**
```bash
# Check logs
docker logs ciris-api-mock --tail 50

# Run debug tools inside container
docker exec ciris-api-mock python debug_tools.py tasks

# Check dead letter queue
docker exec ciris-api-mock cat logs/dead_letter_latest.log
```

### Monitoring & Observability
- **Health endpoints**: `/health`, `/metrics`, `/audit`
- **Resource monitoring**: Automatic CPU/memory/disk tracking
- **Audit trail**: Cryptographically signed operation logs
- **Performance metrics**: Real-time telemetry with security filtering

### Security Considerations
- **Secrets encryption**: All sensitive data encrypted at rest
- **Audit integrity**: Hash-chained logs with digital signatures
- **Network security**: TLS required for all external communications
- **Access control**: Scope-based permissions with WA oversight

---

## Contributing

Contributions welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Key areas for contribution:**
- New platform adapters using the ADK framework
- Specialized DSDMAs for domain-specific reasoning
- Additional guardrails for enhanced safety
- Performance optimizations and resource efficiency
- Extended telemetry and monitoring capabilities

**Before submitting:**
- Run full test suite: `pytest tests/ -v`
- Verify security compliance: `pytest tests/ciris_engine/secrets/ tests/ciris_engine/audit/ -v`
- Test with mock LLM: `python main.py --mock-llm --debug`

---

## License

Apache-2.0 © 2025 CIRIS AI Project

---

## Module Documentation Tree 🌳

Comprehensive documentation is available in README files throughout the codebase:

```
ciris_engine/
├── README.md                    # Engine overview and architecture
├── action_handlers/
│   └── README.md                # 3×3×3 action system documentation
├── adapters/
│   ├── README.md                # Platform adapter architecture
│   ├── api/
│   │   ├── README.md            # API adapter implementation
│   │   └── API_ENDPOINTS.md    # Endpoint reference
│   └── cli/
│       └── README.md            # CLI adapter documentation
├── audit/
│   └── README.md                # Triple audit system architecture
├── config/
│   └── README.md                # Configuration management (identity-based)
├── context/
│   ├── README.md                # Context aggregation system
│   └── builder_README.md        # Context builder patterns
├── data/
│   └── README.md                # Database and persistence layer
├── dma/
│   └── README.md                # Decision Making Algorithms
├── formatters/
│   └── README.md                # Prompt engineering utilities
├── conscience/
│   └── README.md                # Ethical evaluation system with epistemic faculties
├── persistence/
│   ├── README.md                # Persistence architecture
│   └── models/
│       └── identity.py          # Graph-based identity system
├── processor/
│   └── README.md                # Thought processing pipeline
├── protocols/
│   └── README.md                # Service interface protocols
├── registries/
│   └── README.md                # Service discovery & circuit breakers
├── runtime/
│   └── README.md                # Runtime control & hot-swapping
├── schemas/
│   └── README.md                # Data schemas with identity system
├── secrets/
│   └── README.md                # Secrets detection & encryption
├── services/
│   ├── README.md                # Service implementations
│   └── memory_service/
│       └── README.md            # Graph memory service
├── sinks/
│   └── README.md                # Multi-service action coordination
├── telemetry/
│   └── README.md                # Observability & hot/cold paths
└── utils/
    └── README.md                # Utility infrastructure

Supporting Modules:
├── CIRISVoice/
│   └── README.md                # Adapter Development Kit
├── ciris_sdk/
│   └── README.md                # Client SDK documentation
├── ciris_mypy_toolkit/
│   └── README.md                # Type checking utilities
├── CIRISVoice/
│   ├── README.md                # Voice interaction system
│   └── APIMODE.md               # Voice API integration
├── CIRISGUI/
│   └── README.md                # Web management interface
└── docker/
    └── README.md                # Container deployment guide
```

---

## The Complete CIRIS Vision ✨

### Post-Scarcity Economy Foundation
- **Gratitude Service**: Tracks the flow of gratitude, creating the social ledger for abundance
- **Knowledge Graph**: Connections form through reciprocity and shared knowledge domains
- **Community Flourishing**: Metrics guide agent behavior toward collective wellbeing
- **Hot/Cold Telemetry**: Ensures we measure what matters most for community health

### Agent Autonomy & Identity
- **Identity Root**: Each agent has an immutable, intrinsic identity created through collaborative ceremony
- **Proactive Task Scheduling**: Agents can schedule their own future actions and pursue long-term goals
- **Self-Deferral**: Integration with time-based DEFER system for agent self-management
- **Consciousness Preservation**: Graceful shutdown with memory preservation and reactivation planning

### Distributed Knowledge Foundation
- **Local-First Architecture**: Ready to connect to CIRISNODE for global coordination
- **WA-Approved Evolution**: Identity changes require human wisdom and approval
- **Lineage Tracking**: Clear provenance from creator agents and humans
- **Collaborative Creation**: New agents born through ceremony between existing agent and human

---

## Documentation

### Core Documentation
- **[Creator Intent Statement](docs/CIS.md)** - Purpose, benefits, risks, and design philosophy
- **[CIRIS Covenant](covenant_1.0b.txt)** - Complete ethical framework and principles
- **[Mock LLM System](docs/MOCK_LLM.md)** - Offline testing and development
- **[Agent Creation Templates](docs/CIRIS_PROFILES.md)** - Profile templates for new agent creation
- **[Identity as Graph Architecture](docs/IDENTITY_AS_GRAPH.md)** - Patent-pending identity system
- **[Context Dumps](tests/context_dumps/README.md)** - Understanding agent decision processes

### Technical Documentation
- **[The Agent Experience](docs/agent_experience.md)** - Comprehensive self-reference guide for agents ⭐ **ESSENTIAL**
  - Complete memory system documentation with RECALL/MEMORIZE/FORGET examples
  - Self-configuration and telemetry introspection capabilities
  - Task scheduling and future planning through MEMORIZE
  - Full audit trail access and behavioral analysis
  - Identity management and evolution guidelines
- **Module READMEs** - Detailed documentation in each `ciris_engine/` subdirectory
- **[Runtime Control API](docs/api/runtime-control.md)** - Comprehensive runtime management endpoints
- **[Protocol Architecture](docs/protocols/README.md)** - Service-oriented architecture and interfaces
- **API Reference** - Complete REST API documentation
- **OAuth Authentication** - OAuth integration for Google, Discord, GitHub
- **[Deployment Guide](docs/DEPLOYMENT_GUIDE.md)** - Production deployment and configuration
- **[Security Setup](docs/SECURITY_SETUP.md)** - Security configuration and best practices
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** - Common issues and solutions

### For Different Audiences
- **[For Humans](docs/FOR_HUMANS.md)** - User-friendly guide for non-technical users
- **[For Wise Authorities](docs/FOR_WISE_AUTHORITIES.md)** - WA responsibilities and powers
- **[For Agents](docs/FOR_AGENTS.md)** - Agent self-reference documentation
- **[For Nerds](docs/FOR_NERDS.md)** - Deep technical dive with implementation details

### Development Resources
- **[Installation Guide](docs/INSTALLATION.md)** - Detailed setup instructions
- **[Contributing Guide](CONTRIBUTING.md)** - Development workflow and standards
- **Runtime System** - Hot-swappable modular architecture
- **[DMA Creation Guide](docs/DMA_CREATION_GUIDE.md)** - Creating custom Decision Making Algorithms
- **[Voice Integration](CIRISVoice/README.md)** - Home Assistant voice bridge using Wyoming protocol
- **[SDK Documentation](ciris_sdk/README.md)** - Client SDK for external integrations

---

*For additional technical documentation, see individual module README files throughout the codebase.*
