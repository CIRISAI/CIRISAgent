# CIRIS Protocol Architecture

This directory contains all protocol definitions for the CIRIS system. Protocols define the contracts that implementations must follow exactly - this is the foundation of our Protocol-Module-Schema architecture.

## Protocol Categories

### 🧠 [Services](./services/) - 21 Core Service Protocols
The heart of CIRIS - all 21 service protocols organized by category:
- **Graph Services** (6): Memory, Config, Telemetry, Audit, IncidentManagement, TSDBConsolidation
- **Infrastructure** (7): Time, Shutdown, Initialization, Authentication, ResourceMonitor, DatabaseMaintenance, Secrets
- **Governance** (4): WiseAuthority, AdaptiveFilter, Visibility, SelfObservation
- **Runtime** (3): LLM, RuntimeControl, TaskScheduler
- **Tool** (1): Tool (external tool execution)

### 🎯 [Handlers](./handlers/) - Action Handler Protocols
Protocols for the 10 action handlers:
- External Actions: SPEAK, TOOL, OBSERVE
- Control Actions: REJECT, PONDER, DEFER
- Memory Actions: MEMORIZE, RECALL, FORGET
- Terminal: TASK_COMPLETE

### 🧮 [DMAs](./dmas/) - Decision Making Algorithm Protocols
Protocols for the 4 decision making algorithms:
- **PDMA**: Principled Decision Making Algorithm
- **CSDMA**: Common Sense Decision Making Algorithm
- **DSDMA**: Domain Specific Decision Making Algorithm
- **ActionSelectionDMA**: Recursive ethical action selection

### 🎓 [Faculties](./faculties/) - Specialized Reasoning Protocols
Protocols for specialized reasoning faculties:
- **Epistemic**: Knowledge and uncertainty assessment
- **Coherence**: Internal consistency checking
- **Entropy**: Information complexity analysis
- **Wisdom**: Deep understanding evaluation

### 🛡️ [Adapters](./adapters/) - External Interface Protocols
Protocols for external adapters:
- **API**: RESTful API adapter
- **CLI**: Command-line interface adapter
- **Discord**: Discord bot adapter (future)

### 🏗️ [Infrastructure](./infrastructure/) - System Foundation Protocols
Low-level infrastructure protocols:
- **MessageBus**: Inter-component communication
- **ServiceRegistry**: Service discovery and registration
- **Persistence**: Data persistence layer
- **Monitoring**: System health and metrics

## Base Protocols

All protocols inherit from base protocols defined in [base.py](./base.py):
- `ServiceProtocol`: Base for all services
- `HandlerProtocol`: Base for all handlers
- `DMAProtocol`: Base for all DMAs
- `FacultyProtocol`: Base for all faculties
- `AdapterProtocol`: Base for all adapters

## Protocol Rules

1. **Exact Implementation**: Every method in a protocol MUST be implemented
2. **No Extras**: Implementations MUST NOT have public methods outside the protocol
3. **Type Safety**: All parameters and returns must use typed schemas
4. **Async First**: I/O operations must be async
5. **Documentation**: Every protocol must have comprehensive docstrings

## Adding New Protocols

1. Determine the correct category for your protocol
2. Create the protocol file in the appropriate directory
3. Extend from the appropriate base protocol
4. Define all required methods with proper type hints
5. Update the category's README.md
6. Add compliance tests

## Protocol Compliance

Use the protocol compliance checker:
```bash
python -m ciris_mypy_toolkit check-protocols
```

This verifies:
- All implementations match their protocols exactly
- No extra public methods exist
- All type hints are properly defined
- Protocol inheritance is correct
