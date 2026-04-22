# Configuration Management

The configuration module provides a clean, graph-based configuration system designed for mission-critical operations with 1000-year reliability.

## Architecture

### Two-Phase Configuration System

1. **Bootstrap Phase**: Essential configuration loaded from files/environment to initialize core services
2. **Runtime Phase**: All configuration managed through GraphConfigService with full versioning and audit

### Core Components

#### ConfigBootstrap (`bootstrap.py`)
Loads essential configuration needed to start core services from multiple sources with priority ordering.

#### ConfigAccessor (`config_accessor.py`)
Unified interface for configuration access with graph-first approach and bootstrap fallback.

#### Environment Utilities (`env_utils.py`)
Clean environment variable processing with type conversion.

#### Database Path Utilities (`db_paths.py`)
Centralized database path management for backward compatibility.

## Essential Configuration Only

The system maintains only mission-critical configuration values with zero ambiguity:

```python
class EssentialConfig(BaseModel):
    """Mission-critical configuration for CIRIS bootstrap."""
    database: DatabaseConfig
    services: ServiceEndpointsConfig
    security: SecurityConfig
    limits: OperationalLimitsConfig
    telemetry: TelemetryConfig

    class Config:
        extra = "forbid"  # No ambiguity allowed
```

### Configuration Sources (Priority Order)

1. **CLI Arguments** - Direct command-line overrides
2. **Environment Variables** - `CIRIS_` prefixed variables
3. **Configuration File** - `config/essential.yaml`
4. **Built-in Defaults** - Safe, sensible defaults

## Usage

### Bootstrap Configuration

```python
from ciris_engine.logic.config import ConfigBootstrap

# Load essential config during startup
bootstrap = ConfigBootstrap()
essential_config = await bootstrap.load_essential_config(
    config_path=Path("config/essential.yaml"),
    cli_overrides={"database.main_db": "custom.db"}
)
```

### Runtime Configuration Access

```python
from ciris_engine.logic.config import ConfigAccessor

# Create accessor with graph service
accessor = ConfigAccessor(
    essential_config=essential_config,
    graph_config=graph_config_service
)

# Get configuration (graph-first, bootstrap fallback)
db_path = await accessor.get("database.main_db")
max_tasks = await accessor.get("limits.max_active_tasks", default=10)
```

### Configuration Migration

After services are initialized, bootstrap config migrates to graph:

```python
# In ServiceInitializer
async def _migrate_config_to_graph(self) -> None:
    """Migrate essential config to graph for runtime management."""
    if self.graph_config:
        await self.graph_config.set_config(
            "bootstrap",
            self.essential_config.model_dump(),
            source="bootstrap",
            metadata={"migrated_at": self.time_service.now().isoformat()}
        )
```

## Environment Variables

All environment variables use the `CIRIS_` prefix:

- `CIRIS_DATABASE_MAIN_DB` - Main database path
- `CIRIS_DATABASE_SECRETS_DB` - Secrets database path
- `CIRIS_SERVICES_LLM_PROVIDER` - LLM provider selection
- `CIRIS_SERVICES_LLM_API_KEY` - LLM API key
- `CIRIS_SECURITY_ENABLE_SIGNED_AUDIT` - Enable audit signing
- `CIRIS_LIMITS_MAX_ACTIVE_TASKS` - Maximum concurrent tasks

## Graph Configuration Benefits

Once migrated to graph, configuration gains:

- **Full Versioning** - Every change tracked with timestamp
- **Audit Trail** - Who changed what and why
- **Rollback** - Revert to any previous version
- **Rich Metadata** - Source, validation, relationships
- **Access Control** - Permission-based modifications
- **Real-time Updates** - Changes propagate immediately

## Best Practices

1. **Minimal Bootstrap** - Only essential values in bootstrap config
2. **Graph Migration** - Move all config to graph after startup
3. **Type Safety** - Use Pydantic models with `extra="forbid"`
4. **Clear Naming** - Unambiguous configuration keys
5. **Secure Defaults** - Safe values when not specified
6. **Environment Priority** - Allow runtime overrides via env vars
7. **Validation** - Strict validation at every layer

## Example Configuration File

```yaml
# config/essential.yaml
database:
  main_db: "data/ciris_engine.db"
  secrets_db: "data/secrets.db"
  audit_db: "data/audit.db"
  graph_memory_db: "data/graph_memory.db"

services:
  llm_provider: "openai"
  llm_api_key: ""  # Set via CIRIS_SERVICES_LLM_API_KEY
  llm_model: "gpt-4"
  cirisnode_url: ""

security:
  secrets_encryption_key_env: "CIRIS_MASTER_KEY"
  audit_key_path: "audit_keys"
  enable_signed_audit: true
  max_thought_depth: 7

limits:
  max_active_tasks: 10
  max_active_thoughts: 50
  round_delay_seconds: 5.0
  mock_llm_round_delay: 0.1
  dma_retry_limit: 3
  dma_timeout_seconds: 30.0
  conscience_retry_limit: 2

telemetry:
  enabled: false
  export_interval_seconds: 60
  retention_hours: 24
```

---

*Mission-critical configuration for autonomous moral reasoning agents.*
