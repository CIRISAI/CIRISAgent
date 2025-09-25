# CIRIS Documentation

Welcome to the CIRIS (Core Identity, Integrity, Resilience, Incompleteness, and Signalling Gratitude) documentation.

## Getting Started
- [Quick Start Guide](QUICKSTART.md) - Get running in 5 minutes
- [Deployment Guide](DEPLOYMENT.md) - Local development and production deployment

## Architecture & Design
- [Architecture Overview](ARCHITECTURE.md) - System components and design (22 services)
- [Architecture Pattern](ARCHITECTURE_PATTERN.md) - Intent-Driven Hybrid Architecture  
- [Philosophy](../CLAUDE.md#core-philosophy-type-safety-first) - Core principles: No Untyped Dicts, No Bypass Patterns, No Exceptions

## Configuration & Operations
- [Agent Configuration](AGENT_CONFIGURATION.md) - Creating and configuring agents
- [Agent Creation Ceremony](AGENT_CREATION_CEREMONY.md) - Formal process for agent creation

## Development  
- [API Documentation](single_step_api_audit.md) - REST API specification and debugging
- [Memory System](IDENTITY_AS_GRAPH.md) - Memory management and cognitive recursion
- [Thought Model](DMA_CREATION_GUIDE.md) - Deep reasoning system (DMAs, ASPDMA)
- [Mock LLM](MOCK_LLM.md) - Development and testing with mock LLM providers
- [Type Safety Progress](TYPE_SAFETY_PROGRESS.md) - Dict[str, Any] cleanup progress
- [Dream State Tasks](DREAM_STATE_TASKS.md) - Agent cognitive states and behaviors

### Three-Legged Stool Architecture
- [Logic](../ciris_engine/logic/README.md) - Business logic and service implementations
- [Protocols](../ciris_engine/protocols/) - Service interfaces ([Handlers](../ciris_engine/protocols/handlers/README.md), [Services](../ciris_engine/protocols/services/README.md))
- [Schemas](../ciris_engine/schemas/README.md) - Type-safe data structures

## Security & Operations
- [Security: Agent IDs](SECURITY_AGENT_IDS.md) - Cryptographically secure ID generation
- [Security: Temp Files](SECURITY_TEMP_FILES.md) - Secure temporary file handling
- [Secrets Management](SECRETS_MANAGEMENT.md) - Secure credential and secret handling
- [Emergency Shutdown](EMERGENCY_SHUTDOWN.md) - Critical system shutdown procedures
- [Deferral System](DEFERRAL_SYSTEM.md) - Human oversight and escalation system

## Additional Resources
- [Comprehensive Guide](../CIRIS_COMPREHENSIVE_GUIDE.md) - Key terms and concepts
- [Release Notes](releases/) - Version history and updates
- [Single-Step UI Guide](single_step_ui_guide.md) - Implementation guide for transparent debugging
- [For Humans](FOR_HUMANS.md) - Human-centric guide to CIRIS
- [Mission-Driven Development](../FSD/MISSION_DRIVEN_DEVELOPMENT.md) - Core development methodology

## Voice Integration (CIRISVoice)
- [Voice PE Quickstart](../CIRISVoice/VOICE_PE_QUICKSTART.md) - Quick setup for voice processing
- [Wyoming CIRIS Integration](../CIRISVoice/WYOMING_CIRIS_INTEGRATION.md) - Home Assistant voice integration
- [Simple Integration](../CIRISVoice/SIMPLE_INTEGRATION.md) - Basic voice integration guide
- [Home Assistant Yellow Deployment](../CIRISVoice/HA_YELLOW_DEPLOYMENT.md) - Hardware deployment guide
- [SDK Migration](../CIRISVoice/SDK_MIGRATION.md) - Voice SDK migration guide

## Technical Specifications
- [Authentication System](../FSD/AUTHENTICATION.md) - OAuth, JWT, and WA certificates
- [Graceful Shutdown](../FSD/GRACEFUL_SHUTDOWN.md) - Clean termination procedures
- [Environment Variables](../config/environment_variables.md) - Configuration reference

## Quick Links

### For Users
Start with the [Quick Start Guide](QUICKSTART.md) to get CIRIS running quickly.

### For Developers
Review the [Architecture](ARCHITECTURE.md) and [API Documentation](API_SPEC.md).

### For Operations
See the [Deployment Guide](DEPLOYMENT.md).

## Contributing

Please read our contribution guidelines and ensure all tests pass before submitting PRs.
