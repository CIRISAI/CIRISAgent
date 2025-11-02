# Adapters

External system integrations that enable CIRIS to interact with different environments and platforms.

## Overview

Adapters provide the interface between CIRIS's core engine and external systems. Each adapter implements the standard adapter protocol while providing environment-specific functionality.

## Available Adapters

### [API Adapter](api/README.md)
RESTful API server with OAuth2 authentication, multi-tenant support, and comprehensive endpoint coverage.

**Features:**
- 78+ REST endpoints with full OpenAPI documentation
- Role-based access control (OBSERVER/ADMIN/AUTHORITY/SYSTEM_ADMIN)
- WebSocket support for real-time streaming
- Emergency shutdown with Ed25519 signatures
- Runtime control interface
- Complete TypeScript SDK

**Usage:**
```bash
python main.py --adapter api --port 8080
```

### [CLI Adapter](cli/README.md)
Command-line interface for development, testing, and local operation.

**Features:**
- Interactive command-line interface
- Mock LLM integration for offline testing
- Development and debugging tools
- Local configuration management

**Usage:**
```bash
python main.py --adapter cli --template datum --mock-llm
```

### [Discord Adapter](discord/README.md)
Production-ready Discord bot for community moderation with Wise Authority integration.

**Features:**
- Complete Discord bot functionality with multi-channel support
- Advanced community moderation and user management tools
- Wise Authority deferral workflow through Discord reactions
- Real-time monitoring and automatic content filtering
- Currently powering community moderation at agents.ciris.ai

**Usage:**
```bash
python main.py --adapter discord --guild-id YOUR_GUILD_ID
```

## Adapter Architecture

### Base Components

- **[BaseAdapter](base_adapter.py)** - Core adapter interface and common functionality
- **[BaseObserver](base_observer.py)** - Event observation and monitoring patterns
- **[CIRISNode Client](cirisnode_client.py)** - Network communication utilities

### Service Providers

Adapters provide additional services to the core engine:

1. **Communication Services** - Enable external communication (Discord, API, CLI)
2. **Tool Services** - Adapter-specific tools and capabilities
3. **Runtime Control Services** - Environment-specific management interfaces
4. **Authentication Services** - Platform-specific auth integration

### Message Bus Integration

Adapters integrate with the engine's message bus system:

- **CommunicationBus** - Adapters provide communication implementations
- **ToolBus** - Adapters add their specific tools
- **RuntimeControlBus** - Adapters provide management interfaces

## Development Guidelines

### Creating a New Adapter

1. **Extend BaseAdapter** - Implement the core adapter interface
2. **Define Services** - Implement required service providers (Communication, etc.)
3. **Add Tools** - Provide adapter-specific tools through ToolBus
4. **Handle Authentication** - Implement platform-specific auth if needed
5. **Add Tests** - Comprehensive testing including integration tests
6. **Documentation** - Create adapter-specific README.md

### Adapter Responsibilities

- **Environment Integration** - Connect CIRIS to external platforms
- **Protocol Translation** - Convert between CIRIS protocols and external APIs
- **Authentication** - Handle platform-specific authentication and permissions
- **Tool Provision** - Provide environment-specific capabilities
- **Error Handling** - Graceful degradation and error recovery
- **Resource Management** - Efficient use of external API limits/resources

## Configuration

Adapters are configured through:

- Command-line arguments (`--adapter`, `--port`, etc.)
- Environment variables (API keys, tokens, etc.)
- Configuration files (agent templates, settings)
- Runtime parameters (guild IDs, endpoints, etc.)

## Testing

Each adapter includes:

- **Unit Tests** - Individual component testing
- **Integration Tests** - Full adapter workflow testing
- **Mock Modes** - Offline testing capabilities
- **Security Tests** - Authentication and authorization validation

---

*Adapters enable CIRIS to serve diverse communities through their preferred platforms while maintaining consistent ethical behavior and audit trails across all environments.*
