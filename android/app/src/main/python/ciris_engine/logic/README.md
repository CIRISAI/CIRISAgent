# CIRIS Logic Implementation Layer

This directory contains all the implementation code for CIRIS. It follows the crystalline structure principle with perfect 1:1:1 mapping to protocols/ and schemas/.

## Directory Structure

Each subdirectory here has corresponding directories in:
- `/protocols/` - Interface definitions
- `/schemas/` - Data structures

## Navigation

If you're looking at a file in:
- `logic/services/core/llm_service.py`

You'll find related files at:
- `protocols/services/core/llm.py` - Protocol definition
- `schemas/services/core/llm.py` - Request/response schemas

## Principles

1. **No Dict[str, Any]** - Everything uses typed schemas
2. **Protocol-driven** - All implementations follow protocols
3. **Navigational determinism** - Predictable file locations
4. **Zero backwards compatibility** - Move forward only

## Categories

- **adapters/** - Platform integrations (API, CLI, Discord, etc.)
- **audit/** - Audit and verification logic
- **[buses/](buses/README.md)** - Message bus implementations for multi-provider service coordination
- **config/** - Configuration management
- **context/** - Context building and management
- **dma/** - Decision Making Algorithms
- **faculties/** - Cognitive faculties
- **formatters/** - Output formatting
- **guardrails/** - Safety and constraint enforcement
- **handlers/** - Action handlers
- **infrastructure/** - System infrastructure
- **persistence/** - Data persistence layer
- **processors/** - State processors
- **registries/** - Service and handler registries
- **runtime/** - Runtime management
- **secrets/** - Secret management
- **[services/](services/README.md)** - Core services (22 total)
- **telemetry/** - Metrics and monitoring
- **utils/** - Utility functions
