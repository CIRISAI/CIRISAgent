"""
Adapter startup context schema.

Provides adapters with all necessary startup context without requiring direct runtime references.
This enables cleaner adapter initialization and testing.
"""

from typing import TYPE_CHECKING, Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.config.essential import EssentialConfig

if TYPE_CHECKING:
    from ciris_engine.logic.buses.bus_manager import BusManager
    from ciris_engine.logic.registries.base import ServiceRegistry
    from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol


class AdapterStartupContext(BaseModel):
    """
    Context provided to adapters during startup.

    Contains all essential configuration and service references needed for adapter initialization.
    Replaces the pattern of passing raw runtime references to adapters.
    """

    essential_config: EssentialConfig = Field(..., description="Core system configuration")
    modules_to_load: List[str] = Field(
        default_factory=list, description="External modules to be loaded (e.g., 'mock_llm')"
    )
    startup_channel_id: str = Field("", description="Channel ID for startup messages (may be empty string)")
    debug: bool = Field(False, description="Debug mode enabled")

    # Service references - using Any but documented as specific types
    # NOTE: We use Any here to avoid forward reference issues with Pydantic
    # These are actually: BusManager, TimeServiceProtocol, ServiceRegistry
    bus_manager: Optional[Any] = Field(
        None, description="Message bus manager for inter-service communication (BusManager)"
    )
    time_service: Optional[Any] = Field(
        None, description="Time service for consistent timestamps (TimeServiceProtocol)"
    )
    service_registry: Optional[Any] = Field(
        None, description="Service registry for service discovery (ServiceRegistry)"
    )

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")
