"""
Component builder for CIRIS Agent runtime.

Handles the construction of all processing components.
"""

import logging
from typing import Any, Optional

from ciris_engine.logic.conscience import (
    CoherenceConscience,
    EntropyConscience,
    EpistemicHumilityConscience,
    OptimizationVetoConscience,
    conscienceRegistry,
)
from ciris_engine.logic.conscience.thought_depth_guardrail import ThoughtDepthGuardrail
from ciris_engine.logic.conscience.updated_status_conscience import UpdatedStatusConscience
from ciris_engine.logic.context.builder import ContextBuilder
from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator
from ciris_engine.logic.dma.csdma import CSDMAEvaluator
from ciris_engine.logic.dma.factory import create_dsdma_from_identity
from ciris_engine.logic.dma.pdma import EthicalPDMAEvaluator
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.logic.infrastructure.handlers.handler_registry import build_action_dispatcher
from ciris_engine.logic.processors import AgentProcessor
from ciris_engine.logic.processors.core.thought_processor import ThoughtProcessor
from ciris_engine.logic.processors.support.dma_orchestrator import DMAOrchestrator
from ciris_engine.logic.utils.graphql_context_provider import GraphQLContextProvider
from ciris_engine.logic.utils.shutdown_manager import register_global_shutdown_handler
from ciris_engine.schemas.processors.base import ProcessorServices

logger = logging.getLogger(__name__)


class ComponentBuilder:
    """Builds all processing components for the runtime."""

    def __init__(self, runtime: Any) -> None:
        """
        Initialize component builder.

        Args:
            runtime: Reference to the main runtime for access to services and config
        """
        self.runtime = runtime
        self.agent_processor: Optional[AgentProcessor] = None

    async def build_all_components(self) -> AgentProcessor:
        """Build all processing components and return the agent processor."""
        if not self.runtime.llm_service:
            raise RuntimeError("LLM service not initialized")

        if not self.runtime.service_registry:
            raise RuntimeError("Service registry not initialized")

        config = self.runtime._ensure_config()

        # For values not in EssentialConfig, use defaults
        # (These would come from GraphConfigService once fully migrated)

        # Build DMAs
        ethical_pdma = EthicalPDMAEvaluator(
            service_registry=self.runtime.service_registry,
            model_name=self.runtime.llm_service.model_name,
            max_retries=config.services.llm_max_retries,
            sink=self.runtime.bus_manager,
        )

        # Get overrides from agent identity
        csdma_overrides = None
        if self.runtime.agent_identity and hasattr(self.runtime.agent_identity, "core_profile"):
            csdma_overrides = self.runtime.agent_identity.core_profile.csdma_overrides

        csdma = CSDMAEvaluator(
            service_registry=self.runtime.service_registry,
            model_name=self.runtime.llm_service.model_name,
            max_retries=config.services.llm_max_retries,
            prompt_overrides=csdma_overrides,
            sink=self.runtime.bus_manager,
        )

        # Get action selection overrides from agent identity
        action_selection_overrides = None
        if self.runtime.agent_identity and hasattr(self.runtime.agent_identity, "core_profile"):
            action_selection_overrides = self.runtime.agent_identity.core_profile.action_selection_pdma_overrides

        action_pdma = ActionSelectionPDMAEvaluator(
            service_registry=self.runtime.service_registry,
            model_name=self.runtime.llm_service.model_name,
            max_retries=config.services.llm_max_retries,
            prompt_overrides=action_selection_overrides,
            sink=self.runtime.bus_manager,
        )

        # Create DSDMA using agent's identity
        if not self.runtime.agent_identity:
            raise RuntimeError("Cannot create DSDMA - no agent identity loaded from graph!")

        # Create identity configuration for DSDMA
        from ciris_engine.schemas.config.agent import AgentTemplate, DSDMAConfiguration

        # Create DSDMAConfiguration object
        dsdma_config = None
        domain_knowledge = getattr(self.runtime.agent_identity.core_profile, "domain_specific_knowledge", {})
        prompt_template = getattr(self.runtime.agent_identity.core_profile, "dsdma_prompt_template", None)

        if domain_knowledge or prompt_template:
            dsdma_config = DSDMAConfiguration(
                domain_specific_knowledge=domain_knowledge, prompt_template=prompt_template
            )

        identity_config = AgentTemplate(
            name=self.runtime.agent_identity.agent_id,
            description=self.runtime.agent_identity.core_profile.description,
            role_description=self.runtime.agent_identity.core_profile.role_description,
            dsdma_kwargs=dsdma_config,
            csdma_overrides=self.runtime.agent_identity.core_profile.csdma_overrides,
            action_selection_pdma_overrides=self.runtime.agent_identity.core_profile.action_selection_pdma_overrides,
        )

        dsdma = create_dsdma_from_identity(
            identity_config,
            self.runtime.service_registry,
            model_name=self.runtime.llm_service.model_name,
            sink=self.runtime.bus_manager,
        )

        # Get time service directly from service_initializer (not from registry)
        time_service = getattr(self.runtime.service_initializer, "time_service", None)
        if not time_service:
            raise RuntimeError("TimeService not available from service_initializer - required for consciences")

        # Build consciences
        conscience_registry = conscienceRegistry()
        # Create conscience config
        from ciris_engine.logic.conscience.core import ConscienceConfig

        conscience_config = ConscienceConfig()

        # Register UpdatedStatusConscience FIRST (priority -1) to detect channel updates
        # CRITICAL: bypass_exemption=True ensures it runs even for TASK_COMPLETE
        conscience_registry.register_conscience(
            "updated_status",
            UpdatedStatusConscience(time_service=time_service),
            priority=-1,  # Run BEFORE all other consciences
            bypass_exemption=True,  # Must run even for exempt actions like TASK_COMPLETE
        )

        conscience_registry.register_conscience(
            "entropy",
            EntropyConscience(
                self.runtime.service_registry,
                conscience_config,
                self.runtime.llm_service.model_name,
                self.runtime.bus_manager,
                time_service,
            ),
            priority=0,
        )
        conscience_registry.register_conscience(
            "coherence",
            CoherenceConscience(
                self.runtime.service_registry,
                conscience_config,
                self.runtime.llm_service.model_name,
                self.runtime.bus_manager,
                time_service,
            ),
            priority=1,
        )
        conscience_registry.register_conscience(
            "optimization_veto",
            OptimizationVetoConscience(
                self.runtime.service_registry,
                conscience_config,
                self.runtime.llm_service.model_name,
                self.runtime.bus_manager,
                time_service,
            ),
            priority=2,
        )
        conscience_registry.register_conscience(
            "epistemic_humility",
            EpistemicHumilityConscience(
                self.runtime.service_registry,
                conscience_config,
                self.runtime.llm_service.model_name,
                self.runtime.bus_manager,
                time_service,
            ),
            priority=3,
        )

        conscience_registry.register_conscience(
            "thought_depth",
            ThoughtDepthGuardrail(time_service=time_service, max_depth=config.security.max_thought_depth),
            priority=4,
        )

        # Build context provider
        graphql_provider = GraphQLContextProvider(
            graphql_client=None,  # Remote GraphQL disabled in essential config
            memory_service=self.runtime.memory_service,
            enable_remote_graphql=False,  # Remote GraphQL disabled in essential config
        )

        # Build orchestrators
        dma_orchestrator = DMAOrchestrator(
            ethical_pdma,
            csdma,
            dsdma,
            action_pdma,
            time_service=self.runtime.time_service,
            app_config=self.runtime.essential_config,
            llm_service=self.runtime.llm_service,
            memory_service=self.runtime.memory_service,
        )

        context_builder = ContextBuilder(
            memory_service=self.runtime.memory_service,
            graphql_provider=graphql_provider,
            app_config=self.runtime.essential_config,
            telemetry_service=self.runtime.telemetry_service,
            runtime=self.runtime,
            service_registry=self.runtime.service_registry,
            secrets_service=self.runtime.secrets_service,
            resource_monitor=self.runtime.resource_monitor,
            time_service=self.runtime.time_service,
        )

        # Register core services before building action dispatcher
        self.runtime._register_core_services()

        # Build action handler dependencies
        # Use the BusManager from runtime instead of creating a new one
        bus_manager = self.runtime.bus_manager

        dependencies = ActionHandlerDependencies(
            bus_manager=bus_manager,
            time_service=self.runtime.time_service,
            shutdown_callback=lambda: self.runtime.request_shutdown(
                "Handler requested shutdown due to critical service failure"
            ),
            secrets_service=getattr(self.runtime, "secrets_service", None),
        )

        # Register global shutdown handler
        register_global_shutdown_handler(lambda: self.runtime.request_shutdown("Global shutdown manager triggered"))

        # Build thought processor
        if not self.runtime.essential_config:
            raise RuntimeError("AppConfig is required for ThoughtProcessor initialization")

        thought_processor = ThoughtProcessor(
            dma_orchestrator,
            context_builder,
            conscience_registry,  # Pass registry directly
            self.runtime.essential_config,
            dependencies,
            telemetry_service=self.runtime.telemetry_service,
            time_service=self.runtime.time_service,
        )

        # Build action dispatcher
        action_dispatcher = self._build_action_dispatcher(dependencies)

        # Build agent processor
        if not self.runtime.essential_config:
            raise RuntimeError("AppConfig is required for AgentProcessor initialization")
        if not self.runtime.agent_identity:
            raise RuntimeError("Agent identity is required for AgentProcessor initialization")

        # Create ProcessorServices with all required services
        processor_services = ProcessorServices(
            llm_service=self.runtime.llm_service,
            memory_service=self.runtime.memory_service,
            audit_service=self.runtime.audit_service,
            service_registry=self.runtime.service_registry,
            time_service=self.runtime.time_service,
            resource_monitor=self.runtime.resource_monitor,
            secrets_service=self.runtime.secrets_service,
            telemetry_service=self.runtime.telemetry_service,
            app_config=self.runtime.essential_config,
            graphql_provider=graphql_provider,  # Use the actual GraphQL provider
            runtime=self.runtime,
            communication_bus=self.runtime.bus_manager.communication,
        )

        # Get cognitive behaviors from graph (populated by migration on first-run or pre-1.7 upgrade)
        cognitive_behaviors = await self._get_cognitive_behaviors_from_graph()

        self.agent_processor = AgentProcessor(
            app_config=self.runtime.essential_config,
            agent_identity=self.runtime.agent_identity,
            thought_processor=thought_processor,
            action_dispatcher=action_dispatcher,
            services=processor_services,
            startup_channel_id=self.runtime.startup_channel_id,
            time_service=self.runtime.time_service,  # Add missing parameter
            runtime=self.runtime,  # Pass runtime reference for preload tasks
            agent_occurrence_id=self.runtime.essential_config.agent_occurrence_id,  # Pass occurrence_id from config
            cognitive_behaviors=cognitive_behaviors,  # Template-driven state transition config
        )

        return self.agent_processor

    def _build_action_dispatcher(self, dependencies: Any) -> Any:
        """Build action dispatcher. Override in subclasses for custom sinks."""
        _config = self.runtime._ensure_config()
        return build_action_dispatcher(
            bus_manager=dependencies.bus_manager,
            time_service=dependencies.time_service,
            shutdown_callback=dependencies.shutdown_callback,
            max_rounds=10,  # Default max rounds, can be configured via limits
            telemetry_service=self.runtime.telemetry_service,
            secrets_service=dependencies.secrets_service,
            audit_service=self.runtime.audit_service,
        )

    async def _get_cognitive_behaviors_from_graph(self) -> Optional[Any]:
        """Get cognitive state behaviors from graph database.

        The migration in ciris_runtime populates this on:
        1. First-run: Seeds from template
        2. Pre-1.7 upgrade: Creates legacy-compatible config (PLAY/DREAM/SOLITUDE disabled)

        Returns:
            CognitiveStateBehaviors if found in graph, None otherwise
        """
        from ciris_engine.schemas.config.cognitive_state_behaviors import CognitiveStateBehaviors

        logger.info("[COGNITIVE_LOAD] Loading cognitive behaviors from graph...")

        if not self.runtime.service_initializer or not self.runtime.service_initializer.config_service:
            logger.warning("[COGNITIVE_LOAD] Cannot get cognitive behaviors - GraphConfigService not available")
            return None

        config_service = self.runtime.service_initializer.config_service

        try:
            config_entry = await config_service.get_config("cognitive_state_behaviors")
            if config_entry and config_entry.value and config_entry.value.dict_value:
                dict_value = config_entry.value.dict_value
                wakeup_config = dict_value.get("wakeup", {})
                logger.info(
                    f"[COGNITIVE_LOAD] Found in graph: wakeup.enabled={wakeup_config.get('enabled', 'MISSING')}"
                )
                behaviors = CognitiveStateBehaviors(**dict_value)
                logger.info(f"[COGNITIVE_LOAD] Parsed: wakeup.enabled={behaviors.wakeup.enabled}")
                return behaviors
            else:
                logger.info("[COGNITIVE_LOAD] Config entry exists but has no dict_value")
        except Exception as e:
            logger.warning(f"[COGNITIVE_LOAD] Failed to get cognitive behaviors from graph: {e}")

        # Fallback: return default (full Covenant compliance)
        logger.info(
            "[COGNITIVE_LOAD] No cognitive behaviors in graph - using Covenant-compliant defaults (wakeup.enabled=True)"
        )
        return CognitiveStateBehaviors()
