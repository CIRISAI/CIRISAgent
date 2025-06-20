import importlib
import logging
from ciris_engine.protocols.adapter_interface import PlatformAdapter

from .cirisnode_client import CIRISNodeClient
from .tool_registry import ToolRegistry


OpenAICompatibleClient = None
_has_openai_llm = False

__all__ = [
    "load_adapter", 
    "PlatformAdapter",
    "CIRISNodeClient",
    "ToolRegistry"
]


logger = logging.getLogger(__name__)

def load_adapter(mode: str) -> type[PlatformAdapter]:
    """Dynamically imports and returns the adapter class for the given mode."""
    logger.debug(f"Attempting to load adapter for mode: {mode}")
    try:
        adapter_module = importlib.import_module(f".{mode}", package=__name__)

        adapter_class = getattr(adapter_module, "Adapter")

        required_methods = ['get_services_to_register', 'start', 'run_lifecycle', 'stop', '__init__']
        for method_name in required_methods:
            if not hasattr(adapter_class, method_name):
                logger.error(f"Adapter class for mode '{mode}' is missing required method '{method_name}'.")
                raise AttributeError(f"Adapter class for mode '{mode}' does not fully implement PlatformAdapter (missing {method_name}).")

        logger.info(f"Successfully loaded adapter for mode: {mode}")
        # Type assertion: after validation, we know this is a PlatformAdapter class
        return adapter_class  # type: ignore[no-any-return]
    except ImportError as e:
        logger.error(f"Could not import adapter module for mode '{mode}'. Import error: {e}", exc_info=True)
        raise ValueError(f"Could not import adapter module for mode '{mode}'. Ensure 'ciris_engine.adapters.{mode}' exists and is correctly structured.") from e
    except AttributeError as e:
        logger.error(f"Could not load 'Adapter' class or method from mode '{mode}'. Attribute error: {e}", exc_info=True)
        raise ValueError(f"Could not load 'Adapter' class from mode '{mode}' or it's missing PlatformAdapter methods. Ensure it's defined and implements PlatformAdapter.") from e
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading adapter for mode '{mode}': {e}", exc_info=True)
        raise ValueError(f"An unexpected error occurred while loading adapter for mode '{mode}'.") from e
