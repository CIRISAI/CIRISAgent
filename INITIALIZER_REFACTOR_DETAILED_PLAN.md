# ServiceInitializer Refactoring - Detailed Implementation Plan

**Version**: 1.0
**Date**: 2025-10-31
**Status**: Planning Phase
**Estimated Effort**: 18-24 hours across 10 phases

---

## Executive Summary

### Problem Statement

The ServiceInitializer is a 1,333-line monolith that violates CIRIS's core philosophy of type safety and separation of concerns. It mixes 6 distinct responsibilities, accepts untyped `config: Any` parameters in 6 methods, and directly accesses environment variables in 12 locations. This creates maintenance burden, prevents effective testing, and contradicts the "No Untyped Dicts" principle.

### Goals

1. **Eliminate all `config: Any` parameters** - Replace with strongly-typed Pydantic models
2. **Separate concerns** - Split monolith into 5 focused components
3. **Centralize environment access** - Move all env var reads to ConfigurationAdapter
4. **Maintain backward compatibility** - Preserve existing public interfaces
5. **Enable parallel execution** - Support gradual cutover with feature flags
6. **Improve testability** - Each component independently testable

### Expected Outcomes

- **Type Safety**: 100% typed configuration throughout initialization
- **Maintainability**: ~250 lines per component vs. 1,333-line monolith
- **Testability**: Each component unit-testable in isolation
- **Extensibility**: New service types added via composers, not ServiceInitializer
- **Consistency**: Follows established CIRIS patterns (protocols, buses, typed models)

---

## Current State Analysis

### Statistics

- **Total Lines**: 1,333
- **Method Count**: 20 methods
- **`config: Any` Occurrences**: 6 methods
- **`Any` Typed Attributes**: 11 instance variables
- **Environment Variable Reads**: 12 direct `os.getenv()` / `os.environ.get()` calls
- **Service Imports**: 21 direct service imports
- **Distinct Concerns**: 6 (environment probing, config parsing, policy decisions, service construction, lifecycle management, registry wiring)

### Method Catalog

| Line | Method Name | Responsibility | config: Any? | Env Vars? |
|------|-------------|----------------|--------------|-----------|
| 48 | `__init__` | Construction | No | No |
| 94 | `initialize_infrastructure_services` | Infrastructure bootstrap | No | Yes (12x) |
| 183 | `initialize_memory_service` | Memory/secrets setup | Yes | No |
| 326 | `verify_memory_service` | Verification | No | No |
| 377 | `initialize_security_services` | Auth/WA setup | Yes | No |
| 413 | `verify_security_services` | Verification | No | No |
| 433 | `initialize_all_services` | Main orchestration | Yes (2x) | No |
| 742 | `_initialize_llm_services` | LLM setup | Yes | Yes (2x) |
| 811 | `_initialize_secondary_llm` | Secondary LLM | Yes | Yes (3x) |
| 863 | `_initialize_audit_services` | Audit setup | Yes | No |
| 931 | `verify_core_services` | Verification | No | No |
| 964 | `_find_service_manifest` | Modular service discovery | No | No |
| 981 | `_register_tool_service` | Registry wiring | No | No |
| 1008 | `_register_communication_service` | Registry wiring | No | No |
| 1035 | `_register_llm_service` | Registry wiring | No | No |
| 1061 | `_register_modular_service` | Registry wiring | No | No |
| 1070 | `_load_modular_service` | Modular loading | No | No |
| 1140 | `load_modules` | Module orchestration | No | No |
| 1196 | `register_core_services` | Registry population | No | No |
| 1280 | `_migrate_config_to_graph` | Config migration | No | No |
| 1313 | `get_metrics` | Metrics collection | No | No |

### Dependency Graph

```
initialize_infrastructure_services()
    ↓
initialize_memory_service(config)
    ↓ creates: SecretsService, LocalGraphMemoryService, GraphConfigService
    ↓
initialize_security_services(config, app_config)
    ↓ creates: AuthenticationService, WiseAuthorityService
    ↓
initialize_all_services(config, app_config, agent_id, ...)
    ↓ creates: BusManager, GraphTelemetryService
    ↓
    ├─> _initialize_llm_services(config) → OpenAICompatibleClient
    ├─> _initialize_audit_services(config, agent_id) → GraphAuditService, IncidentManagementService
    ├─> AdaptiveFilterService
    ├─> TaskSchedulerService
    ├─> TSDBConsolidationService
    ├─> DatabaseMaintenanceService
    ├─> SelfObservationService
    ├─> VisibilityService
    ├─> ConsentService
    └─> RuntimeControlService
```

### Environment Variable Access Points

| Line | Variable | Purpose | Default |
|------|----------|---------|---------|
| 142 | `CIRIS_BILLING_ENABLED` | Enable billing backend | `"false"` |
| 147 | `CIRIS_BILLING_API_KEY` | Billing API key | None (required if enabled) |
| 153 | `CIRIS_BILLING_API_URL` | Billing service URL | `"https://billing.ciris.ai"` |
| 154 | `CIRIS_BILLING_TIMEOUT_SECONDS` | Billing timeout | `"5.0"` |
| 155 | `CIRIS_BILLING_CACHE_TTL_SECONDS` | Billing cache TTL | `"15"` |
| 156 | `CIRIS_BILLING_FAIL_OPEN` | Fail open on billing errors | `"false"` |
| 169 | `CIRIS_SIMPLE_FREE_USES` | Free uses per user | `"0"` |
| 758 | `OPENAI_API_KEY` | Primary LLM API key | `""` |
| 777 | `INSTRUCTOR_MODE` | Instructor mode setting | `"JSON"` |
| 807 | `CIRIS_OPENAI_API_KEY_2` | Secondary LLM key | `""` |
| 818 | `CIRIS_OPENAI_API_BASE_2` | Secondary LLM base URL | Uses config |
| 826 | `CIRIS_OPENAI_MODEL_NAME_2` | Secondary LLM model | Uses config |

### Service Creation Patterns

**Direct Construction Pattern** (most services):
```python
service = ServiceClass(dep1=..., dep2=..., dep3=...)
await service.start()
self.service_registry.register_service(...)
```

**Conditional Construction** (billing, secondary LLM):
```python
if os.getenv("ENABLE_FEATURE") == "true":
    service = FeatureService(...)
else:
    service = FallbackService(...)
```

**Dynamic Import Pattern** (some services):
```python
from ciris_engine.logic.services.X import XService
service = XService(...)
```

---

## Typed Config Models Design

### Design Principles

1. **One config model per logical grouping** - Not one per service, but per domain
2. **Validation at construction time** - Use Pydantic validators
3. **Explicit defaults** - No magic values hidden in code
4. **Source transparency** - Document which env var maps to which field
5. **Hierarchical structure** - Base configs, specialized configs

### Config Model Hierarchy

```
ConfigurationRoot (top-level)
├─> InfrastructureConfig
│   ├─> ResourceMonitorConfig
│   │   ├─> BillingConfig (optional)
│   │   └─> SimpleCreditConfig (optional)
│   └─> DatabaseMaintenanceConfig
├─> MemoryConfig
├─> SecurityConfig
│   ├─> AuthenticationConfig
│   └─> WiseAuthorityConfig
├─> LLMConfig
│   ├─> PrimaryLLMConfig
│   └─> SecondaryLLMConfig (optional)
├─> ObservabilityConfig
│   ├─> TelemetryConfig
│   ├─> AuditConfig
│   └─> TSDBConfig
└─> GovernanceConfig
    ├─> AdaptiveFilterConfig
    ├─> SelfObservationConfig
    ├─> VisibilityConfig
    └─> ConsentConfig
```

### InfrastructureConfig

```python
"""
File: ciris_engine/schemas/config/infrastructure_config.py
Purpose: Infrastructure service configuration
"""

from enum import Enum
from pathlib import Path
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class CreditProviderType(str, Enum):
    """Credit provider backend types."""
    BILLING = "billing"  # Full CIRIS billing backend
    SIMPLE = "simple"    # Simple free credit provider


class BillingConfig(BaseModel):
    """Configuration for CIRIS billing provider."""

    enabled: bool = Field(
        default=False,
        description="Enable CIRIS billing backend"
    )
    api_key: Optional[str] = Field(
        default=None,
        description="Billing API key (required if enabled=True)"
    )
    base_url: str = Field(
        default="https://billing.ciris.ai",
        description="Billing service base URL"
    )
    timeout_seconds: float = Field(
        default=5.0,
        ge=0.1,
        le=60.0,
        description="Request timeout in seconds"
    )
    cache_ttl_seconds: int = Field(
        default=15,
        ge=0,
        le=300,
        description="Credit check cache TTL"
    )
    fail_open: bool = Field(
        default=False,
        description="Allow access if billing service is down"
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key_if_enabled(cls, v: Optional[str], info) -> Optional[str]:
        """Validate API key is provided if billing is enabled."""
        if info.data.get("enabled") and not v:
            raise ValueError("api_key is required when billing is enabled")
        return v

    @classmethod
    def from_env(cls) -> "BillingConfig":
        """Load from environment variables.

        Environment Variables:
            CIRIS_BILLING_ENABLED: "true"|"false"
            CIRIS_BILLING_API_KEY: API key string
            CIRIS_BILLING_API_URL: Base URL
            CIRIS_BILLING_TIMEOUT_SECONDS: Timeout in seconds
            CIRIS_BILLING_CACHE_TTL_SECONDS: Cache TTL in seconds
            CIRIS_BILLING_FAIL_OPEN: "true"|"false"
        """
        import os
        return cls(
            enabled=os.getenv("CIRIS_BILLING_ENABLED", "false").lower() == "true",
            api_key=os.getenv("CIRIS_BILLING_API_KEY"),
            base_url=os.getenv("CIRIS_BILLING_API_URL", "https://billing.ciris.ai"),
            timeout_seconds=float(os.getenv("CIRIS_BILLING_TIMEOUT_SECONDS", "5.0")),
            cache_ttl_seconds=int(os.getenv("CIRIS_BILLING_CACHE_TTL_SECONDS", "15")),
            fail_open=os.getenv("CIRIS_BILLING_FAIL_OPEN", "false").lower() == "true",
        )


class SimpleCreditConfig(BaseModel):
    """Configuration for simple free credit provider."""

    free_uses: int = Field(
        default=0,
        ge=0,
        description="Number of free uses per OAuth user"
    )

    @classmethod
    def from_env(cls) -> "SimpleCreditConfig":
        """Load from environment variables.

        Environment Variables:
            CIRIS_SIMPLE_FREE_USES: Number of free uses
        """
        import os
        return cls(
            free_uses=int(os.getenv("CIRIS_SIMPLE_FREE_USES", "0"))
        )


class ResourceMonitorConfig(BaseModel):
    """Configuration for ResourceMonitorService."""

    credit_provider: CreditProviderType = Field(
        default=CreditProviderType.SIMPLE,
        description="Which credit provider to use"
    )
    billing: Optional[BillingConfig] = Field(
        default=None,
        description="Billing provider config (required if credit_provider=billing)"
    )
    simple: Optional[SimpleCreditConfig] = Field(
        default=None,
        description="Simple provider config (required if credit_provider=simple)"
    )

    @field_validator("billing")
    @classmethod
    def validate_billing_config(cls, v: Optional[BillingConfig], info) -> Optional[BillingConfig]:
        """Ensure billing config is provided if billing provider selected."""
        if info.data.get("credit_provider") == CreditProviderType.BILLING and not v:
            raise ValueError("billing config required when credit_provider=billing")
        return v

    @field_validator("simple")
    @classmethod
    def validate_simple_config(cls, v: Optional[SimpleCreditConfig], info) -> Optional[SimpleCreditConfig]:
        """Ensure simple config is provided if simple provider selected."""
        if info.data.get("credit_provider") == CreditProviderType.SIMPLE and not v:
            raise ValueError("simple config required when credit_provider=simple")
        return v

    @classmethod
    def from_env(cls) -> "ResourceMonitorConfig":
        """Load from environment, auto-detecting provider type."""
        billing_config = BillingConfig.from_env()
        simple_config = SimpleCreditConfig.from_env()

        # Auto-detect provider type
        provider_type = (
            CreditProviderType.BILLING if billing_config.enabled
            else CreditProviderType.SIMPLE
        )

        return cls(
            credit_provider=provider_type,
            billing=billing_config if provider_type == CreditProviderType.BILLING else None,
            simple=simple_config if provider_type == CreditProviderType.SIMPLE else None,
        )


class DatabaseMaintenanceConfig(BaseModel):
    """Configuration for DatabaseMaintenanceService."""

    archive_dir_path: Path = Field(
        default=Path("data_archive"),
        description="Directory for archived data"
    )
    archive_older_than_hours: int = Field(
        default=24,
        ge=1,
        description="Archive data older than N hours"
    )


class InfrastructureConfig(BaseModel):
    """Complete infrastructure service configuration."""

    resource_monitor: ResourceMonitorConfig
    maintenance: DatabaseMaintenanceConfig

    @classmethod
    def from_env(cls) -> "InfrastructureConfig":
        """Load all infrastructure config from environment."""
        return cls(
            resource_monitor=ResourceMonitorConfig.from_env(),
            maintenance=DatabaseMaintenanceConfig(),  # Uses defaults for now
        )
```

### MemoryConfig

```python
"""
File: ciris_engine/schemas/config/memory_config.py
Purpose: Memory service configuration
"""

from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field


class MemoryConfig(BaseModel):
    """Configuration for memory service initialization."""

    # Secrets service config (memory depends on secrets)
    secrets_key_path: Path = Field(
        default=Path(".ciris_keys"),
        description="Directory containing encryption keys"
    )
    secrets_db_path: Path = Field(
        description="Path to secrets database"
    )

    # Memory service config
    memory_db_path: Path = Field(
        description="Path to main memory database"
    )

    @classmethod
    def from_essential_config(cls, essential_config: "EssentialConfig") -> "MemoryConfig":
        """Create from EssentialConfig using helper functions.

        This maintains backward compatibility with existing path resolution.
        """
        from ciris_engine.logic.config import get_secrets_db_full_path
        from ciris_engine.logic.persistence import get_sqlite_db_full_path

        return cls(
            secrets_key_path=essential_config.security.secrets_key_path,
            secrets_db_path=get_secrets_db_full_path(essential_config),
            memory_db_path=get_sqlite_db_full_path(essential_config),
        )
```

### LLMConfig

```python
"""
File: ciris_engine/schemas/config/llm_config.py
Purpose: LLM service configuration
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class InstructorMode(str, Enum):
    """Instructor library modes."""
    JSON = "JSON"
    MD_JSON = "MD_JSON"
    TOOLS = "TOOLS"


class LLMProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""

    api_key: str = Field(
        description="API key for LLM provider"
    )
    base_url: str = Field(
        default="https://api.openai.com/v1",
        description="API base URL"
    )
    model_name: str = Field(
        default="gpt-4o-mini",
        description="Model identifier"
    )
    instructor_mode: InstructorMode = Field(
        default=InstructorMode.JSON,
        description="Instructor mode for structured output"
    )
    timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Request timeout"
    )
    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts"
    )


class LLMConfig(BaseModel):
    """Complete LLM service configuration."""

    primary: Optional[LLMProviderConfig] = Field(
        default=None,
        description="Primary LLM provider (required unless mock mode)"
    )
    secondary: Optional[LLMProviderConfig] = Field(
        default=None,
        description="Secondary LLM provider for fallback"
    )
    skip_initialization: bool = Field(
        default=False,
        description="Skip LLM init (set by mock module detection)"
    )

    @classmethod
    def from_env_and_essential(
        cls,
        essential_config: "EssentialConfig",
        skip_llm_init: bool = False
    ) -> "LLMConfig":
        """Load from environment and essential config.

        Environment Variables:
            OPENAI_API_KEY: Primary LLM API key
            INSTRUCTOR_MODE: Instructor mode (JSON|MD_JSON|TOOLS)
            CIRIS_OPENAI_API_KEY_2: Secondary LLM key (optional)
            CIRIS_OPENAI_API_BASE_2: Secondary LLM base URL (optional)
            CIRIS_OPENAI_MODEL_NAME_2: Secondary LLM model (optional)
        """
        import os

        if skip_llm_init:
            return cls(skip_initialization=True)

        # Primary LLM
        primary_key = os.getenv("OPENAI_API_KEY", "")
        primary_config = None
        if primary_key:
            primary_config = LLMProviderConfig(
                api_key=primary_key,
                base_url=essential_config.services.llm_endpoint,
                model_name=essential_config.services.llm_model,
                instructor_mode=InstructorMode(os.getenv("INSTRUCTOR_MODE", "JSON")),
                timeout_seconds=essential_config.services.llm_timeout,
                max_retries=essential_config.services.llm_max_retries,
            )

        # Secondary LLM (optional)
        secondary_key = os.getenv("CIRIS_OPENAI_API_KEY_2", "")
        secondary_config = None
        if secondary_key:
            secondary_config = LLMProviderConfig(
                api_key=secondary_key,
                base_url=os.getenv(
                    "CIRIS_OPENAI_API_BASE_2",
                    essential_config.services.llm_endpoint
                ),
                model_name=os.getenv(
                    "CIRIS_OPENAI_MODEL_NAME_2",
                    essential_config.services.llm_model
                ),
                instructor_mode=InstructorMode(os.getenv("INSTRUCTOR_MODE", "JSON")),
                timeout_seconds=essential_config.services.llm_timeout,
                max_retries=essential_config.services.llm_max_retries,
            )

        return cls(
            primary=primary_config,
            secondary=secondary_config,
            skip_initialization=False,
        )
```

### ObservabilityConfig

```python
"""
File: ciris_engine/schemas/config/observability_config.py
Purpose: Observability service configuration (telemetry, audit, TSDB)
"""

from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field


class TelemetryConfig(BaseModel):
    """Configuration for GraphTelemetryService.

    Note: GraphTelemetryService doesn't need much config - it uses MemoryBus
    and TimeService. Config here is minimal.
    """
    pass  # Currently no config needed - service uses injected dependencies


class AuditConfig(BaseModel):
    """Configuration for GraphAuditService."""

    export_path: Path = Field(
        default=Path("audit_logs.jsonl"),
        description="Path for audit log export"
    )
    export_format: Literal["jsonl", "json"] = Field(
        default="jsonl",
        description="Export file format"
    )
    enable_hash_chain: bool = Field(
        default=True,
        description="Enable cryptographic hash chain"
    )
    db_path: Path = Field(
        description="Audit database path"
    )
    key_path: Path = Field(
        description="Audit signing key directory"
    )
    retention_days: int = Field(
        default=90,
        ge=1,
        description="Audit log retention period"
    )

    @classmethod
    def from_essential_config(cls, essential_config: "EssentialConfig") -> "AuditConfig":
        """Create from EssentialConfig."""
        from ciris_engine.logic.config import get_audit_db_full_path

        return cls(
            export_path=Path("audit_logs.jsonl"),
            export_format="jsonl",
            enable_hash_chain=True,
            db_path=get_audit_db_full_path(essential_config),
            key_path=essential_config.security.audit_key_path,
            retention_days=essential_config.security.audit_retention_days,
        )


class TSDBConfig(BaseModel):
    """Configuration for TSDBConsolidationService."""

    consolidation_interval_hours: int = Field(
        default=6,
        frozen=True,  # Fixed for calendar alignment
        description="Consolidation interval (fixed at 6 for calendar alignment)"
    )
    raw_retention_hours: int = Field(
        default=24,
        ge=1,
        description="Raw data retention before consolidation"
    )
    db_path: Path = Field(
        description="Main database path (TSDB uses main DB)"
    )

    @classmethod
    def from_essential_config(cls, essential_config: "EssentialConfig") -> "TSDBConfig":
        """Create from EssentialConfig."""
        from ciris_engine.logic.persistence import get_sqlite_db_full_path

        return cls(
            raw_retention_hours=essential_config.graph.tsdb_raw_retention_hours,
            db_path=get_sqlite_db_full_path(essential_config),
        )


class ObservabilityConfig(BaseModel):
    """Complete observability service configuration."""

    telemetry: TelemetryConfig
    audit: AuditConfig
    tsdb: TSDBConfig

    @classmethod
    def from_essential_config(cls, essential_config: "EssentialConfig") -> "ObservabilityConfig":
        """Create from EssentialConfig."""
        return cls(
            telemetry=TelemetryConfig(),
            audit=AuditConfig.from_essential_config(essential_config),
            tsdb=TSDBConfig.from_essential_config(essential_config),
        )
```

### GovernanceConfig

```python
"""
File: ciris_engine/schemas/config/governance_config.py
Purpose: Governance service configuration
"""

from pathlib import Path
from pydantic import BaseModel, Field


class AdaptiveFilterConfig(BaseModel):
    """Configuration for AdaptiveFilterService.

    Note: Currently uses injected dependencies (memory, time, llm, config).
    No additional configuration needed beyond constructor injection.
    """
    pass


class SelfObservationConfig(BaseModel):
    """Configuration for SelfObservationService."""

    variance_threshold: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
        description="Maximum variance from baseline (20% default)"
    )
    observation_interval_hours: int = Field(
        default=6,
        ge=1,
        description="Observation frequency in hours"
    )


class VisibilityConfig(BaseModel):
    """Configuration for VisibilityService."""

    db_path: Path = Field(
        description="Main database path for visibility storage"
    )

    @classmethod
    def from_essential_config(cls, essential_config: "EssentialConfig") -> "VisibilityConfig":
        """Create from EssentialConfig."""
        from ciris_engine.logic.persistence import get_sqlite_db_full_path
        return cls(db_path=get_sqlite_db_full_path(essential_config))


class ConsentConfig(BaseModel):
    """Configuration for ConsentService."""

    db_path: Path = Field(
        description="Main database path for consent storage"
    )

    @classmethod
    def from_essential_config(cls, essential_config: "EssentialConfig") -> "ConsentConfig":
        """Create from EssentialConfig."""
        from ciris_engine.logic.persistence import get_sqlite_db_full_path
        return cls(db_path=get_sqlite_db_full_path(essential_config))


class GovernanceConfig(BaseModel):
    """Complete governance service configuration."""

    adaptive_filter: AdaptiveFilterConfig
    self_observation: SelfObservationConfig
    visibility: VisibilityConfig
    consent: ConsentConfig

    @classmethod
    def from_essential_config(cls, essential_config: "EssentialConfig") -> "GovernanceConfig":
        """Create from EssentialConfig."""
        return cls(
            adaptive_filter=AdaptiveFilterConfig(),
            self_observation=SelfObservationConfig(),
            visibility=VisibilityConfig.from_essential_config(essential_config),
            consent=ConsentConfig.from_essential_config(essential_config),
        )
```

### ConfigurationRoot

```python
"""
File: ciris_engine/schemas/config/initialization_config.py
Purpose: Root configuration for service initialization
"""

from pydantic import BaseModel
from .infrastructure_config import InfrastructureConfig
from .memory_config import MemoryConfig
from .llm_config import LLMConfig
from .observability_config import ObservabilityConfig
from .governance_config import GovernanceConfig


class InitializationConfig(BaseModel):
    """Root configuration for all service initialization.

    This replaces the untyped `config: Any` parameters throughout
    ServiceInitializer.
    """

    infrastructure: InfrastructureConfig
    memory: MemoryConfig
    llm: LLMConfig
    observability: ObservabilityConfig
    governance: GovernanceConfig

    @classmethod
    def from_essential_config(
        cls,
        essential_config: "EssentialConfig",
        skip_llm_init: bool = False
    ) -> "InitializationConfig":
        """Create complete initialization config from EssentialConfig.

        This is the main factory method that bridges from the existing
        EssentialConfig to the new typed initialization config.

        Args:
            essential_config: Existing bootstrap configuration
            skip_llm_init: Set True when mock LLM module detected

        Returns:
            Complete typed configuration for initialization
        """
        return cls(
            infrastructure=InfrastructureConfig.from_env(),
            memory=MemoryConfig.from_essential_config(essential_config),
            llm=LLMConfig.from_env_and_essential(essential_config, skip_llm_init),
            observability=ObservabilityConfig.from_essential_config(essential_config),
            governance=GovernanceConfig.from_essential_config(essential_config),
        )
```

---

## Component Architecture

### Overview

Five focused components replace the monolithic ServiceInitializer:

1. **ConfigurationAdapter** - Environment → Typed Config (150-200 lines)
2. **InfrastructureBootstrapper** - Core services bootstrap (200-250 lines)
3. **ObservabilityComposer** - Telemetry/Audit/TSDB (150-200 lines)
4. **GovernanceComposer** - WiseAuthority/Filters/Observation (150-200 lines)
5. **ServiceOrchestrator** - Coordinates composers (200-250 lines)

ServiceInitializer remains but delegates to these components (100-150 lines).

### ConfigurationAdapter

**Responsibility**: Convert environment variables and EssentialConfig to typed InitializationConfig

**File**: `ciris_engine/logic/initialization/configuration_adapter.py`

**Interface**:
```python
class ConfigurationAdapter:
    """Adapts environment and EssentialConfig to typed InitializationConfig.

    SINGLE RESPONSIBILITY: Environment variable access and config loading.
    All os.getenv() calls happen here and ONLY here.
    """

    def __init__(self, essential_config: EssentialConfig) -> None:
        """Initialize with essential bootstrap config.

        Args:
            essential_config: Bootstrap configuration from main.py
        """
        self.essential_config = essential_config
        self._cached_config: Optional[InitializationConfig] = None

    def load_config(self, skip_llm_init: bool = False) -> InitializationConfig:
        """Load complete typed configuration.

        This is the ONLY public method - it coordinates all config loading.

        Args:
            skip_llm_init: True if mock LLM module detected

        Returns:
            Complete typed configuration ready for initialization
        """
        if self._cached_config is None:
            self._cached_config = InitializationConfig.from_essential_config(
                self.essential_config,
                skip_llm_init=skip_llm_init
            )
        return self._cached_config

    def reload_config(self, skip_llm_init: bool = False) -> InitializationConfig:
        """Force reload of configuration (clears cache).

        Use when environment variables change at runtime.
        """
        self._cached_config = None
        return self.load_config(skip_llm_init)
```

**Why This Design**:
- Single responsibility: Config loading only
- No service creation - just config
- All env var access centralized
- Cacheable - config doesn't change after load
- Testable - mock EssentialConfig, verify typed output

### InfrastructureBootstrapper

**Responsibility**: Initialize core infrastructure services (Time, Shutdown, Init, ResourceMonitor, Secrets, Memory, Config, Auth, WiseAuthority)

**File**: `ciris_engine/logic/initialization/infrastructure_bootstrapper.py`

**Interface**:
```python
from ciris_engine.protocols.services import (
    TimeServiceProtocol,
    SecretsServiceProtocol,
    MemoryServiceProtocol,
    ConfigServiceProtocol,
    AuthenticationServiceProtocol,
)
from ciris_engine.logic.services.governance.wise_authority import WiseAuthorityService
from ciris_engine.schemas.config.infrastructure_config import InfrastructureConfig
from ciris_engine.schemas.config.memory_config import MemoryConfig


class InfrastructureBundle:
    """Protocol-typed bundle of infrastructure services."""
    time_service: TimeServiceProtocol
    shutdown_service: Any  # ShutdownServiceProtocol
    initialization_service: Any  # InitializationServiceProtocol
    resource_monitor_service: Any  # ResourceMonitorServiceProtocol
    secrets_service: SecretsServiceProtocol
    memory_service: MemoryServiceProtocol
    config_service: ConfigServiceProtocol
    secrets_tool_service: Any  # SecretsToolServiceProtocol
    auth_service: AuthenticationServiceProtocol
    wise_authority_service: WiseAuthorityService


class InfrastructureBootstrapper:
    """Bootstraps core infrastructure services.

    SINGLE RESPONSIBILITY: Create and start infrastructure services in dependency order.
    No environment access, no config loading - only service construction.
    """

    def __init__(
        self,
        infrastructure_config: InfrastructureConfig,
        memory_config: MemoryConfig,
    ) -> None:
        """Initialize with typed configuration.

        Args:
            infrastructure_config: Infrastructure service settings
            memory_config: Memory and secrets configuration
        """
        self.infrastructure_config = infrastructure_config
        self.memory_config = memory_config

    async def bootstrap(self) -> InfrastructureBundle:
        """Bootstrap all infrastructure services.

        Initialization order (critical dependencies):
        1. TimeService (no dependencies)
        2. ShutdownService (no dependencies)
        3. InitializationService (depends on TimeService)
        4. ResourceMonitorService (depends on TimeService)
        5. SecretsService (depends on TimeService)
        6. MemoryService (depends on TimeService, SecretsService)
        7. ConfigService (depends on MemoryService, TimeService)
        8. SecretsToolService (depends on SecretsService, TimeService)
        9. AuthenticationService (depends on TimeService)
        10. WiseAuthorityService (depends on TimeService, AuthService)

        Returns:
            Bundle of all infrastructure services (protocol-typed)

        Raises:
            RuntimeError: If any service fails to initialize
        """
        # Implementation creates services in order
        pass

    async def _create_time_service(self) -> TimeServiceProtocol:
        """Create and start TimeService."""
        pass

    async def _create_resource_monitor(
        self,
        time_service: TimeServiceProtocol
    ) -> Any:  # ResourceMonitorServiceProtocol
        """Create and start ResourceMonitorService with configured credit provider."""
        pass

    async def _create_secrets_service(
        self,
        time_service: TimeServiceProtocol
    ) -> SecretsServiceProtocol:
        """Create and start SecretsService.

        Handles master key loading/generation from configured key path.
        """
        pass

    # ... more private methods for each service
```

**Why This Design**:
- Single responsibility: Infrastructure service creation
- Accepts typed config, returns typed bundles
- Dependency order explicit and documented
- No environment access
- Each service creation in separate method (unit testable)

### ObservabilityComposer

**Responsibility**: Compose observability stack (Telemetry, Audit, Incident, TSDB, Maintenance)

**File**: `ciris_engine/logic/initialization/observability_composer.py`

**Interface**:
```python
from ciris_engine.protocols.services import TelemetryServiceProtocol
from ciris_engine.logic.services.graph.audit_service import GraphAuditService
from ciris_engine.schemas.config.observability_config import ObservabilityConfig


class ObservabilityBundle:
    """Protocol-typed bundle of observability services."""
    telemetry_service: TelemetryServiceProtocol
    audit_service: GraphAuditService
    incident_service: Any  # IncidentManagementServiceProtocol
    tsdb_service: Any  # TSDBConsolidationServiceProtocol
    maintenance_service: Any  # DatabaseMaintenanceServiceProtocol


class ObservabilityComposer:
    """Composes observability services.

    SINGLE RESPONSIBILITY: Create observability stack with proper wiring.
    Depends on infrastructure being initialized first.
    """

    def __init__(
        self,
        observability_config: ObservabilityConfig,
        infrastructure_bundle: InfrastructureBundle,
        service_registry: ServiceRegistry,
        bus_manager: BusManager,
    ) -> None:
        """Initialize with dependencies.

        Args:
            observability_config: Observability configuration
            infrastructure_bundle: Already-initialized infrastructure services
            service_registry: Service registry for protocol-based wiring
            bus_manager: Bus manager for memory/communication buses
        """
        self.config = observability_config
        self.infra = infrastructure_bundle
        self.registry = service_registry
        self.buses = bus_manager

    async def compose(self) -> ObservabilityBundle:
        """Compose complete observability stack.

        Initialization order:
        1. GraphTelemetryService (needs memory_bus, time)
        2. GraphAuditService (needs memory_bus, time)
        3. IncidentManagementService (needs memory_bus, time)
        4. TSDBConsolidationService (needs memory_bus, time)
        5. DatabaseMaintenanceService (needs time, config)

        Returns:
            Bundle of observability services
        """
        pass

    async def _attach_registry_if_needed(self, service: Any) -> None:
        """Attach registry to services that implement RegistryAwareServiceProtocol."""
        from ciris_engine.protocols.infrastructure import RegistryAwareServiceProtocol
        if isinstance(service, RegistryAwareServiceProtocol):
            await service.attach_registry(self.registry)
```

**Why This Design**:
- Single responsibility: Observability composition
- Depends on infrastructure bundle (enforces initialization order)
- Uses RegistryAwareServiceProtocol for clean registry injection
- Returns typed bundle

### GovernanceComposer

**Responsibility**: Compose governance stack (AdaptiveFilter, SelfObservation, Visibility, Consent, RuntimeControl)

**File**: `ciris_engine/logic/initialization/governance_composer.py`

**Interface**:
```python
from ciris_engine.schemas.config.governance_config import GovernanceConfig


class GovernanceBundle:
    """Protocol-typed bundle of governance services."""
    adaptive_filter: Any  # AdaptiveFilterServiceProtocol
    self_observation: Any  # SelfObservationServiceProtocol
    visibility: Any  # VisibilityServiceProtocol
    consent: Any  # ConsentServiceProtocol
    runtime_control: Any  # RuntimeControlServiceProtocol
    task_scheduler: Any  # TaskSchedulerServiceProtocol


class GovernanceComposer:
    """Composes governance services.

    SINGLE RESPONSIBILITY: Create governance stack with proper dependencies.
    """

    def __init__(
        self,
        governance_config: GovernanceConfig,
        infrastructure_bundle: InfrastructureBundle,
        llm_service: Optional[LLMServiceProtocol],
        service_registry: ServiceRegistry,
        bus_manager: BusManager,
    ) -> None:
        """Initialize with dependencies.

        Args:
            governance_config: Governance configuration
            infrastructure_bundle: Infrastructure services
            llm_service: LLM service (optional - may be None in mock mode)
            service_registry: Service registry
            bus_manager: Bus manager
        """
        self.config = governance_config
        self.infra = infrastructure_bundle
        self.llm = llm_service
        self.registry = service_registry
        self.buses = bus_manager

    async def compose(self) -> GovernanceBundle:
        """Compose complete governance stack.

        Initialization order:
        1. AdaptiveFilterService (needs memory, time, llm, config)
        2. TaskSchedulerService (needs db_path, time)
        3. SelfObservationService (needs time, memory_bus)
        4. VisibilityService (needs bus_manager, time, db_path)
        5. ConsentService (needs time, memory_bus, db_path)
        6. RuntimeControlService (needs config_manager, time)

        Returns:
            Bundle of governance services
        """
        pass
```

**Why This Design**:
- Single responsibility: Governance composition
- Handles optional LLM gracefully (mock mode support)
- Clear dependency injection
- Returns typed bundle

### ServiceOrchestrator

**Responsibility**: Orchestrate all composers and coordinate full initialization

**File**: `ciris_engine/logic/initialization/service_orchestrator.py`

**Interface**:
```python
from dataclasses import dataclass
from ciris_engine.schemas.config.initialization_config import InitializationConfig


@dataclass
class InitializedServices:
    """Complete set of initialized services."""
    infrastructure: InfrastructureBundle
    observability: ObservabilityBundle
    governance: GovernanceBundle
    llm_service: Optional[LLMServiceProtocol]
    service_registry: ServiceRegistry
    bus_manager: BusManager


class ServiceOrchestrator:
    """Orchestrates service initialization across all composers.

    SINGLE RESPONSIBILITY: Coordinate initialization phases and dependency flow.
    This is the main entry point for typed initialization.
    """

    def __init__(
        self,
        config: InitializationConfig,
        essential_config: EssentialConfig,
    ) -> None:
        """Initialize orchestrator.

        Args:
            config: Complete typed initialization configuration
            essential_config: Original essential config (needed for some legacy paths)
        """
        self.config = config
        self.essential_config = essential_config
        self._metrics_start_time: Optional[float] = None
        self._metrics_end_time: Optional[float] = None
        self._services_started: int = 0
        self._errors: int = 0

    async def initialize_all(self) -> InitializedServices:
        """Initialize all services using typed configuration.

        Initialization flow:
        1. Bootstrap infrastructure (InfrastructureBootstrapper)
        2. Create ServiceRegistry
        3. Register infrastructure services
        4. Create BusManager
        5. Initialize LLM services (if not skipped)
        6. Compose observability (ObservabilityComposer)
        7. Compose governance (GovernanceComposer)
        8. Wire all services into registry
        9. Migrate essential config to graph

        Returns:
            Complete set of initialized services

        Raises:
            RuntimeError: If any initialization phase fails
        """
        import time
        self._metrics_start_time = time.time()

        try:
            # Phase 1: Infrastructure
            infra_bootstrapper = InfrastructureBootstrapper(
                infrastructure_config=self.config.infrastructure,
                memory_config=self.config.memory,
            )
            infrastructure = await infra_bootstrapper.bootstrap()
            self._services_started += 10  # 10 infrastructure services

            # Phase 2: Registry and buses
            service_registry = self._create_service_registry()
            self._register_infrastructure_services(infrastructure, service_registry)
            bus_manager = self._create_bus_manager(
                service_registry,
                infrastructure.time_service,
                telemetry_service=None,  # Set after observability composition
                audit_service=None,  # Set after observability composition
            )

            # Phase 3: LLM (optional)
            llm_service = await self._initialize_llm_services(
                infrastructure.time_service,
                service_registry
            )

            # Phase 4: Observability
            observability_composer = ObservabilityComposer(
                observability_config=self.config.observability,
                infrastructure_bundle=infrastructure,
                service_registry=service_registry,
                bus_manager=bus_manager,
            )
            observability = await observability_composer.compose()
            self._services_started += 5  # 5 observability services

            # Update bus_manager with telemetry/audit
            bus_manager.telemetry_service = observability.telemetry_service
            bus_manager.audit_service = observability.audit_service
            bus_manager.llm.telemetry_service = observability.telemetry_service

            # Phase 5: Governance
            governance_composer = GovernanceComposer(
                governance_config=self.config.governance,
                infrastructure_bundle=infrastructure,
                llm_service=llm_service,
                service_registry=service_registry,
                bus_manager=bus_manager,
            )
            governance = await governance_composer.compose()
            self._services_started += 6  # 6 governance services

            # Phase 6: Final wiring
            self._register_all_services(
                infrastructure, observability, governance, service_registry
            )

            # Phase 7: Config migration
            await self._migrate_config_to_graph(infrastructure.config_service)

            self._metrics_end_time = time.time()

            return InitializedServices(
                infrastructure=infrastructure,
                observability=observability,
                governance=governance,
                llm_service=llm_service,
                service_registry=service_registry,
                bus_manager=bus_manager,
            )

        except Exception as e:
            self._errors += 1
            raise RuntimeError(f"Service initialization failed: {e}") from e

    async def _initialize_llm_services(
        self,
        time_service: TimeServiceProtocol,
        service_registry: ServiceRegistry,
    ) -> Optional[LLMServiceProtocol]:
        """Initialize LLM services based on configuration.

        Returns None if skip_initialization=True (mock mode).
        """
        if self.config.llm.skip_initialization:
            return None

        if not self.config.llm.primary:
            return None

        # Create primary LLM
        from ciris_engine.logic.services.runtime.llm_service import (
            OpenAICompatibleClient,
            OpenAIConfig,
        )

        llm_config = OpenAIConfig(
            base_url=self.config.llm.primary.base_url,
            model_name=self.config.llm.primary.model_name,
            api_key=self.config.llm.primary.api_key,
            instructor_mode=self.config.llm.primary.instructor_mode.value,
            timeout_seconds=self.config.llm.primary.timeout_seconds,
            max_retries=self.config.llm.primary.max_retries,
        )

        primary_llm = OpenAICompatibleClient(
            config=llm_config,
            telemetry_service=None,  # Set after telemetry initialization
            time_service=time_service,
        )
        await primary_llm.start()
        self._services_started += 1

        # Register primary
        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=primary_llm,
            priority=Priority.HIGH,
            capabilities=[LLMCapabilities.CALL_LLM_STRUCTURED],
            metadata={"provider": "openai", "model": llm_config.model_name},
        )

        # Create secondary if configured
        if self.config.llm.secondary:
            # ... similar to primary ...
            self._services_started += 1

        return primary_llm

    def get_metrics(self) -> Dict[str, float]:
        """Get initialization metrics compatible with v1.4.3 format."""
        startup_time_ms = 0.0
        if self._metrics_start_time and self._metrics_end_time:
            startup_time_ms = (self._metrics_end_time - self._metrics_start_time) * 1000.0

        return {
            "initializer_services_started": float(self._services_started),
            "initializer_startup_time_ms": startup_time_ms,
            "initializer_errors": float(self._errors),
            "initializer_dependencies_resolved": float(self._services_started),  # All started = resolved
        }
```

**Why This Design**:
- Single responsibility: Orchestration only
- Uses composers for actual work
- Clear phase-by-phase initialization
- Maintains metrics for compatibility
- Returns complete typed bundle

### Updated ServiceInitializer (Delegating Version)

**File**: `ciris_engine/logic/runtime/service_initializer.py` (modified)

**Interface**:
```python
class ServiceInitializer:
    """Manages initialization of all core services.

    This class now DELEGATES to the new typed initialization system.
    It maintains the existing public interface for backward compatibility
    while using the new architecture internally.
    """

    def __init__(self, essential_config: Optional[EssentialConfig] = None) -> None:
        self.essential_config = essential_config or EssentialConfig()

        # Feature flag for gradual cutover
        self._use_new_initialization = os.getenv("CIRIS_USE_NEW_INIT", "false").lower() == "true"

        # New architecture components (used when feature flag enabled)
        self._config_adapter: Optional[ConfigurationAdapter] = None
        self._orchestrator: Optional[ServiceOrchestrator] = None
        self._initialized_services: Optional[InitializedServices] = None

        # Existing attributes (maintained for compatibility)
        self.service_registry: Optional[ServiceRegistry] = None
        self.bus_manager: Optional[BusManager] = None
        # ... all existing service attributes ...

    async def initialize_infrastructure_services(self) -> None:
        """Initialize infrastructure services.

        DELEGATING: Routes to new or old implementation based on feature flag.
        """
        if self._use_new_initialization:
            await self._initialize_infrastructure_new()
        else:
            await self._initialize_infrastructure_old()

    async def _initialize_infrastructure_new(self) -> None:
        """New implementation using ConfigurationAdapter and orchestrator."""
        # Create config adapter
        self._config_adapter = ConfigurationAdapter(self.essential_config)

        # Check for mock modules
        skip_llm_init = self._check_for_mock_modules()

        # Load typed config
        init_config = self._config_adapter.load_config(skip_llm_init=skip_llm_init)

        # Create orchestrator
        self._orchestrator = ServiceOrchestrator(
            config=init_config,
            essential_config=self.essential_config,
        )

        # Initialize all services
        self._initialized_services = await self._orchestrator.initialize_all()

        # Wire services to compatibility attributes
        self._wire_services_to_attributes()

    async def _initialize_infrastructure_old(self) -> None:
        """Old implementation - preserved for gradual cutover."""
        # Existing code from lines 94-181
        pass

    def _wire_services_to_attributes(self) -> None:
        """Wire new architecture services to existing attribute names.

        This maintains backward compatibility for code that accesses
        services via self.time_service, self.memory_service, etc.
        """
        if not self._initialized_services:
            return

        infra = self._initialized_services.infrastructure
        obs = self._initialized_services.observability
        gov = self._initialized_services.governance

        # Infrastructure
        self.time_service = infra.time_service
        self.shutdown_service = infra.shutdown_service
        self.initialization_service = infra.initialization_service
        self.resource_monitor_service = infra.resource_monitor_service
        self.secrets_service = infra.secrets_service
        self.memory_service = infra.memory_service
        self.config_service = infra.config_service
        self.secrets_tool_service = infra.secrets_tool_service
        self.auth_service = infra.auth_service
        self.wa_auth_system = infra.wise_authority_service

        # Observability
        self.telemetry_service = obs.telemetry_service
        self.audit_service = obs.audit_service
        self.incident_management_service = obs.incident_service
        self.tsdb_consolidation_service = obs.tsdb_service
        self.maintenance_service = obs.maintenance_service

        # Governance
        self.adaptive_filter_service = gov.adaptive_filter
        self.self_observation_service = gov.self_observation
        self.visibility_service = gov.visibility
        self.consent_service = gov.consent
        self.runtime_control_service = gov.runtime_control
        self.task_scheduler_service = gov.task_scheduler

        # LLM
        self.llm_service = self._initialized_services.llm_service

        # Registry and buses
        self.service_registry = self._initialized_services.service_registry
        self.bus_manager = self._initialized_services.bus_manager

    # All other methods delegate or remain unchanged for compatibility
    async def initialize_memory_service(self, config: Any) -> None:
        """DEPRECATED: Use initialize_infrastructure_services instead."""
        if self._use_new_initialization:
            # Already initialized in infrastructure phase
            pass
        else:
            # Old code
            pass

    def get_metrics(self) -> Dict[str, float]:
        """Get initializer metrics."""
        if self._use_new_initialization and self._orchestrator:
            return self._orchestrator.get_metrics()
        else:
            # Old metrics code
            pass
```

**Why This Design**:
- Maintains backward compatibility
- Feature flag enables gradual cutover
- Delegates to new architecture when enabled
- Wiring layer preserves existing attribute access
- Can run old and new paths in parallel during testing

---

## Migration Strategy

### Phase-by-Phase Approach

Migration happens in 10 phases over 3-4 weeks:

#### Phase 1: Create Config Models (Week 1, Days 1-2)

**Goal**: Create all typed config models with validation

**Tasks**:
1. Create directory structure: `ciris_engine/schemas/config/`
2. Implement `infrastructure_config.py` (BillingConfig, ResourceMonitorConfig, etc.)
3. Implement `memory_config.py`
4. Implement `llm_config.py`
5. Implement `observability_config.py`
6. Implement `governance_config.py`
7. Implement `initialization_config.py` (root)

**Validation Criteria**:
- [ ] All config models have Pydantic validation
- [ ] All config models have `.from_env()` or `.from_essential_config()` factory methods
- [ ] All environment variable mappings documented
- [ ] Config models import cleanly
- [ ] No circular dependencies

**Tests**:
```python
# tests/schemas/config/test_infrastructure_config.py
def test_billing_config_from_env():
    """Test BillingConfig loads from environment."""
    os.environ["CIRIS_BILLING_ENABLED"] = "true"
    os.environ["CIRIS_BILLING_API_KEY"] = "test-key"

    config = BillingConfig.from_env()

    assert config.enabled is True
    assert config.api_key == "test-key"
    assert config.base_url == "https://billing.ciris.ai"  # default

def test_billing_config_requires_key_when_enabled():
    """Test validation fails if enabled but no key."""
    with pytest.raises(ValueError, match="api_key is required"):
        BillingConfig(enabled=True, api_key=None)

# ... similar tests for all config models
```

#### Phase 2: Create ConfigurationAdapter (Week 1, Day 3)

**Goal**: Centralize all environment variable access

**Tasks**:
1. Create `ciris_engine/logic/initialization/configuration_adapter.py`
2. Implement `ConfigurationAdapter` class
3. Move all `os.getenv()` logic from ServiceInitializer to adapter
4. Add caching for loaded config

**Validation Criteria**:
- [ ] ConfigurationAdapter has single public method: `load_config()`
- [ ] All env var access delegated to config models
- [ ] Config caching works correctly
- [ ] No direct env var access in adapter (delegates to config models)

**Tests**:
```python
# tests/logic/initialization/test_configuration_adapter.py
def test_load_config_creates_complete_config(mock_essential_config):
    """Test adapter creates complete InitializationConfig."""
    adapter = ConfigurationAdapter(mock_essential_config)

    config = adapter.load_config()

    assert isinstance(config, InitializationConfig)
    assert isinstance(config.infrastructure, InfrastructureConfig)
    assert isinstance(config.memory, MemoryConfig)
    assert isinstance(config.llm, LLMConfig)
    assert isinstance(config.observability, ObservabilityConfig)
    assert isinstance(config.governance, GovernanceConfig)

def test_load_config_caches_result(mock_essential_config):
    """Test config is cached after first load."""
    adapter = ConfigurationAdapter(mock_essential_config)

    config1 = adapter.load_config()
    config2 = adapter.load_config()

    assert config1 is config2  # Same object
```

#### Phase 3: Create InfrastructureBootstrapper (Week 1, Days 4-5)

**Goal**: Extract infrastructure initialization to separate component

**Tasks**:
1. Create `ciris_engine/logic/initialization/infrastructure_bootstrapper.py`
2. Define `InfrastructureBundle` dataclass/model
3. Implement `InfrastructureBootstrapper.bootstrap()` method
4. Extract service creation logic from ServiceInitializer lines 94-411
5. Create separate method for each service

**Validation Criteria**:
- [ ] All infrastructure services created in correct dependency order
- [ ] No environment variable access (uses typed config)
- [ ] Returns protocol-typed bundle
- [ ] Each service creation in separate method

**Tests**:
```python
# tests/logic/initialization/test_infrastructure_bootstrapper.py
@pytest.mark.asyncio
async def test_bootstrap_creates_all_services(mock_infra_config, mock_memory_config):
    """Test bootstrap creates complete infrastructure bundle."""
    bootstrapper = InfrastructureBootstrapper(mock_infra_config, mock_memory_config)

    bundle = await bootstrapper.bootstrap()

    assert bundle.time_service is not None
    assert bundle.shutdown_service is not None
    assert bundle.initialization_service is not None
    assert bundle.resource_monitor_service is not None
    assert bundle.secrets_service is not None
    assert bundle.memory_service is not None
    assert bundle.config_service is not None
    assert bundle.auth_service is not None
    assert bundle.wise_authority_service is not None

@pytest.mark.asyncio
async def test_bootstrap_initializes_in_dependency_order(mock_configs):
    """Test services initialized in correct dependency order."""
    bootstrapper = InfrastructureBootstrapper(...)

    call_order = []
    with patch.object(bootstrapper, '_create_time_service', side_effect=lambda: call_order.append('time')):
        with patch.object(bootstrapper, '_create_secrets_service', side_effect=lambda: call_order.append('secrets')):
            await bootstrapper.bootstrap()

    assert call_order.index('time') < call_order.index('secrets')
```

#### Phase 4: Create ObservabilityComposer (Week 2, Days 1-2)

**Goal**: Extract observability service composition

**Tasks**:
1. Create `ciris_engine/logic/initialization/observability_composer.py`
2. Define `ObservabilityBundle`
3. Implement `ObservabilityComposer.compose()` method
4. Extract telemetry/audit/TSDB/maintenance initialization from ServiceInitializer

**Validation Criteria**:
- [ ] Composer depends on InfrastructureBundle (enforces init order)
- [ ] Uses RegistryAwareServiceProtocol for registry attachment
- [ ] Returns typed bundle
- [ ] All observability services started

**Tests**: Similar structure to InfrastructureBootstrapper tests

#### Phase 5: Create GovernanceComposer (Week 2, Days 3-4)

**Goal**: Extract governance service composition

**Tasks**:
1. Create `ciris_engine/logic/initialization/governance_composer.py`
2. Define `GovernanceBundle`
3. Implement `GovernanceComposer.compose()` method
4. Extract filter/observation/visibility/consent/control initialization

**Validation Criteria**:
- [ ] Handles optional LLM service (mock mode support)
- [ ] Returns typed bundle
- [ ] All governance services started

**Tests**: Similar structure to other composers

#### Phase 6: Create ServiceOrchestrator (Week 2, Day 5)

**Goal**: Coordinate all composers

**Tasks**:
1. Create `ciris_engine/logic/initialization/service_orchestrator.py`
2. Define `InitializedServices` dataclass
3. Implement `ServiceOrchestrator.initialize_all()` method
4. Wire together: bootstrapper → registry → LLM → observability → governance
5. Implement metrics collection (compatible with v1.4.3)

**Validation Criteria**:
- [ ] Orchestrator coordinates all phases
- [ ] Metrics match existing format
- [ ] Service registry fully populated
- [ ] BusManager wired correctly

**Tests**:
```python
@pytest.mark.asyncio
async def test_initialize_all_creates_complete_system(mock_init_config, mock_essential):
    """Test orchestrator creates complete system."""
    orchestrator = ServiceOrchestrator(mock_init_config, mock_essential)

    services = await orchestrator.initialize_all()

    assert services.infrastructure is not None
    assert services.observability is not None
    assert services.governance is not None
    assert services.service_registry is not None
    assert services.bus_manager is not None

@pytest.mark.asyncio
async def test_metrics_compatible_with_v143(orchestrator):
    """Test metrics format matches v1.4.3."""
    await orchestrator.initialize_all()

    metrics = orchestrator.get_metrics()

    assert "initializer_services_started" in metrics
    assert "initializer_startup_time_ms" in metrics
    assert "initializer_errors" in metrics
    assert "initializer_dependencies_resolved" in metrics
```

#### Phase 7: Update ServiceInitializer (Week 3, Days 1-2)

**Goal**: Make ServiceInitializer delegate to new architecture

**Tasks**:
1. Add `_use_new_initialization` feature flag
2. Add new architecture attributes
3. Implement `_initialize_infrastructure_new()` delegate method
4. Implement `_wire_services_to_attributes()` compatibility method
5. Add delegation logic to all public methods

**Validation Criteria**:
- [ ] Feature flag controls which path is used
- [ ] New path creates orchestrator and delegates
- [ ] Compatibility wiring preserves existing attribute access
- [ ] All public methods work in both modes

**Tests**:
```python
@pytest.mark.asyncio
async def test_new_initialization_path_with_feature_flag(mock_essential):
    """Test new initialization path when feature flag enabled."""
    os.environ["CIRIS_USE_NEW_INIT"] = "true"

    initializer = ServiceInitializer(mock_essential)
    await initializer.initialize_infrastructure_services()

    # New architecture created
    assert initializer._orchestrator is not None
    assert initializer._initialized_services is not None

    # Compatibility attributes wired
    assert initializer.time_service is not None
    assert initializer.memory_service is not None

@pytest.mark.asyncio
async def test_old_initialization_path_without_flag(mock_essential):
    """Test old initialization still works when flag disabled."""
    os.environ["CIRIS_USE_NEW_INIT"] = "false"

    initializer = ServiceInitializer(mock_essential)
    await initializer.initialize_infrastructure_services()

    # Old path used
    assert initializer._orchestrator is None
```

#### Phase 8: Parallel Execution Testing (Week 3, Days 3-4)

**Goal**: Validate both paths produce identical results

**Tasks**:
1. Create comparison test harness
2. Run both initialization paths
3. Compare service attributes
4. Compare metrics
5. Compare registry contents

**Validation Criteria**:
- [ ] Both paths create same services
- [ ] Both paths populate registry identically
- [ ] Both paths produce compatible metrics
- [ ] No regressions in existing tests

**Tests**:
```python
@pytest.mark.asyncio
async def test_new_and_old_paths_create_identical_services(mock_essential):
    """Test both initialization paths produce same services."""
    # Initialize with old path
    os.environ["CIRIS_USE_NEW_INIT"] = "false"
    old_initializer = ServiceInitializer(mock_essential)
    await old_initializer.initialize_infrastructure_services()
    await old_initializer.initialize_memory_service(mock_essential)
    await old_initializer.initialize_security_services(mock_essential, mock_essential)

    # Initialize with new path
    os.environ["CIRIS_USE_NEW_INIT"] = "true"
    new_initializer = ServiceInitializer(mock_essential)
    await new_initializer.initialize_infrastructure_services()

    # Compare services
    assert type(old_initializer.time_service) == type(new_initializer.time_service)
    assert type(old_initializer.memory_service) == type(new_initializer.memory_service)
    # ... compare all services
```

#### Phase 9: Gradual Cutover (Week 3, Day 5)

**Goal**: Enable new path in staging, monitor, cutover production

**Tasks**:
1. Deploy with feature flag disabled to staging
2. Enable feature flag in staging
3. Monitor for 24 hours
4. Run full QA suite
5. Deploy to production with flag disabled
6. Enable feature flag in production
7. Monitor for 48 hours

**Validation Criteria**:
- [ ] No errors in staging logs
- [ ] Metrics match baseline
- [ ] All QA tests pass
- [ ] Production metrics stable
- [ ] No incidents reported

#### Phase 10: Cleanup and Documentation (Week 4)

**Goal**: Remove old code, update documentation

**Tasks**:
1. Remove old initialization methods from ServiceInitializer
2. Remove feature flag (new path becomes default)
3. Update CLAUDE.md with initialization patterns
4. Update architecture documentation
5. Add initialization flow diagrams
6. Document config model usage

**Validation Criteria**:
- [ ] No old code paths remain
- [ ] Feature flag removed
- [ ] CLAUDE.md updated
- [ ] Architecture docs updated
- [ ] Example code in docs

---

## Testing Strategy

### Unit Tests (Per Component)

**Config Models** (tests/schemas/config/):
- `test_infrastructure_config.py` - Test all infrastructure config models
- `test_memory_config.py` - Test memory config
- `test_llm_config.py` - Test LLM config with primary/secondary
- `test_observability_config.py` - Test observability config
- `test_governance_config.py` - Test governance config
- `test_initialization_config.py` - Test root config assembly

**ConfigurationAdapter** (tests/logic/initialization/):
- `test_configuration_adapter.py`
  - Test config loading
  - Test caching
  - Test reload
  - Test with different env var combinations

**InfrastructureBootstrapper**:
- `test_infrastructure_bootstrapper.py`
  - Test complete bootstrap
  - Test dependency order
  - Test individual service creation
  - Test error handling (service fails to start)
  - Test with different config variations (billing vs simple credit)

**ObservabilityComposer**:
- `test_observability_composer.py`
  - Test complete composition
  - Test registry attachment
  - Test with different configs

**GovernanceComposer**:
- `test_governance_composer.py`
  - Test complete composition
  - Test with optional LLM (mock mode)
  - Test with full LLM

**ServiceOrchestrator**:
- `test_service_orchestrator.py`
  - Test full initialization
  - Test metrics collection
  - Test phase-by-phase progress
  - Test error propagation

**ServiceInitializer (Updated)**:
- Update `test_service_initializer.py`
  - Test old path still works
  - Test new path works
  - Test feature flag switching
  - Test compatibility wiring

### Integration Tests

**Full Initialization Flow**:
```python
# tests/integration/test_initialization_flow.py

@pytest.mark.asyncio
async def test_complete_initialization_with_new_architecture():
    """Test complete system initialization using new architecture."""
    # Create essential config
    essential_config = EssentialConfig()
    essential_config.load_env_vars()

    # Initialize via new path
    os.environ["CIRIS_USE_NEW_INIT"] = "true"
    initializer = ServiceInitializer(essential_config)

    await initializer.initialize_infrastructure_services()
    # ... continue through all phases

    # Verify all services operational
    assert await initializer.verify_memory_service()
    assert await initializer.verify_security_services()
    assert initializer.verify_core_services()

@pytest.mark.asyncio
async def test_initialization_with_mock_llm():
    """Test initialization with mock LLM module detected."""
    # Setup mock module
    # ...

    os.environ["CIRIS_USE_NEW_INIT"] = "true"
    initializer = ServiceInitializer(essential_config)

    # Initialization should skip real LLM
    await initializer.initialize_all_services(...)

    assert initializer.llm_service is None or is_mock_llm(initializer.llm_service)

@pytest.mark.asyncio
async def test_parallel_old_and_new_initialization():
    """Test old and new paths produce identical results."""
    # Run both paths
    # Compare outputs
    # Assert equality
```

**Service Registry Population**:
```python
# tests/integration/test_service_registry_population.py

def test_registry_contains_all_expected_services():
    """Test registry populated with all expected services."""
    # Initialize system
    # ...

    registry = initializer.service_registry

    # Check infrastructure services
    assert registry.get_services_by_type(ServiceType.TIME) is not None
    assert registry.get_services_by_type(ServiceType.MEMORY) is not None
    assert registry.get_services_by_type(ServiceType.CONFIG) is not None

    # Check observability services
    assert registry.get_services_by_type(ServiceType.WISE_AUTHORITY) is not None

    # Check governance services
    # ...
```

### Existing Test Updates

**Tests to Update**:
1. `tests/ciris_engine/logic/runtime/test_service_initializer.py` - Add new path tests
2. All tests that create ServiceInitializer - May need config updates
3. Integration tests - Verify compatibility with new initialization

**Migration Checklist**:
- [ ] All existing ServiceInitializer tests still pass
- [ ] New component tests added
- [ ] Integration tests cover both paths
- [ ] QA runner tests pass with new initialization
- [ ] API tests pass with new initialization

---

## Risk Assessment

### Risk 1: Breaking Existing Initialization Flows

**Probability**: Medium
**Impact**: High (production outage)

**Mitigation**:
1. Feature flag enables parallel execution
2. Comprehensive integration testing
3. Staged rollout (staging → production)
4. Easy rollback (disable feature flag)
5. Monitoring during cutover

**Rollback Plan**:
```bash
# Disable feature flag
export CIRIS_USE_NEW_INIT=false
# Restart services
```

### Risk 2: Missing Environment Variable Mappings

**Probability**: Low
**Impact**: Medium (services fail to start)

**Mitigation**:
1. Document all env var mappings in config models
2. Comprehensive env var tests
3. Validate against production env vars before deployment
4. Keep old code path available during testing

**Detection**:
- Config validation errors at startup
- Service initialization failures
- Missing config in logs

### Risk 3: Config Model Validation Too Strict

**Probability**: Medium
**Impact**: Medium (prevents valid configs)

**Mitigation**:
1. Start with relaxed validation
2. Gradually tighten based on real-world usage
3. Provide clear validation error messages
4. Document validation rules

**Example**:
```python
# Instead of:
api_key: str  # Fails if empty string

# Use:
api_key: str = ""  # Allow empty, validate in service
```

### Risk 4: Performance Regression

**Probability**: Low
**Impact**: Low (slightly slower startup)

**Mitigation**:
1. Config caching in ConfigurationAdapter
2. No redundant service creation
3. Parallel service initialization where possible
4. Benchmark before/after

**Monitoring**:
- Track `initializer_startup_time_ms` metric
- Alert if startup time increases >10%

### Risk 5: Circular Dependencies in Config Models

**Probability**: Low
**Impact**: Medium (import errors)

**Mitigation**:
1. Careful import structure
2. Use TYPE_CHECKING for forward references
3. Import tests in Phase 1

**Example**:
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ciris_engine.schemas.config.essential import EssentialConfig
```

---

## Validation Criteria

### Phase 1 Complete When:
- [ ] All config models created in `ciris_engine/schemas/config/`
- [ ] All config models have Pydantic validation
- [ ] All config models have factory methods
- [ ] Config models import without errors
- [ ] Unit tests for all config models pass
- [ ] No circular import dependencies

### Phase 2 Complete When:
- [ ] ConfigurationAdapter created
- [ ] ConfigurationAdapter loads all config types
- [ ] Config caching works
- [ ] No direct env var access in adapter
- [ ] Unit tests pass

### Phase 3 Complete When:
- [ ] InfrastructureBootstrapper created
- [ ] All 10 infrastructure services created
- [ ] Dependency order enforced
- [ ] Returns typed InfrastructureBundle
- [ ] Unit tests pass
- [ ] No `config: Any` parameters

### Phase 4 Complete When:
- [ ] ObservabilityComposer created
- [ ] All 5 observability services created
- [ ] Uses RegistryAwareServiceProtocol
- [ ] Returns typed ObservabilityBundle
- [ ] Unit tests pass

### Phase 5 Complete When:
- [ ] GovernanceComposer created
- [ ] All 6 governance services created
- [ ] Handles optional LLM
- [ ] Returns typed GovernanceBundle
- [ ] Unit tests pass

### Phase 6 Complete When:
- [ ] ServiceOrchestrator created
- [ ] Coordinates all phases
- [ ] Metrics match v1.4.3 format
- [ ] Registry fully populated
- [ ] BusManager wired correctly
- [ ] Unit tests pass

### Phase 7 Complete When:
- [ ] ServiceInitializer delegates to orchestrator
- [ ] Feature flag controls path selection
- [ ] Compatibility wiring preserves attributes
- [ ] All public methods work in both modes
- [ ] Existing tests still pass

### Phase 8 Complete When:
- [ ] Both paths produce identical services
- [ ] Both paths populate registry identically
- [ ] Metrics compatible
- [ ] No test regressions
- [ ] Comparison tests pass

### Phase 9 Complete When:
- [ ] Staging deployment successful
- [ ] 24 hours monitoring shows no issues
- [ ] QA tests pass in staging
- [ ] Production deployment successful
- [ ] 48 hours monitoring shows no issues

### Phase 10 Complete When:
- [ ] Old code removed
- [ ] Feature flag removed
- [ ] CLAUDE.md updated with examples
- [ ] Architecture docs updated
- [ ] All tests passing
- [ ] No `config: Any` anywhere in initialization

---

## Example Code

### Example: Using ConfigurationAdapter

```python
# In main.py or startup code

from ciris_engine.logic.initialization.configuration_adapter import ConfigurationAdapter
from ciris_engine.schemas.config.essential import EssentialConfig

# Load bootstrap config
essential_config = EssentialConfig()
essential_config.load_env_vars()

# Create adapter
config_adapter = ConfigurationAdapter(essential_config)

# Load typed config (centralizes all env var access)
init_config = config_adapter.load_config(skip_llm_init=False)

# Now have strongly-typed config
print(f"LLM endpoint: {init_config.llm.primary.base_url}")
print(f"Billing enabled: {init_config.infrastructure.resource_monitor.billing.enabled if init_config.infrastructure.resource_monitor.billing else False}")
```

### Example: Using ServiceOrchestrator Directly

```python
# For tests or custom initialization

from ciris_engine.logic.initialization.service_orchestrator import ServiceOrchestrator
from ciris_engine.logic.initialization.configuration_adapter import ConfigurationAdapter

# Load config
config_adapter = ConfigurationAdapter(essential_config)
init_config = config_adapter.load_config()

# Create orchestrator
orchestrator = ServiceOrchestrator(
    config=init_config,
    essential_config=essential_config,
)

# Initialize everything
services = await orchestrator.initialize_all()

# Access services
time_service = services.infrastructure.time_service
memory_service = services.infrastructure.memory_service
telemetry = services.observability.telemetry_service

# Get metrics
metrics = orchestrator.get_metrics()
print(f"Startup time: {metrics['initializer_startup_time_ms']}ms")
```

### Example: Creating Custom Service Bundle

```python
# For specialized deployment scenarios

from ciris_engine.logic.initialization.infrastructure_bootstrapper import InfrastructureBootstrapper
from ciris_engine.logic.initialization.observability_composer import ObservabilityComposer

# Bootstrap minimal infrastructure
bootstrapper = InfrastructureBootstrapper(infra_config, memory_config)
infrastructure = await bootstrapper.bootstrap()

# Only compose observability (skip governance)
observability_composer = ObservabilityComposer(
    observability_config=obs_config,
    infrastructure_bundle=infrastructure,
    service_registry=registry,
    bus_manager=bus_manager,
)
observability = await observability_composer.compose()

# Custom wiring
# ...
```

### Example: Config Model Validation in Tests

```python
# Testing with invalid config

def test_billing_config_validation():
    """Test BillingConfig validates API key requirement."""
    # Should fail - enabled but no key
    with pytest.raises(ValueError, match="api_key is required"):
        BillingConfig(enabled=True, api_key=None)

    # Should succeed - enabled with key
    config = BillingConfig(enabled=True, api_key="test-key")
    assert config.enabled
    assert config.api_key == "test-key"

    # Should succeed - disabled, no key needed
    config = BillingConfig(enabled=False, api_key=None)
    assert not config.enabled
```

---

## Implementation Timeline

**Week 1: Config Models and Adapter**
- Days 1-2: Phase 1 (Config Models)
- Day 3: Phase 2 (ConfigurationAdapter)
- Days 4-5: Phase 3 (InfrastructureBootstrapper)

**Week 2: Composers**
- Days 1-2: Phase 4 (ObservabilityComposer)
- Days 3-4: Phase 5 (GovernanceComposer)
- Day 5: Phase 6 (ServiceOrchestrator)

**Week 3: Integration and Testing**
- Days 1-2: Phase 7 (ServiceInitializer delegation)
- Days 3-4: Phase 8 (Parallel execution testing)
- Day 5: Phase 9 (Gradual cutover - staging)

**Week 4: Production and Cleanup**
- Days 1-2: Phase 9 continued (Production cutover)
- Days 3-5: Phase 10 (Cleanup and documentation)



---

## References

### Key Files

**Current Implementation**:
- `/home/emoore/CIRISAgent/ciris_engine/logic/runtime/service_initializer.py` (1,333 lines)
- `/home/emoore/CIRISAgent/ciris_engine/schemas/config/essential.py` (170 lines)

**Tests**:
- `/home/emoore/CIRISAgent/tests/ciris_engine/logic/runtime/test_service_initializer.py` (932 lines)

**Related Documentation**:
- `/home/emoore/CIRISAgent/QUALITY_IMPROVEMENT_PLAN.md` - Overall quality plan
- `/home/emoore/CIRISAgent/QUALITY_IMPROVEMENT_ANALYSIS.md` - Analysis of issues
- `/home/emoore/CIRISAgent/CLAUDE.md` - Project guidelines

### Protocol References

**RegistryAwareServiceProtocol**:
- Defined in: `ciris_engine/protocols/infrastructure.py` (to be created in Issue 2)
- Used by: GraphTelemetryService, SelfObservationService, GraphAuditService
- Purpose: Standardize post-construction registry injection

### Environment Variables Catalog

All environment variables referenced in initialization:

| Variable | Config Model | Field |
|----------|--------------|-------|
| `CIRIS_BILLING_ENABLED` | `BillingConfig` | `enabled` |
| `CIRIS_BILLING_API_KEY` | `BillingConfig` | `api_key` |
| `CIRIS_BILLING_API_URL` | `BillingConfig` | `base_url` |
| `CIRIS_BILLING_TIMEOUT_SECONDS` | `BillingConfig` | `timeout_seconds` |
| `CIRIS_BILLING_CACHE_TTL_SECONDS` | `BillingConfig` | `cache_ttl_seconds` |
| `CIRIS_BILLING_FAIL_OPEN` | `BillingConfig` | `fail_open` |
| `CIRIS_SIMPLE_FREE_USES` | `SimpleCreditConfig` | `free_uses` |
| `OPENAI_API_KEY` | `LLMProviderConfig` | `api_key` (primary) |
| `INSTRUCTOR_MODE` | `LLMProviderConfig` | `instructor_mode` |
| `CIRIS_OPENAI_API_KEY_2` | `LLMProviderConfig` | `api_key` (secondary) |
| `CIRIS_OPENAI_API_BASE_2` | `LLMProviderConfig` | `base_url` (secondary) |
| `CIRIS_OPENAI_MODEL_NAME_2` | `LLMProviderConfig` | `model_name` (secondary) |
| `CIRIS_USE_NEW_INIT` | Feature flag | N/A (removed after cutover) |

---

## Conclusion

This detailed plan provides everything needed to refactor the ServiceInitializer monolith into a maintainable, type-safe, testable architecture. The phased approach with feature flags enables safe migration with easy rollback. The typed config models eliminate all `config: Any` parameters and centralize environment variable access. The five focused components replace a 1,333-line monolith with five ~200-line components, each with a single clear responsibility.

**Success will be measured by**:
- Zero `config: Any` parameters in initialization code
- ServiceInitializer under 200 lines (delegating to components)
- All environment variable access centralized in ConfigurationAdapter
- Each component independently unit-testable
- No production incidents during cutover
- Improved developer velocity for adding new service types

**Next Steps**:
1. Review this plan with stakeholders
2. Create tracking issue for each phase
3. Begin Phase 1 (Config Models)
4. Iterate based on learnings from each phase
