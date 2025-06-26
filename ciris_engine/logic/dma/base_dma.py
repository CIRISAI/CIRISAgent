from __future__ import annotations

import yaml
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Any, Dict, TypeVar, Generic, TYPE_CHECKING, Tuple

from pydantic import BaseModel

from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.protocols.services import LLMService
from ciris_engine.schemas.runtime.enums import ServiceType

if TYPE_CHECKING:
    pass

InputT = TypeVar('InputT')
DMAResultT = TypeVar('DMAResultT', bound=BaseModel)

class BaseDMA(ABC, Generic[InputT, DMAResultT]):
    """Concrete base class for Decision Making Algorithms.
    
    This class provides the implementation of the BaseDMAInterface
    with backward compatibility for existing DMAs.
    """

    def __init__(
        self,
        service_registry: ServiceRegistry,
        model_name: Optional[str] = None,
        max_retries: int = 3,
        prompt_overrides: Optional[Dict[str, str]] = None,
        faculties: Optional[Dict[str, EpistemicFaculty]] = None,
        sink: Optional[Any] = None,
        **kwargs: Any
    ) -> None:
        self.service_registry = service_registry
        self.model_name = model_name
        self.max_retries = max_retries
        self.faculties = faculties or {}
        self.sink = sink
        
        self.kwargs = kwargs
        
        self.prompts: Dict[str, str] = {}
        self._load_prompts(prompt_overrides)
        
    def _load_prompts(self, overrides: Optional[Dict[str, str]] = None) -> None:
        """Load prompts from YAML file or use defaults.
        
        First checks for PROMPT_FILE class attribute, then falls back to 
        prompts/<class_name>.yml file in the same directory as the DMA.
        Finally falls back to DEFAULT_PROMPT or DEFAULT_PROMPT_TEMPLATE if defined.
        """
        prompt_file = None
        if hasattr(self.__class__, 'PROMPT_FILE'):
            prompt_file = getattr(self.__class__, 'PROMPT_FILE')
        else:
            dma_file = Path(self.__class__.__module__.replace('.', '/'))
            prompt_file = dma_file.parent / "prompts" / f"{self.__class__.__name__.lower()}.yml"
        
        if prompt_file and Path(prompt_file).exists():
            try:
                with open(prompt_file, 'r') as f:
                    file_prompts = yaml.safe_load(f) or {}
                self.prompts = {**file_prompts, **(overrides or {})}
                return
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to load prompts from {prompt_file}: {e}")
        
        defaults = {}
        if hasattr(self, 'DEFAULT_PROMPT'):
            defaults = getattr(self, 'DEFAULT_PROMPT')
        elif hasattr(self, 'DEFAULT_PROMPT_TEMPLATE'):
            defaults = getattr(self, 'DEFAULT_PROMPT_TEMPLATE')
            
        self.prompts = {**defaults, **(overrides or {})}

    async def get_llm_service(self) -> Optional[LLMService]:
        """Return the LLM service for this DMA from the service registry."""
        service = await self.service_registry.get_service(
            handler=self.__class__.__name__,
            service_type=ServiceType.LLM,
        )
        return service
    
    async def call_llm_structured(self, messages: list, response_model: type, 
                                 max_tokens: int = 1024, temperature: float = 0.0) -> Tuple[Any, ...]:
        """Call LLM via sink for centralized failover, round-robin, and circuit breaker protection.
        
        Returns:
            Tuple[BaseModel, ResourceUsage]
        """
        if not self.sink:
            # Critical system failure - DMAs cannot function without the multi-service sink
            import logging
            logger = logging.getLogger(__name__)
            logger.critical(f"FATAL: No multi-service sink available for {self.__class__.__name__}. System cannot continue.")
            raise RuntimeError(f"FATAL: No multi-service sink available for {self.__class__.__name__}. DMAs require the sink for all LLM calls. System must shutdown.")
            
        # Use LLM bus for centralized failover, round-robin, and circuit breaker protection
        result = await self.sink.llm.call_llm_structured(
            messages=messages,
            response_model=response_model,
            handler_name=self.__class__.__name__,
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        # The sink returns Optional[tuple] which we need to ensure is a valid tuple
        if result is None:
            raise RuntimeError(f"Multi-service sink returned None for structured LLM call in {self.__class__.__name__}")
        
        # Ensure result is a tuple (it should be from the type annotation)
        if not isinstance(result, tuple):
            raise RuntimeError(f"Multi-service sink returned non-tuple: {type(result)}")
            
        return result

    async def apply_faculties(self, content: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, BaseModel]:
        """Apply available epistemic faculties to content.
        
        Args:
            content: The content to analyze
            context: Optional context for analysis
            
        Returns:
            Dictionary mapping faculty name to evaluation result
        """
        results: Dict[str, Any] = {}
        
        if not self.faculties:
            return results
            
        for name, faculty in self.faculties.items():
            try:
                result = await faculty.evaluate(content, context)
                results[name] = result
            except Exception as e:
                # Log error but don't fail the entire evaluation
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Faculty {name} failed to evaluate: {e}")
                continue
                
        return results
    
    def get_confidence(self) -> float:
        """Get confidence in the last decision."""
        # Default implementation - subclasses can override
        return 0.8
    
    def get_algorithm_type(self) -> str:
        """Get the type of decision making algorithm."""
        # Return class name by default
        return self.__class__.__name__

    @abstractmethod
    async def evaluate(self, *args: Any, **kwargs: Any) -> BaseModel:
        """Execute DMA evaluation and return a pydantic model.
        
        Note: This maintains the old signature for backward compatibility.
        New DMAs should use the typed interface methods.
        """
        raise NotImplementedError