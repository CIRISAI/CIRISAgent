"""
Essential Configuration Schema for CIRIS Bootstrap.

Mission-critical configuration only. No ambiguity allowed.
This replaces AppConfig for a cleaner, graph-based config system.
"""
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

class DatabaseConfig(BaseModel):
    """Core database paths configuration."""
    main_db: Path = Field(
        Path("data/ciris_engine.db"),
        description="Main SQLite database for persistence"
    )
    secrets_db: Path = Field(
        Path("data/secrets.db"),
        description="Encrypted secrets storage database"
    )
    audit_db: Path = Field(
        Path("data/ciris_audit.db"),
        description="Audit trail database with signatures"
    )

    model_config = ConfigDict(extra = "forbid")

class ServiceEndpointsConfig(BaseModel):
    """External service endpoints configuration."""
    llm_endpoint: str = Field(
        "https://api.openai.com/v1",
        description="LLM API endpoint URL"
    )
    llm_model: str = Field(
        "gpt-4o-mini",
        description="LLM model identifier"
    )
    llm_timeout: int = Field(
        30,
        description="LLM request timeout in seconds"
    )
    llm_max_retries: int = Field(
        3,
        description="Maximum LLM retry attempts"
    )

    model_config = ConfigDict(extra = "forbid")

class SecurityConfig(BaseModel):
    """Security and audit configuration."""
    audit_retention_days: int = Field(
        90,
        description="Days to retain audit logs"
    )
    secrets_encryption_key_env: str = Field(
        "CIRIS_MASTER_KEY",
        description="Environment variable containing master encryption key"
    )
    audit_key_path: Path = Field(
        Path("audit_keys"),
        description="Directory containing audit signing keys"
    )
    enable_signed_audit: bool = Field(
        True,
        description="Enable cryptographic signing of audit entries"
    )
    max_thought_depth: int = Field(
        7,
        description="Maximum thought chain depth before auto-defer"
    )

    model_config = ConfigDict(extra = "forbid")

class OperationalLimitsConfig(BaseModel):
    """Operational limits and thresholds."""
    max_active_tasks: int = Field(
        10,
        description="Maximum concurrent active tasks"
    )
    max_active_thoughts: int = Field(
        50,
        description="Maximum thoughts in processing queue"
    )
    round_delay_seconds: float = Field(
        5.0,
        description="Delay between processing rounds"
    )
    mock_llm_round_delay: float = Field(
        0.1,
        description="Reduced delay for mock LLM testing"
    )
    dma_retry_limit: int = Field(
        3,
        description="Maximum DMA evaluation retries"
    )
    dma_timeout_seconds: float = Field(
        30.0,
        description="DMA evaluation timeout"
    )
    conscience_retry_limit: int = Field(
        2,
        description="Maximum conscience evaluation retries"
    )

    model_config = ConfigDict(extra = "forbid")

class TelemetryConfig(BaseModel):
    """Telemetry configuration."""
    enabled: bool = Field(
        False,
        description="Enable telemetry collection"
    )
    export_interval_seconds: int = Field(
        60,
        description="Telemetry export interval"
    )
    retention_hours: int = Field(
        24,
        description="Telemetry data retention period"
    )

    model_config = ConfigDict(extra = "forbid")

class WorkflowConfig(BaseModel):
    """Workflow configuration for agent processing."""
    max_rounds: int = Field(
        10,
        description="Maximum rounds of processing before automatic pause"
    )
    round_timeout_seconds: float = Field(
        300.0,
        description="Timeout for each processing round"
    )
    enable_auto_defer: bool = Field(
        True,
        description="Automatically defer when hitting limits"
    )

    model_config = ConfigDict(extra = "forbid")

class EssentialConfig(BaseModel):
    """
    Mission-critical configuration for CIRIS bootstrap.

    This is the minimal configuration needed to start core services.
    After bootstrap, all config is migrated to GraphConfigService.
    """
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    services: ServiceEndpointsConfig = Field(default_factory=ServiceEndpointsConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    limits: OperationalLimitsConfig = Field(default_factory=OperationalLimitsConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)

    # Runtime settings
    log_level: str = Field(
        "INFO",
        description="Logging level"
    )
    debug_mode: bool = Field(
        False,
        description="Enable debug mode"
    )
    template_directory: Path = Field(
        Path("ciris_templates"),
        description="Directory containing identity templates"
    )
    default_template: str = Field(
        "default",
        description="Default template name for agent identity creation"
    )

    model_config = ConfigDict(extra = "forbid")  # No ambiguity allowed in mission-critical config

class CIRISNodeConfig(BaseModel):
    """Configuration for CIRISNode integration."""
    base_url: Optional[str] = Field(
        None,
        description="CIRISNode base URL"
    )
    enabled: bool = Field(
        False,
        description="Whether CIRISNode integration is enabled"
    )

    model_config = ConfigDict(extra = "forbid")
    
    def load_env_vars(self) -> None:
        """Load configuration from environment variables if present."""
        from ciris_engine.logic.config.env_utils import get_env_var
        
        env_url = get_env_var("CIRISNODE_BASE_URL")
        if env_url:
            self.base_url = env_url
            
        env_enabled = get_env_var("CIRISNODE_ENABLED")
        if env_enabled is not None:
            self.enabled = env_enabled.lower() in ("true", "1", "yes", "on")
