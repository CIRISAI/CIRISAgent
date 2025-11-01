"""
Root configuration model for service initialization.

This module provides the complete typed configuration that replaces
the Dict[str, Any] parameters in ServiceInitializer.
"""

from typing import TYPE_CHECKING

from pydantic import BaseModel

from ciris_engine.schemas.config.governance_config import GovernanceConfig
from ciris_engine.schemas.config.infrastructure_config import InfrastructureConfig
from ciris_engine.schemas.config.llm_config import LLMConfig
from ciris_engine.schemas.config.memory_config import MemoryConfig
from ciris_engine.schemas.config.observability_config import ObservabilityConfig

if TYPE_CHECKING:
    from ciris_engine.schemas.config.essential import EssentialConfig


class InitializationConfig(BaseModel):
    """
    Complete typed configuration for service initialization.

    This replaces the Dict[str, Any] parameters throughout ServiceInitializer,
    providing full type safety and validation for all service configurations.

    Attributes:
        infrastructure: Config for ResourceMonitor and DatabaseMaintenance
        memory: Config for Secrets and Memory services
        llm: Config for LLM services (primary/secondary providers)
        observability: Config for Telemetry, Audit, and TSDB services
        governance: Config for AdaptiveFilter, SelfObservation, Visibility, Consent

    Usage:
        ```python
        # Load from environment and essential config
        init_config = InitializationConfig.from_essential_config(
            essential_config=essential_config,
            skip_llm_init=False
        )

        # Pass to ServiceInitializer
        service_initializer = ServiceInitializer(
            essential_config=essential_config,
            init_config=init_config,
            service_registry=service_registry,
            db_path=db_path
        )
        ```
    """

    infrastructure: InfrastructureConfig
    memory: MemoryConfig
    llm: LLMConfig
    observability: ObservabilityConfig
    governance: GovernanceConfig

    @classmethod
    def from_essential_config(cls, essential_config, skip_llm_init: bool = False) -> "InitializationConfig":
        """
        Load complete initialization config from essential config and environment.

        This is the single entry point for creating all typed service configurations,
        replacing the scattered environment variable access throughout ServiceInitializer.

        Args:
            essential_config: EssentialConfig instance with base configuration
            skip_llm_init: Skip LLM initialization (for mock mode)

        Returns:
            Complete InitializationConfig with all service configurations

        Environment Variables Used:
            Infrastructure:
                - CIRIS_BILLING_ENABLED, CIRIS_BILLING_API_KEY, etc. (billing)
                - CIRIS_SIMPLE_FREE_USES (simple credits)

            LLM:
                - OPENAI_API_KEY (primary)
                - CIRIS_OPENAI_API_KEY_2 (secondary, optional)
                - INSTRUCTOR_MODE

            All other config derived from essential_config paths.

        Example:
            ```python
            config = InitializationConfig.from_essential_config(
                essential_config=load_config(),
                skip_llm_init=False
            )
            ```
        """
        return cls(
            infrastructure=InfrastructureConfig.from_env(),
            memory=MemoryConfig.from_essential_config(essential_config),
            llm=LLMConfig.from_env_and_essential(essential_config, skip_llm_init=skip_llm_init),
            observability=ObservabilityConfig.from_essential_config(essential_config),
            governance=GovernanceConfig.from_essential_config(essential_config),
        )
