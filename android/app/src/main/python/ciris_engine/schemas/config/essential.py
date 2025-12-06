"""
Essential Configuration Schema for CIRIS Bootstrap.

Mission-critical configuration only. No ambiguity allowed.
This replaces AppConfig for a cleaner, graph-based config system.
"""

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


def _get_default_main_db() -> Path:
    """Get default main database path using central path resolution."""
    from ciris_engine.logic.utils.path_resolution import get_data_dir

    return get_data_dir() / "ciris_engine.db"


def _get_default_secrets_db() -> Path:
    """Get default secrets database path using central path resolution."""
    from ciris_engine.logic.utils.path_resolution import get_data_dir

    return get_data_dir() / "secrets.db"


def _get_default_audit_db() -> Path:
    """Get default audit database path using central path resolution."""
    from ciris_engine.logic.utils.path_resolution import get_data_dir

    return get_data_dir() / "ciris_audit.db"


class DatabaseConfig(BaseModel):
    """Core database paths configuration."""

    main_db: Path = Field(default_factory=_get_default_main_db, description="Main SQLite database for persistence")
    secrets_db: Path = Field(default_factory=_get_default_secrets_db, description="Encrypted secrets storage database")
    audit_db: Path = Field(default_factory=_get_default_audit_db, description="Audit trail database with signatures")
    database_url: Optional[str] = Field(
        None,
        description="Database connection string. If set, overrides main_db path. "
        "Format: 'sqlite://path/to/db' or 'postgresql://user:pass@host:port/dbname'. "
        "Defaults to SQLite at main_db path for backward compatibility.",
    )

    model_config = ConfigDict(extra="forbid")


class ServiceEndpointsConfig(BaseModel):
    """External service endpoints configuration."""

    llm_endpoint: str = Field("https://api.openai.com/v1", description="LLM API endpoint URL")
    llm_model: str = Field("gpt-4o-mini", description="LLM model identifier")
    llm_timeout: int = Field(30, description="LLM request timeout in seconds")
    llm_max_retries: int = Field(3, description="Maximum LLM retry attempts")

    model_config = ConfigDict(extra="forbid")


class SecurityConfig(BaseModel):
    """Security and audit configuration."""

    audit_retention_days: int = Field(90, description="Days to retain audit logs")
    secrets_encryption_key_env: str = Field(
        "CIRIS_MASTER_KEY", description="Environment variable containing master encryption key"
    )
    secrets_key_path: Path = Field(Path(".ciris_keys"), description="Directory containing secrets master key")
    audit_key_path: Path = Field(Path("audit_keys"), description="Directory containing audit signing keys")
    enable_signed_audit: bool = Field(True, description="Enable cryptographic signing of audit entries")
    max_thought_depth: int = Field(7, description="Maximum thought chain depth before auto-defer")

    model_config = ConfigDict(extra="forbid")


class OperationalLimitsConfig(BaseModel):
    """Operational limits and thresholds."""

    max_active_tasks: int = Field(10, description="Maximum concurrent active tasks")
    max_active_thoughts: int = Field(50, description="Maximum thoughts in processing queue")
    round_delay_seconds: float = Field(5.0, description="Delay between processing rounds")
    mock_llm_round_delay: float = Field(0.1, description="Reduced delay for mock LLM testing")
    dma_retry_limit: int = Field(3, description="Maximum DMA evaluation retries")
    dma_timeout_seconds: float = Field(30.0, description="DMA evaluation timeout")
    conscience_retry_limit: int = Field(2, description="Maximum conscience evaluation retries")

    model_config = ConfigDict(extra="forbid")


class TelemetryConfig(BaseModel):
    """Telemetry configuration."""

    enabled: bool = Field(False, description="Enable telemetry collection")
    export_interval_seconds: int = Field(60, description="Telemetry export interval")
    retention_hours: int = Field(24, description="Telemetry data retention period")

    model_config = ConfigDict(extra="forbid")


class WorkflowConfig(BaseModel):
    """Workflow configuration for agent processing."""

    max_rounds: int = Field(10, description="Maximum rounds of processing before automatic pause")
    round_timeout_seconds: float = Field(300.0, description="Timeout for each processing round")
    enable_auto_defer: bool = Field(True, description="Automatically defer when hitting limits")

    model_config = ConfigDict(extra="forbid")


class GraphConfig(BaseModel):
    """Graph service configuration."""

    # TSDB Consolidation settings
    # Note: Consolidation intervals are FIXED for calendar alignment:
    # - Basic: Every 6 hours (00:00, 06:00, 12:00, 18:00 UTC)
    # - Extensive: Every Monday at 00:00 UTC
    # - Profound: 1st of each month at 00:00 UTC

    tsdb_profound_target_mb_per_day: float = Field(
        20.0, description="Target size in MB per day after profound consolidation"
    )
    tsdb_raw_retention_hours: int = Field(24, description="How long to keep raw TSDB data before basic consolidation")
    consolidation_timezone: str = Field("UTC", description="Timezone for consolidation scheduling (default: UTC)")

    model_config = ConfigDict(extra="forbid")


class EssentialConfig(BaseModel):
    """
    Mission-critical configuration for CIRIS bootstrap.

    This is the minimal configuration needed to start core services.
    After bootstrap, all config is migrated to GraphConfigService.
    """

    database: DatabaseConfig = Field(default_factory=lambda: DatabaseConfig())
    services: ServiceEndpointsConfig = Field(default_factory=lambda: ServiceEndpointsConfig())
    security: SecurityConfig = Field(default_factory=lambda: SecurityConfig())
    limits: OperationalLimitsConfig = Field(default_factory=lambda: OperationalLimitsConfig())
    telemetry: TelemetryConfig = Field(default_factory=lambda: TelemetryConfig())
    workflow: WorkflowConfig = Field(default_factory=lambda: WorkflowConfig())
    graph: GraphConfig = Field(default_factory=lambda: GraphConfig())

    # Runtime settings
    log_level: str = Field("INFO", description="Logging level")
    debug_mode: bool = Field(False, description="Enable debug mode")
    template_directory: Path = Field(Path("ciris_templates"), description="Directory containing identity templates")
    default_template: str = Field("default", description="Default template name for agent identity creation")
    agent_occurrence_id: str = Field(
        "default",
        description="Unique ID for this runtime occurrence (enables multiple instances against same database)",
    )

    model_config = ConfigDict(extra="forbid")  # No ambiguity allowed in mission-critical config

    def load_env_vars(self) -> None:
        """Load configuration from environment variables if present."""
        import os

        # Check both CIRIS_OCCURRENCE_ID (new standard) and AGENT_OCCURRENCE_ID (legacy) for backward compatibility
        env_occurrence_id = os.getenv("CIRIS_OCCURRENCE_ID") or os.getenv("AGENT_OCCURRENCE_ID")
        if env_occurrence_id:
            self.agent_occurrence_id = env_occurrence_id

        # Load database URL from environment (supports PostgreSQL with credentials)
        env_db_url = os.getenv("CIRIS_DB_URL")
        if env_db_url:
            self.database.database_url = env_db_url

        # Load template from environment (set by setup wizard)
        env_template = os.getenv("CIRIS_TEMPLATE")
        if env_template:
            self.default_template = env_template


class CIRISNodeConfig(BaseModel):
    """Configuration for CIRISNode integration."""

    base_url: Optional[str] = Field(None, description="CIRISNode base URL")
    enabled: bool = Field(False, description="Whether CIRISNode integration is enabled")

    model_config = ConfigDict(extra="forbid")

    def load_env_vars(self) -> None:
        """Load configuration from environment variables if present."""
        from ciris_engine.logic.config.env_utils import get_env_var

        env_url = get_env_var("CIRISNODE_BASE_URL")
        if env_url:
            self.base_url = env_url

        env_enabled = get_env_var("CIRISNODE_ENABLED")
        if env_enabled is not None:
            self.enabled = env_enabled.lower() in ("true", "1", "yes", "on")
