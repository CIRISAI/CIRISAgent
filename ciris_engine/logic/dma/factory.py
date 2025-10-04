import logging
from typing import Any, Dict, Optional, Type

from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.protocols.dma.base import ActionSelectionDMAProtocol as ActionSelectionDMAInterface
from ciris_engine.protocols.dma.base import CSDMAProtocol as CSDMAInterface
from ciris_engine.protocols.dma.base import PDMAProtocol as EthicalDMAInterface
from ciris_engine.protocols.faculties import EpistemicFaculty
from ciris_engine.schemas.config.agent import AgentTemplate

from .dsdma_base import BaseDSDMA

logger = logging.getLogger(__name__)

# No longer need a registry - all agents use BaseDSDMA
DSDMA_CLASS_REGISTRY: Dict[str, Type[BaseDSDMA]] = {
    "BaseDSDMA": BaseDSDMA,
}

ETHICAL_DMA_REGISTRY: Dict[str, Type[EthicalDMAInterface]] = {}
CSDMA_REGISTRY: Dict[str, Type[CSDMAInterface]] = {}
ACTION_SELECTION_DMA_REGISTRY: Dict[str, Type[ActionSelectionDMAInterface]] = {}

try:
    from .pdma import EthicalPDMAEvaluator

    ETHICAL_DMA_REGISTRY["EthicalPDMAEvaluator"] = EthicalPDMAEvaluator
except ImportError:
    pass

try:
    from .csdma import CSDMAEvaluator

    CSDMA_REGISTRY["CSDMAEvaluator"] = CSDMAEvaluator
except ImportError:
    pass

try:
    from .action_selection_pdma import ActionSelectionPDMAEvaluator

    ACTION_SELECTION_DMA_REGISTRY["ActionSelectionPDMAEvaluator"] = ActionSelectionPDMAEvaluator
except ImportError:
    pass


def create_dma(
    dma_type: str,
    dma_identifier: str,
    service_registry: ServiceRegistry,
    *,
    model_name: Optional[str] = None,
    prompt_overrides: Optional[Dict[str, str]] = None,
    faculties: Optional[Dict[str, EpistemicFaculty]] = None,
    **kwargs: Any,
) -> Any:
    """Create a DMA instance of the specified type.

    Args:
        dma_type: Type of DMA ('ethical', 'csdma', 'dsdma', 'action_selection')
        dma_identifier: Specific DMA class identifier
        service_registry: Service registry for dependencies
        model_name: Optional LLM model name
        prompt_overrides: Optional prompt customizations
        faculties: Optional epistemic faculties
        **kwargs: Additional DMA-specific parameters

    Returns:
        DMA instance or None if creation fails
    """
    registries = {
        "ethical": ETHICAL_DMA_REGISTRY,
        "csdma": CSDMA_REGISTRY,
        "dsdma": DSDMA_CLASS_REGISTRY,
        "action_selection": ACTION_SELECTION_DMA_REGISTRY,
    }

    registry = registries.get(dma_type)
    if not registry:
        logger.error(f"Unknown DMA type: {dma_type}")
        return None

    dma_class = registry.get(dma_identifier)  # type: ignore[attr-defined]
    if not dma_class:
        logger.error(f"Unknown {dma_type} DMA identifier: {dma_identifier}")
        return None

    try:
        constructor_args = {"service_registry": service_registry, **kwargs}

        if model_name is not None:
            constructor_args["model_name"] = model_name
        if prompt_overrides is not None:
            constructor_args["prompt_overrides"] = prompt_overrides
        if faculties is not None:
            constructor_args["faculties"] = faculties

        return dma_class(**constructor_args)
    except Exception as e:
        logger.error(f"Failed to create {dma_type} DMA {dma_identifier}: {e}")
        return None


def create_dsdma_from_identity(
    identity: Optional[AgentTemplate],
    service_registry: ServiceRegistry,
    *,
    model_name: Optional[str] = None,
    sink: Optional[Any] = None,
) -> BaseDSDMA:
    """Instantiate a DSDMA based on the agent's identity.

    The identity represents the agent's configuration loaded from the graph. If ``identity``
    is ``None``, this is a fatal error as the agent has no identity.

    All agents now use BaseDSDMA with domain-specific overrides provided through
    dsdma_kwargs in their identity configuration.
    """
    if identity is None:
        logger.critical("FATAL: No identity provided - agent has no identity!")
        raise RuntimeError("Cannot create DSDMA without agent identity. Who am I?")

    # Extract overrides from identity configuration
    if identity.dsdma_kwargs:
        # Handle DSDMAConfiguration object
        prompt_template = identity.dsdma_kwargs.prompt_template
        domain_knowledge = identity.dsdma_kwargs.domain_specific_knowledge
    else:
        prompt_template = None
        domain_knowledge = None

    # Always use BaseDSDMA now
    dma_result = create_dma(
        dma_type="dsdma",
        dma_identifier="BaseDSDMA",  # Always use BaseDSDMA
        service_registry=service_registry,
        model_name=model_name,
        prompt_overrides=None,
        domain_name=identity.name,
        domain_specific_knowledge=domain_knowledge,
        prompt_template=prompt_template,
        sink=sink,
    )

    # Ensure we return the correct type - FAIL FAST if not BaseDSDMA
    if isinstance(dma_result, BaseDSDMA):
        return dma_result

    # FAIL FAST: All 3 DMAs are required
    logger.critical(f"create_dma returned unexpected type: {type(dma_result)} - DSDMA is required!")
    raise RuntimeError(f"Failed to create DSDMA - got {type(dma_result)} instead of BaseDSDMA")
