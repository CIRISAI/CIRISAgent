# CIRIS Runtime System

The CIRIS runtime system provides a modular, hot-swappable architecture for running the agent in different environments with comprehensive runtime control capabilities.

## Core Components

### CIRISRuntime
The unified base runtime class that initializes the service registry and all core services. Supports multiple adapter modes simultaneously.

**Key Features**:
- **Multi-Adapter Support**: Load Discord, CLI, and API adapters simultaneously
- **Hot-Swapping**: Add/remove adapters at runtime without restart
- **Service Registry**: Centralized service discovery with priority and capability-based routing
- **Configuration Management**: Dynamic configuration with runtime updates
- **Comprehensive Telemetry**: Built-in monitoring and observability

### RuntimeControlService
**Location**: `runtime_control.py`

Provides comprehensive runtime management capabilities through both API endpoints and programmatic interface.

**Capabilities**:
```python
# Processor Control
await runtime_control.single_step()           # Debug single execution step
await runtime_control.pause_processing()      # Pause for debugging
await runtime_control.resume_processing()     # Resume normal operation

# Adapter Management
await runtime_control.load_adapter(           # Hot-load new adapter
    "discord", "bot_prod", {"token": "...", "home_channel": "general"}
)
await runtime_control.unload_adapter("bot_prod")  # Remove adapter

# Configuration Management
await runtime_control.update_config(          # Live config updates
    "llm_services.openai.temperature", 0.8, ConfigScope.SESSION
)
# Profile switching removed - identity is now graph-based
```

### RuntimeAdapterManager
**Location**: `adapter_manager.py`

Manages the lifecycle of platform adapters with support for multiple instances of the same adapter type.

**Features**:
- **Multi-Instance Support**: Run multiple Discord bots with different configurations
- **Graceful Lifecycle**: Proper startup, shutdown, and error handling
- **Service Coordination**: Automatic service registration/deregistration
- **Configuration Integration**: Profile-based adapter configuration

### ConfigManagerService
**Location**: `config_manager_service.py`

Handles dynamic configuration management with validation, persistence, and rollback support.

**Features**:
- **Live Updates**: Change configuration without restart
- **Validation**: Comprehensive config validation with rollback
- **Backup/Restore**: Configuration snapshots and restore points
- **Environment Integration**: Environment variable management
- **Identity Management**: Graph-based identity (profiles are creation templates only)

## Architecture Patterns

### 1. Service-Oriented Architecture
All components communicate through well-defined service interfaces:

```python
# Service registration pattern
def get_services_to_register(self) -> List[ServiceRegistration]:
    return [
        ServiceRegistration(
            service_type=ServiceType.COMMUNICATION,
            service_instance=self.communication_service,
            priority=Priority.HIGH,
            handlers=["SpeakHandler", "ObserveHandler"],
            capabilities=["send_message", "receive_message"]
        )
    ]
```

### 2. Hot-Swappable Modularity
Adapters can be loaded and unloaded dynamically:

```python
# Load new Discord adapter at runtime
result = await runtime_control.load_adapter(
    adapter_type="discord",
    adapter_id="discord_admin",
    config={
        "token": "admin_bot_token",
        "home_channel": "admin-alerts"
    },
    auto_start=True
)
```

### 3. Configuration Scopes
Three configuration scopes for different persistence levels:

- **`runtime`**: Changes only affect current session (not persisted)
- **`session`**: Changes persist until restart
- **`persistent`**: Changes are written to configuration files

### 4. Comprehensive Auditing
All runtime control operations are automatically logged:

```python
# All operations logged to audit service
await runtime_control.update_config(...)  # Automatically audited
# Console output: [RUNTIME_CONTROL] config_control.update COMPLETED
```

## Usage Examples

### 1. Multi-Platform Agent
Run agent with Discord, API, and CLI simultaneously:

```python
runtime = CIRISRuntime(
    modes=["discord", "api", "cli"],
    agent_identity="multi_platform"  # From graph, not profile
)
await runtime.initialize()
await runtime.run()
```

### 2. Hot-Swap Configuration
Update Discord bot configuration without restart:

```python
# Update home channel
await runtime_control.update_config(
    "discord.home_channel",
    "new-general",
    ConfigScope.SESSION
)

# Reload Discord adapter with new config
await runtime_control.unload_adapter("discord_main")
await runtime_control.load_adapter(
    "discord", "discord_main",
    {"home_channel": "new-general"}
)
```

### 3. Development Debugging
Use processor control for debugging:

```python
# Pause for debugging
await runtime_control.pause_processing()

# Execute single steps
result = await runtime_control.single_step()
print(f"Processed {result.result['thoughts_processed']} thoughts")

# Resume when ready
await runtime_control.resume_processing()
```

### 4. Profile Management
Agent identity management:

```python
# Profile switching removed - identity is now graph-based
# To modify identity, use MEMORIZE action with WA approval
# Identity changes require:
# 1. WA authorization
# 2. < 20% variance or reconsideration
# 3. Cryptographic audit trail
```

## Legacy Runtime Classes (Deprecated)

The following runtime classes are deprecated in favor of the unified `CIRISRuntime`:

- **DiscordRuntime** → Use `CIRISRuntime(modes=["discord"])`
- **CLIRuntime** → Use `CIRISRuntime(modes=["cli"])`
- **APIRuntimeEntrypoint** → Use `CIRISRuntime(modes=["api"])`

**Migration Path**:
```python
# Old approach
from ciris_engine.runtime.discord_runtime import DiscordRuntime
runtime = DiscordRuntime(...)

# New approach
from ciris_engine.runtime.ciris_runtime import CIRISRuntime
runtime = CIRISRuntime(modes=["discord"], ...)
```

## Service Registry Integration

Each runtime waits for the service registry to become ready before processing thoughts. The registry validates that core services are available:

- **Communication Services** (Discord, CLI, API)
- **Memory Services** (Graph-based memory)
- **LLM Services** (OpenAI-compatible)
- **Audit Services** (Cryptographic logging)
- **Tool Services** (External tool execution)

**Default timeout**: 30 seconds, after which processing continues with available services.

## Configuration Integration

### Agent Profiles
Runtime configuration is managed through the configuration system:

```json
{
  "name": "production",
  "description": "Production agent configuration",
  "discord_config": {
    "token": "...",
    "home_channel": "general",
    "enabled_channels": ["general", "dev"]
  },
  "api_config": {
    "host": "0.0.0.0",
    "port": 8080
  },
  "cli_config": {
    "interactive": false
  }
}
```

### Environment Variables
Configuration can be overridden by environment variables:

```bash
export CIRIS_API_HOST=0.0.0.0
export CIRIS_API_PORT=8080
export DISCORD_TOKEN=your_bot_token
export OPENAI_API_KEY=your_openai_key
```

## Error Handling & Resilience

### 1. Circuit Breaker Protection
Services implement circuit breaker patterns for external dependencies.

### 2. Graceful Degradation
System continues operating with reduced functionality when services fail.

### 3. Automatic Recovery
Failed services are automatically restarted with exponential backoff.

### 4. Comprehensive Logging
All errors logged with context for debugging and forensic analysis.

## Monitoring & Observability

### 1. Telemetry Integration
Built-in telemetry collection for all runtime operations:

```python
# Automatic telemetry for all operations
telemetry = runtime.telemetry_collector
snapshot = await telemetry.get_system_snapshot()
```

### 2. Health Monitoring
Continuous health checks for all services and adapters.

### 3. Metrics Collection
Time-series metrics for performance monitoring and alerting.

### 4. Audit Trails
Cryptographically signed audit logs for all runtime control operations.

## Security Features

### 1. Secrets Management
Automatic detection and encryption of sensitive configuration:

```python
# Secrets automatically detected and encrypted
config = {
    "discord_token": "sensitive_bot_token",  # Auto-encrypted
    "api_key": "openai_key"                  # Auto-encrypted
}
```

### 2. Access Control
Role-based access control for runtime control operations.

### 3. Audit Logging
All configuration changes and administrative actions logged.

### 4. Configuration Validation
Strict validation prevents invalid or dangerous configurations.

## API Integration

The runtime system is fully integrated with the CIRIS API:

- **Runtime Control Endpoints**: `/v1/runtime/*`
- **System Telemetry**: `/v1/system/*`
- **Adapter Management**: Dynamic loading via API
- **Configuration Updates**: Live config changes via API

See the [Runtime Control API Guide](../../docs/api/runtime-control.md) for complete API documentation.

## Best Practices

### 1. Production Deployment
```python
# Production configuration
runtime = CIRISRuntime(
    modes=["api"],  # API-only for production
    agent_identity="production",  # From graph
    interactive=False
)
```

### 2. Development Setup
```python
# Development with debugging
runtime = CIRISRuntime(
    modes=["cli", "api"],  # Local CLI + API access
    agent_identity="development",  # From graph
    debug=True
)
```

### 3. Multi-Bot Discord Setup
```python
# Multiple Discord bots
await runtime_control.load_adapter(
    "discord", "main_bot",
    {"token": "main_token", "home_channel": "general"}
)
await runtime_control.load_adapter(
    "discord", "admin_bot",
    {"token": "admin_token", "home_channel": "admin"}
)
```

### 4. Configuration Management
```python
# Always backup before major changes
await runtime_control.backup_config(
    include_settings=True,  # Profiles removed
    backup_name="pre_update"
)

# Make changes with validation
await runtime_control.update_config(
    "path.to.setting", new_value,
    validation_level=ConfigValidationLevel.STRICT
)
```

The CIRIS runtime system provides a robust, flexible foundation for running the agent across different platforms while maintaining full control over system behavior and configuration.

---

*Copyright © 2025 Eric Moore and CIRIS L3C - Apache 2.0 License*
