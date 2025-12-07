"""
Resource Schemas v1 - Resource management and cost tracking for CIRIS Agent

Provides schemas for monitoring resource usage, costs, and environmental impact.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ResourceAction(str, Enum):
    """Actions to take when a resource limit is exceeded"""

    LOG = "log"
    WARN = "warn"
    THROTTLE = "throttle"
    DEFER = "defer"
    REJECT = "reject"
    SHUTDOWN = "shutdown"


class ResourceLimit(BaseModel):
    """Configuration for a single resource"""

    limit: int = Field(description="Hard limit value")
    warning: int = Field(description="Warning threshold")
    critical: int = Field(description="Critical threshold")
    action: ResourceAction = Field(default=ResourceAction.DEFER, description="Action when limit exceeded")
    cooldown_seconds: int = Field(default=60, ge=0, description="Cooldown period in seconds")

    model_config = ConfigDict(extra="forbid")


def _memory_mb_limit() -> ResourceLimit:
    return ResourceLimit(limit=4096, warning=3072, critical=3840)


def _cpu_percent_limit() -> ResourceLimit:
    return ResourceLimit(limit=80, warning=60, critical=75, action=ResourceAction.THROTTLE)


def _tokens_hour_limit() -> ResourceLimit:
    return ResourceLimit(limit=10000, warning=8000, critical=9500)


def _tokens_day_limit() -> ResourceLimit:
    return ResourceLimit(limit=100000, warning=80000, critical=95000, action=ResourceAction.REJECT)


def _disk_mb_limit() -> ResourceLimit:
    return ResourceLimit(limit=100, warning=80, critical=95, action=ResourceAction.WARN)


def _thoughts_active_limit() -> ResourceLimit:
    return ResourceLimit(limit=50, warning=40, critical=48)


class ResourceBudget(BaseModel):
    """Limits for all monitored resources"""

    memory_mb: ResourceLimit = Field(default_factory=_memory_mb_limit, description="Memory usage limits in MB")
    cpu_percent: ResourceLimit = Field(default_factory=_cpu_percent_limit, description="CPU usage limits in percent")
    tokens_hour: ResourceLimit = Field(default_factory=_tokens_hour_limit, description="Token usage per hour")
    tokens_day: ResourceLimit = Field(default_factory=_tokens_day_limit, description="Token usage per day")
    disk_mb: ResourceLimit = Field(default_factory=_disk_mb_limit, description="Disk usage limits in MB")
    thoughts_active: ResourceLimit = Field(default_factory=_thoughts_active_limit, description="Active thoughts limit")

    model_config = ConfigDict(extra="forbid")


class ResourceSnapshot(BaseModel):
    """Current resource usage snapshot"""

    memory_mb: int = Field(default=0, ge=0, description="Memory usage in MB")
    memory_percent: int = Field(default=0, ge=0, le=100, description="Memory usage percentage")
    cpu_percent: int = Field(default=0, ge=0, le=100, description="CPU usage percentage")
    cpu_average_1m: int = Field(default=0, ge=0, le=100, description="1-minute CPU average")
    tokens_used_hour: int = Field(default=0, ge=0, description="Tokens used in current hour")
    tokens_used_day: int = Field(default=0, ge=0, description="Tokens used today")
    disk_used_mb: int = Field(default=0, ge=0, description="Disk space used in MB")
    disk_free_mb: int = Field(default=0, ge=0, description="Free disk space in MB")
    thoughts_active: int = Field(default=0, ge=0, description="Number of active thoughts")
    thoughts_queued: int = Field(default=0, ge=0, description="Number of queued thoughts")
    healthy: bool = Field(default=True, description="Overall health status")
    warnings: List[str] = Field(default_factory=list, description="Active warnings")
    critical: List[str] = Field(default_factory=list, description="Critical issues")

    model_config = ConfigDict(extra="forbid")


class ResourceCost(BaseModel):
    """Environmental and financial cost of AI operations"""

    # Token usage
    tokens_used: int = Field(default=0, ge=0, description="Total tokens consumed")

    # Financial cost
    cost_cents: float = Field(default=0.0, ge=0.0, description="Cost in cents USD")
    cost_per_token_cents: float = Field(default=0.002, description="Cost per token in cents")

    # Environmental impact (estimates based on research)
    water_ml: float = Field(default=0.0, ge=0.0, description="Water usage in milliliters")
    water_per_token_ml: float = Field(default=0.05, description="Water per token in ml (50ml per 1k tokens)")

    carbon_g: float = Field(default=0.0, ge=0.0, description="Carbon emissions in grams CO2")
    carbon_per_token_g: float = Field(default=0.002, description="Carbon per token in grams (2g per 1k tokens)")

    # Energy consumption
    energy_kwh: float = Field(default=0.0, ge=0.0, description="Energy consumption in kilowatt-hours")
    energy_per_token_kwh: float = Field(default=0.00001, description="Energy per token in kWh")

    # Metadata
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="When costs were calculated"
    )
    model_used: Optional[str] = Field(default=None, description="Model that incurred these costs")

    model_config = ConfigDict(protected_namespaces=())

    def calculate_from_tokens(self, tokens: int, model: Optional[str] = None) -> None:
        """Calculate all costs from token count"""
        self.tokens_used = tokens
        self.cost_cents = tokens * self.cost_per_token_cents
        self.water_ml = tokens * self.water_per_token_ml
        self.carbon_g = tokens * self.carbon_per_token_g
        self.energy_kwh = tokens * self.energy_per_token_kwh
        self.model_used = model
        self.timestamp = datetime.now(timezone.utc)

    def add_usage(self, other: "ResourceCost") -> None:
        """Add another resource cost to this one"""
        self.tokens_used += other.tokens_used
        self.cost_cents += other.cost_cents
        self.water_ml += other.water_ml
        self.carbon_g += other.carbon_g
        self.energy_kwh += other.energy_kwh

    @property
    def cost_dollars(self) -> float:
        """Get cost in dollars"""
        return self.cost_cents / 100.0

    @property
    def water_liters(self) -> float:
        """Get water usage in liters"""
        return self.water_ml / 1000.0

    @property
    def carbon_kg(self) -> float:
        """Get carbon emissions in kilograms"""
        return self.carbon_g / 1000.0

    model_config = ConfigDict(extra="forbid")


class ResourceAlert(BaseModel):
    """Resource usage alert"""

    resource_type: str = Field(description="Type of resource (memory, cpu, tokens, etc.)")
    current_value: float = Field(description="Current usage value")
    limit_value: float = Field(description="Configured limit")
    severity: str = Field(description="Alert severity (warning, critical)")
    action_taken: ResourceAction = Field(description="Action taken in response")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="When alert was triggered"
    )
    message: str = Field(description="Human-readable alert message")

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "ResourceAction",
    "ResourceLimit",
    "ResourceBudget",
    "ResourceSnapshot",
    "ResourceCost",
    "ResourceAlert",
]
